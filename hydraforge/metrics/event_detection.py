"""High-Flow and Extreme-Flow Event Detection Metrics (Provisional Weight: 25 Points).

Evaluates binary classification and probabilistic exceedance forecasting for:
- Q95 high-flow events (provisional: 15.0 points)
- Q99 extreme high-flow events (provisional: 10.0 points)

Handles extreme class imbalance, zero positive events, and precision-recall edge cases.
All thresholds MUST be supplied by benchmark metadata; never estimated from test labels.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

PROVISIONAL_WEIGHT_EVENT_DETECTION = 25.0
PROVISIONAL_WEIGHT_Q95 = 15.0
PROVISIONAL_WEIGHT_Q99 = 10.0


def calculate_brier_score(y_true_binary: np.ndarray, y_prob: np.ndarray) -> float:
    """Mean squared error of probability forecasts against binary outcomes."""
    if len(y_true_binary) == 0:
        return 0.0
    return float(np.mean((y_prob - y_true_binary) ** 2))


def calculate_confusion_metrics(
    y_true_binary: np.ndarray,
    y_prob: np.ndarray,
    alert_threshold: float = 0.50
) -> Dict[str, Any]:
    """Compute precision, recall, and F1 at a specified alert probability threshold."""
    if len(y_true_binary) == 0:
        return {
            "tp": 0, "fp": 0, "fn": 0, "tn": 0,
            "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "has_positive_events": False,
            "prevalence": 0.0
        }

    y_pred_binary = (y_prob >= alert_threshold).astype(int)
    y_true_int = y_true_binary.astype(int)

    tp = int(np.sum((y_pred_binary == 1) & (y_true_int == 1)))
    fp = int(np.sum((y_pred_binary == 1) & (y_true_int == 0)))
    fn = int(np.sum((y_pred_binary == 0) & (y_true_int == 1)))
    tn = int(np.sum((y_pred_binary == 0) & (y_true_int == 0)))

    total_positives = tp + fn
    has_positive = total_positives > 0
    prevalence = float(total_positives / len(y_true_binary))

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / total_positives) if has_positive else None
    
    if recall is not None and (precision + recall) > 0:
        f1 = float(2.0 * precision * recall / (precision + recall))
    else:
        f1 = 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4),
        "has_positive_events": has_positive,
        "prevalence": round(prevalence, 4),
        "alert_threshold": alert_threshold
    }


def calculate_auprc(
    y_true_binary: np.ndarray,
    y_prob: np.ndarray
) -> Tuple[Optional[float], Optional[str]]:
    """Compute Area Under Precision-Recall Curve (AUPRC) via trapezoidal integration.

    Returns (auprc, warning_or_none).
    AUPRC is undefined when there are no positive events or no negative events.
    """
    n_positives = int(np.sum(y_true_binary == 1))
    n_samples = len(y_true_binary)

    if n_samples == 0:
        return None, "Empty array for AUPRC calculation."
    if n_positives == 0:
        return None, "AUPRC undefined: zero positive events in evaluation slice."
    if n_positives == n_samples:
        return 1.0, "All events are positive in evaluation slice; AUPRC=1.0 by definition."

    # Sort by predicted probability descending
    desc_indices = np.argsort(-y_prob)
    sorted_y = y_true_binary[desc_indices]
    
    # Cumulative True Positives and False Positives
    tps = np.cumsum(sorted_y)
    fps = np.cumsum(1 - sorted_y)

    recalls = tps / n_positives
    precisions = tps / (tps + fps)

    # Prepend boundary: at recall 0, precision is typically precision of first prediction
    recalls = np.concatenate(([0.0], recalls))
    precisions = np.concatenate(([precisions[0]], precisions))

    # Integrate area using trapezoidal rule (monotonic recalls)
    # Using np.trapezoid (NumPy >= 2.0 compatible)
    if hasattr(np, "trapezoid"):
        area = float(np.trapezoid(precisions, recalls))
    else:
        area = float(np.trapz(precisions, recalls))

    auprc = max(0.0, min(1.0, area))
    return round(auprc, 4), None


def evaluate_event_level(
    y_true_binary: np.ndarray,
    y_prob: np.ndarray,
    max_points: float,
    event_label: str
) -> Tuple[float, Dict[str, Any], List[str]]:
    """Score a single event level (Q95 or Q99) out of max_points.

    Provisional rubric:
    - 60% weight from discriminative skill (F1 and AUPRC where defined).
    - 40% weight from probabilistic calibration (Brier skill = 1.0 - Brier Score).
    """
    warnings: List[str] = []
    brier = calculate_brier_score(y_true_binary, y_prob)
    conf = calculate_confusion_metrics(y_true_binary, y_prob)
    auprc, auprc_warn = calculate_auprc(y_true_binary, y_prob)
    if auprc_warn:
        warnings.append(f"{event_label}: {auprc_warn}")

    brier_skill = max(0.0, 1.0 - brier)

    if conf["has_positive_events"]:
        prevalence = conf["prevalence"]
        # Baseline-normalized AUPRC skill: AUPRC at or below prevalence indicates no skill
        if auprc is not None and prevalence < 1.0:
            if auprc <= prevalence:
                norm_auprc = 0.0
            else:
                norm_auprc = (auprc - prevalence) / (1.0 - prevalence)
        else:
            norm_auprc = conf["f1"]

        # If zero true positives (F1 == 0), discriminative skill is zero
        if conf["f1"] == 0.0:
            discrim_metric = 0.0
        else:
            discrim_metric = (norm_auprc + conf["f1"]) / 2.0

        # Balanced score: 60% discriminative, 40% probabilistic
        combined_ratio = (0.60 * discrim_metric) + (0.40 * brier_skill)
    else:
        # Zero positive events in this evaluation period: evaluate purely on Brier calibration
        warnings.append(f"{event_label}: Zero actual positive events; scoring exclusively on probability calibration (Brier skill).")
        combined_ratio = brier_skill

    points = max(0.0, min(max_points, combined_ratio * max_points))

    summary = {
        "event_label": event_label,
        "max_points": max_points,
        "points_awarded": round(points, 4),
        "brier_score": round(brier, 4),
        "brier_skill": round(brier_skill, 4),
        "auprc": auprc,
        "f1": conf["f1"],
        "precision": conf["precision"],
        "recall": conf["recall"],
        "tp": conf["tp"],
        "fp": conf["fp"],
        "fn": conf["fn"],
        "tn": conf["tn"],
        "prevalence": conf["prevalence"],
        "has_positive_events": conf["has_positive_events"]
    }
    return points, summary, warnings


def evaluate_event_detection(
    records: Sequence[Dict[str, Any]],
    max_points: float = PROVISIONAL_WEIGHT_EVENT_DETECTION
) -> Dict[str, Any]:
    """Evaluate event detection across high-flow (Q95) and extreme-flow (Q99) tiers.

    Each record must have:
        'y_true': float
        'high_flow_threshold': float (from benchmark metadata)
        'extreme_flow_threshold': float (from benchmark metadata)
        'high_flow_prob': float
        'extreme_flow_prob': float
    """
    if not records:
        return {
            "dimension": "event_detection",
            "points_awarded": 0.0,
            "max_points": max_points,
            "weight": max_points,
            "normalized_score": 0.0,
            "is_provisional": True,
            "warnings": ["No records provided for event detection evaluation."],
            "high_flow_q95": {},
            "extreme_flow_q99": {}
        }

    all_warnings: List[str] = []

    y_true = np.array([r["y_true"] for r in records], dtype=np.float64)
    th_high = np.array([r["high_flow_threshold"] for r in records], dtype=np.float64)
    th_ext = np.array([r["extreme_flow_threshold"] for r in records], dtype=np.float64)
    p_high = np.array([r["high_flow_prob"] for r in records], dtype=np.float64)
    p_ext = np.array([r["extreme_flow_prob"] for r in records], dtype=np.float64)

    # Binary indicators from official benchmark metadata thresholds
    true_high = (y_true >= th_high).astype(int)
    true_ext = (y_true >= th_ext).astype(int)

    # Evaluate Q95
    pts_q95, res_q95, w_q95 = evaluate_event_level(
        true_high, p_high, max_points=PROVISIONAL_WEIGHT_Q95, event_label="High-Flow (Q95)"
    )
    all_warnings.extend(w_q95)

    # Evaluate Q99
    pts_q99, res_q99, w_q99 = evaluate_event_level(
        true_ext, p_ext, max_points=PROVISIONAL_WEIGHT_Q99, event_label="Extreme-Flow (Q99)"
    )
    all_warnings.extend(w_q99)

    total_points = min(max_points, pts_q95 + pts_q99)
    normalized = total_points / max_points if max_points > 0 else 0.0

    return {
        "dimension": "event_detection",
        "points_awarded": round(total_points, 4),
        "max_points": max_points,
        "weight": max_points,
        "normalized_score": round(normalized, 4),
        "is_provisional": True,
        "warnings": all_warnings,
        "high_flow_q95": res_q95,
        "extreme_flow_q99": res_q99
    }
