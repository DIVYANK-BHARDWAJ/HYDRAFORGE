"""
scripts/validate_submission.py
Participant-Facing Prediction File Validator.
Validates submission prediction JSON against all HYDRAFORGE schema,
finite number, non-negativity, quantile-ordering, and probability constraints.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def validate_prediction_payload(data: Any) -> Tuple[bool, List[str]]:
    """Validate prediction data dictionary against the HYDRAFORGE contract."""
    errors: List[str] = []

    if not isinstance(data, dict):
        return False, ["Payload must be a JSON object with top-level 'predictions' list."]

    version = data.get("contract_version")
    if not version:
        errors.append("Missing required field 'contract_version'. Expected '1.0.0'.")

    predictions = data.get("predictions")
    if not isinstance(predictions, list) or len(predictions) == 0:
        return False, ["Field 'predictions' must be a non-empty list of forecast records."]

    required_keys = {
        "forecast_timestamp",
        "lead_day",
        "predicted_discharge_m3_s",
        "quantile_10",
        "quantile_50",
        "quantile_90",
        "prob_exceed_q95",
        "prob_exceed_q99",
    }

    seen_days = set()

    for idx, p in enumerate(predictions):
        prefix = f"Prediction [{idx}]"
        if not isinstance(p, dict):
            errors.append(f"{prefix}: Must be a dictionary.")
            continue

        missing = required_keys - set(p.keys())
        if missing:
            errors.append(f"{prefix}: Missing required fields: {', '.join(sorted(missing))}")
            continue

        # Lead day check
        ld = p.get("lead_day")
        if not isinstance(ld, int) or ld < 1 or ld > 14:
            errors.append(f"{prefix}: 'lead_day' must be an integer between 1 and 14, got {ld}.")
        elif ld in seen_days:
            errors.append(f"{prefix}: Duplicate 'lead_day' {ld} found.")
        else:
            seen_days.add(ld)

        # Numeric and finite checks
        for key in ["predicted_discharge_m3_s", "quantile_10", "quantile_50", "quantile_90", "prob_exceed_q95", "prob_exceed_q99"]:
            val = p.get(key)
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                errors.append(f"{prefix}: '{key}' must be a finite number, got {val}.")

        # Non-negative discharge
        q_pred = p.get("predicted_discharge_m3_s", 0)
        if isinstance(q_pred, (int, float)) and q_pred < 0:
            errors.append(f"{prefix}: 'predicted_discharge_m3_s' cannot be negative ({q_pred}).")

        # Quantile ordering
        q10 = p.get("quantile_10", 0)
        q50 = p.get("quantile_50", 0)
        q90 = p.get("quantile_90", 0)
        if isinstance(q10, (int, float)) and isinstance(q50, (int, float)) and isinstance(q90, (int, float)):
            if q10 < 0 or q50 < 0 or q90 < 0:
                errors.append(f"{prefix}: Quantile values cannot be negative.")
            if not (q10 <= q50 <= q90):
                errors.append(
                    f"{prefix}: Invalid quantile ordering: q10 ({q10}) <= q50 ({q50}) <= q90 ({q90}) violated."
                )

        # Exceedance probabilities
        p95 = p.get("prob_exceed_q95", 0)
        p99 = p.get("prob_exceed_q99", 0)
        if isinstance(p95, (int, float)):
            if not (0.0 <= p95 <= 1.0):
                errors.append(f"{prefix}: 'prob_exceed_q95' must be in [0.0, 1.0], got {p95}.")
        if isinstance(p99, (int, float)):
            if not (0.0 <= p99 <= 1.0):
                errors.append(f"{prefix}: 'prob_exceed_q99' must be in [0.0, 1.0], got {p99}.")

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description="Validate HYDRAFORGE prediction JSON file.")
    parser.add_argument("file", type=str, help="Path to predictions JSON file")
    args = parser.parse_args()

    target = Path(args.file)
    if not target.exists():
        print(f"Error: File '{target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)

    valid, errors = validate_prediction_payload(data)
    if valid:
        num_preds = len(data.get("predictions", []))
        print(f"SUCCESS: '{target.name}' is valid according to HYDRAFORGE Contract v1.0.0.")
        print(f"Checked {num_preds} forecast lead-days with all bounds, orderings, and probabilities verified.")
        sys.exit(0)
    else:
        print(f"VALIDATION FAILED: Found {len(errors)} error(s) in '{target.name}':", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
