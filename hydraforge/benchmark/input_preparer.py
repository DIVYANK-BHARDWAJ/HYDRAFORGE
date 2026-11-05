"""
hydraforge/benchmark/input_preparer.py
Deterministic Benchmark Input Preparation Pipeline with Strict Temporal
Leakage Protection and Label Shielding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from hydraforge.benchmark.config import BenchmarkConfig, BENCHMARK_SPEC_VERSION
from hydraforge.benchmark.validation import DataValidationError
from hydraforge.runner.isolation import (
    LabelLeakageSecurityViolation,
    verify_hidden_label_shielding,
)
from hydraforge.schema import BenchmarkInputRecord


class BenchmarkInputPreparer:
    """
    Transforms BenchmarkInputRecords into serialized participant model inputs,
    strictly verifying:
    1. Zero temporal leakage (no observations post-dating forecast_origin).
    2. Zero label leakage (ground-truth reference observations stripped).
    3. Canonical schema conformity and cryptographic hashing.
    """

    def __init__(self, config: Optional[BenchmarkConfig] = None) -> None:
        self.config = config or BenchmarkConfig()

    def prepare_inference_inputs(
        self,
        cases: Sequence[BenchmarkInputRecord],
        output_file_path: Optional[Path] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Produce sanitized inference input payload conforming to the contract.
        Returns:
            Tuple of (sanitized_cases_list, sha256_input_hash).
        """
        sanitized_cases: List[Dict[str, Any]] = []

        for case in cases:
            # 1. Temporal Leakage Audit
            origin_str = case.forecast_origin.replace("Z", "+00:00")
            origin_dt = datetime.fromisoformat(origin_str)

            # If timeseries data contains timestamps, verify no timestamp > origin_dt
            forcing_history = {}
            for k, v in case.forcing_history.items():
                if isinstance(v, dict) and "dates" in v:
                    for d_str in v["dates"]:
                        obs_dt = datetime.fromisoformat(d_str.replace("Z", "+00:00"))
                        if obs_dt > origin_dt:
                            raise DataValidationError(
                                f"Temporal leakage detected: Observation date {d_str} in forcing "
                                f"is after forecast origin {case.forecast_origin} for case {case.case_id}."
                            )
                forcing_history[k] = v

            # 2. Strict Label Shielding
            # Construct permitted model input explicitly (never copy unknown fields)
            case_dict: Dict[str, Any] = {
                "case_id": str(case.case_id),
                "catchment_id": str(case.catchment_id),
                "forecast_origin": str(case.forecast_origin),
                "horizons": [int(h) for h in case.horizons],
                "discharge_history": [float(q) for q in case.discharge_history],
                "forcing_history": forcing_history,
                "attributes": dict(case.attributes),
                "split": str(case.split),
                "region": str(case.region) if case.region else None,
                "is_corrupted": bool(case.is_corrupted),
                "corruption_family": str(case.corruption_family) if case.corruption_family else None,
                "clean_case_id": str(case.clean_case_id) if case.clean_case_id else None,
            }

            # Verify no forbidden label keys exist
            forbidden_keys = {
                "true_discharge",
                "ground_truth",
                "persistence_discharge",
                "high_flow_threshold",
                "extreme_flow_threshold",
                "y_true",
                "labels",
            }
            intersection = set(case_dict.keys()).intersection(forbidden_keys)
            if intersection:
                raise LabelLeakageSecurityViolation(
                    f"Label shielding violation: Input contains ground-truth field(s): {intersection}"
                )

            sanitized_cases.append(case_dict)

        payload = {
            "benchmark_version": self.config.version,
            "cases": sanitized_cases,
        }

        # Deterministic JSON serialization
        json_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        input_hash = hashlib.sha256(json_bytes).hexdigest()

        if output_file_path:
            out_p = Path(output_file_path).resolve()
            # Verify destination path doesn't point to labels directory
            verify_hidden_label_shielding(out_p, [], {})
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_bytes(json_bytes)

        return sanitized_cases, input_hash

