"""Unit tests for HYDRAFORGE deterministic metric engine and master aggregator."""

import math
import numpy as np
import pytest

from hydraforge.schema import (
    BenchmarkInputRecord,
    GroundTruthLabel,
    PredictionRecord,
)
from hydraforge.metrics.forecast_skill import (
    calculate_mae,
    calculate_rmse,
    calculate_nse,
    calculate_persistence_relative_skill,
    evaluate_forecast_skill,
)
from hydraforge.metrics.event_detection import (
    calculate_brier_score,
    calculate_confusion_metrics,
    calculate_auprc,
    evaluate_event_detection,
)
from hydraforge.metrics.generalization import evaluate_generalization
from hydraforge.metrics.calibration import (
    evaluate_calibration,
    evaluate_prediction_intervals,
)
from hydraforge.metrics.robustness import evaluate_robustness
from hydraforge.metrics.efficiency import evaluate_efficiency
from hydraforge.metrics.evaluator import HydraForgeEvaluator, EvaluationConfig


# ============================================================================
# 1. FORECAST SKILL TESTS
# ============================================================================

def test_forecast_skill_perfect_predictions():
    y_true = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    y_pred = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    y_persist = np.array([10.0, 10.0, 10.0, 10.0, 10.0])

    assert calculate_mae(y_true, y_pred) == 0.0
    assert calculate_rmse(y_true, y_pred) == 0.0
    nse_m, w_m = calculate_nse(y_true, y_pred)
    assert nse_m == 1.0
    assert w_m is None

    nse_p, _ = calculate_nse(y_true, y_persist)
    skill, warnings = calculate_persistence_relative_skill(nse_m, nse_p, max_points=25.0)
    assert skill == 25.0
    assert len(warnings) == 0


def test_forecast_skill_persistence_equivalent():
    y_true = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    y_persist = np.array([10.0, 12.0, 22.0, 32.0, 42.0])
    # Model predictions equal persistence
    y_pred = y_persist.copy()

    nse_m, _ = calculate_nse(y_true, y_pred)
    nse_p, _ = calculate_nse(y_true, y_persist)
    skill, warnings = calculate_persistence_relative_skill(nse_m, nse_p, max_points=25.0)
    assert skill == 0.0


def test_forecast_skill_worse_than_persistence():
    y_true = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    y_persist = np.array([12.0, 18.0, 28.0, 38.0, 48.0])
    # Model predictions much worse
    y_pred = np.array([0.0, 100.0, 0.0, 100.0, 0.0])

    nse_m, _ = calculate_nse(y_true, y_pred)
    nse_p, _ = calculate_nse(y_true, y_persist)
    skill, warnings = calculate_persistence_relative_skill(nse_m, nse_p, max_points=25.0)
    # Must be bounded at 0.0, never negative
    assert skill == 0.0
    assert not math.isnan(skill)


def test_forecast_skill_constant_target_series():
    # Target series with zero variance
    y_true = np.array([15.0, 15.0, 15.0, 15.0])
    y_pred_exact = np.array([15.0, 15.0, 15.0, 15.0])
    nse_exact, w_exact = calculate_nse(y_true, y_pred_exact)
    assert nse_exact == 1.0
    assert "Constant target series detected" in w_exact

    y_pred_diff = np.array([10.0, 20.0, 15.0, 15.0])
    nse_diff, w_diff = calculate_nse(y_true, y_pred_diff)
    assert nse_diff is None
    assert "NSE is mathematically undefined" in w_diff

    # Relative skill should handle None safely without error
    skill, warnings = calculate_persistence_relative_skill(nse_diff, nse_exact)
    assert skill == 0.0
    assert len(warnings) > 0


def test_forecast_skill_near_zero_denominator():
    # Persistence NSE is effectively 1.0
    skill_perfect_model, w1 = calculate_persistence_relative_skill(1.0, 1.0, max_points=25.0)
    assert skill_perfect_model == 25.0
    assert any("near-zero error" in w for w in w1)

    skill_imperfect_model, w2 = calculate_persistence_relative_skill(0.8, 1.0, max_points=25.0)
    assert skill_imperfect_model == 0.0


# ============================================================================
# 2. EVENT DETECTION TESTS
# ============================================================================

def test_event_detection_perfect_probabilities():
    records = [
        {"y_true": 5.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.0, "extreme_flow_prob": 0.0},
        {"y_true": 10.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.0, "extreme_flow_prob": 0.0},
        {"y_true": 25.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 1.0, "extreme_flow_prob": 0.0},
        {"y_true": 35.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 1.0, "extreme_flow_prob": 1.0},
    ]
    res = evaluate_event_detection(records, max_points=25.0)
    assert res["points_awarded"] == 25.0
    assert res["high_flow_q95"]["f1"] == 1.0
    assert res["high_flow_q95"]["brier_score"] == 0.0
    assert res["extreme_flow_q99"]["f1"] == 1.0
    assert res["extreme_flow_q99"]["brier_score"] == 0.0


def test_event_detection_completely_wrong_probabilities():
    records = [
        {"y_true": 5.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 1.0, "extreme_flow_prob": 1.0},
        {"y_true": 10.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 1.0, "extreme_flow_prob": 1.0},
        {"y_true": 25.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.0, "extreme_flow_prob": 1.0},
        {"y_true": 35.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.0, "extreme_flow_prob": 0.0},
    ]
    res = evaluate_event_detection(records, max_points=25.0)
    assert res["points_awarded"] == 0.0
    assert res["high_flow_q95"]["f1"] == 0.0
    assert res["high_flow_q95"]["brier_score"] == 1.0


def test_event_detection_zero_event_prevalence():
    # No high flow or extreme flow events occur
    records = [
        {"y_true": 5.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.0, "extreme_flow_prob": 0.0},
        {"y_true": 8.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.05, "extreme_flow_prob": 0.0},
        {"y_true": 12.0, "high_flow_threshold": 20.0, "extreme_flow_threshold": 30.0, "high_flow_prob": 0.02, "extreme_flow_prob": 0.0},
    ]
    res = evaluate_event_detection(records, max_points=25.0)
    assert not res["high_flow_q95"]["has_positive_events"]
    assert res["high_flow_q95"]["recall"] is None
    # Model predicted near zero probabilities, so Brier skill is high
    assert res["high_flow_q95"]["brier_skill"] > 0.95
    assert res["points_awarded"] > 0.0  # Does not crash; rewarded for calibration


# ============================================================================
# 3. GENERALIZATION TESTS
# ============================================================================

def test_generalization_evaluation():
    test_b = [
        {"catchment_id": "C_UNSEEN_1", "y_true": 10.0, "y_pred": 10.2, "y_persist": 8.0},
        {"catchment_id": "C_UNSEEN_1", "y_true": 20.0, "y_pred": 19.8, "y_persist": 10.0},
        {"catchment_id": "C_UNSEEN_2", "y_true": 30.0, "y_pred": 30.5, "y_persist": 15.0},
        {"catchment_id": "C_UNSEEN_2", "y_true": 40.0, "y_pred": 39.5, "y_persist": 20.0},
    ]
    ref_records = [
        {"catchment_id": "C_TRAIN_1", "y_true": 10.0, "y_pred": 10.0, "y_persist": 5.0},
        {"catchment_id": "C_TRAIN_1", "y_true": 20.0, "y_pred": 20.0, "y_persist": 10.0},
    ]
    meta = {
        "C_UNSEEN_1": {"region": "Alps"},
        "C_UNSEEN_2": {"region": "Rockies"},
    }

    res = evaluate_generalization(test_b, ref_records=ref_records, catchment_metadata=meta, max_points=20.0)
    assert res["points_awarded"] > 15.0
    assert "Alps" in res["regional_breakdown"]["regions"]
    assert "Rockies" in res["regional_breakdown"]["regions"]
    assert res["regional_breakdown"]["regional_std"] is not None


def test_generalization_missing_region_metadata():
    test_b = [
        {"catchment_id": "C_UNSEEN_1", "y_true": 10.0, "y_pred": 10.2, "y_persist": 8.0},
        {"catchment_id": "C_UNSEEN_1", "y_true": 20.0, "y_pred": 19.8, "y_persist": 10.0},
    ]
    # No region in metadata
    meta = {"C_UNSEEN_1": {}}
    res = evaluate_generalization(test_b, catchment_metadata=meta, max_points=20.0)
    assert any("Region metadata missing" in w for w in res["warnings"])
    assert res["regional_breakdown"]["regional_std"] is None


# ============================================================================
# 4. CALIBRATION & UNCERTAINTY TESTS
# ============================================================================

def test_calibration_perfect_intervals():
    # 10 records with 9 hits and 1 miss -> 90% empirical coverage
    y_true = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 100.0])
    lower = np.array([8.0] * 10)
    upper = np.array([12.0] * 10)

    summary, warnings = evaluate_prediction_intervals(y_true, lower, upper, nominal_coverage=0.90)
    assert summary["empirical_coverage"] == 0.90
    assert summary["coverage_error"] == 0.0
    assert summary["coverage_score_ratio"] == 1.0
    assert summary["invalid_interval_count"] == 0


def test_calibration_invalid_intervals():
    # Lower > upper
    y_true = np.array([10.0, 20.0])
    lower = np.array([15.0, 25.0])
    upper = np.array([10.0, 20.0])  # Inverted

    summary, warnings = evaluate_prediction_intervals(y_true, lower, upper, nominal_coverage=0.90)
    assert summary["invalid_interval_count"] == 2
    assert summary["empirical_coverage"] == 0.0
    assert any("invalid or inverted" in w for w in warnings)


# ============================================================================
# 5. ROBUSTNESS TESTS (PAIRED CLEAN / CORRUPTED)
# ============================================================================

def test_robustness_paired_evaluation():
    clean = [
        {"case_id": "c1", "horizon": 1, "y_true": 10.0, "y_pred": 10.0},
        {"case_id": "c2", "horizon": 1, "y_true": 20.0, "y_pred": 20.0},
    ]
    corrupt = [
        {"case_id": "c1_noisy", "clean_case_id": "c1", "horizon": 1, "corruption_family": "input_noise", "y_true": 10.0, "y_pred": 10.1},
        {"case_id": "c2_noisy", "clean_case_id": "c2", "horizon": 1, "corruption_family": "input_noise", "y_true": 20.0, "y_pred": 20.1},
    ]
    res = evaluate_robustness(clean, corrupt, max_points=10.0)
    assert res["points_awarded"] > 5.0
    assert "input_noise" in res["corruption_families"]
    assert res["paired_sample_count"] == 2


def test_robustness_unpaired_cases_skipped():
    clean = [{"case_id": "c1", "horizon": 1, "y_true": 10.0, "y_pred": 10.0}]
    corrupt = [{"case_id": "c99", "clean_case_id": "c_NONEXISTENT", "horizon": 1, "y_true": 10.0, "y_pred": 10.0}]
    res = evaluate_robustness(clean, corrupt, max_points=10.0)
    assert res["points_awarded"] == 0.0
    assert res["paired_sample_count"] == 0
    assert any("Skipped 1 corrupted records" in w for w in res["warnings"])


# ============================================================================
# 6. EFFICIENCY TESTS
# ============================================================================

def test_efficiency_full_measurements():
    res = evaluate_efficiency(
        runtime_seconds=30.0,
        peak_memory_mb=512.0,
        artifact_size_mb=50.0,
        prediction_count=1000,
        max_points=5.0
    )
    assert res["points_awarded"] == 5.0
    assert res["breakdown"]["ms_per_prediction"] == 30.0


def test_efficiency_missing_measurements():
    # Explicitly verify None is not treated as 0.0
    res = evaluate_efficiency(
        runtime_seconds=None,
        peak_memory_mb=None,
        artifact_size_mb=None,
        max_points=5.0
    )
    assert res["points_awarded"] == 0.0
    assert len(res["warnings"]) == 3
    assert any("Runtime measurement is unavailable" in w for w in res["warnings"])


# ============================================================================
# 7. MASTER EVALUATOR INTEGRATION TESTS
# ============================================================================

def test_master_evaluator_complete_flow():
    evaluator = HydraForgeEvaluator()

    gt = [
        GroundTruthLabel("case_1", "B1", "2026-01-01T00:00:00Z", 1, 15.0, 20.0, 30.0, 10.0, split="test_a"),
        GroundTruthLabel("case_2", "B1", "2026-01-01T00:00:00Z", 3, 25.0, 20.0, 30.0, 15.0, split="test_a"),
        GroundTruthLabel("case_3", "B_UNSEEN", "2026-01-01T00:00:00Z", 1, 12.0, 18.0, 25.0, 10.0, split="test_b", region="North"),
    ]

    preds = [
        PredictionRecord("case_1", "B1", "2026-01-01T00:00:00Z", 1, 15.0, 0.1, 0.01, 12.0, 18.0),
        PredictionRecord("case_2", "B1", "2026-01-01T00:00:00Z", 3, 24.5, 0.8, 0.1, 20.0, 28.0),
        PredictionRecord("case_3", "B_UNSEEN", "2026-01-01T00:00:00Z", 1, 12.2, 0.1, 0.01, 10.0, 15.0),
    ]

    meta = {"B_UNSEEN": {"region": "North"}}
    stats = {"runtime_seconds": 12.0, "peak_memory_mb": 450.0, "artifact_size_mb": 25.0}

    result = evaluator.evaluate(preds, gt, catchment_metadata=meta, execution_stats=stats, submission_id="test_sub")
    assert result.is_valid
    assert 0.0 <= result.total_score <= 100.0
    assert result.audit_hash is not None
    assert len(result.audit_hash) == 64  # SHA-256
    assert "forecast_skill" in result.dimensions
    assert "event_detection" in result.dimensions
    assert "generalization" in result.dimensions
    assert "calibration_and_uncertainty" in result.dimensions
    assert "robustness" in result.dimensions
    assert "efficiency" in result.dimensions


def test_master_evaluator_empty_splits():
    evaluator = HydraForgeEvaluator()
    # Ground truth with only Test A, no Test B and no Test C
    gt = [
        GroundTruthLabel("case_1", "B1", "2026-01-01T00:00:00Z", 1, 15.0, 20.0, 30.0, 10.0, split="test_a"),
    ]
    preds = [
        PredictionRecord("case_1", "B1", "2026-01-01T00:00:00Z", 1, 15.0, 0.1, 0.01, 12.0, 18.0),
    ]

    result = evaluator.evaluate(preds, gt, submission_id="empty_splits_sub")
    assert result.is_valid
    assert result.split_breakdown["test_b_count"] == 0
    assert result.split_breakdown["test_c_count"] == 0
    # Must report warnings for empty Test B and Test C without crashing
    assert any("No Test B" in w for w in result.warnings)
    assert any("No corrupted (Test C)" in w for w in result.warnings)


def test_extreme_discharge_values():
    y_true = np.array([1e5, 2e5, 3e5, 4e5])
    y_pred = np.array([1.01e5, 1.99e5, 3.01e5, 3.99e5])
    y_persist = np.array([0.9e5, 1.8e5, 2.7e5, 3.6e5])

    nse_m, _ = calculate_nse(y_true, y_pred)
    nse_p, _ = calculate_nse(y_true, y_persist)
    assert nse_m is not None and nse_m > 0.99
    skill, _ = calculate_persistence_relative_skill(nse_m, nse_p)
    assert skill > 20.0

