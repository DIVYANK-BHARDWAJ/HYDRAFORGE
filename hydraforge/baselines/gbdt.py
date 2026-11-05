"""Gradient Boosted Decision Tree (XGBoost) Reference Baseline.

Engineers lagged hydrological and meteorological features, trains an XGBoost regressor
exclusively on the training partition, and produces point forecasts, exceedance probabilities,
and prediction intervals.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import numpy as np
import xgboost as xgb

from hydraforge.schema import BenchmarkInputRecord, GroundTruthLabel, PredictionRecord


class GBDTBaseline:
    """XGBoost regressor with hydrological lag features."""

    def __init__(self, name: str = "GBDTBaseline", random_seed: int = 42) -> None:
        self.name = name
        self.random_seed = random_seed
        self.booster: Optional[xgb.Booster] = None
        self.residual_std: float = 1.0
        self.feature_names = [
            "horizon",
            "last_q",
            "mean_q_7d",
            "max_q_7d",
            "precip_sum_3d",
            "precip_sum_7d",
            "temp_mean_7d",
            "area_km2",
            "elevation_m",
        ]
        self.runtime_seconds: float = 0.0
        self.artifact_size_mb: float = 0.0

    def _extract_features(
        self,
        record: BenchmarkInputRecord,
        horizon: int
    ) -> List[float]:
        """Extract tabular feature vector from input record."""
        # Discharge history features
        dh = record.discharge_history
        if dh and len(dh) > 0:
            last_q = float(dh[-1])
            mean_q_7d = float(np.mean(dh[-7:]))
            max_q_7d = float(np.max(dh[-7:]))
        else:
            last_q = 5.0
            mean_q_7d = 5.0
            max_q_7d = 5.0

        # Forcing features
        fh = record.forcing_history
        precip = fh.get("precipitation_mm", [])
        if precip and len(precip) > 0:
            precip_sum_3d = float(np.sum(precip[-3:]))
            precip_sum_7d = float(np.sum(precip[-7:]))
        else:
            precip_sum_3d = 0.0
            precip_sum_7d = 0.0

        temp = fh.get("temperature_c", [])
        temp_mean_7d = float(np.mean(temp[-7:])) if temp else 12.0

        # Attributes
        attrs = record.attributes
        area_km2 = float(attrs.get("area_km2", 100.0))
        elevation_m = float(attrs.get("mean_elevation_m", 500.0))

        return [
            float(horizon),
            last_q,
            mean_q_7d,
            max_q_7d,
            precip_sum_3d,
            precip_sum_7d,
            temp_mean_7d,
            area_km2,
            elevation_m,
        ]

    def fit(
        self,
        train_inputs: Sequence[BenchmarkInputRecord],
        train_labels: Sequence[GroundTruthLabel]
    ) -> None:
        """Fit XGBoost model strictly on historical training cases and labels."""
        start_time = time.perf_counter()

        # Build lookup for inputs by case_id
        input_map = {inp.case_id: inp for inp in train_inputs}

        X_list: List[List[float]] = []
        y_list: List[float] = []

        for lbl in train_labels:
            if lbl.case_id in input_map:
                inp = input_map[lbl.case_id]
                feats = self._extract_features(inp, lbl.horizon)
                X_list.append(feats)
                y_list.append(lbl.true_discharge)

        if not X_list:
            raise ValueError("No matching training inputs and labels provided to GBDTBaseline.")

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.float32)

        dtrain = xgb.DMatrix(X, label=y, feature_names=self.feature_names)
        params = {
            "max_depth": 4,
            "eta": 0.08,
            "subsample": 0.8,
            "seed": self.random_seed,
            "verbosity": 0,
            "objective": "reg:squarederror"
        }
        self.booster = xgb.train(params, dtrain, num_boost_round=50)

        # Estimate training residual standard deviation for prediction intervals
        preds = self.booster.predict(dtrain)
        residuals = y - preds
        self.residual_std = float(np.std(residuals)) if len(residuals) > 1 else 1.0
        self.residual_std = max(0.1, self.residual_std)

        self.runtime_seconds = time.perf_counter() - start_time

    def predict(
        self,
        inputs: Sequence[BenchmarkInputRecord],
        catchment_metadata: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[PredictionRecord]:
        start_time = time.perf_counter()
        if self.booster is None:
            raise RuntimeError("GBDTBaseline must be fitted before predict() is called.")

        meta = catchment_metadata or {}
        predictions: List[PredictionRecord] = []

        X_rows: List[List[float]] = []
        index_pairs: List[tuple] = []  # (record, horizon)

        for rec in inputs:
            for h in rec.horizons:
                feats = self._extract_features(rec, h)
                X_rows.append(feats)
                index_pairs.append((rec, h))

        if not X_rows:
            return []

        X_arr = np.array(X_rows, dtype=np.float32)
        dtest = xgb.DMatrix(X_arr, feature_names=self.feature_names)
        y_preds = self.booster.predict(dtest)

        for (rec, h), pred_val in zip(index_pairs, y_preds):
            pred_q = max(0.0, float(pred_val))
            cid = rec.catchment_id
            c_meta = meta.get(cid, {})

            q95 = float(c_meta.get("q95_threshold", pred_q * 1.5))
            q99 = float(c_meta.get("q99_threshold", pred_q * 2.0))

            # Probability of exceeding threshold: Gaussian approximation via residual std
            z_high = (q95 - pred_q) / (self.residual_std + 1e-6)
            z_ext = (q99 - pred_q) / (self.residual_std + 1e-6)
            p_high = 1.0 / (1.0 + np.exp(1.7 * z_high))
            p_ext = 1.0 / (1.0 + np.exp(1.7 * z_ext))

            # 90% Prediction Intervals (+- 1.645 residual std)
            lower_q = max(0.0, pred_q - 1.645 * self.residual_std)
            upper_q = pred_q + 1.645 * self.residual_std

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

    def save(self, model_path: Path) -> None:
        """Serialize model and metadata to disk."""
        model_path = Path(model_path)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        if self.booster is not None:
            self.booster.save_model(str(model_path))
            meta_path = model_path.with_suffix(".json")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({
                    "name": self.name,
                    "residual_std": self.residual_std,
                    "feature_names": self.feature_names,
                    "random_seed": self.random_seed
                }, f, indent=2)
            self.artifact_size_mb = model_path.stat().st_size / (1024 * 1024)
