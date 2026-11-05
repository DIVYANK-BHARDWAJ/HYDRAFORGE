"""Robustness Evaluation Metric (Provisional Weight: 10 Points).

Compares forecast performance on strictly paired clean and corrupted benchmark cases.
Evaluates degradation across distinct corruption families (e.g., missing discharge history,
sensor noise, reporting latency).
Never compares unpaired or unrelated case sets.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from hydraforge.metrics.forecast_skill import calculate_mae
from hydraforge.metrics.event_detection import calculate_brier_score

PROVISIONAL_WEIGHT_ROBUSTNESS = 10.0


def evaluate_robustness(
    clean_records: Sequence[Dict[str, Any]],
    corrupt_records: Sequence[Dict[str, Any]],
    max_points: float = PROVISIONAL_WEIGHT_ROBUSTNESS
) -> Dict[str, Any]:
    """Evaluate performance retention under controlled input corruptions (Test C).

    clean_records: baseline uncorrupted cases with keys:
        'case_id', 'horizon', 'y_true', 'y_pred', 'high_flow_prob', 'high_flow_threshold'
    corrupt_records: perturbed cases with matching keys PLUS:
        'clean_case_id', 'corruption_family'

    Returns strict per-family degradation metrics and overall robustness score.
    """
    all_warnings: List[str] = []

    if not corrupt_records:
        return {
            "dimension": "robustness",
            "points_awarded": 0.0,
            "max_points": max_points,
            "weight": max_points,
            "normalized_score": 0.0,
            "is_provisional": True,
            "warnings": ["No corrupted (Test C) records provided for robustness evaluation."],
            "corruption_families": {},
            "paired_sample_count": 0
        }

    # Build clean lookup index by (case_id, horizon)
    clean_index: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for r in clean_records:
        key = (str(r["case_id"]), int(r["horizon"]))
        clean_index[key] = r

    # Group paired records by corruption family
    family_pairs: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = {}
    unpaired_count = 0

    for c_rec in corrupt_records:
        clean_cid = c_rec.get("clean_case_id")
        h = int(c_rec["horizon"])
        family = str(c_rec.get("corruption_family", "unspecified_corruption"))

        if not clean_cid:
            unpaired_count += 1
            continue

        clean_key = (str(clean_cid), h)
        if clean_key not in clean_index:
            unpaired_count += 1
            continue

        clean_rec = clean_index[clean_key]
        family_pairs.setdefault(family, []).append((clean_rec, c_rec))

    if unpaired_count > 0:
        all_warnings.append(
            f"Skipped {unpaired_count} corrupted records lacking paired clean counter-parts in reference set."
        )

    if not family_pairs:
        return {
            "dimension": "robustness",
            "points_awarded": 0.0,
            "max_points": max_points,
            "weight": max_points,
            "normalized_score": 0.0,
            "is_provisional": True,
            "warnings": all_warnings + ["Zero valid clean-corrupted pairs could be established."],
            "corruption_families": {},
            "paired_sample_count": 0
        }

    family_results: Dict[str, Dict[str, Any]] = {}
    family_retentions: List[float] = []
    total_pairs = 0

    for family, pairs in family_pairs.items():
        total_pairs += len(pairs)
        y_true_clean = np.array([p[0]["y_true"] for p in pairs], dtype=np.float64)
        y_pred_clean = np.array([p[0]["y_pred"] for p in pairs], dtype=np.float64)
        
        y_true_corrupt = np.array([p[1]["y_true"] for p in pairs], dtype=np.float64)
        y_pred_corrupt = np.array([p[1]["y_pred"] for p in pairs], dtype=np.float64)

        clean_mae = calculate_mae(y_true_clean, y_pred_clean)
        corrupt_mae = calculate_mae(y_true_corrupt, y_pred_corrupt)
        delta_mae = corrupt_mae - clean_mae

        # Relative error degradation retention
        # If corrupt MAE <= clean MAE, model is completely robust (retention = 1.0)
        # Otherwise, degradation is normalized against max(clean_mae, 1.0)
        denom = max(clean_mae, 1.0)
        if delta_mae <= 0:
            retention = 1.0
        else:
            retention = max(0.0, 1.0 - (delta_mae / denom))

        family_retentions.append(retention)
        family_results[family] = {
            "n_pairs": len(pairs),
            "clean_mae": round(clean_mae, 4),
            "corrupt_mae": round(corrupt_mae, 4),
            "delta_mae": round(delta_mae, 4),
            "retention_ratio": round(retention, 4)
        }

    # Mean retention across corruption families
    mean_retention = float(np.mean(family_retentions)) if family_retentions else 0.0
    points_awarded = min(max_points, max(0.0, mean_retention * max_points))
    normalized_score = points_awarded / max_points if max_points > 0 else 0.0

    return {
        "dimension": "robustness",
        "points_awarded": round(points_awarded, 4),
        "max_points": max_points,
        "weight": max_points,
        "normalized_score": round(normalized_score, 4),
        "is_provisional": True,
        "warnings": all_warnings,
        "mean_retention": round(mean_retention, 4),
        "paired_sample_count": total_pairs,
        "corruption_families": family_results
    }

