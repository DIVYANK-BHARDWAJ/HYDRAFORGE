"""Persistence Reference Baseline.

Predicts the most recent known discharge observation for all future horizons.
Computes deterministic exceedance probabilities and empirical intervals around persistence.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import numpy as np

from hydraforge.schema import BenchmarkInputRecord, GroundTruthLabel, PredictionRecord


class PersistenceBaseline:
    """Predicts discharge at forecast origin: q(c, t+h) = q(c, t)."""

    def __init__(self, name: str = "PersistenceBaseline") -> None:
        self.name = name
        self.fallback_discharge: float = 1.0
        self.runtime_seconds: float = 0.0

    def fit(
        self,
        train_inputs: Sequence[BenchmarkInputRecord],
        train_labels: Sequence[GroundTruthLabel]
    ) -> None:
        """Persistence requires no fitting, but records training mean as fallback for ungauged cases."""
        if train_labels:
            self.fallback_discharge = float(np.mean([l.true_discharge for l in train_labels]))

    def predict(
        self,
        inputs: Sequence[BenchmarkInputRecord],
        catchment_metadata: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[PredictionRecord]:
        start_time = time.perf_counter()
        predictions: List[PredictionRecord] = []
        meta = catchment_metadata or {}

        for rec in inputs:
            # Most recent known discharge
            if rec.discharge_history and len(rec.discharge_history) > 0:
                last_q = float(rec.discharge_history[-1])
            else:
                last_q = self.fallback_discharge

            c_meta = meta.get(rec.catchment_id, {})
            q95 = float(c_meta.get("q95_threshold", last_q * 1.5))
            q99 = float(c_meta.get("q99_threshold", last_q * 2.0))

            # Exceedance probabilities: sharp if exceeding threshold, otherwise proportional
            p_high = 1.0 if last_q >= q95 else max(0.0, min(0.99, last_q / (q95 + 1e-6) * 0.5))
            p_ext = 1.0 if last_q >= q99 else max(0.0, min(0.99, last_q / (q99 + 1e-6) * 0.2))

            # Symmetrical intervals (+-20% around persistence)
            lower_q = max(0.0, last_q * 0.80)
            upper_q = last_q * 1.25

            for h in rec.horizons:
                predictions.append(PredictionRecord(
                    case_id=rec.case_id,
                    catchment_id=rec.catchment_id,
                    forecast_origin=rec.forecast_origin,
                    horizon=h,
                    predicted_discharge=round(last_q, 3),
                    high_flow_probability=round(p_high, 4),
                    extreme_flow_probability=round(p_ext, 4),
                    prediction_interval_lower=round(lower_q, 3),
                    prediction_interval_upper=round(upper_q, 3),
                    nominal_interval_coverage=0.90
                ))

        self.runtime_seconds = time.perf_counter() - start_time
        return predictions

