"""Forecast Skill Evaluation Metric (Provisional Weight: 25 Points).

Calculates MAE, RMSE, Nash-Sutcliffe Efficiency (NSE), and persistence-relative skill.
Handles constant target series and zero-denominator singularities gracefully.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

PROVISIONAL_WEIGHT_FORECAST_SKILL = 25.0


def calculate_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error."""
    if len(y_true) == 0:
        return 0.0
    return float(np.mean(np.abs(y_true - y_pred)))


def calculate_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error."""
    if len(y_true) == 0:
        return 0.0
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def calculate_nse(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    variance_eps: float = 1e-12
) -> Tuple[Optional[float], Optional[str]]:
    """Nash-Sutcliffe Efficiency with explicit constant-target detection.

    Returns:
        (nse_value, warning_message)
        If true target is constant (SS_tot < variance_eps), returns (None, warning).
    """
    if len(y_true) == 0:
        return 0.0, "Empty series provided to NSE calculation"

    mean_obs = np.mean(y_true)
    ss_tot = np.sum((y_true - mean_obs) ** 2)
    ss_res = np.sum((y_true - y_pred) ** 2)

    if ss_tot < variance_eps:
        # Constant target series: variance is zero
        if ss_res < variance_eps:
            return 1.0, "Constant target series detected; predictions match constant exactly (assigned NSE=1.0)"
        return None, "Constant target series detected (variance near zero); NSE is mathematically undefined"

    nse = 1.0 - (ss_res / ss_tot)
    if math.isnan(nse) or math.isinf(nse):
        return None, "Non-finite NSE encountered"
    return float(nse), None


def calculate_persistence_relative_skill(
    nse_model: Optional[float],
    nse_persist: Optional[float],
    max_points: float = PROVISIONAL_WEIGHT_FORECAST_SKILL,
    eps: float = 1e-6
) -> Tuple[float, List[str]]:
    """Compute persistence-relative skill using the provisional formula:

        max(0, (NSE_model - NSE_persistence) / (1 - NSE_persistence)) * max_points

    Guarantees:
    - Never returns NaN or infinity.
    - Always bounded in [0.0, max_points].
    - Explicitly reports and handles denominator near zero.
    """
    warnings: List[str] = []

    if nse_model is None or nse_persist is None:
        warnings.append("NSE was undefined for model or persistence baseline; awarded 0.0 forecast skill points.")
        return 0.0, warnings

    denominator = 1.0 - nse_persist

    if abs(denominator) < eps:
        # Persistence has effectively 0 error (perfect persistence)
        warnings.append("Persistence baseline has near-zero error (denominator in skill formula near zero).")
        if nse_model >= 1.0 - eps:
            return float(max_points), warnings
        return 0.0, warnings

    if denominator < 0:
        warnings.append(f"Anomalous persistence denominator ({denominator:.4f}); persistence NSE > 1.0.")
        return 0.0, warnings

    numerator = nse_model - nse_persist
    raw_ratio = numerator / denominator

    # Bounded in [0.0, 1.0] then scaled to max_points
    skill_score = max(0.0, min(1.0, raw_ratio)) * max_points
    return float(skill_score), warnings


def evaluate_forecast_skill(
    records: Sequence[Dict[str, Any]],
    max_points: float = PROVISIONAL_WEIGHT_FORECAST_SKILL
) -> Dict[str, Any]:
    """Evaluate forecast skill across a set of paired evaluation records.

    Each record must have:
        'catchment_id': str
        'y_true': float
        'y_pred': float
        'y_persist': float

    Returns detailed diagnostic dictionary including per-catchment and macro-averages.
    """
    if not records:
        return {
            "dimension": "forecast_skill",
            "points_awarded": 0.0,
            "max_points": max_points,
            "weight": max_points,
            "normalized_score": 0.0,
            "is_provisional": True,
            "warnings": ["No records provided for forecast skill evaluation."],
            "per_catchment": {},
            "macro_avg": {},
            "pooled": {}
        }

    # Group by catchment
    by_catchment: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        cid = r["catchment_id"]
        by_catchment.setdefault(cid, []).append(r)

    catchment_results: Dict[str, Dict[str, Any]] = {}
    catchment_skills: List[float] = []
    all_warnings: List[str] = []

    all_y_true = []
    all_y_pred = []
    all_y_persist = []

    for cid, items in by_catchment.items():
        y_true = np.array([x["y_true"] for x in items], dtype=np.float64)
        y_pred = np.array([x["y_pred"] for x in items], dtype=np.float64)
        y_persist = np.array([x["y_persist"] for x in items], dtype=np.float64)

        all_y_true.extend(y_true)
        all_y_pred.extend(y_pred)
        all_y_persist.extend(y_persist)

        mae = calculate_mae(y_true, y_pred)
        rmse = calculate_rmse(y_true, y_pred)
        nse_model, w_model = calculate_nse(y_true, y_pred)
        nse_persist, w_persist = calculate_nse(y_true, y_persist)

        if w_model:
            all_warnings.append(f"Catchment {cid} model: {w_model}")
        if w_persist:
            all_warnings.append(f"Catchment {cid} persistence: {w_persist}")

        c_skill, w_skill = calculate_persistence_relative_skill(nse_model, nse_persist, max_points)
        all_warnings.extend([f"Catchment {cid}: {w}" for w in w_skill])

        catchment_skills.append(c_skill)
        catchment_results[cid] = {
            "n_samples": len(y_true),
            "mae": mae,
            "rmse": rmse,
            "nse_model": nse_model,
            "nse_persist": nse_persist,
            "skill_points": c_skill,
        }

    # Macro-average across catchments
    macro_skill = float(np.mean(catchment_skills)) if catchment_skills else 0.0

    # Pooled metrics across all records
    arr_true = np.array(all_y_true, dtype=np.float64)
    arr_pred = np.array(all_y_pred, dtype=np.float64)
    arr_persist = np.array(all_y_persist, dtype=np.float64)

    pooled_mae = calculate_mae(arr_true, arr_pred)
    pooled_rmse = calculate_rmse(arr_true, arr_pred)
    pooled_nse, _ = calculate_nse(arr_true, arr_pred)
    pooled_persist_nse, _ = calculate_nse(arr_true, arr_persist)

    normalized_score = macro_skill / max_points if max_points > 0 else 0.0

    return {
        "dimension": "forecast_skill",
        "points_awarded": round(macro_skill, 4),
        "max_points": max_points,
        "weight": max_points,
        "normalized_score": round(normalized_score, 4),
        "is_provisional": True,
        "warnings": all_warnings,
        "macro_avg": {
            "mean_skill_points": round(macro_skill, 4),
            "median_skill_points": round(float(np.median(catchment_skills)), 4) if catchment_skills else 0.0,
            "n_catchments": len(by_catchment)
        },
        "pooled": {
            "mae": round(pooled_mae, 4),
            "rmse": round(pooled_rmse, 4),
            "nse_model": round(pooled_nse, 4) if pooled_nse is not None else None,
            "nse_persist": round(pooled_persist_nse, 4) if pooled_persist_nse is not None else None,
            "total_samples": len(arr_true)
        },
        "per_catchment": catchment_results
    }

