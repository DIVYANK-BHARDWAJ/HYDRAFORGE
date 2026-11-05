"""Evaluation Job Lifecycle, State Machine, and Provenance Record."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from hydraforge.schema import CONTRACT_VERSION, EvaluationResult


class JobStatus(str, Enum):
    """Formal lifecycle states for an automated evaluation run."""
    CREATED = "CREATED"
    REPOSITORY_VALIDATED = "REPOSITORY_VALIDATED"
    SUBMISSION_VALIDATED = "SUBMISSION_VALIDATED"
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    OUTPUT_VALIDATION = "OUTPUT_VALIDATION"
    SCORING = "SCORING"
    COMPLETED = "COMPLETED"

    # Terminal failure states
    REPOSITORY_REJECTED = "REPOSITORY_REJECTED"
    SUBMISSION_REJECTED = "SUBMISSION_REJECTED"
    UNSAFE_EXECUTION_ENVIRONMENT = "UNSAFE_EXECUTION_ENVIRONMENT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    INVALID_PREDICTIONS = "INVALID_PREDICTIONS"
    SCORING_FAILED = "SCORING_FAILED"


TERMINAL_FAILURE_STATES = {
    JobStatus.REPOSITORY_REJECTED,
    JobStatus.SUBMISSION_REJECTED,
    JobStatus.UNSAFE_EXECUTION_ENVIRONMENT,
    JobStatus.EXECUTION_FAILED,
    JobStatus.RESOURCE_LIMIT_EXCEEDED,
    JobStatus.INVALID_PREDICTIONS,
    JobStatus.SCORING_FAILED,
}


@dataclass
class EvaluationJob:
    """Audit record and state container for an evaluation job."""
    job_id: str
    repository_url: str
    commit_sha: str
    contract_version: str = CONTRACT_VERSION
    benchmark_version: str = "1.0.0"
    scoring_config_version: str = "1.0.0"
    execution_backend: str = "DockerRunner"
    status: JobStatus = JobStatus.CREATED
    failure_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    runtime_seconds: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    prediction_artifact_hash: Optional[str] = None
    score_report_hash: Optional[str] = None
    final_score: Optional[float] = None
    evaluation_result: Optional[EvaluationResult] = None
    audit_log: List[str] = field(default_factory=list)

    def transition_to(self, new_status: JobStatus, message: Optional[str] = None) -> None:
        """Record state transition in audit log and update status."""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] Transition: {self.status.value} -> {new_status.value}"
        if message:
            log_entry += f" ({message})"
        self.audit_log.append(log_entry)
        self.status = new_status

        if new_status in TERMINAL_FAILURE_STATES:
            self.completed_at = timestamp
            self.failure_reason = message
            self.final_score = None  # Invariant: Failed jobs NEVER receive scores!

        elif new_status == JobStatus.EXECUTING:
            if not self.started_at:
                self.started_at = timestamp

        elif new_status == JobStatus.COMPLETED:
            self.completed_at = timestamp

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

