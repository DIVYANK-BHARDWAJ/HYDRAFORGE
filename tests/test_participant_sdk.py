"""
tests/test_participant_sdk.py
Tests for Participant Reference Submission and Prediction Validator.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.validate_submission import validate_prediction_payload
from examples.baseline_submission.predict import generate_forecast


def test_baseline_predict_produces_contract_compliant_output():
    sample_input_path = Path("examples/sample_inputs.json")
    assert sample_input_path.exists()

    with open(sample_input_path, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    preds = generate_forecast(input_data)
    assert len(preds) == 7

    payload = {
        "contract_version": "1.0.0",
        "predictions": preds,
    }

    valid, errors = validate_prediction_payload(payload)
    assert valid, f"Validation errors: {errors}"
    assert len(errors) == 0


def test_validator_detects_all_contract_violations():
    # 1. Negative discharge
    bad_q = {
        "contract_version": "1.0.0",
        "predictions": [{
            "forecast_timestamp": "2024-01-08T00:00:00Z",
            "lead_day": 1,
            "predicted_discharge_m3_s": -2.0,
            "quantile_10": 1.0,
            "quantile_50": 2.0,
            "quantile_90": 3.0,
            "prob_exceed_q95": 0.1,
            "prob_exceed_q99": 0.05
        }]
    }
    v1, errs1 = validate_prediction_payload(bad_q)
    assert not v1
    assert any("cannot be negative" in e for e in errs1)

    # 2. Inverted quantiles
    bad_quantiles = {
        "contract_version": "1.0.0",
        "predictions": [{
            "forecast_timestamp": "2024-01-08T00:00:00Z",
            "lead_day": 1,
            "predicted_discharge_m3_s": 5.0,
            "quantile_10": 10.0,
            "quantile_50": 5.0,
            "quantile_90": 2.0,
            "prob_exceed_q95": 0.1,
            "prob_exceed_q99": 0.05
        }]
    }
    v2, errs2 = validate_prediction_payload(bad_quantiles)
    assert not v2
    assert any("Invalid quantile ordering" in e for e in errs2)

    # 3. Probability > 1.0
    bad_prob = {
        "contract_version": "1.0.0",
        "predictions": [{
            "forecast_timestamp": "2024-01-08T00:00:00Z",
            "lead_day": 1,
            "predicted_discharge_m3_s": 5.0,
            "quantile_10": 2.0,
            "quantile_50": 5.0,
            "quantile_90": 8.0,
            "prob_exceed_q95": 1.5,
            "prob_exceed_q99": 0.05
        }]
    }
    v3, errs3 = validate_prediction_payload(bad_prob)
    assert not v3
    assert any("prob_exceed_q95" in e for e in errs3)
