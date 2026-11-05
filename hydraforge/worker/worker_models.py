"""
hydraforge/worker/worker_models.py
Worker state machine enums, context definitions, resource limits,
and execution telemetry records for isolated model evaluation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydraforge.schema import PredictionRecord


class WorkerState(str, Enum):
    """Explicit lifecycle states for isolated worker execution."""
    WORKER_PENDING = "WORKER_PENDING"
    WORKER_PROVISIONING = "WORKER_PROVISIONING"
    WORKER_READY = "WORKER_READY"
    DEPENDENCY_INSTALLATION = "DEPENDENCY_INSTALLATION"
    DEPENDENCY_INSTALLATION_FAILED = "DEPENDENCY_INSTALLATION_FAILED"
    EXECUTION_RUNNING = "EXECUTION_RUNNING"
    EXECUTION_SUCCESS = "EXECUTION_SUCCESS"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    OUTPUT_COLLECTION = "OUTPUT_COLLECTION"
    OUTPUT_COLLECTION_FAILED = "OUTPUT_COLLECTION_FAILED"
    WORKER_CLEANUP = "WORKER_CLEANUP"
    WORKER_CLEANUP_FAILED = "WORKER_CLEANUP_FAILED"
    SAFE_WORKER_UNAVAILABLE = "SAFE_WORKER_UNAVAILABLE"


@dataclass(frozen=True)
class WorkerResourceLimits:
    """Configurable resource boundaries for isolated container execution."""
    cpu_limit: float = 2.0
    memory_limit_mb: float = 4096.0
    disk_quota_mb: float = 2048.0
    pids_limit: int = 64
    timeout_seconds: int = 300
    install_timeout_seconds: int = 120


@dataclass
class ExecutionTelemetry:
    """Audit and telemetry metrics collected during worker execution."""
    start_time: str = ""
    end_time: Optional[str] = None
    wall_clock_seconds: float = 0.0
    cpu_usage_percent: float = 0.0
    peak_memory_mb: float = 0.0
    disk_consumed_mb: float = 0.0
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    termination_reason: Optional[str] = None
    input_hash: str = ""
    output_hash: Optional[str] = None

    @property
    def runtime_seconds(self) -> float:
        return self.wall_clock_seconds

    @runtime_seconds.setter
    def runtime_seconds(self, val: float) -> None:
        self.wall_clock_seconds = val

    @property
    def cpu_percent(self) -> float:
        return self.cpu_usage_percent

    @cpu_percent.setter
    def cpu_percent(self, val: float) -> None:
        self.cpu_usage_percent = val


@dataclass
class WorkerContext:
    """Input payload delivered to the isolated worker."""
    submission_id: str
    job_id: str
    commit_sha: str
    discovery_report_id: str
    benchmark_cases: List[Dict[str, Any]]
    inference_contract_version: str = "1.0.0"
    resource_limits: WorkerResourceLimits = field(default_factory=WorkerResourceLimits)
    scratch_dir: Optional[Path] = None
    is_trusted_developer_fixture: bool = False


@dataclass
class WorkerExecutionResult:
    """Final outcome of an isolated worker evaluation run."""
    job_id: str
    submission_id: str
    final_state: WorkerState
    telemetry: ExecutionTelemetry
    prediction_records: List[PredictionRecord] = field(default_factory=list)
    error_message: Optional[str] = None
    cleanup_success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert execution result to dictionary."""
        return {
            "job_id": self.job_id,
            "submission_id": self.submission_id,
            "final_state": self.final_state.value,
            "telemetry": asdict(self.telemetry),
            "prediction_count": len(self.prediction_records),
            "error_message": self.error_message,
            "cleanup_success": self.cleanup_success,
        }

