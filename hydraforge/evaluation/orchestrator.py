"""Master Evaluation Orchestrator."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from hydraforge.benchmark.loader import OrganizerBenchmarkLoader, ParticipantBenchmarkLoader
from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.metrics.evaluator import HydraForgeEvaluator
from hydraforge.runner.errors import (
    ExecutionTimeoutError,
    ResourceLimitExceededError,
    RunnerError,
    UnsafeExecutionEnvironmentError,
)
from hydraforge.runner.interface import BaseRunner
from hydraforge.runner.docker_runner import DockerRunner
from hydraforge.runner.local_test_runner import LocalTestRunner
from hydraforge.schema import PredictionRecord, ValidationError, validate_predictions
from hydraforge.submission.manifest_loader import load_submission_manifest
from hydraforge.submission.repository import (
    RepositoryIntake,
    RepositorySecurityError,
    validate_commit_sha,
    validate_repository_url,
)
from hydraforge.submission.validation import validate_submission_package


class EvaluationOrchestrator:
    """Manages full lifecycle execution, validation, and scoring of submissions."""

    def __init__(
        self,
        benchmark_root: Path,
        runner: Optional[BaseRunner] = None,
        scratch_dir: Optional[Path] = None
    ) -> None:
        self.benchmark_root = Path(benchmark_root).resolve()
        self.runner = runner or DockerRunner()
        self.scratch_dir = Path(scratch_dir or "data/artifacts/eval_scratch").resolve()
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        self.evaluator = HydraForgeEvaluator()

    def run_job(
        self,
        repo_source: str,  # URL or local path for trusted test
        commit_sha: str,
        is_trusted: bool = False,
        timeout_seconds: int = 300,
        eval_splits: Sequence[str] = ("test_a", "test_b", "test_c")
    ) -> EvaluationJob:
        """Execute end-to-end evaluation with strict state transitions and error capture."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        backend_name = self.runner.__class__.__name__

        job = EvaluationJob(
            job_id=job_id,
            repository_url=str(repo_source),
            commit_sha=commit_sha,
            execution_backend=backend_name,
            status=JobStatus.CREATED
        )

        job_scratch = self.scratch_dir / job_id
        job_scratch.mkdir(parents=True, exist_ok=True)
        repo_dest = job_scratch / "repo"

        try:
            # 1. Repository Intake & Validation
            if is_trusted and Path(repo_source).is_dir():
                # Trusted local development fixture
                repo_dest = Path(repo_source)
                job.transition_to(JobStatus.REPOSITORY_VALIDATED, "Trusted local fixture accepted.")
            else:
                # Untrusted participant repository
                intake = RepositoryIntake()
                provenance = intake.checkout(
                    repo_url=repo_source,
                    commit_sha=commit_sha,
                    destination_dir=repo_dest
                )
                job.transition_to(JobStatus.REPOSITORY_VALIDATED, f"Cloned SHA {provenance.commit_sha}")

            # 2. Submission & Manifest Validation
            manifest = validate_submission_package(repo_dest)
            job.transition_to(JobStatus.SUBMISSION_VALIDATED, f"Manifest '{manifest.submission_name}' validated.")

            # 3. Queue & Execute
            job.transition_to(JobStatus.QUEUED, f"Queued for {backend_name} execution.")

            # Load participant inputs for all evaluated splits into combined input volume
            p_loader = ParticipantBenchmarkLoader(self.benchmark_root / "inputs")
            combined_inputs = []
            for sp in eval_splits:
                combined_inputs.extend(p_loader.load_inputs(sp))

            exec_inputs_dir = job_scratch / "inputs"
            exec_outputs_dir = job_scratch / "outputs"
            exec_inputs_dir.mkdir(parents=True, exist_ok=True)
            exec_outputs_dir.mkdir(parents=True, exist_ok=True)

            with open(exec_inputs_dir / "inputs.json", "w", encoding="utf-8") as f:
                json.dump([asdict(inp) if hasattr(inp, "__dataclass_fields__") else inp.__dict__ for inp in combined_inputs], f, indent=2)

            job.transition_to(JobStatus.EXECUTING, f"Running {manifest.entrypoint} under {backend_name}")

            run_result = self.runner.run_submission(
                repo_dir=repo_dest,
                input_dir=exec_inputs_dir,
                output_dir=exec_outputs_dir,
                entrypoint=manifest.entrypoint,
                timeout_seconds=timeout_seconds,
                is_trusted=is_trusted
            )

            job.runtime_seconds = run_result.runtime_seconds
            job.peak_memory_mb = run_result.peak_memory_mb

            if not run_result.is_success:
                job.transition_to(JobStatus.EXECUTION_FAILED, run_result.failure_reason or "Non-zero exit")
                return job

            # 4. Output Prediction Validation
            job.transition_to(JobStatus.OUTPUT_VALIDATION, "Validating predictions.json schema")
            predictions_file = exec_outputs_dir / "predictions.json"
            if not predictions_file.exists():
                job.transition_to(JobStatus.INVALID_PREDICTIONS, "Output file 'predictions.json' was not created.")
                return job

            from hydraforge.benchmark.provenance import compute_file_sha256
            job.prediction_artifact_hash = compute_file_sha256(predictions_file)

            with open(predictions_file, "r", encoding="utf-8") as f:
                raw_preds = json.load(f)

            if not isinstance(raw_preds, list):
                job.transition_to(JobStatus.INVALID_PREDICTIONS, "predictions.json root must be a list.")
                return job

            prediction_records: List[PredictionRecord] = []
            for item in raw_preds:
                prediction_records.append(PredictionRecord.from_dict(item))

            # Strict contract validation: check for missing, duplicate, or unknown cases
            validate_predictions(prediction_records, combined_inputs)

            # 5. Scoring (Organizer-side only with hidden ground-truth labels)
            job.transition_to(JobStatus.SCORING, "Scoring against hidden benchmark ground truth.")
            o_loader = OrganizerBenchmarkLoader(self.benchmark_root)
            ground_truth_labels = []
            for sp in eval_splits:
                ground_truth_labels.extend(o_loader.load_ground_truth(sp))

            # Load catchment metadata if present
            catchment_meta_path = self.benchmark_root / "metadata" / "catchments.json"
            catchment_meta = {}
            if catchment_meta_path.exists():
                with open(catchment_meta_path, "r", encoding="utf-8") as f:
                    catchment_meta = json.load(f)

            execution_stats = {
                "runtime_seconds": job.runtime_seconds,
                "peak_memory_mb": job.peak_memory_mb,
                "artifact_size_mb": 10.0
            }

            eval_result = self.evaluator.evaluate(
                predictions=prediction_records,
                ground_truth=ground_truth_labels,
                catchment_metadata=catchment_meta,
                execution_stats=execution_stats,
                submission_id=f"{manifest.team_name}_{manifest.submission_name}"
            )

            job.evaluation_result = eval_result
            job.final_score = eval_result.total_score
            job.score_report_hash = eval_result.audit_hash
            job.transition_to(JobStatus.COMPLETED, f"Scored successfully: {eval_result.total_score:.2f} pts")
            return job

        except RepositorySecurityError as e:
            job.transition_to(JobStatus.REPOSITORY_REJECTED, str(e))
            return job
        except ValidationError as e:
            job.transition_to(JobStatus.SUBMISSION_REJECTED, str(e))
            return job
        except UnsafeExecutionEnvironmentError as e:
            job.transition_to(JobStatus.UNSAFE_EXECUTION_ENVIRONMENT, str(e))
            return job
        except ExecutionTimeoutError as e:
            job.transition_to(JobStatus.RESOURCE_LIMIT_EXCEEDED, str(e))
            return job
        except ResourceLimitExceededError as e:
            job.transition_to(JobStatus.RESOURCE_LIMIT_EXCEEDED, str(e))
            return job
        except Exception as e:
            job.transition_to(JobStatus.EXECUTION_FAILED, f"Unexpected failure: {e}")
            return job
