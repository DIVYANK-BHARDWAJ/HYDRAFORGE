"""Benchmark Service: Reads benchmark metadata, split counts, and leakage audits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class BenchmarkService:
    """Provides metadata and leakage audit status without exposing hidden ground truth."""

    def __init__(self, benchmark_root: Path = Path("data/benchmark")) -> None:
        self.benchmark_root = Path(benchmark_root).resolve()
        self.metadata_dir = self.benchmark_root / "metadata"

    def get_benchmark_summary(self) -> Dict[str, Any]:
        """Return non-sensitive benchmark stats and split details."""
        thresholds_path = self.metadata_dir / "thresholds.json"
        catchments_path = self.metadata_dir / "catchments.json"
        audit_path = self.metadata_dir / "leakage_audit.json"
        manifests_path = self.metadata_dir / "split_manifests.json"

        catchments_data = {}
        if catchments_path.exists():
            with open(catchments_path, "r", encoding="utf-8") as f:
                catchments_data = json.load(f)

        regions = set()
        for cid, meta in catchments_data.items():
            if meta.get("region"):
                regions.add(meta["region"])

        split_manifests = {}
        if manifests_path.exists():
            with open(manifests_path, "r", encoding="utf-8") as f:
                split_manifests = json.load(f)

        leakage_audit = {}
        if audit_path.exists():
            with open(audit_path, "r", encoding="utf-8") as f:
                leakage_audit = json.load(f)

        return {
            "dataset_name": "Caravan / Synthetic Test Fleet",
            "benchmark_version": "1.0.0",
            "is_synthetic": True,
            "notice": "SYNTHETIC — FOR SOFTWARE INTEGRATION TESTING ONLY",
            "catchment_count": len(catchments_data),
            "region_count": len(regions),
            "regions": sorted(regions),
            "available_splits": ["train", "validation", "test_a", "test_b", "test_c"],
            "split_manifests": split_manifests,
            "leakage_audit": {
                "is_leakage_free": leakage_audit.get("is_leakage_free", True),
                "catchment_overlap_count": leakage_audit.get("catchment_overlap_count", 0),
                "temporal_leakage_detected": leakage_audit.get("temporal_leakage_detected", False),
                "corrupted_cases_paired_correctly": leakage_audit.get("corrupted_cases_paired_correctly", True)
            }
        }

