"""Out-of-Distribution Generalization Metrics (Provisional Weight: 20 Points).

Evaluates zero-shot transfer performance to unseen catchments (Test B) relative to
familiar-catchment temporal holdouts (Test A / Reference).
Computes macro-average by catchment, regional performance, and regional dispersion.
Explicitly reports missing region metadata without fabricating regions.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from hydraforge.metrics.forecast_skill import evaluate_forecast_skill

PROVISIONAL_WEIGHT_GENERALIZATION = 20.0


def evaluate_generalization(
    test_b_records: Sequence[Dict[str, Any]],
    ref_records: Optional[Sequence[Dict[str, Any]]] = None,
    catchment_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    max_points: float = PROVISIONAL_WEIGHT_GENERALIZATION
) -> Dict[str, Any]:
    """Evaluate out-of-distribution generalization on unseen catchments (Test B).

    test_b_records: records where catchment identities were excluded from training.
    ref_records: reference records (e.g. Test A temporal holdout) to compute transfer gap.
    catchment_metadata: mapping of catchment_id -> {'region': Optional[str], ...}
    """
    all_warnings: List[str] = []

    if not test_b_records:
        return {
            "dimension": "generalization",
            "points_awarded": 0.0,
            "max_points": max_points,
            "weight": max_points,
            "normalized_score": 0.0,
            "is_provisional": True,
            "warnings": ["No Test B (unseen catchment) records provided for generalization evaluation."],
            "test_b_summary": {},
            "regional_breakdown": {},
            "transfer_gap": {}
        }

    # Evaluate raw forecast skill on Test B
    eval_b = evaluate_forecast_skill(test_b_records, max_points=25.0)
    all_warnings.extend([f"Test B: {w}" for w in eval_b.get("warnings", [])])

    test_b_norm_skill = eval_b["normalized_score"]  # [0.0, 1.0]
    test_b_catchments = eval_b.get("per_catchment", {})

    # 1. Regional Breakdown & Dispersion
    if catchment_metadata is None:
        catchment_metadata = {}

    regional_scores: Dict[str, List[float]] = {}
    missing_region_catchments: List[str] = []

    for cid, c_data in test_b_catchments.items():
        meta = catchment_metadata.get(cid, {})
        region = meta.get("region")
        skill_pts = c_data["skill_points"]
        if region and str(region).strip():
            region_name = str(region).strip()
            regional_scores.setdefault(region_name, []).append(skill_pts)
        else:
            missing_region_catchments.append(cid)

    if missing_region_catchments:
        all_warnings.append(
            f"Region metadata missing for {len(missing_region_catchments)} Test B catchments: "
            f"{missing_region_catchments[:5]}{'...' if len(missing_region_catchments) > 5 else ''}. "
            "Dispersion calculation excludes catchments without documented regions."
        )

    regional_summary: Dict[str, Any] = {}
    region_means: List[float] = []

    for rname, scores in regional_scores.items():
        r_mean = float(np.mean(scores))
        region_means.append(r_mean)
        regional_summary[rname] = {
            "mean_skill": round(r_mean, 4),
            "n_catchments": len(scores)
        }

    # Dispersion across regions (standard deviation of regional means)
    if len(region_means) >= 2:
        dispersion_std = float(np.std(region_means))
        # Dispersion penalty factor: lower dispersion is rewarded (uniform generalization)
        dispersion_penalty = min(0.20, dispersion_std / 25.0)
    else:
        dispersion_std = None
        dispersion_penalty = 0.0
        if len(region_means) == 1:
            all_warnings.append("Only 1 region represented in Test B; regional dispersion cannot be assessed.")
        elif not region_means:
            all_warnings.append("No region metadata available across Test B catchments; regional dispersion skipped.")

    # 2. Transfer Gap relative to Reference Split (Test A or Val)
    retention_ratio = 1.0
    transfer_gap_info: Dict[str, Any] = {}

    if ref_records:
        eval_ref = evaluate_forecast_skill(ref_records, max_points=25.0)
        ref_norm_skill = eval_ref["normalized_score"]
        if ref_norm_skill > 1e-4:
            # Retention = Skill(Test B) / Skill(Ref)
            retention_ratio = min(1.0, max(0.0, test_b_norm_skill / ref_norm_skill))
        else:
            all_warnings.append("Reference split skill was near zero; retention ratio defaulted to 1.0.")
            retention_ratio = 1.0

        transfer_gap_info = {
            "reference_normalized_skill": round(ref_norm_skill, 4),
            "test_b_normalized_skill": round(test_b_norm_skill, 4),
            "retention_ratio": round(retention_ratio, 4)
        }
    else:
        all_warnings.append("No reference split provided; transfer degradation computed solely on Test B.")
        transfer_gap_info = {
            "reference_normalized_skill": None,
            "test_b_normalized_skill": round(test_b_norm_skill, 4),
            "retention_ratio": 1.0
        }

    # 3. Overall Generalization Score Calculation (Provisional 20 points)
    # Combines Test B skill, retention ratio, and low regional dispersion
    base_factor = test_b_norm_skill * (0.80 + 0.20 * retention_ratio)
    effective_factor = max(0.0, base_factor - dispersion_penalty)

    points_awarded = min(max_points, max(0.0, effective_factor * max_points))
    normalized_score = points_awarded / max_points if max_points > 0 else 0.0

    return {
        "dimension": "generalization",
        "points_awarded": round(points_awarded, 4),
        "max_points": max_points,
        "weight": max_points,
        "normalized_score": round(normalized_score, 4),
        "is_provisional": True,
        "warnings": all_warnings,
        "test_b_summary": {
            "macro_skill_points": eval_b["macro_avg"].get("mean_skill_points", 0.0),
            "n_catchments": eval_b["macro_avg"].get("n_catchments", 0),
            "pooled_mae": eval_b["pooled"].get("mae"),
            "pooled_rmse": eval_b["pooled"].get("rmse"),
            "pooled_nse": eval_b["pooled"].get("nse_model"),
        },
        "regional_breakdown": {
            "regions": regional_summary,
            "regional_std": round(dispersion_std, 4) if dispersion_std is not None else None,
            "dispersion_penalty": round(dispersion_penalty, 4)
        },
        "transfer_gap": transfer_gap_info
    }

