"""Climatological Reference Baseline.

Predicts seasonal historical day-of-year mean river discharge fitted exclusively
on historical training records. Never touches validation or test labels.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

from hydraforge.schema import BenchmarkInputRecord, GroundTruthLabel, PredictionRecord


class ClimatologyBaseline:
    """Predicts day-of-year historical mean discharge: q(c, t+h) = mean_training_q(c, doy(t+h))."""

    def __init__(self, name: str = "ClimatologyBaseline") -> None:
        self.name = name
        self.catchment_doy_means: Dict[Tuple[str, int], float] = {}
        self.catchment_overall_means: Dict[str, float] = {}
        self.catchment_stds: Dict[str, float] = {}
        self.global_mean: float = 10.0
        self.runtime_seconds: float = 0.0

    def fit(
        self,
        train_inputs: Sequence[BenchmarkInputRecord],
        train_labels: Sequence[GroundTruthLabel]
    ) -> None:
        """Fit day-of-year seasonal statistics strictly on training data."""
        start_time = time.perf_counter()
        by_c_doy: Dict[Tuple[str, int], List[float]] = {}
        by_c: Dict[str, List[float]] = {}
        all_vals: List[float] = []

        for lbl in train_labels:
            cid = lbl.catchment_id
            val = lbl.true_discharge
            all_vals.append(val)
            by_c.setdefault(cid, []).append(val)

            # Extract day of year
            dt = datetime.fromisoformat(lbl.forecast_origin.replace("Z", "+00:00"))
            doy = dt.timetuple().tm_yday
            by_c_doy.setdefault((cid, doy), []).append(val)

        for (cid, doy), vals in by_c_doy.items():
            self.catchment_doy_means[(cid, doy)] = float(np.mean(vals))

        for cid, vals in by_c.items():
            self.catchment_overall_means[cid] = float(np.mean(vals))
            self.catchment_stds[cid] = float(np.std(vals)) if len(vals) > 1 else 1.0

        if all_vals:
            self.global_mean = float(np.mean(all_vals))

        self.runtime_seconds = time.perf_counter() - start_time

    def predict(
        self,
        inputs: Sequence[BenchmarkInputRecord],
        catchment_metadata: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[PredictionRecord]:
        start_time = time.perf_counter()
        predictions: List[PredictionRecord] = []
        meta = catchment_metadata or {}

        for rec in inputs:
            cid = rec.catchment_id
            c_mean = self.catchment_overall_means.get(cid, self.global_mean)
            c_std = self.catchment_stds.get(cid, max(1.0, 0.25 * c_mean))
            c_meta = meta.get(cid, {})

            q95 = float(c_meta.get("q95_threshold", c_mean + 1.645 * c_std))
            q99 = float(c_meta.get("q99_threshold", c_mean + 2.326 * c_std))

            dt_origin = datetime.fromisoformat(rec.forecast_origin.replace("Z", "+00:00"))

            for h in rec.horizons:
                # Estimate target day of year
                target_doy = (dt_origin.timetuple().tm_yday + h) % 365
                pred_q = self.catchment_doy_means.get((cid, target_doy), c_mean)
                pred_q = max(0.05, pred_q)

                # Climatological exceedance probability via Gaussian tail approximation
                z_high = (q95 - pred_q) / (c_std + 1e-6)
                z_ext = (q99 - pred_q) / (c_std + 1e-6)
                # Logistic approximation to standard normal CDF: 1 / (1 + exp(-1.7 * z))
                p_high = 1.0 / (1.0 + np.exp(1.7 * z_high))
                p_ext = 1.0 / (1.0 + np.exp(1.7 * z_ext))

                # 90% prediction intervals (+- 1.645 std)
                lower_q = max(0.0, pred_q - 1.645 * c_std)
                upper_q = pred_q + 1.645 * c_std

                predictions.append(PredictionRecord(
                    case_id=rec.case_id,
                    catchment_id=rec.catchment_id,
                    forecast_origin=rec.forecast_origin,
                    horizon=h,
                    predicted_discharge=round(pred_q, 3),
                    high_flow_probability=round(float(p_high), 4),
                    extreme_flow_probability=round(float(p_ext), 4),
                    prediction_interval_lower=round(lower_q, 3),
                    prediction_interval_upper=round(upper_q, 3),
                    nominal_interval_coverage=0.90
                ))

        self.runtime_seconds += time.perf_counter() - start_time
        return predictions

