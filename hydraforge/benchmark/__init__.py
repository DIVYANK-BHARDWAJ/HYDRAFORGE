"""HYDRAFORGE Benchmark Subpackage.

Provides dataset adapters, split management, threshold provenance,
and deterministic synthetic benchmark generation.
"""

from hydraforge.benchmark.config import (
    BenchmarkConfig,
    BENCHMARK_SPEC_VERSION,
    SUPPORTED_SPLITS,
    HIDDEN_SPLITS,
    PUBLIC_SPLITS,
    CORRUPTION_FAMILIES,
)
from hydraforge.benchmark.provenance import (
    ThresholdMetadata,
    SplitManifest,
    compute_file_sha256,
    compute_object_sha256,
)
from hydraforge.benchmark.validation import (
    DataValidationError,
    LeakageError,
    LeakageAuditReport,
    validate_units,
    audit_splits_for_leakage,
)
from hydraforge.benchmark.loader import (
    BaseDatasetAdapter,
    TabularDatasetAdapter,
    CaravanDatasetAdapter,
    ParticipantBenchmarkLoader,
    OrganizerBenchmarkLoader,
)
from hydraforge.benchmark.split_manager import SplitManager
from hydraforge.benchmark.synthetic import (
    generate_synthetic_benchmark,
    SYNTHETIC_BANNER,
)
from hydraforge.benchmark.case_manager import BenchmarkCaseManager
from hydraforge.benchmark.input_preparer import BenchmarkInputPreparer

__all__ = [
    "BenchmarkConfig",
    "BENCHMARK_SPEC_VERSION",
    "SUPPORTED_SPLITS",
    "HIDDEN_SPLITS",
    "PUBLIC_SPLITS",
    "CORRUPTION_FAMILIES",
    "ThresholdMetadata",
    "SplitManifest",
    "compute_file_sha256",
    "compute_object_sha256",
    "DataValidationError",
    "LeakageError",
    "LeakageAuditReport",
    "validate_units",
    "audit_splits_for_leakage",
    "BaseDatasetAdapter",
    "TabularDatasetAdapter",
    "CaravanDatasetAdapter",
    "ParticipantBenchmarkLoader",
    "OrganizerBenchmarkLoader",
    "SplitManager",
    "generate_synthetic_benchmark",
    "SYNTHETIC_BANNER",
    "BenchmarkCaseManager",
    "BenchmarkInputPreparer",
]

