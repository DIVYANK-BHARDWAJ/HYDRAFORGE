"""
hydraforge/evaluation/split_evaluator.py
Independent Test Split Evaluator for Temporal (Test A), Geographic (Test B),
and Robustness Stress (Test C) Holdout Partitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from hydraforge.metrics.forecast_skill import evaluate_forecast_skill
from hydraforge.metrics.event_detection import evaluate_event_detection
from hydraforge.metrics.generalization import evaluate_generalization
from hydraforge.metrics.robustness import evaluate_robustness
from hydraforge.schema import GroundTruthLabel, PredictionRecord


@dataclass
class SplitEvaluationSummary:
    """Detailed evaluation summary for an individual benchmark split."""
    split_name: str
    case_count: int
    valid_predictions: int
    invalid_predictions: int
    missing_predictions: int
    metrics: Dict[str, Any] = field(default_factory=dict)
    runtime_seconds: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    status: str = "COMPLETED"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "split_name": self.split_name,
            "case_count": self.case_count,
            "valid_predictions": self.valid_predictions,
            "invalid_predictions": self.invalid_predictions,
            "missing_predictions": self.missing_predictions,
            "metrics": dict(self.metrics),
            "runtime_seconds": self.runtime_seconds,
            "peak_memory_mb": self.peak_memory_mb,
            "status": self.status,
            "warnings": list(self.warnings),
        }


class SplitEvaluator:
    """
    Evaluates individual benchmark splits independently to maintain
    scientific auditability and prevent opaque metric aggregation.
    """

    def evaluate_test_a(
        self,
        predictions: Sequence[PredictionRecord],
        ground_truth: Sequence[GroundTruthLabel],
        runtime: Optional[float] = None,
        memory: Optional[float] = None,
    ) -> SplitEvaluationSummary:
        """
        Evaluate Split A: Temporal Holdout (Forecast Skill & Event Detection).
        """
        pred_map = {(str(p.case_id), int(p.horizon)): p for p in predictions}
        gt_test_a = [gt for gt in ground_truth if gt.split == "test_a" and not gt.is_corrupted]

        paired = []
        missing = 0
        for gt in gt_test_a:
            key = (str(gt.case_id), int(gt.horizon))
            if key in pred_map:
                p = pred_map[key]
                persist = gt.persistence_discharge if gt.persistence_discharge is not None else gt.true_discharge
                paired.append({
                    "case_id": gt.case_id,
                    "catchment_id": gt.catchment_id,
                    "forecast_origin": gt.forecast_origin,
                    "horizon": gt.horizon,
                    "y_true": gt.true_discharge,
                    "y_pred": p.predicted_discharge,
                    "y_persist": persist,
                    "high_flow_threshold": gt.high_flow_threshold,
                    "extreme_flow_threshold": gt.extreme_flow_threshold,
                    "high_flow_prob": p.high_flow_probability,
                    "extreme_flow_prob": p.extreme_flow_probability,
                    "interval_lower": p.prediction_interval_lower,
                    "interval_upper": p.prediction_interval_upper,
                })
            else:
                missing += 1

        skill_res = evaluate_forecast_skill(paired, max_points=25.0) if paired else {}
        event_res = evaluate_event_detection(paired, max_points=25.0) if paired else {}

        metrics = {
            "forecast_skill": skill_res,
            "event_detection": event_res,
        }

        return SplitEvaluationSummary(
            split_name="test_a",
            case_count=len(gt_test_a),
            valid_predictions=len(paired),
            invalid_predictions=0,
            missing_predictions=missing,
            metrics=metrics,
            runtime_seconds=runtime,
            peak_memory_mb=memory,
            status="COMPLETED" if missing == 0 else "PARTIAL",
        )

    def evaluate_test_b(
        self,
        predictions: Sequence[PredictionRecord],
        ground_truth: Sequence[GroundTruthLabel],
        reference_predictions: Sequence[PredictionRecord],
        reference_ground_truth: Sequence[GroundTruthLabel],
        catchment_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
        runtime: Optional[float] = None,
        memory: Optional[float] = None,
    ) -> SplitEvaluationSummary:
        """
        Evaluate Split B: Geographic Holdout (Unseen catchments).
        """
        pred_map = {(str(p.case_id), int(p.horizon)): p for p in predictions}
        gt_test_b = [gt for gt in ground_truth if gt.split == "test_b" and not gt.is_corrupted]

        paired_b = []
        missing = 0
        for gt in gt_test_b:
            key = (str(gt.case_id), int(gt.horizon))
            if key in pred_map:
                p = pred_map[key]
                paired_b.append({
                    "case_id": gt.case_id,
                    "catchment_id": gt.catchment_id,
                    "forecast_origin": gt.forecast_origin,
                    "horizon": gt.horizon,
                    "region": gt.region,
                    "y_true": gt.true_discharge,
                    "y_pred": p.predicted_discharge,
                    "y_persist": gt.persistence_discharge if gt.persistence_discharge is not None else gt.true_discharge,
                })
            else:
                missing += 1

        # Reference records (from Test A)
        ref_pred_map = {(str(p.case_id), int(p.horizon)): p for p in reference_predictions}
        ref_paired = []
        for gt in reference_ground_truth:
            key = (str(gt.case_id), int(gt.horizon))
            if key in ref_pred_map:
                p = ref_pred_map[key]
                ref_paired.append({
                    "case_id": gt.case_id,
                    "catchment_id": gt.catchment_id,
                    "forecast_origin": gt.forecast_origin,
                    "horizon": gt.horizon,
                    "region": gt.region,
                    "y_true": gt.true_discharge,
                    "y_pred": p.predicted_discharge,
                    "y_persist": gt.persistence_discharge if gt.persistence_discharge is not None else gt.true_discharge,
                })

        gen_res = evaluate_generalization(
            test_b_records=paired_b,
            ref_records=ref_paired,
            catchment_metadata=catchment_metadata,
            max_points=20.0,
        )

        return SplitEvaluationSummary(
            split_name="test_b",
            case_count=len(gt_test_b),
            valid_predictions=len(paired_b),
            invalid_predictions=0,
            missing_predictions=missing,
            metrics={"generalization": gen_res},
            runtime_seconds=runtime,
            peak_memory_mb=memory,
            status="COMPLETED" if missing == 0 else "PARTIAL",
        )

    def evaluate_test_c(
        self,
        predictions: Sequence[PredictionRecord],
        ground_truth: Sequence[GroundTruthLabel],
        clean_predictions: Sequence[PredictionRecord],
        clean_ground_truth: Sequence[GroundTruthLabel],
        runtime: Optional[float] = None,
        memory: Optional[float] = None,
    ) -> SplitEvaluationSummary:
        """
        Evaluate Split C: Stress and Robustness (Controlled input corruptions).
        """
        pred_map = {(str(p.case_id), int(p.horizon)): p for p in predictions}
        gt_test_c = [gt for gt in ground_truth if gt.is_corrupted]

        paired_c = []
        missing = 0
        for gt in gt_test_c:
            key = (str(gt.case_id), int(gt.horizon))
            if key in pred_map:
                p = pred_map[key]
                paired_c.append({
                    "case_id": gt.case_id,
                    "catchment_id": gt.catchment_id,
                    "horizon": gt.horizon,
                    "clean_case_id": gt.clean_case_id,
                    "corruption_family": gt.corruption_family,
                    "y_true": gt.true_discharge,
                    "y_pred": p.predicted_discharge,
                })
            else:
                missing += 1

        # Clean reference paired
        clean_pred_map = {(str(p.case_id), int(p.horizon)): p for p in clean_predictions}
        clean_paired = []
        for gt in clean_ground_truth:
            key = (str(gt.case_id), int(gt.horizon))
            if key in clean_pred_map:
                p = clean_pred_map[key]
                clean_paired.append({
                    "case_id": gt.case_id,
                    "catchment_id": gt.catchment_id,
                    "horizon": gt.horizon,
                    "y_true": gt.true_discharge,
                    "y_pred": p.predicted_discharge,
                })

        rob_res = evaluate_robustness(
            clean_records=clean_paired,
            corrupt_records=paired_c,
            max_points=10.0,
        )

        return SplitEvaluationSummary(
            split_name="test_c",
            case_count=len(gt_test_c),
            valid_predictions=len(paired_c),
            invalid_predictions=0,
            missing_predictions=missing,
            metrics={"robustness": rob_res},
            runtime_seconds=runtime,
            peak_memory_mb=memory,
            status="COMPLETED" if missing == 0 else "PARTIAL",
        )

