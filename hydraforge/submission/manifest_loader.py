"""Submission Manifest Loader and Contract Verifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from hydraforge.schema import CONTRACT_VERSION, SubmissionManifest, ValidationError


def load_submission_manifest(repo_dir: Path) -> SubmissionManifest:
    """Load and parse submission_manifest.json from the repository root."""
    repo_dir = Path(repo_dir)
    manifest_path = repo_dir / "submission_manifest.json"

    if not manifest_path.exists():
        raise ValidationError(
            f"Mandatory submission manifest not found: '{manifest_path}'. "
            "Every participant repository must include a root 'submission_manifest.json'."
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValidationError(f"Failed to parse submission_manifest.json: {e}")

    if not isinstance(data, dict):
        raise ValidationError("submission_manifest.json must contain a JSON object.")

    # Instantiate and validate
    manifest = SubmissionManifest(
        team_name=str(data.get("team_name", "")),
        submission_name=str(data.get("submission_name", "")),
        contract_version=str(data.get("contract_version", "")),
        repository_url=data.get("repository_url"),
        commit_sha=data.get("commit_sha"),
        dataset_declarations=data.get("dataset_declarations", {}),
        pretrained_models=data.get("pretrained_models", []),
        entrypoint=str(data.get("entrypoint", "run_forecast.py")),
        created_at=str(data.get("created_at", ""))
    )
    manifest.validate()
    return manifest

