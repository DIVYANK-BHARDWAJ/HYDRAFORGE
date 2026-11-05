"""Local Subprocess Test Runner (TRUSTED_TEST_ONLY).

WARNING:
This runner is designed EXCLUSIVELY for trusted, developer-authored unit test fixtures.
It does NOT provide container-level security boundaries.
It strictly refuses untrusted participant submissions and must NEVER be used to
generate official leaderboard scores.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from hydraforge.runner.errors import (
    ExecutionTimeoutError,
    ResourceLimitExceededError,
    RunnerExecutionError,
    UnsafeExecutionEnvironmentError,
)
from hydraforge.runner.interface import BaseRunner, RunnerExecutionResult
from hydraforge.runner.isolation import scrub_environment, verify_hidden_label_shielding
from hydraforge.runner.resource_monitor import run_process_with_monitoring


class LocalTestRunner(BaseRunner):
    """Subprocess runner for trusted developer test fixtures only."""

    def __init__(self, trusted_test_only: bool = True) -> None:
        if not trusted_test_only:
            raise UnsafeExecutionEnvironmentError(
                "LocalTestRunner cannot be initialized without trusted_test_only=True."
            )
        self.trusted_test_only = True

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
        """Execute a trusted test script with resource monitoring."""
        # Critical Safety Gate: Refuse untrusted participant code
        if not is_trusted:
            raise UnsafeExecutionEnvironmentError(
                "UNSAFE_EXECUTION_ENVIRONMENT: LocalTestRunner strictly refuses untrusted submissions. "
                "Participant repositories must be evaluated via hardened container backends."
            )

        repo_dir = Path(repo_dir).resolve()
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Enforce that trusted runner ONLY accepts developer-created fixtures in tests/fixtures
        workspace_root = Path.cwd().resolve()
        fixtures_dir = (workspace_root / "tests" / "fixtures").resolve()
        try:
            repo_dir.relative_to(fixtures_dir)
        except ValueError:
            raise UnsafeExecutionEnvironmentError(
                f"UNSAFE_EXECUTION_ENVIRONMENT: The trusted runner is strictly restricted to developer-created test fixtures "
                f"within '{fixtures_dir}'. Arbitrary participant repositories cannot be executed with --trusted."
            )

        entrypoint_path = repo_dir / entrypoint
        if not entrypoint_path.exists():
            raise RunnerExecutionError(f"Entrypoint script not found: '{entrypoint_path}'")

        inputs_file = input_dir / "inputs.json"
        outputs_file = output_dir / "predictions.json"

        # Verify hidden labels are not exposed
        cmd_args = [
            sys.executable,
            str(entrypoint_path),
            "--inputs", str(inputs_file),
            "--outputs", str(outputs_file)
        ]
        clean_env = scrub_environment()
        verify_hidden_label_shielding(input_dir, cmd_args, clean_env)

        # Run process tree with monitoring
        exit_code, stdout, stderr, runtime, peak_mb = run_process_with_monitoring(
            args=cmd_args,
            cwd=str(repo_dir),
            env=clean_env,
            timeout_seconds=timeout_seconds,
            max_memory_mb=max_memory_mb
        )

        is_success = (exit_code == 0)
        failure_reason = None if is_success else f"Process exited with non-zero status code: {exit_code}"

        return RunnerExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            runtime_seconds=runtime,
            peak_memory_mb=peak_mb,
            output_dir=output_dir,
            is_success=is_success,
            failure_reason=failure_reason
        )

