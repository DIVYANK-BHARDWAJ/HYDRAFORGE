"""Unit tests for HYDRAFORGE submission schemas and validation rules."""

import math
import pytest
from hydraforge.schema import (
    CONTRACT_VERSION,
    BenchmarkInputRecord,
    ContractConfig,
    PredictionRecord,
    SubmissionManifest,
    ValidationError,
    validate_prediction_record,
    validate_predictions,
)


def test_submission_manifest_valid():
    manifest = SubmissionManifest(
        team_name="HydroAI Labs",
        submission_name="DeepBasin-v1",
        repository_url="https://github.com/example/hydro-ai",
        commit_sha="a" * 40,
    )
    manifest.validate()  # Should not raise


def test_submission_manifest_invalid():
    with pytest.raises(ValidationError, match="team_name cannot be empty"):
        SubmissionManifest(team_name="", submission_name="Test").validate()

    with pytest.raises(ValidationError, match="submission_name cannot be empty"):
        SubmissionManifest(team_name="Team", submission_name="   ").validate()

    with pytest.raises(ValidationError, match="Unsupported contract_version"):
        SubmissionManifest(
            team_name="Team", submission_name="Test", contract_version="0.9.0"
        ).validate()


def test_prediction_record_valid():
    rec = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=15.5,
        high_flow_probability=0.25,
        extreme_flow_probability=0.05,
        prediction_interval_lower=10.0,
        prediction_interval_upper=22.0,
        nominal_interval_coverage=0.90,
    )
    config = ContractConfig()
    validate_prediction_record(rec, config)
    d = rec.to_dict()
    roundtrip = PredictionRecord.from_dict(d)
    assert roundtrip.case_id == "case_001"
    assert roundtrip.predicted_discharge == 15.5


def test_prediction_record_negative_discharge():
    rec = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=-0.5,
        high_flow_probability=0.2,
        extreme_flow_probability=0.01,
        prediction_interval_lower=0.0,
        prediction_interval_upper=10.0,
    )
    with pytest.raises(ValidationError, match="predicted_discharge must be >= 0.0"):
        validate_prediction_record(rec, ContractConfig())


def test_prediction_record_invalid_probabilities():
    config = ContractConfig()
    # High flow prob > 1.0
    rec_high = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=10.0,
        high_flow_probability=1.05,
        extreme_flow_probability=0.05,
        prediction_interval_lower=5.0,
        prediction_interval_upper=15.0,
    )
    with pytest.raises(ValidationError, match="high_flow_probability must be in"):
        validate_prediction_record(rec_high, config)

    # Extreme flow prob < 0.0
    rec_neg = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=10.0,
        high_flow_probability=0.5,
        extreme_flow_probability=-0.01,
        prediction_interval_lower=5.0,
        prediction_interval_upper=15.0,
    )
    with pytest.raises(ValidationError, match="extreme_flow_probability must be in"):
        validate_prediction_record(rec_neg, config)


def test_prediction_record_invalid_intervals():
    config = ContractConfig()
    # Lower > upper
    rec = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=10.0,
        high_flow_probability=0.1,
        extreme_flow_probability=0.01,
        prediction_interval_lower=20.0,
        prediction_interval_upper=10.0,
    )
    with pytest.raises(ValidationError, match="prediction_interval_lower .* cannot exceed"):
        validate_prediction_record(rec, config)

    # Negative lower bound
    rec_neg_lower = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=10.0,
        high_flow_probability=0.1,
        extreme_flow_probability=0.01,
        prediction_interval_lower=-1.0,
        prediction_interval_upper=10.0,
    )
    with pytest.raises(ValidationError, match="prediction_interval_lower must be >= 0.0"):
        validate_prediction_record(rec_neg_lower, config)


def test_prediction_record_nan_and_infinity():
    config = ContractConfig()
    rec_nan = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=float("nan"),
        high_flow_probability=0.1,
        extreme_flow_probability=0.01,
        prediction_interval_lower=0.0,
        prediction_interval_upper=10.0,
    )
    with pytest.raises(ValidationError, match="must be finite"):
        validate_prediction_record(rec_nan, config)

    rec_inf = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=1,
        predicted_discharge=float("inf"),
        high_flow_probability=0.1,
        extreme_flow_probability=0.01,
        prediction_interval_lower=0.0,
        prediction_interval_upper=10.0,
    )
    with pytest.raises(ValidationError, match="must be finite"):
        validate_prediction_record(rec_inf, config)


def test_prediction_record_unsupported_horizon():
    config = ContractConfig(supported_horizons=(1, 3, 7))
    rec = PredictionRecord(
        case_id="case_001",
        catchment_id="BASIN_101",
        forecast_origin="2026-01-01T00:00:00Z",
        horizon=2,  # Horizon 2 is not in (1, 3, 7)
        predicted_discharge=10.0,
        high_flow_probability=0.1,
        extreme_flow_probability=0.01,
        prediction_interval_lower=5.0,
        prediction_interval_upper=15.0,
    )
    with pytest.raises(ValidationError, match="Unsupported horizon 2"):
        validate_prediction_record(rec, config)


def test_validate_predictions_collection():
    config = ContractConfig(supported_horizons=(1, 3))
    benchmark_cases = [
        BenchmarkInputRecord(
            case_id="c1", catchment_id="B1", forecast_origin="2026-01-01T00:00:00Z", horizons=[1, 3]
        ),
        BenchmarkInputRecord(
            case_id="c2", catchment_id="B1", forecast_origin="2026-01-02T00:00:00Z", horizons=[1, 3]
        ),
    ]

    # Valid collection
    preds = [
        PredictionRecord("c1", "B1", "2026-01-01T00:00:00Z", 1, 10.0, 0.1, 0.01, 5.0, 15.0),
        PredictionRecord("c1", "B1", "2026-01-01T00:00:00Z", 3, 12.0, 0.2, 0.02, 6.0, 18.0),
        PredictionRecord("c2", "B1", "2026-01-02T00:00:00Z", 1, 11.0, 0.1, 0.01, 5.5, 16.0),
        PredictionRecord("c2", "B1", "2026-01-02T00:00:00Z", 3, 13.0, 0.2, 0.02, 6.5, 19.0),
    ]
    validate_predictions(preds, benchmark_cases, config)  # Should pass

    # Unknown case ID
    preds_unknown = preds + [
        PredictionRecord("c_UNKNOWN", "B1", "2026-01-01T00:00:00Z", 1, 10.0, 0.1, 0.01, 5.0, 15.0)
    ]
    with pytest.raises(ValidationError, match="Unknown evaluation case_id 'c_UNKNOWN'"):
        validate_predictions(preds_unknown, benchmark_cases, config)

    # Duplicate prediction
    preds_duplicate = preds + [
        PredictionRecord("c1", "B1", "2026-01-01T00:00:00Z", 1, 9.0, 0.1, 0.01, 5.0, 15.0)
    ]
    with pytest.raises(ValidationError, match="Duplicate prediction submitted"):
        validate_predictions(preds_duplicate, benchmark_cases, config)

    # Missing prediction
    preds_missing = preds[:-1]  # drop c2:h3
    with pytest.raises(ValidationError, match="Missing required predictions"):
        validate_predictions(preds_missing, benchmark_cases, config)

