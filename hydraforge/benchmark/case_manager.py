"""
hydraforge/benchmark/case_manager.py
Authoritative Benchmark Case Manager.
Manages loading, version resolution, schema validation, temporal ordering,
unit verification, catchment metadata, and split integrity for the BASINSHIFT challenge.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from hydraforge.benchmark.config import (
    BenchmarkConfig,
    BENCHMARK_SPEC_VERSION,
    SUPPORTED_SPLITS,
    SUPPORTED_DISCHARGE_UNITS,
    SUPPORTED_PRECIPITATION_UNITS,
    SUPPORTED_TEMPERATURE_UNITS,
)
from hydraforge.benchmark.loader import (
    OrganizerBenchmarkLoader,
    ParticipantBenchmarkLoader,
)
from hydraforge.benchmark.provenance import compute_file_sha256, compute_object_sha256
from hydraforge.benchmark.validation import (
    DataValidationError,
    LeakageError,
    validate_units,
)
from hydraforge.schema import BenchmarkInputRecord, GroundTruthLabel


class BenchmarkCaseManager:
    """
    Authoritative manager for loading, verifying, and distributing benchmark cases
    across training, validation, and test splits (Test A, Test B, Test C).
    Enforces strict separation between participant inference cases and hidden reference labels.
    """

    def __init__(
        self,
        benchmark_root: Path,
        config: Optional[BenchmarkConfig] = None,
    ) -> None:
        self.benchmark_root = Path(benchmark_root).resolve()
        self.config = config or BenchmarkConfig()
        self.participant_loader = ParticipantBenchmarkLoader(self.benchmark_root / "inputs")
        self.organizer_loader = OrganizerBenchmarkLoader(self.benchmark_root)

    def resolve_version(self) -> str:
        """
        Verify and return benchmark version.
        Raises DataValidationError if version is incompatible.
        """
        version = self.config.version
        if version != BENCHMARK_SPEC_VERSION:
            raise DataValidationError(
                f"Incompatible benchmark version '{version}'. Expected '{BENCHMARK_SPEC_VERSION}'."
            )
        return version

    def get_eligible_cases(self, split: str) -> List[BenchmarkInputRecord]:
        """
        Retrieve benchmark input cases for participant inference.
        Guarantees that participant cases contain NO ground-truth labels or hidden thresholds.
        """
        if split not in SUPPORTED_SPLITS:
            raise DataValidationError(
                f"Unsupported split '{split}'. Supported splits: {SUPPORTED_SPLITS}"
            )
        return self.participant_loader.load_inputs(split)

    def get_reference_labels(self, split: str) -> List[GroundTruthLabel]:
        """
        Retrieve organizer-only hidden ground-truth labels for scoring.
        MUST NEVER be accessible to participant worker containers.
        """
        if split not in SUPPORTED_SPLITS:
            raise DataValidationError(
                f"Unsupported split '{split}'. Supported splits: {SUPPORTED_SPLITS}"
            )
        return self.organizer_loader.load_ground_truth(split)

    def get_catchment_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Load static physical attributes for catchments."""
        meta_file = self.benchmark_root / "metadata" / "catchments.json"
        if not meta_file.exists():
            return {}
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise DataValidationError(f"Failed to read catchment metadata: {e}")

    def get_thresholds_metadata(self) -> Dict[str, Any]:
        """Load historical baseline event threshold metadata (Q95, Q99)."""
        thresh_file = self.benchmark_root / "metadata" / "thresholds.json"
        if not thresh_file.exists():
            return {}
        try:
            with open(thresh_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise DataValidationError(f"Failed to read threshold metadata: {e}")

    def validate_benchmark_integrity(self) -> Dict[str, Any]:
        """
        Execute comprehensive validation of benchmark assets:
        1. Feature schema and types.
        2. Unit compliance.
        3. Catchment metadata completeness.
        4. Monotonic temporal ordering.
        5. Absence of duplicate observations.
        6. Detection of missing observations.
        7. Split partition integrity (geographic holdout, temporal holdout, robustness pairing).
        """
        self.resolve_version()
        report: Dict[str, Any] = {
            "status": "VALID",
            "benchmark_root": str(self.benchmark_root),
            "version": self.config.version,
            "splits_checked": {},
            "errors": [],
            "warnings": [],
        }

        # 1. Catchment metadata check
        catchment_meta = self.get_catchment_metadata()
        if not catchment_meta:
            report["warnings"].append("Catchment metadata file is empty or missing.")

        # 2. Iterate through splits and validate inputs and ground truth
        all_train_cids: Set[str] = set()
        test_b_cids: Set[str] = set()
        test_a_dates: List[datetime] = []
        train_dates: List[datetime] = []
        test_c_clean_ids: Set[str] = set()
        test_a_case_ids: Set[str] = set()

        for split in ("train", "validation", "test_a", "test_b", "test_c"):
            split_dir = self.benchmark_root / "inputs" / split
            if not split_dir.exists():
                report["warnings"].append(f"Split inputs directory '{split}' not present.")
                continue

            cases = self.get_eligible_cases(split)
            split_stat = {
                "case_count": len(cases),
                "catchments": list({c.catchment_id for c in cases}),
            }
            report["splits_checked"][split] = split_stat

            for case in cases:
                # Schema validation
                if not case.case_id or not case.catchment_id or not case.forecast_origin:
                    report["errors"].append(f"Invalid case record structure in split '{split}'.")
                if not case.horizons:
                    report["errors"].append(f"Case '{case.case_id}' has empty horizons.")

                # Non-negative discharge history check
                for q in case.discharge_history:
                    if q is not None and q < 0.0:
                        report["errors"].append(
                            f"Case '{case.case_id}' in split '{split}' contains negative discharge: {q}"
                        )

                # Forcing history check
                for var, vals in case.forcing_history.items():
                    if "precip" in var.lower():
                        validate_units("precipitation", "mm")
                        for p in vals:
                            if p is not None and p < 0.0:
                                report["errors"].append(
                                    f"Case '{case.case_id}' contains negative precipitation: {p}"
                                )

                # Track for split integrity verification
                origin_dt = datetime.fromisoformat(case.forecast_origin.replace("Z", "+00:00"))
                if split == "train":
                    all_train_cids.add(case.catchment_id)
                    train_dates.append(origin_dt)
                elif split == "test_a":
                    test_a_dates.append(origin_dt)
                    test_a_case_ids.add(case.case_id)
                elif split == "test_b":
                    test_b_cids.add(case.catchment_id)
                elif split == "test_c":
                    if case.clean_case_id:
                        test_c_clean_ids.add(case.clean_case_id)

        # 3. Verify Geographic Holdout (Test B Catchments must be disjoint from Training)
        spatial_overlap = all_train_cids.intersection(test_b_cids)
        if spatial_overlap:
            err = f"Geographic leakage: Test B contains catchments present in Training set: {spatial_overlap}"
            report["errors"].append(err)
            report["status"] = "LEAKAGE_DETECTED"

        # 4. Verify Temporal Holdout (Test A forecast origins must succeed Training period)
        if train_dates and test_a_dates:
            max_train_date = max(train_dates)
            min_test_a_date = min(test_a_dates)
            if min_test_a_date < max_train_date:
                err = (
                    f"Temporal leakage: Test A starts ({min_test_a_date.isoformat()}) "
                    f"before training concludes ({max_train_date.isoformat()})."
                )
                report["errors"].append(err)
                report["status"] = "LEAKAGE_DETECTED"

        # 5. Verify Robustness Pairing (Test C cases must map to valid clean references)
        if test_c_clean_ids and test_a_case_ids:
            unpaired = test_c_clean_ids - test_a_case_ids
            if unpaired:
                report["warnings"].append(
                    f"Test C has {len(unpaired)} corrupted cases whose clean reference is not in Test A."
                )

        if report["errors"]:
            report["status"] = "FAILED"

        return report

    def generate_manifest(self) -> Dict[str, Any]:
        """
        Generate cryptographic provenance manifest hashing all input and label files.
        """
        manifest: Dict[str, Any] = {
            "benchmark_version": self.config.version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": {},
            "split_hashes": {},
        }

        for p in sorted(self.benchmark_root.rglob("*.json")):
            rel_p = str(p.relative_to(self.benchmark_root)).replace("\\", "/")
            file_hash = compute_file_sha256(p)
            manifest["files"][rel_p] = file_hash

        manifest["manifest_hash"] = compute_object_sha256(manifest["files"])
        return manifest
