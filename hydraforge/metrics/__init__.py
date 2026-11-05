"""HYDRAFORGE Metrics Package.

Exports deterministic evaluation modules for the six challenge dimensions:
- Forecast Skill (25 pts)
- High-Flow & Extreme-Flow Event Detection (25 pts)
- Out-of-Distribution Generalization (20 pts)
- Calibration & Uncertainty (15 pts)
- Robustness (10 pts)
- Efficiency (5 pts)
"""

from hydraforge.metrics.forecast_skill import (
    calculate_mae,
    calculate_rmse,
    calculate_nse,
    calculate_persistence_relative_skill,
    evaluate_forecast_skill,
)
from hydraforge.metrics.event_detection import (
    calculate_brier_score,
    calculate_confusion_metrics,
    calculate_auprc,
    evaluate_event_detection,
)
from hydraforge.metrics.generalization import evaluate_generalization
from hydraforge.metrics.calibration import evaluate_calibration, evaluate_prediction_intervals
from hydraforge.metrics.robustness import evaluate_robustness
from hydraforge.metrics.efficiency import evaluate_efficiency
from hydraforge.metrics.evaluator import HydraForgeEvaluator, EvaluationConfig

__all__ = [
    "calculate_mae",
    "calculate_rmse",
    "calculate_nse",
    "calculate_persistence_relative_skill",
    "evaluate_forecast_skill",
    "calculate_brier_score",
    "calculate_confusion_metrics",
    "calculate_auprc",
    "evaluate_event_detection",
    "evaluate_generalization",
    "evaluate_calibration",
    "evaluate_prediction_intervals",
    "evaluate_robustness",
    "evaluate_efficiency",
    "HydraForgeEvaluator",
    "EvaluationConfig",
]

