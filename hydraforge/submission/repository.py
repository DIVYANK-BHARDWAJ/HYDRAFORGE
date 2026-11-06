"""GitHub Repository Intake, URL Sanitization, and Commit Verification."""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urlparse


APPROVED_GIT_DOMAINS: Set[str] = {
    "github.com",
    "www.github.com",
    "gitlab.com",
    "www.gitlab.com",
    "bitbucket.org",
    "www.bitbucket.org",
}

COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

DEFAULT_MAX_REPO_SIZE_MB = float(os.environ.get("HYDRAFORGE_MAX_REPO_SIZE_MB", "250.0"))
DEFAULT_MAX_FILE_COUNT = 2000
DEFAULT_MAX_PATH_DEPTH = 8


class RepositorySecurityError(Exception):
    """Raised when repository intake or cloning violates security constraints."""
    pass


@dataclass(frozen=True)
class RepositoryProvenance:
    """Immutable audit record of a verified checked-out repository."""
    repository_url: str
    commit_sha: str
    checkout_timestamp: str
    file_count: int
    total_size_bytes: int
    tree_hash: str
    cloned_path: str


def validate_repository_url(url: str) -> str:
    """Validate repository URL against approved Git domains and prevent SSRF.

    Rejects:
    - Non-HTTPS schemes (file://, git://, http://, ssh://)
    - Localhost, 127.0.0.1, ::1
    - Private IPv4 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16)
    - Unapproved hosting domains
    """
    if not url or not isinstance(url, str):
        raise RepositorySecurityError("Repository URL must be a non-empty string.")

    cleaned_url = url.strip()
    try:
        parsed = urlparse(cleaned_url)
    except Exception as e:
        raise RepositorySecurityError(f"Malformed URL: {e}")

    # 1. Scheme check: HTTPS only
    if parsed.scheme.lower() != "https":
        raise RepositorySecurityError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only 'https' is permitted."
        )

    # 2. Hostname check
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise RepositorySecurityError("Repository URL lacks a valid hostname.")

    # Check localhost and loopback names
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise RepositorySecurityError("SSRF Prevention: Localhost addresses are strictly forbidden.")

    # Check if host is an IP address
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            raise RepositorySecurityError(
                f"SSRF Prevention: IP address '{hostname}' is private/reserved and strictly forbidden."
            )
        # Even public bare IPs are rejected: Git hosting must be a recognized domain
        raise RepositorySecurityError("Bare IP addresses are not permitted as Git repository hosts.")
    except ValueError:
        # Host is a domain name, proceed to domain whitelist
        pass

    # Approved domain verification
    if hostname not in APPROVED_GIT_DOMAINS:
        raise RepositorySecurityError(
            f"Unapproved Git hosting domain '{hostname}'. Approved domains: {sorted(APPROVED_GIT_DOMAINS)}"
        )

    return cleaned_url


def validate_commit_sha(commit_sha: str) -> str:
    """Validate that commit reference is an immutable 40-character hexadecimal SHA.

    Rejects mutable references like branch names ('main', 'master', 'dev') or short SHAs.
    """
    if not commit_sha or not isinstance(commit_sha, str):
        raise RepositorySecurityError("Commit SHA must be a non-empty string.")

    cleaned_sha = commit_sha.strip().lower()
    if not COMMIT_SHA_PATTERN.match(cleaned_sha):
        raise RepositorySecurityError(
            f"Invalid commit SHA '{commit_sha}'. Evaluation requires an immutable 40-character "
            "lowercase hexadecimal SHA. Mutable branch names (e.g. 'main') are forbidden."
        )
    return cleaned_sha


class RepositoryIntake:
    """Clones, verifies, and audits participant GitHub repositories."""

    def __init__(
        self,
        max_size_mb: float = DEFAULT_MAX_REPO_SIZE_MB,
        max_files: int = DEFAULT_MAX_FILE_COUNT,
        max_depth: int = DEFAULT_MAX_PATH_DEPTH
    ) -> None:
        self.max_size_mb = max_size_mb
        self.max_files = max_files
        self.max_depth = max_depth

    def inspect_tree_safety(self, target_dir: Path) -> Tuple[int, int]:
        """Check for path traversal, symlinks pointing outside tree, and size limits.

        Returns (file_count, total_size_bytes).
        """
        target_dir = target_dir.resolve()
        file_count = 0
        total_size = 0

        for path in target_dir.rglob("*"):
            # Path depth check relative to repo root
            try:
                rel_parts = path.relative_to(target_dir).parts
            except ValueError:
                raise RepositorySecurityError(f"Path traversal detected: {path}")

            # Exclude .git internal objects from participant source quota calculations
            if rel_parts and rel_parts[0] == ".git":
                continue

            if len(rel_parts) > self.max_depth:
                raise RepositorySecurityError(
                    f"Repository directory depth ({len(rel_parts)}) exceeds maximum limit of {self.max_depth}."
                )

            # Symlink safety check: symlinks pointing outside target_dir are forbidden
            if path.is_symlink():
                resolved = path.resolve()
                try:
                    resolved.relative_to(target_dir)
                except ValueError:
                    raise RepositorySecurityError(
                        f"Insecure symlink detected: '{path}' points outside repository root to '{resolved}'."
                    )

            if path.is_file():
                file_count += 1
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                total_size += size

                if file_count > self.max_files:
                    raise RepositorySecurityError(
                        f"Repository file count ({file_count}) exceeds limit of {self.max_files}."
                    )

        total_mb = total_size / (1024 * 1024)
        if total_mb > self.max_size_mb:
            raise RepositorySecurityError(
                f"Repository total size ({total_mb:.1f} MB) exceeds maximum limit of {self.max_size_mb} MB."
            )

        return file_count, total_size

    def checkout(
        self,
        repo_url: str,
        commit_sha: str,
        destination_dir: Path
    ) -> RepositoryProvenance:
        """Clone and checkout exact commit SHA with cryptographic verification."""
        clean_url = validate_repository_url(repo_url)
        clean_sha = validate_commit_sha(commit_sha)

        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)

        checkout_time = datetime.now(timezone.utc).isoformat()

        # Execute git clone without executing repository scripts
        # Use --depth 1 if possible or clone then checkout specific SHA
        try:
            # 1. Init empty repo
            subprocess.run(
                ["git", "init"],
                cwd=str(destination_dir),
                check=True,
                capture_output=True,
                text=True
            )
            # 2. Add remote
            subprocess.run(
                ["git", "remote", "add", "origin", clean_url],
                cwd=str(destination_dir),
                check=True,
                capture_output=True,
                text=True
            )
            # 3. Fetch exact commit SHA
            subprocess.run(
                ["git", "fetch", "--depth", "1", "origin", clean_sha],
                cwd=str(destination_dir),
                check=True,
                capture_output=True,
                text=True
            )
            # 4. Checkout fetched SHA
            subprocess.run(
                ["git", "checkout", "FETCH_HEAD"],
                cwd=str(destination_dir),
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() if e.stderr else str(e)
            raise RepositorySecurityError(f"Git checkout failed for commit {clean_sha}: {err_msg}")

        # 5. Verify checked-out HEAD
        head_proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(destination_dir),
            check=True,
            capture_output=True,
            text=True
        )
        actual_head = head_proc.stdout.strip().lower()
        if actual_head != clean_sha:
            raise RepositorySecurityError(
                f"Integrity Mismatch: Checked out HEAD ({actual_head}) does not match requested SHA ({clean_sha})."
            )

        # 6. Remove .git directory so Git hooks / submodules cannot be abused
        git_dir = destination_dir / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)

        # 7. Audit filesystem tree safety
        file_count, total_size = self.inspect_tree_safety(destination_dir)

        # 8. Compute tree hash
        from hydraforge.submission.integrity import compute_tree_hash
        tree_hash = compute_tree_hash(destination_dir)

        return RepositoryProvenance(
            repository_url=clean_url,
            commit_sha=clean_sha,
            checkout_timestamp=checkout_time,
            file_count=file_count,
            total_size_bytes=total_size,
            tree_hash=tree_hash,
            cloned_path=str(destination_dir)
        )

