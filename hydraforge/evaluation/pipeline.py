"""
hydraforge/evaluation/pipeline.py
Master Benchmark Execution, Prediction Validation, and Automated Scoring Pipeline.
Connects Phase 1 (Six-axis scoring), Phase 2 (Benchmark infrastructure),
Phase 5A (Dynamic discovery), and Phase 5B (Secure isolated worker).
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from hydraforge.benchmark.case_manager import BenchmarkCaseManager
from hydraforge.benchmark.config import BenchmarkConfig
from hydraforge.benchmark.input_preparer import BenchmarkInputPreparer
from hydraforge.discovery.discovery_models import DiscoveryReport, InterfaceStatus
from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.evaluation.prediction_validator import PredictionValidationReport, PredictionValidator
from hydraforge.evaluation.split_evaluator import SplitEvaluator, SplitEvaluationSummary
from hydraforge.metrics.evaluator import EvaluationConfig, HydraForgeEvaluator
from hydraforge.runner.isolation import verify_hidden_label_shielding
from hydraforge.schema import BenchmarkInputRecord, EvaluationResult, GroundTruthLabel, PredictionRecord
from hydraforge.submission.repository import validate_commit_sha
from hydraforge.worker.worker_manager import WorkerManager
from hydraforge.worker.worker_models import (
    ExecutionTelemetry,
    WorkerContext,
    WorkerExecutionResult,
    WorkerResourceLimits,
    WorkerState,
)


@dataclass
class ComprehensiveEvaluationReport:
    """Complete, reproducible audit report for a benchmark evaluation."""
    evaluation_id: str
    job_id: str
    submission_id: str
    team_name: str
    repository_url: str
    commit_sha: str
    discovery_report_id: str
    inference_contract_version: str
    benchmark_version: str
    scoring_version: str
    dataset_provenance: Dict[str, Any]
    test_split_details: Dict[str, Any]
    execution_configuration: Dict[str, Any]
    validation_report: Dict[str, Any]
    six_axis_scores: Dict[str, Any]
    total_score: Optional[float]
    runtime_seconds: Optional[float]
    peak_memory_mb: Optional[float]
    input_hash: Optional[str]
    output_hash: Optional[str]
    audit_hash: Optional[str]
    evaluated_at: str
    status: str
    is_provisional: bool = True
    is_eligible_for_leaderboard: bool = False
    warnings: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_csv(self) -> str:
        """Export high-level metric breakdown and provenance as CSV."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "evaluation_id", "job_id", "submission_id", "team_name", "commit_sha",
            "total_score", "forecast_skill", "event_detection", "generalization",
            "calibration", "robustness", "efficiency", "status", "evaluated_at",
            "is_eligible_for_leaderboard"
        ])
        scores = self.six_axis_scores or {}
        writer.writerow([
            self.evaluation_id,
            self.job_id,
            self.submission_id,
            self.team_name,
            self.commit_sha,
            self.total_score if self.total_score is not None else "N/A",
            scores.get("forecast_skill", {}).get("points_awarded", "N/A"),
            scores.get("event_detection", {}).get("points_awarded", "N/A"),
            scores.get("generalization", {}).get("points_awarded", "N/A"),
            scores.get("calibration_and_uncertainty", {}).get("points_awarded", "N/A"),
            scores.get("robustness", {}).get("points_awarded", "N/A"),
            scores.get("efficiency", {}).get("points_awarded", "N/A"),
            self.status,
            self.evaluated_at,
            self.is_eligible_for_leaderboard,
        ])
        return output.getvalue()


class BenchmarkEvaluationPipeline:
    """
    Coordinates end-to-end evaluation:
    Benchmark Case Loading -> Label Shielded Input Preparation ->
    Phase 5B Worker Execution -> Prediction Validation ->
    Hidden Label Evaluation (6-axis) -> Report Generation -> DB Persistence.
    """

    def __init__(
        self,
        benchmark_root: Optional[Path] = None,
        worker_manager: Optional[WorkerManager] = None,
        db_repository: Optional[Any] = None,
        repository: Optional[Any] = None,
        scoring_evaluator: Optional[HydraForgeEvaluator] = None,
        prediction_validator: Optional[PredictionValidator] = None,
        split_evaluator: Optional[SplitEvaluator] = None,
        scratch_dir: Optional[Path] = None,
    ) -> None:
        self.benchmark_root = Path(benchmark_root or "data/benchmark").resolve()
        self.case_manager = BenchmarkCaseManager(self.benchmark_root)
        self.input_preparer = BenchmarkInputPreparer()
        self.worker_manager = worker_manager or WorkerManager()
        self.db_repo = db_repository or repository
        self.evaluator = scoring_evaluator or HydraForgeEvaluator()
        self.validator = prediction_validator or PredictionValidator()
        self.split_evaluator = split_evaluator or SplitEvaluator()
        self.scratch_dir = Path(scratch_dir or "data/artifacts/pipeline_scratch").resolve()
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    def execute_evaluation(
        self,
        submission_id: str,
        team_name: str,
        repo_dir: Path,
        commit_sha: str,
        discovery_report: DiscoveryReport,
        repository_url: str = "https://github.com/hydraforge/submission",
        eval_splits: Sequence[str] = ("test_a", "test_b", "test_c"),
        resource_limits: Optional[WorkerResourceLimits] = None,
        is_organizer_approved: bool = True,
        is_trusted_developer_fixture: bool = False,
    ) -> ComprehensiveEvaluationReport:
        """
        Execute full end-to-end evaluation pipeline with strict error isolation.
        """
        eval_id = f"eval_{uuid.uuid4().hex[:12]}"
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        warnings: List[str] = []
        failure_reasons: List[str] = []

        limits = resource_limits or WorkerResourceLimits()

        # Initialize tracking job
        job = EvaluationJob(
            job_id=job_id,
            repository_url=repository_url,
            commit_sha=commit_sha,
            contract_version=getattr(discovery_report, "inference_contract_version", "1.0.0"),
            benchmark_version=self.case_manager.config.version,
            execution_backend="WorkerManager (Isolated Container)",
            status=JobStatus.CREATED,
        )

        if self.db_repo:
            try:
                self.db_repo.insert_job(
                    job,
                    submission_metadata={
                        "submission_id": submission_id,
                        "team_name": team_name,
                        "evaluation_id": eval_id,
                    },
                )
            except Exception as e:
                warnings.append(f"DB job insertion note: {e}")

        # 1. Commit SHA Validation
        try:
            clean_sha = validate_commit_sha(commit_sha)
        except Exception as e:
            job.transition_to(JobStatus.REPOSITORY_REJECTED, str(e))
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, commit_sha,
                discovery_report.discovery_id, "REPOSITORY_REJECTED", [str(e)], warnings
            )

        # 2. Confirm Approved Inference Interface
        if discovery_report.interface_status != InterfaceStatus.INTERFACE_IDENTIFIED:
            msg = f"Interface ambiguous or rejected: {discovery_report.interface_status.value}"
            job.transition_to(JobStatus.SUBMISSION_REJECTED, msg)
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "SUBMISSION_REJECTED", [msg], warnings
            )

        # 3. Retrieve and Validate Benchmark Cases
        combined_benchmark_cases: List[BenchmarkInputRecord] = []
        for sp in eval_splits:
            cases = self.case_manager.get_eligible_cases(sp)
            combined_benchmark_cases.extend(cases)

        if not combined_benchmark_cases:
            msg = f"No benchmark cases found for splits: {eval_splits}"
            job.transition_to(JobStatus.SUBMISSION_REJECTED, msg)
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "SUBMISSION_REJECTED", [msg], warnings
            )

        # 4. Prepare Benchmark Input Payload with Zero Temporal & Zero Label Leakage
        job.transition_to(JobStatus.SUBMISSION_VALIDATED, "Preparing benchmark inputs")
        job_scratch = self.scratch_dir / job_id
        job_scratch.mkdir(parents=True, exist_ok=True)

        try:
            sanitized_input_cases, input_hash = self.input_preparer.prepare_inference_inputs(
                combined_benchmark_cases,
                output_file_path=job_scratch / "inputs" / "cases.json",
            )
        except Exception as e:
            job.transition_to(JobStatus.SUBMISSION_REJECTED, f"Input preparation failed: {e}")
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "SUBMISSION_REJECTED", [str(e)], warnings
            )

        # 5. Provision Isolated Worker & Execute Inference
        job.transition_to(JobStatus.EXECUTING, f"Executing inference via WorkerManager")
        context = WorkerContext(
            submission_id=submission_id,
            job_id=job_id,
            commit_sha=clean_sha,
            discovery_report_id=discovery_report.discovery_id,
            benchmark_cases=sanitized_input_cases,
            inference_contract_version=getattr(discovery_report, "inference_contract_version", "1.0.0"),
            resource_limits=limits,
            scratch_dir=job_scratch,
            is_trusted_developer_fixture=is_trusted_developer_fixture,
        )

        worker_result: WorkerExecutionResult = self.worker_manager.run_worker_job(
            context=context,
            discovery_report=discovery_report,
            repo_dir=repo_dir,
        )

        telemetry = worker_result.telemetry
        job.runtime_seconds = telemetry.runtime_seconds
        job.peak_memory_mb = telemetry.peak_memory_mb

        # Check worker execution state
        if worker_result.final_state == WorkerState.SAFE_WORKER_UNAVAILABLE:
            job.transition_to(JobStatus.UNSAFE_EXECUTION_ENVIRONMENT, worker_result.error_message)
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "UNSAFE_EXECUTION_ENVIRONMENT",
                [worker_result.error_message or "SAFE_WORKER_UNAVAILABLE"], warnings,
                input_hash=input_hash, telemetry=telemetry
            )

        if worker_result.final_state in (WorkerState.EXECUTION_FAILED, WorkerState.DEPENDENCY_INSTALLATION_FAILED):
            job.transition_to(JobStatus.EXECUTION_FAILED, worker_result.error_message)
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "EXECUTION_FAILED",
                [worker_result.error_message or "Execution failed"], warnings,
                input_hash=input_hash, telemetry=telemetry
            )

        if worker_result.final_state in (WorkerState.EXECUTION_TIMEOUT, WorkerState.RESOURCE_LIMIT_EXCEEDED):
            job.transition_to(JobStatus.RESOURCE_LIMIT_EXCEEDED, worker_result.error_message)
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "RESOURCE_LIMIT_EXCEEDED",
                [worker_result.error_message or "Resource limit exceeded"], warnings,
                input_hash=input_hash, telemetry=telemetry
            )

        if worker_result.final_state != WorkerState.EXECUTION_SUCCESS or not worker_result.prediction_records:
            job.transition_to(JobStatus.INVALID_PREDICTIONS, worker_result.error_message or "No predictions produced")
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "INVALID_PREDICTIONS",
                [worker_result.error_message or "Empty predictions"], warnings,
                input_hash=input_hash, telemetry=telemetry
            )

        output_hash = telemetry.output_hash
        job.prediction_artifact_hash = output_hash

        # 6. Validate Predictions with PredictionValidator
        job.transition_to(JobStatus.OUTPUT_VALIDATION, "Validating predictions against inference contract")
        val_report: PredictionValidationReport = self.validator.validate(
            predictions=worker_result.prediction_records,
            benchmark_cases=combined_benchmark_cases,
        )

        if not val_report.is_valid:
            msg = f"Prediction validation failed: {len(val_report.errors)} violations."
            job.transition_to(JobStatus.INVALID_PREDICTIONS, msg)
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "INVALID_PREDICTIONS",
                val_report.errors, warnings + val_report.warnings,
                input_hash=input_hash, output_hash=output_hash, telemetry=telemetry,
                val_report_dict=val_report.to_dict()
            )

        # 7. Independent Ground-Truth Evaluation (Organizer Environment Only)
        job.transition_to(JobStatus.SCORING, "Scoring against hidden benchmark ground truth")
        all_gt_labels: List[GroundTruthLabel] = []
        for sp in eval_splits:
            all_gt_labels.extend(self.case_manager.get_reference_labels(sp))

        catchment_meta = self.case_manager.get_catchment_metadata()

        # Six-axis Master Evaluation
        exec_stats = {
            "runtime_seconds": telemetry.runtime_seconds,
            "peak_memory_mb": telemetry.peak_memory_mb,
            "artifact_size_mb": 10.0,
            "cpu_percent": telemetry.cpu_percent,
        }

        try:
            eval_result: EvaluationResult = self.evaluator.evaluate(
                predictions=worker_result.prediction_records,
                ground_truth=all_gt_labels,
                catchment_metadata=catchment_meta,
                execution_stats=exec_stats,
                submission_id=f"{team_name}_{submission_id}",
            )
        except Exception as e:
            job.transition_to(JobStatus.SCORING_FAILED, f"Scoring calculation error: {e}")
            if self.db_repo:
                self.db_repo.update_job(job)
            return self._build_failure_report(
                eval_id, job_id, submission_id, team_name, repository_url, clean_sha,
                discovery_report.discovery_id, "SCORING_FAILED",
                [str(e)], warnings, input_hash=input_hash, output_hash=output_hash, telemetry=telemetry
            )

        # 8. Split-Level Independent Evaluations
        split_summaries: Dict[str, Any] = {}
        if "test_a" in eval_splits:
            sum_a = self.split_evaluator.evaluate_test_a(
                predictions=worker_result.prediction_records,
                ground_truth=all_gt_labels,
                runtime=telemetry.runtime_seconds,
                memory=telemetry.peak_memory_mb,
            )
            split_summaries["test_a"] = sum_a.to_dict()

        if "test_b" in eval_splits:
            sum_b = self.split_evaluator.evaluate_test_b(
                predictions=worker_result.prediction_records,
                ground_truth=all_gt_labels,
                reference_predictions=worker_result.prediction_records,
                reference_ground_truth=all_gt_labels,
                catchment_metadata=catchment_meta,
                runtime=telemetry.runtime_seconds,
                memory=telemetry.peak_memory_mb,
            )
            split_summaries["test_b"] = sum_b.to_dict()

        if "test_c" in eval_splits:
            sum_c = self.split_evaluator.evaluate_test_c(
                predictions=worker_result.prediction_records,
                ground_truth=all_gt_labels,
                clean_predictions=worker_result.prediction_records,
                clean_ground_truth=all_gt_labels,
                runtime=telemetry.runtime_seconds,
                memory=telemetry.peak_memory_mb,
            )
            split_summaries["test_c"] = sum_c.to_dict()

        # 9. Finalize Job State & Leaderboard Eligibility
        job.evaluation_result = eval_result
        job.final_score = round(eval_result.total_score, 2)
        job.score_report_hash = eval_result.audit_hash
        job.transition_to(JobStatus.COMPLETED, f"Scored successfully: {eval_result.total_score:.2f} pts")

        # Leaderboard eligibility rule: must be COMPLETED, valid, and organizer approved
        is_eligible = (
            job.status == JobStatus.COMPLETED
            and val_report.is_valid
            and job.final_score is not None
            and is_organizer_approved
        )

        dim_scores = {
            dim_name: dim.points_awarded
            for dim_name, dim in eval_result.dimensions.items()
        }

        # 10. Persist into Database
        if self.db_repo:
            try:
                self.db_repo.update_job(job)
                self.db_repo.save_evaluation_result(
                    job_id=job.job_id,
                    total_score=eval_result.total_score,
                    dimensions=dim_scores,
                    full_report_json=json.dumps({
                        "evaluation_id": eval_id,
                        "splits": split_summaries,
                        "validation": val_report.to_dict(),
                        "telemetry": asdict(telemetry),
                        "audit_hash": eval_result.audit_hash,
                        "is_eligible_for_leaderboard": is_eligible,
                    }),
                )
            except Exception as e:
                warnings.append(f"DB result saving note: {e}")

        # 11. Compile Comprehensive Report
        six_axis_details = {}
        for dim_name, dim_obj in eval_result.dimensions.items():
            six_axis_details[dim_name] = {
                "points_awarded": round(dim_obj.points_awarded, 2),
                "max_points": dim_obj.max_points,
                "normalized_score": round(dim_obj.normalized_score, 4),
                "is_provisional": dim_obj.is_provisional,
                "notes": dim_obj.notes,
                "raw_metrics": dim_obj.raw_metrics,
            }

        return ComprehensiveEvaluationReport(
            evaluation_id=eval_id,
            job_id=job_id,
            submission_id=submission_id,
            team_name=team_name,
            repository_url=repository_url,
            commit_sha=clean_sha,
            discovery_report_id=discovery_report.discovery_id,
            inference_contract_version=getattr(discovery_report, "inference_contract_version", "1.0.0"),
            benchmark_version=self.case_manager.config.version,
            scoring_version="1.0.0",
            dataset_provenance=self.case_manager.generate_manifest(),
            test_split_details=split_summaries,
            execution_configuration={
                "cpu_limit": limits.cpu_limit,
                "memory_limit_mb": limits.memory_limit_mb,
                "timeout_seconds": limits.timeout_seconds,
                "network_mode": "none",
                "non_root_uid": 10001,
            },
            validation_report=val_report.to_dict(),
            six_axis_scores=six_axis_details,
            total_score=round(eval_result.total_score, 2),
            runtime_seconds=round(telemetry.runtime_seconds, 2) if telemetry.runtime_seconds else None,
            peak_memory_mb=round(telemetry.peak_memory_mb, 1) if telemetry.peak_memory_mb else None,
            input_hash=input_hash,
            output_hash=output_hash,
            audit_hash=eval_result.audit_hash,
            evaluated_at=now_iso,
            status="COMPLETED",
            is_provisional=True,
            is_eligible_for_leaderboard=is_eligible,
            warnings=warnings + eval_result.warnings,
            failure_reasons=[],
        )

    def _build_failure_report(
        self,
        eval_id: str,
        job_id: str,
        submission_id: str,
        team_name: str,
        repository_url: str,
        commit_sha: str,
        discovery_id: str,
        status: str,
        failures: List[str],
        warnings: List[str],
        input_hash: Optional[str] = None,
        output_hash: Optional[str] = None,
        telemetry: Optional[ExecutionTelemetry] = None,
        val_report_dict: Optional[Dict[str, Any]] = None,
    ) -> ComprehensiveEvaluationReport:
        """Construct failure report without leaking hidden benchmark data."""
        return ComprehensiveEvaluationReport(
            evaluation_id=eval_id,
            job_id=job_id,
            submission_id=submission_id,
            team_name=team_name,
            repository_url=repository_url,
            commit_sha=commit_sha,
            discovery_report_id=discovery_id,
            inference_contract_version="1.0.0",
            benchmark_version=self.case_manager.config.version,
            scoring_version="1.0.0",
            dataset_provenance={},
            test_split_details={},
            execution_configuration={},
            validation_report=val_report_dict or {"is_valid": False, "errors": failures},
            six_axis_scores={},
            total_score=None,
            runtime_seconds=telemetry.runtime_seconds if telemetry else None,
            peak_memory_mb=telemetry.peak_memory_mb if telemetry else None,
            input_hash=input_hash,
            output_hash=output_hash,
            audit_hash=None,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            status=status,
            is_provisional=True,
            is_eligible_for_leaderboard=False,
            warnings=warnings,
            failure_reasons=failures,
        )
