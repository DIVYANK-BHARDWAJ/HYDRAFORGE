"""Deterministic Synthetic Hydrological Benchmark Generator for Software Testing.

IMPORTANT NOTICE:
SYNTHETIC DATA — FOR SOFTWARE INTEGRATION AND REGRESSION TESTING ONLY.
This synthetic data is mathematically generated using idealized rainfall-runoff storage
dynamics. It is NEVER to be represented as Caravan data, genuine observations, official
benchmark data, or real-world competition results.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from hydraforge.benchmark.config import BenchmarkConfig, CORRUPTION_FAMILIES
from hydraforge.benchmark.provenance import ThresholdMetadata, compute_object_sha256
from hydraforge.benchmark.split_manager import SplitManager
from hydraforge.benchmark.validation import audit_splits_for_leakage, LeakageAuditReport


SYNTHETIC_BANNER = "SYNTHETIC — FOR SOFTWARE INTEGRATION TESTING ONLY"


def generate_catchment_timeseries(
    catchment_id: str,
    area_km2: float,
    start_date: datetime,
    n_days: int,
    rng: np.random.RandomState,
    inject_extremes: bool = True
) -> Dict[str, Any]:
    """Generate physically plausible daily discharge and meteorology via storage recession."""
    dates: List[str] = []
    discharge: List[float] = []
    precipitation: List[float] = []
    temperature: List[float] = []
    solar_radiation: List[float] = []

    # Hydro characteristics
    q_base = area_km2 * 0.05  # Baseflow scaling
    alpha = rng.uniform(0.85, 0.92)  # Recession storage rate
    runoff_coeff = area_km2 * 0.008

    current_q = q_base

    for i in range(n_days):
        dt = start_date + timedelta(days=i)
        d_str = dt.strftime("%Y-%m-%d")
        d_of_year = dt.timetuple().tm_yday

        # Seasonal temperature cycle
        temp = 12.0 + 10.0 * np.sin(2 * np.pi * (d_of_year - 80) / 365.0) + rng.normal(0, 1.5)
        # Solar radiation
        solar = max(50.0, 180.0 + 80.0 * np.sin(2 * np.pi * (d_of_year - 80) / 365.0) + rng.normal(0, 15.0))

        # Intermittent precipitation
        is_rain = rng.uniform(0, 1) < 0.30
        if is_rain:
            precip = float(rng.gamma(shape=2.0, scale=4.0))
        else:
            precip = 0.0

        # Inject extreme flood pulses at specific times if requested
        if inject_extremes and (i in (45, 120, 210, 290)):
            precip += float(rng.uniform(35.0, 65.0))

        # Rainfall-runoff equation
        runoff = runoff_coeff * precip
        current_q = alpha * current_q + (1.0 - alpha) * q_base + runoff + float(rng.normal(0, 0.05 * q_base))
        current_q = max(0.1, current_q)

        dates.append(d_str)
        discharge.append(round(current_q, 2))
        precipitation.append(round(precip, 2))
        temperature.append(round(temp, 2))
        solar_radiation.append(round(solar, 1))

    return {
        "catchment_id": catchment_id,
        "area_km2": area_km2,
        "dates": dates,
        "discharge": discharge,
        "precipitation": precipitation,
        "temperature": temperature,
        "solar_radiation": solar_radiation
    }


def generate_synthetic_benchmark(
    output_dir: Path,
    config: Optional[BenchmarkConfig] = None
) -> Tuple[Dict[str, Any], LeakageAuditReport]:
    """Generate a complete, self-contained synthetic benchmark suite.

    Partitions:
    - Train: Catchments C_01, C_02, C_03, C_04 (Days 0 to 180)
    - Validation: Catchments C_01, C_02, C_03, C_04 (Days 181 to 240)
    - Test A (Temporal): Catchments C_01, C_02, C_03, C_04 (Days 241 to 365)
    - Test B (Geographic): Catchments C_05_UNSEEN, C_06_UNSEEN (Days 241 to 365)
    - Test C (Robustness): Corrupted versions of Test A cases
    """
    config = config or BenchmarkConfig()
    rng = np.random.RandomState(config.random_seed)
    output_dir = Path(output_dir)

    split_mgr = SplitManager(config)

    # Define synthetic catchment fleet
    catchment_defs = [
        {"id": "BASIN_SYN_01", "area": 120.0, "elev": 450.0, "region": "Alps"},
        {"id": "BASIN_SYN_02", "area": 350.0, "elev": 780.0, "region": "Alps"},
        {"id": "BASIN_SYN_03", "area": 850.0, "elev": 1200.0, "region": "Rockies"},
        {"id": "BASIN_SYN_04", "area": 1400.0, "elev": 310.0, "region": "Rockies"},
        {"id": "BASIN_SYN_05_UNSEEN", "area": 220.0, "elev": 620.0, "region": "Alps"},
        {"id": "BASIN_SYN_06_UNSEEN", "area": 950.0, "elev": 1100.0, "region": "Rockies"},
    ]

    train_cids = ["BASIN_SYN_01", "BASIN_SYN_02", "BASIN_SYN_03", "BASIN_SYN_04"]
    test_b_cids = ["BASIN_SYN_05_UNSEEN", "BASIN_SYN_06_UNSEEN"]

    start_date = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    total_days = 365

    # Generate daily series for each catchment
    series_by_cid: Dict[str, Dict[str, Any]] = {}
    for c_def in catchment_defs:
        cid = c_def["id"]
        series_by_cid[cid] = generate_catchment_timeseries(
            catchment_id=cid,
            area_km2=c_def["area"],
            start_date=start_date,
            n_days=total_days,
            rng=rng,
            inject_extremes=True
        )

    # 1. Compute Thresholds strictly from Training Period (Days 0 to 180)
    # Never derived from test labels!
    threshold_meta: Dict[str, Any] = {
        "metadata_notice": SYNTHETIC_BANNER,
        "calculation_method": "historical_training_empirical_percentile",
        "reference_period": "2025-01-01 to 2025-06-30",
        "catchments": {}
    }

    catchment_metadata_export: Dict[str, Dict[str, Any]] = {}

    for c_def in catchment_defs:
        cid = c_def["id"]
        # If train catchment, compute on its own training period
        # If unseen Test B catchment, use reference training distribution of same region
        if cid in train_cids:
            train_flows = series_by_cid[cid]["discharge"][:180]
        else:
            # Baseline proxy: regional reference from training
            ref_cid = "BASIN_SYN_01" if c_def["region"] == "Alps" else "BASIN_SYN_03"
            train_flows = series_by_cid[ref_cid]["discharge"][:180]

        q95 = float(np.percentile(train_flows, config.q95_percentile))
        q99 = float(np.percentile(train_flows, config.q99_percentile))

        meta_obj = ThresholdMetadata(
            catchment_id=cid,
            percentile=95.0,
            threshold_value=round(q95, 2),
            units=config.discharge_unit,
            source_split="train",
            source_start_date="2025-01-01",
            source_end_date="2025-06-30",
            sample_count=len(train_flows),
            notes=f"Synthetic threshold from baseline {cid}"
        )
        threshold_meta["catchments"][cid] = {
            "q95": meta_obj.to_dict(),
            "q99_threshold_value": round(q99, 2),
            "region": c_def["region"],
            "area_km2": c_def["area"]
        }
        catchment_metadata_export[cid] = {
            "region": c_def["region"],
            "area_km2": c_def["area"],
            "elevation_m": c_def["elev"],
            "q95_threshold": round(q95, 2),
            "q99_threshold": round(q99, 2)
        }

    # Save metadata
    meta_dir = output_dir / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    with open(meta_dir / "thresholds.json", "w", encoding="utf-8") as f:
        json.dump(threshold_meta, f, indent=2)
    with open(meta_dir / "catchments.json", "w", encoding="utf-8") as f:
        json.dump(catchment_metadata_export, f, indent=2)

    # 2. Build Case Records for Each Split
    # Windows: history = 30 days prior to origin; horizons = [1, 3, 7]
    def create_case_slices(
        cids: List[str],
        day_range: Tuple[int, int],
        split_name: str,
        step_days: int = 15
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        in_recs: List[Dict[str, Any]] = []
        lbl_recs: List[Dict[str, Any]] = []
        start_idx, end_idx = day_range

        for cid in cids:
            s = series_by_cid[cid]
            c_meta = catchment_metadata_export[cid]
            q95 = c_meta["q95_threshold"]
            q99 = c_meta["q99_threshold"]

            for origin_idx in range(start_idx, end_idx - 7, step_days):
                origin_date_str = s["dates"][origin_idx]
                case_id = f"{split_name}_{cid}_{origin_date_str.replace('-', '')}"

                # Past 30 days history
                hist_start = max(0, origin_idx - 30)
                discharge_hist = s["discharge"][hist_start:origin_idx]
                forcing_hist = {
                    "precipitation_mm": s["precipitation"][hist_start:origin_idx],
                    "temperature_c": s["temperature"][hist_start:origin_idx],
                    "solar_radiation_wm2": s["solar_radiation"][hist_start:origin_idx],
                }

                in_recs.append({
                    "case_id": case_id,
                    "catchment_id": cid,
                    "forecast_origin": f"{origin_date_str}T00:00:00Z",
                    "horizons": list(config.horizons),
                    "discharge_history": discharge_hist,
                    "forcing_history": forcing_hist,
                    "attributes": {
                        "area_km2": c_meta["area_km2"],
                        "mean_elevation_m": c_meta["elevation_m"]
                    },
                    "split": split_name,
                    "region": c_meta["region"],
                    "is_corrupted": False,
                    "notice": SYNTHETIC_BANNER
                })

                # Labels for each horizon
                last_known_q = s["discharge"][origin_idx - 1] if origin_idx > 0 else s["discharge"][origin_idx]
                for h in config.horizons:
                    target_idx = origin_idx + h
                    true_q = s["discharge"][target_idx]
                    lbl_recs.append({
                        "case_id": case_id,
                        "catchment_id": cid,
                        "forecast_origin": f"{origin_date_str}T00:00:00Z",
                        "horizon": h,
                        "true_discharge": true_q,
                        "high_flow_threshold": q95,
                        "extreme_flow_threshold": q99,
                        "persistence_discharge": last_known_q,
                        "split": split_name,
                        "region": c_meta["region"],
                        "is_corrupted": False
                    })
        return in_recs, lbl_recs

    # Generate Train (days 35 to 175)
    train_in, train_lbl = create_case_slices(train_cids, (35, 175), "train", step_days=14)
    # Generate Validation (days 185 to 235)
    val_in, val_lbl = create_case_slices(train_cids, (185, 235), "validation", step_days=10)
    # Generate Test A (days 245 to 350)
    test_a_in, test_a_lbl = create_case_slices(train_cids, (245, 350), "test_a", step_days=10)
    # Generate Test B (days 245 to 350 on unseen catchments)
    test_b_in, test_b_lbl = create_case_slices(test_b_cids, (245, 350), "test_b", step_days=10)

    # Generate Test C (Corrupted variants of Test A cases)
    test_c_in: List[Dict[str, Any]] = []
    test_c_lbl: List[Dict[str, Any]] = []

    for fam in CORRUPTION_FAMILIES:
        # Corrupt input records
        corr_in = split_mgr.generate_corrupted_cases(test_a_in[:10], corruption_family=fam, rng=rng)
        test_c_in.extend(corr_in)

        # Corresponding ground-truth labels remain identical to clean targets
        # only case_id is modified to pair with corrupted inputs
        clean_lbl_map = {(l["case_id"], l["horizon"]): l for l in test_a_lbl}
        for cin in corr_in:
            for h in config.horizons:
                clean_l = clean_lbl_map.get((cin["clean_case_id"], h))
                if clean_l:
                    c_lbl = dict(clean_l)
                    c_lbl["case_id"] = cin["case_id"]
                    c_lbl["clean_case_id"] = cin["clean_case_id"]
                    c_lbl["is_corrupted"] = True
                    c_lbl["corruption_family"] = fam
                    c_lbl["split"] = "test_c"
                    test_c_lbl.append(c_lbl)

    # Save all partitions to disk
    manifests: Dict[str, Any] = {}
    manifests["train"] = split_mgr.save_split_package(output_dir, "train", train_in, train_lbl).to_dict()
    manifests["validation"] = split_mgr.save_split_package(output_dir, "validation", val_in, val_lbl).to_dict()
    manifests["test_a"] = split_mgr.save_split_package(output_dir, "test_a", test_a_in, test_a_lbl).to_dict()
    manifests["test_b"] = split_mgr.save_split_package(output_dir, "test_b", test_b_in, test_b_lbl).to_dict()
    manifests["test_c"] = split_mgr.save_split_package(output_dir, "test_c", test_c_in, test_c_lbl).to_dict()

    with open(output_dir / "metadata" / "split_manifests.json", "w", encoding="utf-8") as f:
        json.dump(manifests, f, indent=2)

    # Perform Leakage Audit
    audit = audit_splits_for_leakage(train_in, val_in, test_a_in, test_b_in, test_c_in)
    with open(output_dir / "metadata" / "leakage_audit.json", "w", encoding="utf-8") as f:
        json.dump(asdict(audit), f, indent=2)

    summary = {
        "status": "success",
        "notice": SYNTHETIC_BANNER,
        "manifests": manifests,
        "is_leakage_free": audit.is_leakage_free,
        "case_counts": audit.details
    }
    return summary, audit

