"""
hydraforge/discovery/file_classifier.py
Safe, unprivileged file system scanner and file classifier.
Enforces size, depth, count, and duration limits, detects malicious symlinks,
prunes irrelevant cache/virtualenv directories, and categorizes repository files.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from hydraforge.discovery.discovery_models import (
    ConfidenceLevel,
    FileClassificationRecord,
    FileType,
    RepositoryStructureSummary,
)

DEFAULT_MAX_REPO_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
DEFAULT_MAX_FILE_COUNT = 2000
DEFAULT_MAX_INDIVIDUAL_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_DIRECTORY_DEPTH = 8
DEFAULT_MAX_INSPECTION_DURATION_SECONDS = 30.0

PRUNED_DIRECTORIES: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "build",
    "dist",
    ".tox",
    ".idea",
    ".vscode",
}

MANIFEST_FILENAMES: Set[str] = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "pipfile.lock",
    "environment.yml",
    "environment.yaml",
    "conda.yml",
    "conda.yaml",
    "package.json",
    "poetry.lock",
}

DOC_FILENAMES: Set[str] = {
    "readme.md",
    "readme.rst",
    "readme.txt",
    "readme",
    "contributing.md",
    "license",
    "license.txt",
    "license.md",
}


class RepositoryLimitsExceededError(Exception):
    """Raised when repository exceeds safe size, file count, or depth thresholds."""
    pass


class InsecureSymlinkError(Exception):
    """Raised when a symlink resolves outside the repository root."""
    pass


class FileClassifier:
    """Recursively scans and classifies files in an unprivileged, safe manner."""

    def __init__(
        self,
        max_repo_size_bytes: int = DEFAULT_MAX_REPO_SIZE_BYTES,
        max_file_count: int = DEFAULT_MAX_FILE_COUNT,
        max_file_size_bytes: int = DEFAULT_MAX_INDIVIDUAL_FILE_SIZE_BYTES,
        max_depth: int = DEFAULT_MAX_DIRECTORY_DEPTH,
        max_duration_seconds: float = DEFAULT_MAX_INSPECTION_DURATION_SECONDS,
    ) -> None:
        self.max_repo_size_bytes = max_repo_size_bytes
        self.max_file_count = max_file_count
        self.max_file_size_bytes = max_file_size_bytes
        self.max_depth = max_depth
        self.max_duration_seconds = max_duration_seconds

    def scan_and_classify(
        self,
        repo_root: Path
    ) -> Tuple[List[FileClassificationRecord], RepositoryStructureSummary, List[str]]:
        """
        Scan repository tree safely without executing any files.
        Returns:
            (classified_files, structure_summary, security_warnings)
        """
        repo_root = Path(repo_root).resolve()
        if not repo_root.is_dir():
            raise ValueError(f"Repository root '{repo_root}' is not a valid directory.")

        start_time = time.monotonic()
        classified_files: List[FileClassificationRecord] = []
        warnings: List[str] = []
        languages: Set[str] = set()

        total_files = 0
        total_size = 0
        source_count = 0
        manifest_count = 0
        doc_count = 0
        max_depth_seen = 0
        tree_preview: List[str] = []

        for root, dirs, files in os.walk(repo_root, followlinks=False):
            # Check elapsed duration
            if (time.monotonic() - start_time) > self.max_duration_seconds:
                warnings.append(
                    f"Repository scan stopped: inspection duration exceeded limit of {self.max_duration_seconds}s."
                )
                break

            current_path = Path(root).resolve()
            try:
                rel_parts = current_path.relative_to(repo_root).parts
            except ValueError:
                warnings.append(f"Skipped path outside repository root: {current_path}")
                continue

            current_depth = len(rel_parts)
            if current_depth > max_depth_seen:
                max_depth_seen = current_depth

            if current_depth > self.max_depth:
                raise RepositoryLimitsExceededError(
                    f"Directory depth ({current_depth}) exceeds maximum limit of {self.max_depth}."
                )

            # Prune ignored directory trees in-place
            dirs[:] = [
                d for d in dirs
                if d.lower() not in PRUNED_DIRECTORIES and not d.endswith(".egg-info")
            ]

            for fname in files:
                fpath = current_path / fname
                rel_fpath = fpath.relative_to(repo_root).as_posix()

                # Check symlink safety
                if fpath.is_symlink():
                    try:
                        resolved_symlink = fpath.resolve()
                        resolved_symlink.relative_to(repo_root)
                    except ValueError:
                        msg = f"Insecure symlink detected: '{rel_fpath}' resolves outside repository root to '{resolved_symlink}'."
                        warnings.append(msg)
                        continue

                try:
                    stat_info = fpath.stat()
                    fsize = stat_info.st_size
                except OSError as e:
                    warnings.append(f"Could not stat file '{rel_fpath}': {e}")
                    continue

                total_files += 1
                total_size += fsize

                if total_files > self.max_file_count:
                    raise RepositoryLimitsExceededError(
                        f"Repository file count ({total_files}) exceeds limit of {self.max_file_count}."
                    )

                if total_size > self.max_repo_size_bytes:
                    raise RepositoryLimitsExceededError(
                        f"Repository total size ({total_size / (1024*1024):.1f} MB) "
                        f"exceeds limit of {self.max_repo_size_bytes / (1024*1024):.1f} MB."
                    )

                if fsize > self.max_file_size_bytes:
                    warnings.append(
                        f"Oversized file ignored for inspection: '{rel_fpath}' ({fsize / (1024*1024):.1f} MB > limit {self.max_file_size_bytes / (1024*1024):.1f} MB)."
                    )
                    continue

                # Add to tree preview (up to first 50 entries)
                if len(tree_preview) < 50:
                    tree_preview.append(rel_fpath)

                record = self._classify_single_file(rel_fpath, fsize)
                classified_files.append(record)

                if record.language:
                    languages.add(record.language)
                if record.file_type == FileType.PYTHON_SOURCE:
                    source_count += 1
                elif record.file_type == FileType.CONFIG_MANIFEST:
                    manifest_count += 1
                elif record.file_type == FileType.DOCUMENTATION:
                    doc_count += 1

        summary = RepositoryStructureSummary(
            total_files=total_files,
            total_size_bytes=total_size,
            source_file_count=source_count,
            manifest_count=manifest_count,
            doc_file_count=doc_count,
            max_depth_reached=max_depth_seen,
            languages_detected=sorted(list(languages)),
            tree_preview=tree_preview,
        )

        return classified_files, summary, warnings

    def _classify_single_file(self, rel_path: str, size_bytes: int) -> FileClassificationRecord:
        """Classify a single file based on filename, location, and extension."""
        name_lower = os.path.basename(rel_path).lower()
        ext = os.path.splitext(rel_path)[1].lower()

        # 1. Manifests & Dependency Configurations
        if name_lower in MANIFEST_FILENAMES or name_lower.startswith("requirements"):
            return FileClassificationRecord(
                path=rel_path,
                file_type=FileType.CONFIG_MANIFEST,
                purpose="Package manifest or dependency specification",
                language="toml" if ext == ".toml" else ("yaml" if ext in (".yml", ".yaml") else "plaintext"),
                size_bytes=size_bytes,
                confidence=ConfidenceLevel.HIGH,
                details=f"Identified manifest '{name_lower}'."
            )

        # 2. Dockerfiles
        if name_lower == "dockerfile" or name_lower.startswith("dockerfile.") or name_lower == "containerfile":
            return FileClassificationRecord(
                path=rel_path,
                file_type=FileType.DOCKERFILE,
                purpose="Container image specification",
                language="dockerfile",
                size_bytes=size_bytes,
                confidence=ConfidenceLevel.HIGH,
                details="Container build definition."
            )

        # 3. Build Scripts
        if name_lower in ("makefile", "gnumakefile") or ext in (".sh", ".bash", ".bat", ".cmd", ".ps1"):
            return FileClassificationRecord(
                path=rel_path,
                file_type=FileType.BUILD_SCRIPT,
                purpose="Build automation or task runner script",
                language="shell" if ext in (".sh", ".bash") else "make",
                size_bytes=size_bytes,
                confidence=ConfidenceLevel.MEDIUM,
                details="Shell or Make build script."
            )

        # 4. Documentation
        if name_lower in DOC_FILENAMES or rel_path.lower().startswith("docs/") and ext in (".md", ".rst", ".txt"):
            return FileClassificationRecord(
                path=rel_path,
                file_type=FileType.DOCUMENTATION,
                purpose="Project documentation and user guides",
                language="markdown" if ext == ".md" else "restructuredtext",
                size_bytes=size_bytes,
                confidence=ConfidenceLevel.HIGH,
                details="Primary project documentation."
            )

        # 5. Python Source
        if ext in (".py", ".pyw"):
            # Check heuristic purpose based on relative path and filename
            purpose = "Python source code"
            if "test" in name_lower or "tests" in rel_path.split("/"):
                purpose = "Automated test suite module"
            elif any(k in name_lower for k in ("predict", "infer", "forecast")):
                purpose = "Candidate inference / forecasting module"
            elif any(k in name_lower for k in ("train", "fit", "trainer")):
                purpose = "Candidate model training module"
            elif "model" in name_lower or "net" in name_lower:
                purpose = "Neural network or model architecture definition"

            return FileClassificationRecord(
                path=rel_path,
                file_type=FileType.PYTHON_SOURCE,
                purpose=purpose,
                language="python",
                size_bytes=size_bytes,
                confidence=ConfidenceLevel.HIGH,
                details=f"Python module: {purpose}."
            )

        # 6. Data Files / Weights Checkpoints
        if ext in (".csv", ".parquet", ".json", ".npz", ".pt", ".pth", ".onnx", ".bin", ".h5", ".nc"):
            return FileClassificationRecord(
                path=rel_path,
                file_type=FileType.DATA_FILE,
                purpose="Dataset, parameters, or model weights artifact",
                language=None,
                size_bytes=size_bytes,
                confidence=ConfidenceLevel.MEDIUM,
                details="Model checkpoint, weights, or tabular data file."
            )

        # 7. Other Generic File
        return FileClassificationRecord(
            path=rel_path,
            file_type=FileType.OTHER,
            purpose="Generic repository asset",
            language=None,
            size_bytes=size_bytes,
            confidence=ConfidenceLevel.LOW,
            details=f"File extension '{ext}'."
        )

