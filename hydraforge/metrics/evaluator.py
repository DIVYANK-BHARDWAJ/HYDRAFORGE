"""Master Evaluator for HYDRAFORGE / BASINSHIFT.

Integrates the six scoring dimensions:
1. Forecast skill (25 pts)
2. High-flow event detection (25 pts)
3. Out-of-distribution generalization (20 pts)
4. Calibration and uncertainty (15 pts)
5. Robustness (10 pts)
6. Efficiency (5 pts)
Total: 100 Points.

Enforces:
- Standalone baseline-anchored normalization (no relative participant min-max).
- Full auditability, transparent diagnostic warnings, and split-level breakdowns.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from hydraforge.schema import (
    DimensionScore,
    EvaluationResult,
    GroundTruthLabel,
    PredictionRecord,
    ValidationError,
)
from hydraforge.metrics.forecast_skill import evaluate_forecast_skill
from hydraforge.metrics.event_detection import evaluate_event_detection
from hydraforge.metrics.generalization import evaluate_generalization
from hydraforge.metrics.calibration import evaluate_calibration
from hydraforge.metrics.robustness import evaluate_robustness
from hydraforge.metrics.efficiency import evaluate_efficiency


@dataclass
class EvaluationConfig:
    """Master evaluation parameters and provisional weights."""
    weight_forecast_skill: float = 25.0
    weight_event_detection: float = 25.0
    weight_generalization: float = 20.0
    weight_calibration: float = 15.0
    weight_robustness: float = 10.0
    weight_efficiency: float = 5.0
    nominal_coverage: float = 0.90
    version: str = "1.0.0"

    @property
    def total_weight(self) -> float:
        return (
            self.weight_forecast_skill
            + self.weight_event_detection
            + self.weight_generalization
            + self.weight_calibration
            + self.weight_robustness
            + self.weight_efficiency
        )


class HydraForgeEvaluator:
    """Authoritative evaluation engine for participant forecasting submissions."""

    def __init__(self, config: Optional[EvaluationConfig] = None) -> None:
        self.config = config or EvaluationConfig()

    def evaluate(
        self,
        predictions: Sequence[PredictionRecord],
        ground_truth: Sequence[GroundTruthLabel],
        catchment_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        execution_stats: Optional[Dict[str, Any]] = None,
        submission_id: str = "submission"
    ) -> EvaluationResult:
        """Execute full 6-dimension evaluation."""
        eval_time = datetime.now(timezone.utc).isoformat()
        all_warnings: List[str] = []

        # 1. Index predictions by (case_id, horizon)
        pred_map: Dict[Tuple[str, int], PredictionRecord] = {}
        for p in predictions:
            key = (str(p.case_id), int(p.horizon))
            if key in pred_map:
                all_warnings.append(f"Duplicate prediction record ignored: {key}")
            else:
                pred_map[key] = p

        # 2. Pair predictions with ground-truth labels
        paired_records: List[Dict[str, Any]] = []
        missing_count = 0

        for gt in ground_truth:
            key = (str(gt.case_id), int(gt.horizon))
            if key in pred_map:
                pred = pred_map[key]
                # If persistence_discharge is missing from GT, fall back to true_discharge as safe reference
                persist_val = gt.persistence_discharge if gt.persistence_discharge is not None else gt.true_discharge
                paired_records.append({
                    "case_id": gt.case_id,
                    "catchment_id": gt.catchment_id,
                    "forecast_origin": gt.forecast_origin,
                    "horizon": gt.horizon,
                    "split": gt.split,
                    "region": gt.region,
                    "is_corrupted": gt.is_corrupted,
                    "corruption_family": gt.corruption_family,
                    "clean_case_id": gt.clean_case_id,
                    "y_true": gt.true_discharge,
                    "y_pred": pred.predicted_discharge,
                    "y_persist": persist_val,
                    "high_flow_threshold": gt.high_flow_threshold,
                    "extreme_flow_threshold": gt.extreme_flow_threshold,
                    "high_flow_prob": pred.high_flow_probability,
                    "extreme_flow_prob": pred.extreme_flow_probability,
                    "interval_lower": pred.prediction_interval_lower,
                    "interval_upper": pred.prediction_interval_upper,
                    "nominal_coverage": pred.nominal_interval_coverage,
                })
            else:
                missing_count += 1

        if missing_count > 0:
            all_warnings.append(
                f"Missing {missing_count} required predictions out of {len(ground_truth)} target evaluation cases."
            )

        # 3. Partition by Split
        records_test_a = [r for r in paired_records if r["split"] == "test_a" and not r["is_corrupted"]]
        records_test_b = [r for r in paired_records if r["split"] == "test_b" and not r["is_corrupted"]]
        records_test_c = [r for r in paired_records if r["is_corrupted"]]
        records_val = [r for r in paired_records if r["split"] == "val" and not r["is_corrupted"]]

        # Standard uncorrupted evaluation records (Test A + Test B)
        records_standard = records_test_a + records_test_b

        # 4. DIMENSION 1: Forecast Skill (25 pts)
        # Evaluated on Test A temporal holdout (or standard if Test A is empty)
        skill_eval_records = records_test_a if records_test_a else records_standard
        d1_eval = evaluate_forecast_skill(skill_eval_records, max_points=self.config.weight_forecast_skill)
        d1_score = DimensionScore(
            dimension_name="forecast_skill",
            weight=self.config.weight_forecast_skill,
            points_awarded=d1_eval["points_awarded"],
            max_points=d1_eval["max_points"],
            raw_metrics=d1_eval["pooled"],
            normalized_score=d1_eval["normalized_score"],
            warnings=d1_eval["warnings"],
            is_provisional=True,
            notes="Evaluated via persistence-relative NSE on temporal holdouts."
        )

        # 5. DIMENSION 2: Event Detection (25 pts)
        event_eval_records = records_standard if records_standard else paired_records
        d2_eval = evaluate_event_detection(event_eval_records, max_points=self.config.weight_event_detection)
        d2_score = DimensionScore(
            dimension_name="event_detection",
            weight=self.config.weight_event_detection,
            points_awarded=d2_eval["points_awarded"],
            max_points=d2_eval["max_points"],
            raw_metrics={"q95": d2_eval["high_flow_q95"], "q99": d2_eval["extreme_flow_q99"]},
            normalized_score=d2_eval["normalized_score"],
            warnings=d2_eval["warnings"],
            is_provisional=True,
            notes="Evaluated against Q95 high-flow and Q99 extreme-flow thresholds from benchmark metadata."
        )

        # 6. DIMENSION 3: Generalization (20 pts)
        d3_eval = evaluate_generalization(
            test_b_records=records_test_b,
            ref_records=records_test_a if records_test_a else records_val,
            catchment_metadata=catchment_metadata,
            max_points=self.config.weight_generalization
        )
        d3_score = DimensionScore(
            dimension_name="generalization",
            weight=self.config.weight_generalization,
            points_awarded=d3_eval["points_awarded"],
            max_points=d3_eval["max_points"],
            raw_metrics={
                "test_b_summary": d3_eval["test_b_summary"],
                "regional_breakdown": d3_eval["regional_breakdown"],
                "transfer_gap": d3_eval["transfer_gap"]
            },
            normalized_score=d3_eval["normalized_score"],
            warnings=d3_eval["warnings"],
            is_provisional=True,
            notes="Evaluated on Test B unseen catchments with regional dispersion penalty."
        )

        # 7. DIMENSION 4: Calibration and Uncertainty (15 pts)
        d4_eval = evaluate_calibration(
            records=records_standard if records_standard else paired_records,
            nominal_coverage=self.config.nominal_coverage,
            max_points=self.config.weight_calibration
        )
        d4_score = DimensionScore(
            dimension_name="calibration_and_uncertainty",
            weight=self.config.weight_calibration,
            points_awarded=d4_eval["points_awarded"],
            max_points=d4_eval["max_points"],
            raw_metrics={
                "probability_calibration": d4_eval["probability_calibration"],
                "interval_calibration": d4_eval["interval_calibration"]
            },
            normalized_score=d4_eval["normalized_score"],
            warnings=d4_eval["warnings"],
            is_provisional=True,
            notes="Evaluates Brier exceedance scores and empirical interval coverage vs nominal 90%."
        )

        # 8. DIMENSION 5: Robustness (10 pts)
        clean_ref_records = records_test_a if records_test_a else records_standard
        d5_eval = evaluate_robustness(
            clean_records=clean_ref_records,
            corrupt_records=records_test_c,
            max_points=self.config.weight_robustness
        )
        d5_score = DimensionScore(
            dimension_name="robustness",
            weight=self.config.weight_robustness,
            points_awarded=d5_eval["points_awarded"],
            max_points=d5_eval["max_points"],
            raw_metrics={
                "corruption_families": d5_eval["corruption_families"],
                "mean_retention": d5_eval.get("mean_retention", 0.0),
                "paired_sample_count": d5_eval.get("paired_sample_count", 0)
            },
            normalized_score=d5_eval["normalized_score"],
            warnings=d5_eval["warnings"],
            is_provisional=True,
            notes="Measures relative error degradation under controlled input perturbations (Test C)."
        )

        # 9. DIMENSION 6: Efficiency (5 pts)
        stats = execution_stats or {}
        d6_eval = evaluate_efficiency(
            runtime_seconds=stats.get("runtime_seconds"),
            peak_memory_mb=stats.get("peak_memory_mb"),
            artifact_size_mb=stats.get("artifact_size_mb"),
            prediction_count=len(predictions),
            max_points=self.config.weight_efficiency
        )
        d6_score = DimensionScore(
            dimension_name="efficiency",
            weight=self.config.weight_efficiency,
            points_awarded=d6_eval["points_awarded"],
            max_points=d6_eval["max_points"],
            raw_metrics=d6_eval["breakdown"],
            normalized_score=d6_eval["normalized_score"],
            warnings=d6_eval["warnings"],
            is_provisional=True,
            notes="Evaluates inference runtime, memory consumption, and checkpoint footprint."
        )

        # 10. Aggregate Total Score
        dimensions = {
            "forecast_skill": d1_score,
            "event_detection": d2_score,
            "generalization": d3_score,
            "calibration_and_uncertainty": d4_score,
            "robustness": d5_score,
            "efficiency": d6_score
        }

        total_score = sum(dim.points_awarded for dim in dimensions.values())
        total_score = round(min(100.0, max(0.0, total_score)), 4)

        # Compile split summaries
        split_breakdown = {
            "test_a_count": len(records_test_a),
            "test_b_count": len(records_test_b),
            "test_c_count": len(records_test_c),
            "val_count": len(records_val),
            "total_paired_count": len(paired_records)
        }

        # Catchment summary
        catchment_breakdown = d1_eval.get("per_catchment", {})

        # Collect all dimension warnings
        for dim_obj in dimensions.values():
            all_warnings.extend(dim_obj.warnings)

        # Compute audit digest hash
        audit_payload = {
            "submission_id": submission_id,
            "total_score": total_score,
            "dimensions": {k: v.points_awarded for k, v in dimensions.items()},
            "evaluated_at": eval_time
        }
        audit_str = json.dumps(audit_payload, sort_keys=True)
        audit_hash = hashlib.sha256(audit_str.encode("utf-8")).hexdigest()

        return EvaluationResult(
            submission_id=submission_id,
            evaluated_at=eval_time,
            total_score=total_score,
            max_total_score=100.0,
            dimensions=dimensions,
            split_breakdown=split_breakdown,
            catchment_breakdown=catchment_breakdown,
            execution_stats=stats,
            warnings=all_warnings,
            is_valid=True,
            audit_hash=audit_hash
        )

