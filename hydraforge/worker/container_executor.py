"""
hydraforge/worker/container_executor.py
Isolated Container Execution Backend.
Enforces non-root execution, network airgap, read-only code mounts, and strict fail-closed gating.
Never falls back to unrestricted local execution.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from hydraforge.runner.isolation import scrub_environment, verify_hidden_label_shielding
from hydraforge.worker.execution_monitor import ExecutionMonitor
from hydraforge.worker.resource_enforcer import ResourceEnforcer
from hydraforge.worker.worker_cleanup import WorkerCleanup
from hydraforge.worker.worker_config import DEFAULT_SECURITY_PROFILE, WorkerSecurityProfile
from hydraforge.worker.worker_models import (
    ExecutionTelemetry,
    WorkerResourceLimits,
    WorkerState,
)

# Testing hook for simulating isolated container behavior in unit test suites
_MOCK_CONTAINER_EXECUTOR: Optional[
    Callable[[List[str], Path, Path, Path, WorkerResourceLimits], Tuple[WorkerState, int, str, str, bool]]
] = None


def set_mock_container_executor(
    executor_fn: Optional[
        Callable[[List[str], Path, Path, Path, WorkerResourceLimits], Tuple[WorkerState, int, str, str, bool]]
    ]
) -> None:
    """Register a testing mock for deterministic adversarial test simulation."""
    global _MOCK_CONTAINER_EXECUTOR
    _MOCK_CONTAINER_EXECUTOR = executor_fn


class ContainerExecutionError(Exception):
    """Raised when container launch or lifecycle fails."""
    pass


class ContainerExecutor:
    """Manages Docker/container execution with strict isolation controls."""

    def __init__(
        self,
        security_profile: WorkerSecurityProfile = DEFAULT_SECURITY_PROFILE,
    ) -> None:
        self.security_profile = security_profile

    def is_isolation_backend_available(self) -> bool:
        """Verify Docker daemon or container runtime is operational."""
        if _MOCK_CONTAINER_EXECUTOR is not None:
            return True

        if shutil.which("docker") is None:
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=4
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute_in_container(
        self,
        command_args: List[str],
        repo_dir: Path,
        input_dir: Path,
        output_dir: Path,
        scratch_dir: Path,
        limits: WorkerResourceLimits,
        input_hash: str,
        used_adapter: bool = False,
    ) -> Tuple[WorkerState, ExecutionTelemetry, str]:
        """
        Execute command strictly inside isolated container.
        Returns:
            (worker_state, telemetry, container_name)
        """
        monitor = ExecutionMonitor()
        monitor.start(input_hash=input_hash)

        repo_dir = Path(repo_dir).resolve()
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()
        scratch_dir = Path(scratch_dir).resolve()

        # 1. Label shielding verification
        verify_hidden_label_shielding(input_dir, command_args, {})

        # 2. Check if mock hook is active for tests
        if _MOCK_CONTAINER_EXECUTOR is not None:
            state, code, stdout, stderr, timed_out = _MOCK_CONTAINER_EXECUTOR(
                command_args, repo_dir, input_dir, output_dir, limits
            )
            telemetry = monitor.finish(
                exit_code=code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                termination_reason="Mock execution finished" if not timed_out else "Execution timed out",
                peak_memory_mb=128.0,
                cpu_usage_percent=45.0
            )
            return state, telemetry, "mock_container"

        # 3. Fail-Closed Check: Verify container daemon is active
        if not self.is_isolation_backend_available():
            telemetry = monitor.finish(
                exit_code=-1,
                stderr="Container daemon is offline. Untrusted code cannot be executed.",
                termination_reason="SAFE_WORKER_UNAVAILABLE"
            )
            return WorkerState.SAFE_WORKER_UNAVAILABLE, telemetry, ""

        # 4. Formulate hardened Docker command
        container_name = f"hydraforge_worker_{uuid.uuid4().hex[:12]}"
        resource_args = ResourceEnforcer.build_docker_resource_args(limits)

        docker_cmd = [
            "docker", "run",
            "--name", container_name,
            "--rm",
            "--network", self.security_profile.network_mode,
            "--user", self.security_profile.container_user,
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
        ]
        docker_cmd.extend(resource_args)

        # Mounts: Input is RO, Repo is RO, Output is RW
        docker_cmd.extend([
            "-v", f"{input_dir}:{self.security_profile.container_input_dir}:ro",
            "-v", f"{repo_dir}:{self.security_profile.container_workspace_dir}:ro",
            "-v", f"{output_dir}:{self.security_profile.container_output_dir}:rw",
        ])

        # If an adapter shim was synthesized in scratch, mount it read-only
        if used_adapter and (scratch_dir / "hydraforge_shim.py").exists():
            docker_cmd.extend([
                "-v", f"{scratch_dir / 'hydraforge_shim.py'}:/tmp/hydraforge_shim.py:ro"
            ])

        docker_cmd.extend([
            "-w", self.security_profile.container_workspace_dir,
            self.security_profile.prewarmed_ml_image,
        ])
        docker_cmd.extend(command_args)

        # 5. Execute container with monitoring and timeout
        timed_out = False
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=limits.timeout_seconds,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            WorkerCleanup.cleanup_container(container_name)
            exit_code = -9
            stdout = e.stdout or ""
            stderr = (e.stderr or "") + f"\nWorker killed: execution exceeded timeout of {limits.timeout_seconds}s."
        except Exception as e:
            WorkerCleanup.cleanup_container(container_name)
            exit_code = -1
            stdout = ""
            stderr = f"Subprocess launch error: {str(e)}"

        # 6. Map to WorkerState
        if timed_out:
            state = WorkerState.EXECUTION_TIMEOUT
        elif exit_code == 0:
            state = WorkerState.EXECUTION_SUCCESS
        elif exit_code == 137:  # OOM killer standard exit code
            state = WorkerState.RESOURCE_LIMIT_EXCEEDED
        else:
            state = WorkerState.EXECUTION_FAILED

        telemetry = monitor.finish(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            termination_reason=state.value,
        )

        return state, telemetry, container_name

