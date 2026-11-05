"""
hydraforge/worker/worker_manager.py
Master Orchestrator for Secure Model Execution and Isolated Worker Lifecycle.
Integrates Phase 5A Discovery Reports, prepares benchmark inputs without labels,
enforces isolation boundaries, executes containers, and safely collects predictions.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hydraforge.discovery.discovery_models import DiscoveryReport, InterfaceStatus
from hydraforge.runner.isolation import verify_hidden_label_shielding
from hydraforge.schema import PredictionRecord, ValidationError
from hydraforge.submission.repository import validate_commit_sha
from hydraforge.worker.command_builder import CommandBuilder, UnresolvedInterfaceError
from hydraforge.worker.container_executor import ContainerExecutor
from hydraforge.worker.dependency_manager import DependencyManager
from hydraforge.worker.output_collector import OutputCollector, OutputCollectionSecurityError
from hydraforge.worker.worker_cleanup import WorkerCleanup
from hydraforge.worker.worker_models import (
    ExecutionTelemetry,
    WorkerContext,
    WorkerExecutionResult,
    WorkerState,
)


class WorkerManager:
    """Coordinates isolated execution of authorized participant submissions."""

    def __init__(
        self,
        container_executor: Optional[ContainerExecutor] = None,
        command_builder: Optional[CommandBuilder] = None,
        dependency_manager: Optional[DependencyManager] = None,
        output_collector: Optional[OutputCollector] = None,
    ) -> None:
        self.container_executor = container_executor or ContainerExecutor()
        self.command_builder = command_builder or CommandBuilder()
        self.dependency_manager = dependency_manager or DependencyManager()
        self.output_collector = output_collector or OutputCollector()

    def run_worker_job(
        self,
        context: WorkerContext,
        discovery_report: DiscoveryReport,
        repo_dir: Path,
    ) -> WorkerExecutionResult:
        """
        Execute end-to-end isolated worker workflow.
        Returns immutable WorkerExecutionResult with telemetry and predictions.
        """
        # 1. Validate immutable commit reference
        try:
            clean_sha = validate_commit_sha(context.commit_sha)
        except Exception as e:
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.EXECUTION_FAILED,
                telemetry=ExecutionTelemetry(),
                error_message=f"Invalid commit reference: {str(e)}",
                cleanup_success=True,
            )

        repo_dir = Path(repo_dir).resolve()
        scratch_base = context.scratch_dir or Path(f"data/artifacts/worker_scratch/{context.job_id}")
        scratch_base = scratch_base.resolve()

        inputs_dir = scratch_base / "inputs"
        outputs_dir = scratch_base / "outputs"
        shim_dir = scratch_base / "shim"

        inputs_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)
        shim_dir.mkdir(parents=True, exist_ok=True)

        input_cases_file = inputs_dir / "cases.json"
        telemetry = ExecutionTelemetry()

        # 2. Prepare benchmark input cases (without hidden reference labels)
        try:
            # Assert label shielding
            verify_hidden_label_shielding(inputs_dir, [], {})

            # Format benchmark cases into canonical contract input format
            payload = {"cases": context.benchmark_cases}
            input_bytes = json.dumps(payload, indent=2).encode("utf-8")
            input_cases_file.write_bytes(input_bytes)

            input_hash = hashlib.sha256(input_bytes).hexdigest()
        except Exception as e:
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.EXECUTION_FAILED,
                telemetry=telemetry,
                error_message=f"Failed to deliver benchmark inputs: {str(e)}",
                cleanup_success=True,
            )

        # 3. Check Discovery Report and Interface Status
        if discovery_report.interface_status != InterfaceStatus.INTERFACE_IDENTIFIED:
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.EXECUTION_FAILED,
                telemetry=telemetry,
                error_message=(
                    f"Execution blocked: Discovery report interface status is "
                    f"'{discovery_report.interface_status.value}'. Organizer review required."
                ),
                cleanup_success=True,
            )

        # 4. Validate dependencies
        deps_ok, plan, dep_err = self.dependency_manager.evaluate_dependencies(discovery_report)
        if not deps_ok:
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.DEPENDENCY_INSTALLATION_FAILED,
                telemetry=telemetry,
                error_message=f"Dependency safety evaluation failed: {dep_err}",
                cleanup_success=True,
            )

        # 5. Build validated command & adapter
        try:
            cmd_args, used_adapter = self.command_builder.build_execution_command(
                report=discovery_report,
                scratch_dir=shim_dir,
            )
        except UnresolvedInterfaceError as e:
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.EXECUTION_FAILED,
                telemetry=telemetry,
                error_message=f"Command construction failed: {str(e)}",
                cleanup_success=True,
            )

        # 6. Check container isolation availability
        if not self.container_executor.is_isolation_backend_available():
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            telemetry.termination_reason = "SAFE_WORKER_UNAVAILABLE"
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.SAFE_WORKER_UNAVAILABLE,
                telemetry=telemetry,
                error_message=(
                    "SAFE_WORKER_UNAVAILABLE: Container isolation backend is unavailable. "
                    "Fail-closed policy strictly forbids unisolated execution of untrusted code."
                ),
                cleanup_success=True,
            )

        # 7. Execute in container
        worker_state, telemetry, container_name = self.container_executor.execute_in_container(
            command_args=cmd_args,
            repo_dir=repo_dir,
            input_dir=inputs_dir,
            output_dir=outputs_dir,
            scratch_dir=shim_dir,
            limits=context.resource_limits,
            input_hash=input_hash,
            used_adapter=used_adapter,
        )

        # If execution did not succeed, return failure telemetry immediately
        if worker_state != WorkerState.EXECUTION_SUCCESS:
            WorkerCleanup.cleanup_container(container_name)
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=worker_state,
                telemetry=telemetry,
                error_message=telemetry.stderr or f"Execution halted with state {worker_state.value}",
                cleanup_success=True,
            )

        # 8. Collect and validate output predictions
        try:
            predictions, output_hash, warnings = self.output_collector.collect_predictions(outputs_dir)
            telemetry.output_hash = output_hash
        except (OutputCollectionSecurityError, ValidationError, FileNotFoundError) as e:
            WorkerCleanup.cleanup_container(container_name)
            WorkerCleanup.cleanup_scratch_directory(scratch_base)
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.OUTPUT_COLLECTION_FAILED,
                telemetry=telemetry,
                error_message=f"Output collection failed: {str(e)}",
                cleanup_success=True,
            )

        # 9. Cleanup disposable containers and temporary scratch files
        cleanup_ok_c = WorkerCleanup.cleanup_container(container_name)
        cleanup_ok_s, _ = WorkerCleanup.cleanup_scratch_directory(scratch_base)

        return WorkerExecutionResult(
            job_id=context.job_id,
            submission_id=context.submission_id,
            final_state=WorkerState.EXECUTION_SUCCESS,
            telemetry=telemetry,
            prediction_records=predictions,
            error_message=None,
            cleanup_success=(cleanup_ok_c and cleanup_ok_s),
        )

