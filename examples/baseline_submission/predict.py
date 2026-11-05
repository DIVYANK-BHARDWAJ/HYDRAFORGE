"""
BASINSHIFT Reference Submission — Hydrological Baseline Forecaster.
This script demonstrates an eligible participant model implementation.
It accepts standardized benchmark inputs and produces valid probabilistic hydrological predictions.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List


def generate_forecast(input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Generate 7-day discharge forecast from historical hydrology and weather forcings.
    """
    history = input_data.get("historical_data", [])
    forcings = input_data.get("meteorological_forecast", [])

    # Recent discharge baseline (last known discharge or conservative default)
    last_q = 10.0
    if history:
        last_q = float(history[-1].get("discharge_m3_s", 10.0))

    predictions = []
    current_q = max(0.1, last_q)

    for item in forcings:
        lead_day = int(item.get("lead_day", 1))
        forecast_ts = item.get("forecast_timestamp", "")
        precip = float(item.get("precipitation_mm", 0.0))
        temp = float(item.get("temperature_c", 10.0))
        pet = float(item.get("pet_mm", 1.0))

        # Simple hydrological balance response
        runoff_contrib = precip * 0.45
        evap_loss = pet * 0.15
        current_q = max(0.01, (current_q * 0.85) + runoff_contrib - evap_loss)

        # Quantile estimates
        q50 = round(current_q, 3)
        q10 = round(max(0.01, current_q * 0.75), 3)
        q90 = round(current_q * 1.35, 3)

        # Exceedance probabilities
        prob_q95 = min(1.0, max(0.0, round((precip / 40.0) * 0.6, 4)))
        prob_q99 = min(1.0, max(0.0, round((precip / 60.0) * 0.3, 4)))

        pred_record = {
            "forecast_timestamp": forecast_ts,
            "lead_day": lead_day,
            "predicted_discharge_m3_s": q50,
            "quantile_10": q10,
            "quantile_50": q50,
            "quantile_90": q90,
            "prob_exceed_q95": prob_q95,
            "prob_exceed_q99": prob_q99,
        }
        predictions.append(pred_record)

    return predictions


def main():
    parser = argparse.ArgumentParser(description="BASINSHIFT Hydrological Baseline Predictor")
    parser.add_argument("--input", "-i", type=str, help="Path to input benchmark JSON file")
    parser.add_argument("--output", "-o", type=str, help="Path to output prediction JSON file")
    args = parser.parse_args()

    # Read input data
    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            input_data = json.load(f)
    else:
        # Read from stdin
        input_data = json.load(sys.stdin)

    predictions = generate_forecast(input_data)
    output_payload = {
        "contract_version": "1.0.0",
        "predictions": predictions,
    }

    # Write output data
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_payload, f, indent=2)
        print(f"Predictions written to {args.output}")
    else:
        print(json.dumps(output_payload, indent=2))


if __name__ == "__main__":
    main()
