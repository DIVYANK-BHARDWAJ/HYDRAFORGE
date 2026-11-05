"""Configuration and constants for HYDRAFORGE Benchmark Infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

BENCHMARK_SPEC_VERSION = "1.0.0"

SUPPORTED_SPLITS: Tuple[str, ...] = ("train", "validation", "test_a", "test_b", "test_c")
HIDDEN_SPLITS: Set[str] = {"test_a", "test_b", "test_c"}
PUBLIC_SPLITS: Set[str] = {"train", "validation"}

SUPPORTED_DISCHARGE_UNITS: Set[str] = {"m3/s", "mm/d"}
SUPPORTED_PRECIPITATION_UNITS: Set[str] = {"mm", "mm/d"}
SUPPORTED_TEMPERATURE_UNITS: Set[str] = {"degC", "K"}

CORRUPTION_FAMILIES: Tuple[str, ...] = (
    "missing_discharge",  # Historical discharge observations completely or partially withheld
    "input_noise",        # Additive Gaussian sensor noise on meteorological forcings
    "reporting_delay"     # 48-hour observation latency in meteorological inputs
)


@dataclass(frozen=True)
class BenchmarkConfig:
    """Master benchmark split and feature configuration."""
    version: str = BENCHMARK_SPEC_VERSION
    horizons: Tuple[int, ...] = (1, 3, 7)
    q95_percentile: float = 95.0
    q99_percentile: float = 99.0
    discharge_unit: str = "m3/s"
    random_seed: int = 42
    history_window_days: int = 30
    default_nominal_coverage: float = 0.90

