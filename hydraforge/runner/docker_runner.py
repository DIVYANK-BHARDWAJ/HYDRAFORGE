"""Hardened Containerized Submission Runner (Docker).

Enforces strict isolation, non-root execution, network cutoff, and fail-closed security.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from hydraforge.runner.errors import (
    ExecutionTimeoutError,
    ResourceLimitExceededError,
    RunnerExecutionError,
    UnsafeExecutionEnvironmentError,
)
from hydraforge.runner.interface import BaseRunner, RunnerExecutionResult
from hydraforge.runner.isolation import scrub_environment, verify_hidden_label_shielding


class DockerRunner(BaseRunner):
    """Hardened Docker execution backend for untrusted participant submissions."""

    def __init__(
        self,
        image_name: str = "hydraforge/runner:1.0.0",
        cpu_limit: float = 2.0,
        memory_limit_mb: float = 4096.0,
        pids_limit: int = 100
    ) -> None:
        self.image_name = image_name
        self.cpu_limit = cpu_limit
        self.memory_limit_mb = memory_limit_mb
        self.pids_limit = pids_limit

    def is_docker_daemon_available(self) -> bool:
        """Check if Docker CLI can communicate with an active Docker daemon."""
        if shutil.which("docker") is None:
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If server API failed to connect, exit code is non-zero
            return res.returncode == 0
        except Exception:
            return False

    def run_submission(
        self,
        repo_dir: Path,
        input_dir: Path,
        output_dir: Path,
        entrypoint: str,
        timeout_seconds: int = 300,
        max_memory_mb: float = 4096.0,
        is_trusted: bool = False
    ) -> RunnerExecutionResult:
        """Execute submission inside a hardened, isolated Docker container."""
        # Critical Fail-Closed Rule
        if not self.is_docker_daemon_available():
            raise UnsafeExecutionEnvironmentError(
                "UNSAFE_EXECUTION_ENVIRONMENT: Docker daemon is offline or inaccessible. "
                "Production execution of untrusted submissions is blocked. "
                "Local unconfined fallback is strictly forbidden for untrusted code."
            )

        repo_dir = Path(repo_dir).resolve()
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Label shielding verification
        verify_hidden_label_shielding(input_dir, [entrypoint], {})

        docker_args = [
            "docker", "run",
            "--rm",
            "--network", "none",                       # Network disabled
            "--read-only",                             # Read-only root filesystem
            "--user", "1000:1000",                     # Non-root user
            "--cpus", str(self.cpu_limit),             # CPU core ceiling
            "--memory", f"{int(self.memory_limit_mb)}m", # RAM limit
            "--pids-limit", str(self.pids_limit),      # Fork-bomb protection
            "--cap-drop", "ALL",                       # Drop all Linux capabilities
            "--security-opt", "no-new-privileges",     # Prevent privilege escalation
            "-v", f"{input_dir}:/inputs:ro",           # Read-only inputs
            "-v", f"{repo_dir}:/workspace:ro",         # Read-only participant code
            "-v", f"{output_dir}:/outputs:rw",         # Writable isolated output volume
            "-w", "/workspace",
            self.image_name,
            "python", entrypoint,
            "--inputs", "/inputs/inputs.json",
            "--outputs", "/outputs/predictions.json"
        ]

        import time
        start_time = time.perf_counter()

        try:
            proc = subprocess.run(
                docker_args,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            runtime = time.perf_counter() - start_time
            is_success = proc.returncode == 0

            return RunnerExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                runtime_seconds=runtime,
                peak_memory_mb=None,  # Reported via container stats if enabled
                output_dir=output_dir,
                is_success=is_success,
                failure_reason=None if is_success else f"Container exited with code {proc.returncode}"
            )
        except subprocess.TimeoutExpired as e:
            raise ExecutionTimeoutError(
                f"Container execution timed out after {timeout_seconds} seconds."
            )
        except Exception as e:
            raise RunnerExecutionError(f"Container execution failed: {e}")

