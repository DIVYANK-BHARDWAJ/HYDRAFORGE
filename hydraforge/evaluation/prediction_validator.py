"""
hydraforge/evaluation/prediction_validator.py
Strict Prediction Validation Engine for the BASINSHIFT Hydrological Challenge.
Verifies conformity to the Phase 5A inference contract and Phase 1 schemas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from hydraforge.schema import BenchmarkInputRecord, PredictionRecord


@dataclass
class PredictionValidationReport:
    """Detailed diagnostic validation audit of model predictions."""
    is_valid: bool
    total_expected: int
    total_received: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    missing_count: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_expected": self.total_expected,
            "total_received": self.total_received,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "duplicate_count": self.duplicate_count,
            "missing_count": self.missing_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": dict(self.details),
        }


class PredictionValidator:
    """
    Authoritative validator enforcing the inference contract on participant predictions.
    Rejects malformed, incomplete, or physically impossible predictions.
    """

    def validate(
        self,
        predictions: Sequence[Any],
        benchmark_cases: Sequence[BenchmarkInputRecord],
    ) -> PredictionValidationReport:
        """
        Execute exhaustive validation against benchmark cases.
        Args:
            predictions: Raw or parsed prediction objects / dicts.
            benchmark_cases: The expected benchmark cases provided to the model.
        Returns:
            PredictionValidationReport with complete error diagnostics.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Map expected (case_id, horizon) targets
        expected_targets: Dict[Tuple[str, int], BenchmarkInputRecord] = {}
        for case in benchmark_cases:
            for h in case.horizons:
                expected_targets[(str(case.case_id), int(h))] = case

        total_expected = len(expected_targets)
        total_received = len(predictions)

        # 2. Track seen keys for duplicate detection
        seen_keys: Set[Tuple[str, int]] = set()
        duplicate_count = 0
        invalid_count = 0
        valid_records: List[PredictionRecord] = []

        for idx, item in enumerate(predictions):
            item_errors: List[str] = []

            # Dict to record conversion if needed
            if isinstance(item, dict):
                # Required field check
                required_fields = [
                    "case_id",
                    "catchment_id",
                    "forecast_origin",
                    "horizon",
                    "predicted_discharge",
                    "high_flow_probability",
                    "extreme_flow_probability",
                    "prediction_interval_lower",
                    "prediction_interval_upper",
                ]
                for rf in required_fields:
                    if rf not in item or item[rf] is None:
                        item_errors.append(f"Record #{idx} missing required field '{rf}'.")

                if item_errors:
                    errors.extend(item_errors)
                    invalid_count += 1
                    continue

                case_id = str(item.get("case_id", ""))
                catchment_id = str(item.get("catchment_id", ""))
                forecast_origin = str(item.get("forecast_origin", ""))
                horizon = item.get("horizon")
                predicted_discharge = item.get("predicted_discharge")
                high_flow_prob = item.get("high_flow_probability")
                extreme_flow_prob = item.get("extreme_flow_probability")
                interval_lower = item.get("prediction_interval_lower")
                interval_upper = item.get("prediction_interval_upper")
                nominal_cov = item.get("nominal_interval_coverage", 0.90)
            elif isinstance(item, PredictionRecord):
                case_id = str(item.case_id)
                catchment_id = str(item.catchment_id)
                forecast_origin = str(item.forecast_origin)
                horizon = item.horizon
                predicted_discharge = item.predicted_discharge
                high_flow_prob = item.high_flow_probability
                extreme_flow_prob = item.extreme_flow_probability
                interval_lower = item.prediction_interval_lower
                interval_upper = item.prediction_interval_upper
                nominal_cov = item.nominal_interval_coverage
            else:
                errors.append(f"Record #{idx} is neither a dict nor PredictionRecord: {type(item)}")
                invalid_count += 1
                continue

            # Horizon validation
            try:
                horizon_int = int(horizon)
            except (ValueError, TypeError):
                errors.append(f"Record #{idx} ({case_id}): horizon '{horizon}' is not a valid integer.")
                invalid_count += 1
                continue

            key = (case_id, horizon_int)

            # Duplicate check
            if key in seen_keys:
                duplicate_count += 1
                errors.append(f"Duplicate prediction detected for (case_id={case_id}, horizon={horizon_int}).")
                invalid_count += 1
                continue
            seen_keys.add(key)

            # Case alignment check
            if key not in expected_targets:
                errors.append(
                    f"Unexpected prediction (case_id={case_id}, horizon={horizon_int}) not in benchmark cases."
                )
                invalid_count += 1
                continue

            expected_case = expected_targets[key]

            # Catchment ID match check
            if catchment_id != str(expected_case.catchment_id):
                item_errors.append(
                    f"Catchment ID mismatch for case {case_id}: expected '{expected_case.catchment_id}', "
                    f"got '{catchment_id}'."
                )

            # Forecast origin match check
            # Standardize Z to +00:00 for comparison
            c_orig = expected_case.forecast_origin.replace("Z", "+00:00")
            p_orig = forecast_origin.replace("Z", "+00:00")
            if c_orig != p_orig:
                item_errors.append(
                    f"Forecast origin mismatch for case {case_id}: expected '{expected_case.forecast_origin}', "
                    f"got '{forecast_origin}'."
                )

            # Numeric validity (types, NaN, Inf)
            numeric_fields = {
                "predicted_discharge": predicted_discharge,
                "high_flow_probability": high_flow_prob,
                "extreme_flow_probability": extreme_flow_prob,
                "prediction_interval_lower": interval_lower,
                "prediction_interval_upper": interval_upper,
            }
            if nominal_cov is not None:
                numeric_fields["nominal_interval_coverage"] = nominal_cov

            for name, val in numeric_fields.items():
                if not isinstance(val, (int, float)):
                    item_errors.append(f"Field '{name}' in case {case_id} is not numeric: {type(val)} ({val})")
                elif math.isnan(val) or math.isinf(val):
                    item_errors.append(f"Field '{name}' in case {case_id} contains invalid numeric value: {val}")

            # Value domain constraints
            if isinstance(predicted_discharge, (int, float)) and not math.isnan(predicted_discharge):
                if predicted_discharge < 0.0:
                    item_errors.append(
                        f"predicted_discharge must be non-negative: got {predicted_discharge} for case {case_id}."
                    )

            if isinstance(high_flow_prob, (int, float)) and not math.isnan(high_flow_prob):
                if not (0.0 <= high_flow_prob <= 1.0):
                    item_errors.append(
                        f"high_flow_probability must be in [0, 1]: got {high_flow_prob} for case {case_id}."
                    )

            if isinstance(extreme_flow_prob, (int, float)) and not math.isnan(extreme_flow_prob):
                if not (0.0 <= extreme_flow_prob <= 1.0):
                    item_errors.append(
                        f"extreme_flow_probability must be in [0, 1]: got {extreme_flow_prob} for case {case_id}."
                    )

            # Quantile probability ordering: extreme threshold >= high threshold,
            # so P(extreme) <= P(high)
            if (
                isinstance(high_flow_prob, (int, float))
                and isinstance(extreme_flow_prob, (int, float))
                and not math.isnan(high_flow_prob)
                and not math.isnan(extreme_flow_prob)
            ):
                if extreme_flow_prob > high_flow_prob + 1e-6:
                    item_errors.append(
                        f"Quantile probability inversion for case {case_id}: extreme_flow_probability ({extreme_flow_prob:.4f}) "
                        f"exceeds high_flow_probability ({high_flow_prob:.4f})."
                    )

            # Prediction interval ordering: lower <= upper
            if (
                isinstance(interval_lower, (int, float))
                and isinstance(interval_upper, (int, float))
                and not math.isnan(interval_lower)
                and not math.isnan(interval_upper)
            ):
                if interval_lower > interval_upper:
                    item_errors.append(
                        f"Uncertainty interval inversion for case {case_id}: prediction_interval_lower ({interval_lower}) "
                        f"> prediction_interval_upper ({interval_upper})."
                    )
                if interval_lower < 0.0:
                    warnings.append(
                        f"Warning: Negative prediction_interval_lower ({interval_lower}) for streamflow in case {case_id}."
                    )

            if nominal_cov is not None and isinstance(nominal_cov, (int, float)) and not math.isnan(nominal_cov):
                if not (0.0 < nominal_cov < 1.0):
                    item_errors.append(
                        f"nominal_interval_coverage must be in (0, 1): got {nominal_cov} for case {case_id}."
                    )

            if item_errors:
                errors.extend(item_errors)
                invalid_count += 1
            else:
                valid_records.append(
                    PredictionRecord(
                        case_id=case_id,
                        catchment_id=catchment_id,
                        forecast_origin=forecast_origin,
                        horizon=horizon_int,
                        predicted_discharge=float(predicted_discharge),
                        high_flow_probability=float(high_flow_prob),
                        extreme_flow_probability=float(extreme_flow_prob),
                        prediction_interval_lower=float(interval_lower),
                        prediction_interval_upper=float(interval_upper),
                        nominal_interval_coverage=float(nominal_cov) if nominal_cov is not None else 0.90,
                    )
                )

        # 3. Missing prediction check
        missing_keys = set(expected_targets.keys()) - seen_keys
        missing_count = len(missing_keys)
        if missing_count > 0:
            sample_missing = list(missing_keys)[:5]
            errors.append(
                f"Missing {missing_count} required benchmark predictions out of {total_expected} expected. "
                f"Examples: {sample_missing}"
            )

        is_valid = (len(errors) == 0 and missing_count == 0 and duplicate_count == 0)

        return PredictionValidationReport(
            is_valid=is_valid,
            total_expected=total_expected,
            total_received=total_received,
            valid_count=len(valid_records),
            invalid_count=invalid_count,
            duplicate_count=duplicate_count,
            missing_count=missing_count,
            errors=errors,
            warnings=warnings,
            details={
                "valid_record_count": len(valid_records),
                "expected_targets_count": total_expected,
            },
        )

