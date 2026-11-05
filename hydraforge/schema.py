"""Submission and Evaluation Schemas for HYDRAFORGE / BASINSHIFT.

Provides dataclasses and strict validators for submission manifests,
benchmark cases, participant predictions, ground-truth labels, and score results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

CONTRACT_VERSION = "1.0.0"
DEFAULT_SUPPORTED_HORIZONS: Tuple[int, ...] = (1, 3, 7)
DEFAULT_NOMINAL_COVERAGE = 0.90
MIN_PERMISSIBLE_DISCHARGE = 0.0


class ValidationError(Exception):
    """Raised when a submission violates the contract schema."""
    pass


@dataclass(frozen=True)
class ContractConfig:
    """Central configuration for contract verification."""
    contract_version: str = CONTRACT_VERSION
    supported_horizons: Tuple[int, ...] = DEFAULT_SUPPORTED_HORIZONS
    default_nominal_coverage: float = DEFAULT_NOMINAL_COVERAGE
    min_discharge: float = MIN_PERMISSIBLE_DISCHARGE
    require_intervals: bool = True
    allow_extreme_values_above: float = 1e7  # Sanity upper bound to catch numerical overflows


@dataclass
class SubmissionManifest:
    """Participant submission metadata and provenance declaration."""
    team_name: str
    submission_name: str
    contract_version: str = CONTRACT_VERSION
    repository_url: Optional[str] = None
    commit_sha: Optional[str] = None
    dataset_declarations: Dict[str, Any] = field(default_factory=dict)
    pretrained_models: List[str] = field(default_factory=list)
    entrypoint: str = "run_forecast.py"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def validate(self) -> None:
        if not self.team_name or not self.team_name.strip():
            raise ValidationError("team_name cannot be empty")
        if not self.submission_name or not self.submission_name.strip():
            raise ValidationError("submission_name cannot be empty")
        if self.contract_version != CONTRACT_VERSION:
            raise ValidationError(
                f"Unsupported contract_version '{self.contract_version}'. Expected '{CONTRACT_VERSION}'"
            )


@dataclass
class BenchmarkInputRecord:
    """A single evaluation input presented to participant models."""
    case_id: str
    catchment_id: str
    forecast_origin: str
    horizons: List[int]
    discharge_history: List[float] = field(default_factory=list)
    forcing_history: Dict[str, List[float]] = field(default_factory=dict)
    attributes: Dict[str, float] = field(default_factory=dict)
    split: str = "test_a"  # "train", "val", "test_a", "test_b", "test_c"
    region: Optional[str] = None
    is_corrupted: bool = False
    corruption_family: Optional[str] = None  # e.g., "missing_discharge", "input_noise", "reporting_delay"
    clean_case_id: Optional[str] = None


@dataclass
class GroundTruthLabel:
    """Hidden evaluation target known only to the organizer evaluator."""
    case_id: str
    catchment_id: str
    forecast_origin: str
    horizon: int
    true_discharge: float
    high_flow_threshold: float  # Q95 threshold supplied by benchmark metadata
    extreme_flow_threshold: float  # Q99 threshold supplied by benchmark metadata
    persistence_discharge: Optional[float] = None  # Last known discharge at forecast origin
    split: str = "test_a"
    region: Optional[str] = None
    is_corrupted: bool = False
    corruption_family: Optional[str] = None
    clean_case_id: Optional[str] = None


@dataclass
class PredictionRecord:
    """A single forecast submitted by participant for a specific horizon."""
    case_id: str
    catchment_id: str
    forecast_origin: str
    horizon: int
    predicted_discharge: float
    high_flow_probability: float
    extreme_flow_probability: float
    prediction_interval_lower: float
    prediction_interval_upper: float
    nominal_interval_coverage: float = DEFAULT_NOMINAL_COVERAGE

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PredictionRecord":
        required_fields = {
            "case_id", "catchment_id", "forecast_origin", "horizon",
            "predicted_discharge", "high_flow_probability", "extreme_flow_probability",
            "prediction_interval_lower", "prediction_interval_upper"
        }
        missing = required_fields - set(data.keys())
        if missing:
            raise ValidationError(f"Prediction dictionary is missing required fields: {sorted(missing)}")
        return cls(
            case_id=str(data["case_id"]),
            catchment_id=str(data["catchment_id"]),
            forecast_origin=str(data["forecast_origin"]),
            horizon=int(data["horizon"]),
            predicted_discharge=float(data["predicted_discharge"]),
            high_flow_probability=float(data["high_flow_probability"]),
            extreme_flow_probability=float(data["extreme_flow_probability"]),
            prediction_interval_lower=float(data["prediction_interval_lower"]),
            prediction_interval_upper=float(data["prediction_interval_upper"]),
            nominal_interval_coverage=float(data.get("nominal_interval_coverage", DEFAULT_NOMINAL_COVERAGE)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "catchment_id": self.catchment_id,
            "forecast_origin": self.forecast_origin,
            "horizon": self.horizon,
            "predicted_discharge": self.predicted_discharge,
            "high_flow_probability": self.high_flow_probability,
            "extreme_flow_probability": self.extreme_flow_probability,
            "prediction_interval_lower": self.prediction_interval_lower,
            "prediction_interval_upper": self.prediction_interval_upper,
            "nominal_interval_coverage": self.nominal_interval_coverage,
        }


def validate_prediction_record(record: PredictionRecord, config: ContractConfig) -> None:
    """Validate a single PredictionRecord against numeric and contract bounds."""
    # 1. Identifier checks
    if not record.case_id or not record.case_id.strip():
        raise ValidationError("case_id cannot be empty")
    if not record.catchment_id or not record.catchment_id.strip():
        raise ValidationError(f"catchment_id cannot be empty (case_id: {record.case_id})")
    if not record.forecast_origin or not record.forecast_origin.strip():
        raise ValidationError(f"forecast_origin cannot be empty (case_id: {record.case_id})")

    # 2. Supported horizon check
    if record.horizon not in config.supported_horizons:
        raise ValidationError(
            f"Unsupported horizon {record.horizon} for case_id '{record.case_id}'. "
            f"Supported horizons are: {config.supported_horizons}"
        )

    # 3. Finite number checks
    float_values = {
        "predicted_discharge": record.predicted_discharge,
        "high_flow_probability": record.high_flow_probability,
        "extreme_flow_probability": record.extreme_flow_probability,
        "prediction_interval_lower": record.prediction_interval_lower,
        "prediction_interval_upper": record.prediction_interval_upper,
        "nominal_interval_coverage": record.nominal_interval_coverage,
    }
    for field_name, value in float_values.items():
        if math.isnan(value) or math.isinf(value):
            raise ValidationError(
                f"Field '{field_name}' must be finite, got '{value}' in case_id '{record.case_id}' horizon {record.horizon}"
            )

    # 4. Nonnegative discharge
    if record.predicted_discharge < config.min_discharge:
        raise ValidationError(
            f"predicted_discharge must be >= {config.min_discharge}, got {record.predicted_discharge} "
            f"in case_id '{record.case_id}' horizon {record.horizon}"
        )

    # 5. Probabilities in [0.0, 1.0]
    if not (0.0 <= record.high_flow_probability <= 1.0):
        raise ValidationError(
            f"high_flow_probability must be in [0.0, 1.0], got {record.high_flow_probability} "
            f"in case_id '{record.case_id}' horizon {record.horizon}"
        )
    if not (0.0 <= record.extreme_flow_probability <= 1.0):
        raise ValidationError(
            f"extreme_flow_probability must be in [0.0, 1.0], got {record.extreme_flow_probability} "
            f"in case_id '{record.case_id}' horizon {record.horizon}"
        )

    # 6. Prediction interval sanity
    if config.require_intervals:
        if record.prediction_interval_lower > record.prediction_interval_upper:
            raise ValidationError(
                f"prediction_interval_lower ({record.prediction_interval_lower}) cannot exceed "
                f"prediction_interval_upper ({record.prediction_interval_upper}) in case_id '{record.case_id}' horizon {record.horizon}"
            )
        if record.prediction_interval_lower < config.min_discharge:
            # We enforce non-negative lower bound on river discharge
            raise ValidationError(
                f"prediction_interval_lower must be >= {config.min_discharge}, got {record.prediction_interval_lower} "
                f"in case_id '{record.case_id}' horizon {record.horizon}"
            )

    # 7. Coverage sanity
    if not (0.0 < record.nominal_interval_coverage < 1.0):
        raise ValidationError(
            f"nominal_interval_coverage must be in (0.0, 1.0), got {record.nominal_interval_coverage} "
            f"in case_id '{record.case_id}' horizon {record.horizon}"
        )


def validate_predictions(
    predictions: Sequence[PredictionRecord],
    benchmark_cases: Sequence[BenchmarkInputRecord] | Dict[str, Sequence[int]],
    config: Optional[ContractConfig] = None,
) -> None:
    """Validate full collection of predictions against required evaluation cases.

    Ensures:
    - No unknown evaluation case_ids
    - No duplicate (case_id, horizon) predictions
    - All required evaluation cases and horizons are present (no missing predictions)
    - Every prediction individual satisfies value bounds
    """
    if config is None:
        config = ContractConfig()

    # Build required key map: case_id -> set of required horizons
    required_cases: Dict[str, Set[int]] = {}
    if isinstance(benchmark_cases, dict):
        for cid, hlist in benchmark_cases.items():
            required_cases[cid] = set(hlist)
    else:
        for bcase in benchmark_cases:
            required_cases[bcase.case_id] = set(bcase.horizons)

    seen_pairs: Set[Tuple[str, int]] = set()

    for p in predictions:
        # Validate individual record schema
        validate_prediction_record(p, config)

        # Check for unknown case_id
        if p.case_id not in required_cases:
            raise ValidationError(f"Unknown evaluation case_id '{p.case_id}' submitted")

        # Check if horizon is expected for this case
        if p.horizon not in required_cases[p.case_id]:
            raise ValidationError(
                f"Unexpected horizon {p.horizon} for case_id '{p.case_id}'. Expected: {sorted(required_cases[p.case_id])}"
            )

        # Check duplicate
        pair = (p.case_id, p.horizon)
        if pair in seen_pairs:
            raise ValidationError(f"Duplicate prediction submitted for case_id '{p.case_id}' at horizon {p.horizon}")
        seen_pairs.add(pair)

    # Check for missing predictions
    missing_items: List[str] = []
    for cid, expected_horizons in required_cases.items():
        for h in expected_horizons:
            if (cid, h) not in seen_pairs:
                missing_items.append(f"{cid}:h{h}")
                if len(missing_items) >= 10:
                    break
        if len(missing_items) >= 10:
            break

    if missing_items:
        raise ValidationError(
            f"Missing required predictions ({len(missing_items)} shown): {missing_items}"
        )


@dataclass
class DimensionScore:
    """Evaluation score and diagnostic metrics for one evaluation dimension."""
    dimension_name: str
    weight: float
    points_awarded: float
    max_points: float
    raw_metrics: Dict[str, Any]
    normalized_score: float  # Bounded [0.0, 1.0]
    warnings: List[str] = field(default_factory=list)
    is_provisional: bool = True
    notes: Optional[str] = None


@dataclass
class EvaluationResult:
    """Master evaluation outcome produced by HYDRAFORGE."""
    submission_id: str
    evaluated_at: str
    total_score: float  # Sum of points_awarded out of 100.0
    max_total_score: float = 100.0
    dimensions: Dict[str, DimensionScore] = field(default_factory=dict)
    split_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    catchment_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    execution_stats: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    is_valid: bool = True
    audit_hash: Optional[str] = None

