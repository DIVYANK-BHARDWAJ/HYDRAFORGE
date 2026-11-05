"""Validation rules for participant submission structure and manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from hydraforge.schema import SubmissionManifest, ValidationError
from hydraforge.submission.manifest_loader import load_submission_manifest
from hydraforge.submission.repository import RepositorySecurityError


def validate_submission_package(repo_dir: Path) -> SubmissionManifest:
    """Validate repository files, entrypoint, dependencies, and manifest declarations."""
    repo_dir = Path(repo_dir).resolve()

    # 1. Load and validate manifest
    manifest = load_submission_manifest(repo_dir)

    # 2. Check declared entrypoint exists and is inside repository
    entrypoint_name = manifest.entrypoint
    entrypoint_path = (repo_dir / entrypoint_name).resolve()

    try:
        entrypoint_path.relative_to(repo_dir)
    except ValueError:
        raise RepositorySecurityError(
            f"Path traversal detected in entrypoint '{entrypoint_name}'. Must be relative to repository root."
        )

    if not entrypoint_path.exists():
        raise ValidationError(
            f"Declared entrypoint '{entrypoint_name}' not found in repository root '{repo_dir}'."
        )

    if not entrypoint_path.is_file():
        raise ValidationError(
            f"Declared entrypoint '{entrypoint_name}' is not a regular file."
        )

    if entrypoint_path.is_symlink():
        # Check target is also inside repo
        resolved = entrypoint_path.resolve()
        try:
            resolved.relative_to(repo_dir)
        except ValueError:
            raise RepositorySecurityError(
                f"Entrypoint symlink '{entrypoint_name}' points outside repository root."
            )

    # 3. Check for dependency specification
    has_requirements = (repo_dir / "requirements.txt").is_file()
    has_pyproject = (repo_dir / "pyproject.toml").is_file()
    has_environment = (repo_dir / "environment.yml").is_file()

    if not (has_requirements or has_pyproject or has_environment):
        raise ValidationError(
            "Missing dependency manifest. Repository must include at least one of: "
            "'requirements.txt', 'pyproject.toml', or 'environment.yml'."
        )

    return manifest

