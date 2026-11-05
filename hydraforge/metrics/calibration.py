"""Calibration and Uncertainty Evaluation Metrics (Provisional Weight: 15 Points).

Evaluates:
- Probability calibration via Brier score for high-flow and extreme-flow exceedance.
- Empirical prediction interval coverage against configured nominal target (default: 90%).
- Interval sharpness (mean and normalized interval width).
- Robust handling of missing, inverted, or degenerate intervals.

NOTE: CRPS is deliberately not claimed here because the official contract specifies
prediction intervals and threshold probabilities rather than full parametric distributions.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

PROVISIONAL_WEIGHT_CALIBRATION = 15.0
PROVISIONAL_WEIGHT_PROB_CALIBRATION = 7.5
PROVISIONAL_WEIGHT_INTERVAL_CALIBRATION = 7.5
DEFAULT_NOMINAL_COVERAGE = 0.90


def evaluate_prediction_intervals(
    y_true: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    nominal_coverage: float = DEFAULT_NOMINAL_COVERAGE
) -> Tuple[Dict[str, Any], List[str]]:
    """Evaluate empirical coverage and sharpness of prediction intervals.

    Handles:
    - Inverted intervals (lower > upper)
    - Non-finite interval bounds
    - Degenerate zero-width intervals
    """
    warnings: List[str] = []
    n = len(y_true)
    if n == 0:
        return {
            "empirical_coverage": 0.0,
            "nominal_coverage": nominal_coverage,
            "coverage_error": 1.0,
            "mean_interval_width": 0.0,
            "normalized_interval_width": 0.0,
            "invalid_interval_count": 0,
            "coverage_score_ratio": 0.0,
            "sharpness_ratio": 0.0
        }, ["Empty records for interval evaluation."]

    valid_mask = np.isfinite(lower) & np.isfinite(upper) & (lower <= upper)
    invalid_count = int(np.sum(~valid_mask))

    if invalid_count > 0:
        warnings.append(
            f"Detected {invalid_count} / {n} invalid or inverted prediction intervals (lower > upper or non-finite)."
        )

    # For valid intervals, check hit: lower <= y_true <= upper
    # Invalid intervals are automatically counted as non-coverage hits
    hits = np.zeros(n, dtype=bool)
    widths = np.zeros(n, dtype=np.float64)

    if np.any(valid_mask):
        hits[valid_mask] = (y_true[valid_mask] >= lower[valid_mask]) & (y_true[valid_mask] <= upper[valid_mask])
        widths[valid_mask] = upper[valid_mask] - lower[valid_mask]

    empirical_coverage = float(np.mean(hits))
    coverage_error = abs(empirical_coverage - nominal_coverage)
    mean_width = float(np.mean(widths))

    mean_obs = float(np.mean(y_true)) if np.mean(y_true) > 1e-6 else 1.0
    normalized_width = mean_width / mean_obs

    # Coverage score: penalize deviation from nominal coverage
    # Perfect coverage = 1.0; error >= 0.50 -> 0.0
    coverage_score_ratio = max(0.0, 1.0 - (2.0 * coverage_error))

    # Sharpness factor: prevent gaming coverage with absurdly wide intervals
    # If normalized width is <= 1.5x mean discharge, no penalty; otherwise gradual decay
    if normalized_width <= 1.5:
        sharpness_ratio = 1.0
    else:
        sharpness_ratio = max(0.10, math.exp(-(normalized_width - 1.5) / 3.0))

    # Also penalize directly for invalid interval count proportion
    valid_ratio = float((n - invalid_count) / n)
    effective_interval_quality = coverage_score_ratio * sharpness_ratio * valid_ratio

    result = {
        "empirical_coverage": round(empirical_coverage, 4),
        "nominal_coverage": round(nominal_coverage, 4),
        "coverage_error": round(coverage_error, 4),
        "mean_interval_width": round(mean_width, 4),
        "normalized_interval_width": round(normalized_width, 4),
        "invalid_interval_count": invalid_count,
        "coverage_score_ratio": round(coverage_score_ratio, 4),
        "sharpness_ratio": round(sharpness_ratio, 4),
        "effective_interval_quality": round(effective_interval_quality, 4)
    }
    return result, warnings


def evaluate_calibration(
    records: Sequence[Dict[str, Any]],
    nominal_coverage: float = DEFAULT_NOMINAL_COVERAGE,
    max_points: float = PROVISIONAL_WEIGHT_CALIBRATION
) -> Dict[str, Any]:
    """Evaluate full calibration & uncertainty dimension (provisional 15 points).

    Combines:
    - 7.5 pts: Probability calibration (Q95 and Q99 Brier skill)
    - 7.5 pts: Prediction interval empirical coverage and sharpness
    """
    if not records:
        return {
            "dimension": "calibration_and_uncertainty",
            "points_awarded": 0.0,
            "max_points": max_points,
            "weight": max_points,
            "normalized_score": 0.0,
            "is_provisional": True,
            "warnings": ["No records provided for calibration evaluation."],
            "probability_calibration": {},
            "interval_calibration": {}
        }

    all_warnings: List[str] = []

    y_true = np.array([r["y_true"] for r in records], dtype=np.float64)
    p_high = np.array([r["high_flow_prob"] for r in records], dtype=np.float64)
    p_ext = np.array([r["extreme_flow_prob"] for r in records], dtype=np.float64)
    th_high = np.array([r["high_flow_threshold"] for r in records], dtype=np.float64)
    th_ext = np.array([r["extreme_flow_threshold"] for r in records], dtype=np.float64)

    lower = np.array([r["interval_lower"] for r in records], dtype=np.float64)
    upper = np.array([r["interval_upper"] for r in records], dtype=np.float64)

    # 1. Probability Calibration (Brier Score)
    high_events = (y_true >= th_high).astype(int)
    ext_events = (y_true >= th_ext).astype(int)

    brier_high = float(np.mean((p_high - high_events) ** 2))
    brier_ext = float(np.mean((p_ext - ext_events) ** 2))
    mean_brier = (brier_high + brier_ext) / 2.0

    brier_skill = max(0.0, 1.0 - mean_brier)
    prob_points = brier_skill * PROVISIONAL_WEIGHT_PROB_CALIBRATION

    prob_summary = {
        "brier_high_flow": round(brier_high, 4),
        "brier_extreme_flow": round(brier_ext, 4),
        "mean_brier_score": round(mean_brier, 4),
        "brier_skill": round(brier_skill, 4),
        "points_awarded": round(prob_points, 4),
        "max_points": PROVISIONAL_WEIGHT_PROB_CALIBRATION
    }

    # 2. Interval Calibration
    interval_summary, int_warnings = evaluate_prediction_intervals(
        y_true, lower, upper, nominal_coverage=nominal_coverage
    )
    all_warnings.extend(int_warnings)

    interval_points = interval_summary["effective_interval_quality"] * PROVISIONAL_WEIGHT_INTERVAL_CALIBRATION
    interval_summary["points_awarded"] = round(interval_points, 4)
    interval_summary["max_points"] = PROVISIONAL_WEIGHT_INTERVAL_CALIBRATION

    # Combined Calibration Points (max 15.0)
    total_points = min(max_points, max(0.0, prob_points + interval_points))
    normalized_score = total_points / max_points if max_points > 0 else 0.0

    return {
        "dimension": "calibration_and_uncertainty",
        "points_awarded": round(total_points, 4),
        "max_points": max_points,
        "weight": max_points,
        "normalized_score": round(normalized_score, 4),
        "is_provisional": True,
        "warnings": all_warnings,
        "probability_calibration": prob_summary,
        "interval_calibration": interval_summary,
        "methodology_note": "CRPS not computed; evaluates proper Brier score and empirical interval coverage."
    }

