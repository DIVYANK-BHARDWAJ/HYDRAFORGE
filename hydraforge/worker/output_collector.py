"""
hydraforge/worker/output_collector.py
Safe collection, cryptographic hashing, and validation of participant predictions.
Guarantees path containment, rejects symlink escapes, and verifies contract conformance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Tuple

from hydraforge.schema import (
    ContractConfig,
    PredictionRecord,
    ValidationError,
    validate_predictions,
)


class OutputCollectionSecurityError(Exception):
    """Raised when an output file violates containment or attempts path traversal."""
    pass


class OutputCollector:
    """Collects and validates model outputs safely from an isolated output volume."""

    def __init__(self, contract_config: Optional[ContractConfig] = None) -> None:
        self.contract_config = contract_config or ContractConfig()

    def collect_predictions(
        self,
        output_dir: Path,
        expected_filename: str = "predictions.json",
        expected_cases: Optional[Any] = None,
    ) -> Tuple[List[PredictionRecord], str, List[str]]:
        """
        Safely retrieve and validate prediction records from output_dir.
        Returns:
            (validated_records, sha256_output_hash, warnings)
        """
        import os
        from hydraforge.schema import validate_prediction_record

        output_dir = Path(output_dir).resolve()
        norm_combined = os.path.normpath(str(output_dir / expected_filename))
        if not norm_combined.startswith(str(output_dir)):
            raise OutputCollectionSecurityError(
                f"Path traversal detected: Output target '{expected_filename}' escapes directory '{output_dir}'."
            )

        target_file = output_dir / expected_filename

        # 1. Symlink escape check
        if target_file.is_symlink():
            resolved = target_file.resolve()
            try:
                resolved.relative_to(output_dir)
            except ValueError:
                raise OutputCollectionSecurityError(
                    f"Insecure symlink output detected: '{target_file}' resolves outside output volume to '{resolved}'."
                )

        resolved_target = target_file.resolve()
        try:
            resolved_target.relative_to(output_dir)
        except ValueError:
            raise OutputCollectionSecurityError(
                f"Path traversal detected: Output target '{resolved_target}' is outside output directory '{output_dir}'."
            )

        if not resolved_target.exists():
            raise FileNotFoundError(
                f"Expected predictions output file '{expected_filename}' was not created by participant model."
            )

        warnings: List[str] = []

        # 2. Compute cryptographic hash
        sha256 = hashlib.sha256()
        try:
            with open(resolved_target, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)
            output_hash = sha256.hexdigest()
        except Exception as e:
            raise OutputCollectionSecurityError(f"Failed to read output file for hashing: {e}")

        # 3. Parse JSON
        try:
            with open(resolved_target, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format in predictions output: {e}")

        raw_list = raw_data.get("predictions", raw_data) if isinstance(raw_data, dict) else raw_data
        if not isinstance(raw_list, list):
            raise ValidationError("Predictions file must contain a list of prediction records.")

        if not raw_list:
            raise ValidationError("Predictions list is empty.")

        records: List[PredictionRecord] = []
        for idx, item in enumerate(raw_list):
            if not isinstance(item, dict):
                raise ValidationError(f"Prediction item at index {idx} is not an object.")
            records.append(PredictionRecord.from_dict(item))

        # 4. Validate individual predictions against numeric and contract bounds
        for r in records:
            validate_prediction_record(r, self.contract_config)

        if expected_cases is not None:
            validate_predictions(records, expected_cases, self.contract_config)

        return records, output_hash, warnings
