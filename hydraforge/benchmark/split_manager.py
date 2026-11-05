"""Split Manager: Constructs Leakage-Resistant Benchmark Partitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import numpy as np

from hydraforge.benchmark.config import BenchmarkConfig, CORRUPTION_FAMILIES
from hydraforge.benchmark.provenance import SplitManifest, compute_object_sha256
from hydraforge.benchmark.validation import audit_splits_for_leakage, LeakageAuditReport, LeakageError


class SplitManager:
    """Orchestrates creation, validation, and serialization of benchmark splits."""

    def __init__(self, config: Optional[BenchmarkConfig] = None) -> None:
        self.config = config or BenchmarkConfig()

    def partition_catchments(
        self,
        all_catchments: Sequence[str],
        test_b_fraction: float = 0.33,
        seed: Optional[int] = None
    ) -> Tuple[List[str], List[str]]:
        """Geographically partition catchments into training/temporal set vs Test B holdout set."""
        rng = np.random.RandomState(seed or self.config.random_seed)
        shuffled = list(all_catchments)
        rng.shuffle(shuffled)

        n_b = max(1, int(len(shuffled) * test_b_fraction))
        test_b_catchments = sorted(shuffled[:n_b])
        train_catchments = sorted(shuffled[n_b:])

        # Verification: zero catchment overlap
        overlap = set(test_b_catchments).intersection(train_catchments)
        if overlap:
            raise LeakageError(f"Zero-overlap invariant violated: {overlap}")

        return train_catchments, test_b_catchments

    def generate_corrupted_cases(
        self,
        clean_cases: Sequence[Dict[str, Any]],
        corruption_family: str,
        rng: np.random.RandomState
    ) -> List[Dict[str, Any]]:
        """Apply controlled input corruption to clean benchmark cases.

        Ground-truth labels are NEVER modified.
        Only input fields (discharge history, forcings) are perturbed.
        """
        corrupted_cases: List[Dict[str, Any]] = []

        for clean in clean_cases:
            c_copy = dict(clean)
            c_copy["case_id"] = f"{clean['case_id']}_corr_{corruption_family}"
            c_copy["clean_case_id"] = clean["case_id"]
            c_copy["is_corrupted"] = True
            c_copy["corruption_family"] = corruption_family

            # Deep copy input history
            disc_hist = list(clean.get("discharge_history", []))
            forcing_hist = {k: list(v) for k, v in clean.get("forcing_history", {}).items()}

            if corruption_family == "missing_discharge":
                # Withhold past discharge observations (e.g., ungauged basin scenario)
                c_copy["discharge_history"] = []
                c_copy["forcing_history"] = forcing_hist

            elif corruption_family == "input_noise":
                # Add 15% additive Gaussian sensor noise to precipitation
                c_copy["discharge_history"] = disc_hist
                if "precipitation_mm" in forcing_hist:
                    precip = np.array(forcing_hist["precipitation_mm"], dtype=np.float64)
                    noise = rng.normal(0.0, 0.15 * (np.mean(precip) + 1.0), size=len(precip))
                    noisy_precip = np.maximum(0.0, precip + noise).tolist()
                    forcing_hist["precipitation_mm"] = [round(x, 2) for x in noisy_precip]
                c_copy["forcing_history"] = forcing_hist

            elif corruption_family == "reporting_delay":
                # Simulate 48-hour latency: zero out last 2 days of forcing
                c_copy["discharge_history"] = disc_hist
                for var, vals in forcing_hist.items():
                    if len(vals) >= 2:
                        vals[-1] = vals[-2]  # Repeat lagged value
                        vals[-2] = vals[-3] if len(vals) >= 3 else vals[-2]
                c_copy["forcing_history"] = forcing_hist
            else:
                c_copy["discharge_history"] = disc_hist
                c_copy["forcing_history"] = forcing_hist

            corrupted_cases.append(c_copy)

        return corrupted_cases

    def save_split_package(
        self,
        output_root: Path,
        split_name: str,
        input_records: Sequence[Dict[str, Any]],
        label_records: Sequence[Dict[str, Any]],
    ) -> SplitManifest:
        """Serialize inputs and labels to strictly separate directories."""
        inputs_dir = output_root / "inputs" / split_name
        labels_dir = output_root / "labels" / split_name
        inputs_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)

        inputs_file = inputs_dir / "inputs.json"
        labels_file = labels_dir / "labels.json"

        with open(inputs_file, "w", encoding="utf-8") as f:
            json.dump(list(input_records), f, indent=2)

        with open(labels_file, "w", encoding="utf-8") as f:
            json.dump(list(label_records), f, indent=2)

        cids = sorted(list({r["catchment_id"] for r in input_records}))

        manifest = SplitManifest(
            split_name=split_name,
            case_count=len(input_records),
            catchment_count=len(cids),
            catchment_ids=cids,
            input_records_hash=compute_object_sha256(input_records),
            label_records_hash=compute_object_sha256(label_records)
        )
        return manifest

