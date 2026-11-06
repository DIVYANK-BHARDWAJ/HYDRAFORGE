"""Validation rules for participant submission structure and manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from hydraforge.schema import SubmissionManifest, ValidationError
from hydraforge.submission.manifest_loader import load_submission_manifest
from hydraforge.submission.repository import RepositorySecurityError


def validate_submission_package(repo_dir: Path) -> SubmissionManifest:
    """Validate repository files, entrypoint, dependencies, and manifest declarations.
    
    If 'submission_manifest.json' exists, it is loaded and validated.
    If 'submission_manifest.json' is omitted, dynamic repository discovery automatically
    resolves the forecast entrypoint, interface contract, and dependencies.
    """
    repo_dir = Path(repo_dir).resolve()

    manifest_path = repo_dir / "submission_manifest.json"
    if manifest_path.is_file():
        # 1. Load explicit manifest if provided
        manifest = load_submission_manifest(repo_dir)
    else:
        # Dynamic Repository Discovery: auto-detect entrypoint and interface
        from hydraforge.discovery.repository_inspector import RepositoryInspector
        inspector = RepositoryInspector()
        report = inspector.inspect_repository(repo_dir)

        discovered_entrypoint = None
        if report.proposed_interface_mapping and report.proposed_interface_mapping.executable_target:
            discovered_entrypoint = report.proposed_interface_mapping.executable_target
        elif report.candidate_entrypoints:
            preferred_names = [
                "predict.py",
                "inference.py",
                "run_forecast.py",
                "forecast.py",
                "model.py",
                "main.py",
                "run.py",
                "run_backend.py",
            ]
            candidate_files = [c.file_path for c in report.candidate_entrypoints]
            for pref in preferred_names:
                matched = next((f for f in candidate_files if Path(f).name.lower() == pref or f.lower() == pref), None)
                if matched:
                    discovered_entrypoint = matched
                    break
            if not discovered_entrypoint:
                discovered_entrypoint = candidate_files[0]

        if not discovered_entrypoint:
            py_files = sorted(list(repo_dir.glob("*.py")))
            if py_files:
                discovered_entrypoint = py_files[0].name

        if not discovered_entrypoint:
            raise ValidationError(
                f"No forecast entrypoint found in repository root '{repo_dir}'. "
                "Ensure your repository contains an executable script (e.g. predict.py, model.py, or main.py)."
            )

        manifest = SubmissionManifest(
            team_name=repo_dir.name,
            submission_name=repo_dir.name,
            entrypoint=str(discovered_entrypoint),
        )

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

    # 3. Check for dependency specification (graceful fallback if absent)
    has_requirements = (repo_dir / "requirements.txt").is_file()
    has_pyproject = (repo_dir / "pyproject.toml").is_file()
    has_environment = (repo_dir / "environment.yml").is_file()
    has_setup = (repo_dir / "setup.py").is_file()

    # If no explicit dependency file exists, rely on pre-installed base container environment

    return manifest
