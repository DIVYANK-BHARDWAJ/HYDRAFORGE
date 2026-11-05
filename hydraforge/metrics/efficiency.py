"""Computational Efficiency Evaluation Metrics (Provisional Weight: 5 Points).

Measures:
- Wall-clock runtime and inference throughput (ms per prediction).
- Peak resident memory (RSS in MB) when reliably measured.
- Model artifact and checkpoint size on disk (MB).

Explicitly differentiates between missing/unavailable measurements (None) and zero values.
Never awards unearned points for unmeasured metrics.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
import numpy as np

PROVISIONAL_WEIGHT_EFFICIENCY = 5.0
DEFAULT_MAX_RUNTIME_SEC = 300.0
DEFAULT_TARGET_RUNTIME_SEC = 60.0
DEFAULT_MAX_MEMORY_MB = 4096.0
DEFAULT_TARGET_MEMORY_MB = 1024.0
DEFAULT_MAX_ARTIFACT_MB = 500.0
DEFAULT_TARGET_ARTIFACT_MB = 100.0


def evaluate_efficiency(
    runtime_seconds: Optional[float] = None,
    peak_memory_mb: Optional[float] = None,
    artifact_size_mb: Optional[float] = None,
    prediction_count: int = 1,
    max_points: float = PROVISIONAL_WEIGHT_EFFICIENCY,
    target_runtime_sec: float = DEFAULT_TARGET_RUNTIME_SEC,
    max_runtime_sec: float = DEFAULT_MAX_RUNTIME_SEC,
    target_memory_mb: float = DEFAULT_TARGET_MEMORY_MB,
    max_memory_mb: float = DEFAULT_MAX_MEMORY_MB,
    target_artifact_mb: float = DEFAULT_TARGET_ARTIFACT_MB,
    max_artifact_mb: float = DEFAULT_MAX_ARTIFACT_MB,
) -> Dict[str, Any]:
    """Evaluate computational efficiency across runtime, memory, and artifact size.

    Point allocation (5.0 total):
    - Runtime: 2.5 points
    - Memory: 1.5 points
    - Artifact size: 1.0 point
    """
    all_warnings: List[str] = []

    # 1. Runtime scoring (2.5 pts)
    pts_runtime = 0.0
    ms_per_prediction: Optional[float] = None

    if runtime_seconds is None:
        all_warnings.append("Runtime measurement is unavailable (None); 0.0 runtime points awarded.")
    elif runtime_seconds < 0:
        all_warnings.append(f"Invalid negative runtime reported ({runtime_seconds}s); 0.0 runtime points awarded.")
    else:
        if prediction_count > 0:
            ms_per_prediction = round((runtime_seconds * 1000.0) / prediction_count, 3)

        if runtime_seconds <= target_runtime_sec:
            pts_runtime = 2.5
        elif runtime_seconds >= max_runtime_sec:
            pts_runtime = 0.0
            all_warnings.append(f"Runtime ({runtime_seconds:.1f}s) exceeded maximum budget of {max_runtime_sec:.1f}s.")
        else:
            fraction = (max_runtime_sec - runtime_seconds) / (max_runtime_sec - target_runtime_sec)
            pts_runtime = max(0.0, min(2.5, fraction * 2.5))

    # 2. Memory scoring (1.5 pts)
    pts_memory = 0.0
    if peak_memory_mb is None:
        all_warnings.append("Peak memory measurement is unavailable (None); 0.0 memory points awarded.")
    elif peak_memory_mb < 0:
        all_warnings.append(f"Invalid negative peak memory reported ({peak_memory_mb} MB); 0.0 points awarded.")
    else:
        if peak_memory_mb <= target_memory_mb:
            pts_memory = 1.5
        elif peak_memory_mb >= max_memory_mb:
            pts_memory = 0.0
            all_warnings.append(f"Peak memory ({peak_memory_mb:.1f} MB) exceeded maximum budget of {max_memory_mb:.1f} MB.")
        else:
            fraction = (max_memory_mb - peak_memory_mb) / (max_memory_mb - target_memory_mb)
            pts_memory = max(0.0, min(1.5, fraction * 1.5))

    # 3. Artifact size scoring (1.0 pt)
    pts_artifact = 0.0
    if artifact_size_mb is None:
        all_warnings.append("Artifact size measurement is unavailable (None); 0.0 artifact points awarded.")
    elif artifact_size_mb < 0:
        all_warnings.append(f"Invalid negative artifact size ({artifact_size_mb} MB); 0.0 points awarded.")
    else:
        if artifact_size_mb <= target_artifact_mb:
            pts_artifact = 1.0
        elif artifact_size_mb >= max_artifact_mb:
            pts_artifact = 0.0
            all_warnings.append(f"Artifact size ({artifact_size_mb:.1f} MB) exceeded maximum budget of {max_artifact_mb:.1f} MB.")
        else:
            fraction = (max_artifact_mb - artifact_size_mb) / (max_artifact_mb - target_artifact_mb)
            pts_artifact = max(0.0, min(1.0, fraction * 1.0))

    total_points = min(max_points, max(0.0, pts_runtime + pts_memory + pts_artifact))
    normalized_score = total_points / max_points if max_points > 0 else 0.0

    return {
        "dimension": "efficiency",
        "points_awarded": round(total_points, 4),
        "max_points": max_points,
        "weight": max_points,
        "normalized_score": round(normalized_score, 4),
        "is_provisional": True,
        "warnings": all_warnings,
        "breakdown": {
            "runtime_seconds": round(runtime_seconds, 3) if runtime_seconds is not None else None,
            "ms_per_prediction": ms_per_prediction,
            "runtime_points": round(pts_runtime, 4),
            "peak_memory_mb": round(peak_memory_mb, 2) if peak_memory_mb is not None else None,
            "memory_points": round(pts_memory, 4),
            "artifact_size_mb": round(artifact_size_mb, 2) if artifact_size_mb is not None else None,
            "artifact_points": round(pts_artifact, 4),
        }
    }

