"""Evaluation Service: Bridges HTTP API and CLI with Execution & Persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hydraforge.database.repository import EvaluationRepository
from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.evaluation.orchestrator import EvaluationOrchestrator
from hydraforge.runner.docker_runner import DockerRunner
from hydraforge.runner.local_test_runner import LocalTestRunner
from hydraforge.submission.repository import (
    RepositorySecurityError,
    validate_commit_sha,
    validate_repository_url,
)


class EvaluationService:
    """Coordinates submission validation, runner execution, scoring, and DB persistence."""

    def __init__(
        self,
        repository: Optional[EvaluationRepository] = None,
        benchmark_root: Path = Path("data/benchmark")
    ) -> None:
        self.repo = repository or EvaluationRepository()
        self.benchmark_root = Path(benchmark_root).resolve()

    def submit_evaluation(
        self,
        repository_url: str,
        commit_sha: str,
        submission_metadata: Optional[Dict[str, Any]] = None,
        is_trusted: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """Validate submission inputs, check runner availability, execute, and persist."""
        meta = submission_metadata or {}

        # 1. Input validation
        try:
            if not is_trusted:
                clean_url = validate_repository_url(repository_url)
                clean_sha = validate_commit_sha(commit_sha)
            else:
                clean_url = repository_url
                clean_sha = commit_sha
        except RepositorySecurityError as e:
            return False, {
                "error": "REPOSITORY_REJECTED",
                "message": str(e)
            }

        # 2. Check Execution Backend Availability
        docker_runner = DockerRunner()
        docker_available = docker_runner.is_docker_daemon_available()

        if not is_trusted:
            if not docker_available:
                # Critical Fail-Closed Rule
                return False, {
                    "error": "UNSAFE_EXECUTION_ENVIRONMENT",
                    "message": (
                        "UNSAFE_EXECUTION_ENVIRONMENT: The Docker daemon is offline or inaccessible. "
                        "Executing untrusted participant code in an unconfined environment is strictly forbidden. "
                        "Start Docker Desktop or configure an isolated execution worker before submitting."
                    ),
                    "execution_readiness": {
                        "docker_available": False,
                        "untrusted_execution_enabled": False
                    }
                }
            runner = docker_runner
        else:
            # Trusted developer fixture path
            runner = LocalTestRunner(trusted_test_only=True)

        # 3. Create Orchestrator and Run Job
        orchestrator = EvaluationOrchestrator(
            benchmark_root=self.benchmark_root,
            runner=runner
        )

        job = orchestrator.run_job(
            repo_source=clean_url,
            commit_sha=clean_sha,
            is_trusted=is_trusted
        )

        # 4. Persist Job and Result to SQLite
        self.repo.insert_job(job, submission_metadata=meta)

        if job.status == JobStatus.COMPLETED and job.evaluation_result:
            dims = {k: v.points_awarded for k, v in job.evaluation_result.dimensions.items()}
            full_json = json.dumps(job.to_dict(), default=str)
            self.repo.save_evaluation_result(
                job_id=job.job_id,
                total_score=job.final_score or 0.0,
                dimensions=dims,
                full_report_json=full_json
            )

        return True, {
            "job_id": job.job_id,
            "status": job.status.value,
            "final_score": job.final_score,
            "failure_reason": job.failure_reason,
            "report_hash": job.score_report_hash,
            "created_at": job.created_at,
            "completed_at": job.completed_at
        }

    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.repo.get_job(job_id)

    def list_jobs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self.repo.list_jobs(limit=limit, offset=offset)

    def get_job_report(self, job_id: str) -> Optional[Dict[str, Any]]:
        res = self.repo.get_evaluation_result(job_id)
        if res:
            return res.get("full_report")
        job = self.repo.get_job(job_id)
        return job

