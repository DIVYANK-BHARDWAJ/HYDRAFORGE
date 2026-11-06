"""
hydraforge/submission/github_verifier.py
Server-Side GitHub Repository Verification & Immutable Commit SHA Capture.
Inspects public GitHub repositories without requiring participant tokens,
retrieving default branch and HEAD commit SHA, or preserving submission as pending/failed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

from hydraforge.submission.repository import (
    COMMIT_SHA_PATTERN,
    RepositorySecurityError,
    validate_repository_url,
)

# Optional mock resolver hook for unit test simulation
_MOCK_GITHUB_RESOLVER: Optional[Callable[[str], Tuple[bool, Optional[str], Optional[str], str]]] = None


def set_mock_github_resolver(resolver: Optional[Callable[[str], Tuple[bool, Optional[str], Optional[str], str]]]) -> None:
    """Set a testing resolver for deterministic unit testing without outbound network."""
    global _MOCK_GITHUB_RESOLVER
    _MOCK_GITHUB_RESOLVER = resolver


def parse_github_owner_repo(repo_url: str) -> Tuple[str, str]:
    """Extract owner and repository name from GitHub URL."""
    parsed = urlparse(repo_url)
    path = parsed.path.strip("/").rstrip(".git")
    parts = path.split("/")
    if len(parts) < 2:
        raise RepositorySecurityError(f"Cannot parse GitHub owner and repository name from '{repo_url}'.")
    return parts[0], parts[1]


def resolve_github_head_commit(
    repo_url: str,
    timeout: float = 4.0
) -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Server-side GitHub inspection:
    1. Validates repository URL against security rules.
    2. Queries public GitHub API or Git remote wire protocol.
    3. Retrieves default branch and current HEAD commit SHA.
    
    Returns:
        (success, default_branch, head_commit_sha, details_message)
    """
    clean_url = validate_repository_url(repo_url)

    # Check if a test mock hook is registered
    if _MOCK_GITHUB_RESOLVER is not None:
        return _MOCK_GITHUB_RESOLVER(clean_url)

    # 1. Try GitHub REST API (anonymous or using optional server-side GITHUB_TOKEN for elevated rate limits)
    try:
        owner, repo_name = parse_github_owner_repo(clean_url)
        headers = {
            "User-Agent": "HYDRAFORGE-Evaluator/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        api_repo_url = f"https://api.github.com/repos/{owner}/{repo_name}"
        req = urllib.request.Request(api_repo_url, headers=headers)

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            default_branch = data.get("default_branch", "main")

        # Now fetch HEAD commit for default branch
        api_commit_url = f"https://api.github.com/repos/{owner}/{repo_name}/commits/{default_branch}"
        req_commit = urllib.request.Request(api_commit_url, headers=headers)
        with urllib.request.urlopen(req_commit, timeout=timeout) as resp_commit:
            commit_data = json.loads(resp_commit.read().decode("utf-8"))
            sha = commit_data.get("sha", "")
            if COMMIT_SHA_PATTERN.match(sha):
                return True, default_branch, sha, f"Captured commit SHA via GitHub API (branch: {default_branch})."

    except Exception as e:
        # Fall through to git ls-remote or offline handling
        pass

    # 2. Try git ls-remote (non-executing ref lookup over git protocol)
    try:
        proc = subprocess.run(
            ["git", "ls-remote", clean_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        if proc.returncode == 0 and proc.stdout:
            match = re.search(r"^([0-9a-f]{40})\s+HEAD", proc.stdout, re.MULTILINE)
            if match:
                sha = match.group(1)
                return True, "main", sha, "Captured HEAD commit SHA via Git remote protocol."
    except Exception:
        pass

    # If unreachable (offline sandbox, rate limit, network down):
    # Rule: Preserve submission, mark verification as pending or failed, NEVER fabricate a SHA.
    return (
        False,
        None,
        None,
        "Repository could not be reached over public network (offline sandbox or network timeout). Submission preserved with pending verification."
    )

