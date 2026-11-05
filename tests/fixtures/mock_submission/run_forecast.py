"""Developer-only mock forecasting model entrypoint (TRUSTED_TEST_ONLY).

Reads inputs.json and writes valid predictions.json conforming to the v1.0.0 schema.
"""

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Hydro Predictor")
    parser.add_argument("--inputs", required=True, help="Path to inputs.json")
    parser.add_argument("--outputs", required=True, help="Path to predictions.json")
    args = parser.parse_args()

    with open(args.inputs, "r", encoding="utf-8") as f:
        inputs_data = json.load(f)

    predictions = []
    for item in inputs_data:
        case_id = item["case_id"]
        catchment_id = item["catchment_id"]
        origin = item["forecast_origin"]
        horizons = item["horizons"]
        disc_hist = item.get("discharge_history", [])

        # Base discharge forecast from history or fallback
        if disc_hist and len(disc_hist) > 0:
            base_q = float(disc_hist[-1])
        else:
            base_q = 12.0

        for h in horizons:
            # Predict slight trend variation
            pred_q = max(0.1, base_q * (1.0 + 0.02 * (h - 1)))
            predictions.append({
                "case_id": case_id,
                "catchment_id": catchment_id,
                "forecast_origin": origin,
                "horizon": h,
                "predicted_discharge": round(pred_q, 3),
                "high_flow_probability": 0.15,
                "extreme_flow_probability": 0.02,
                "prediction_interval_lower": round(max(0.0, pred_q * 0.8), 3),
                "prediction_interval_upper": round(pred_q * 1.25, 3),
                "nominal_interval_coverage": 0.90
            })

    with open(args.outputs, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)


if __name__ == "__main__":
    main()

