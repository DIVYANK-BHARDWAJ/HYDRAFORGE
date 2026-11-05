"""Unit tests for submission execution runners and resource monitoring."""

import json
from pathlib import Path
import pytest

from hydraforge.evaluation.orchestrator import EvaluationOrchestrator
from hydraforge.runner.docker_runner import DockerRunner
from hydraforge.runner.errors import (
    ExecutionTimeoutError,
    UnsafeExecutionEnvironmentError,
)
from hydraforge.runner.local_test_runner import LocalTestRunner
from hydraforge.runner.resource_monitor import run_process_with_monitoring


def test_docker_runner_fail_closed_when_daemon_offline():
    runner = DockerRunner()
    # The host docker daemon is currently offline
    if not runner.is_docker_daemon_available():
        with pytest.raises(UnsafeExecutionEnvironmentError, match="UNSAFE_EXECUTION_ENVIRONMENT"):
            runner.run_submission(
                repo_dir=Path("."),
                input_dir=Path("."),
                output_dir=Path("."),
                entrypoint="test.py"
            )


def test_local_test_runner_refuses_untrusted_submission():
    runner = LocalTestRunner(trusted_test_only=True)
    # is_trusted=False must be rejected immediately!
    with pytest.raises(UnsafeExecutionEnvironmentError, match="strictly refuses untrusted submissions"):
        runner.run_submission(
            repo_dir=Path("."),
            input_dir=Path("."),
            output_dir=Path("."),
            entrypoint="test.py",
            is_trusted=False
        )


def test_local_test_runner_runs_trusted_mock_submission(tmp_path: Path):
    mock_dir = Path("tests/fixtures/mock_submission").resolve()
    assert mock_dir.exists()

    input_dir = tmp_path / "inputs"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    output_dir.mkdir()

    # Create dummy input record
    sample_input = [{
        "case_id": "test_c1",
        "catchment_id": "B1",
        "forecast_origin": "2026-01-01T00:00:00Z",
        "horizons": [1, 3],
        "discharge_history": [10.0, 12.0]
    }]
    with open(input_dir / "inputs.json", "w", encoding="utf-8") as f:
        json.dump(sample_input, f)

    runner = LocalTestRunner(trusted_test_only=True)
    res = runner.run_submission(
        repo_dir=mock_dir,
        input_dir=input_dir,
        output_dir=output_dir,
        entrypoint="run_forecast.py",
        is_trusted=True
    )

    assert res.is_success
    assert res.exit_code == 0
    assert (output_dir / "predictions.json").exists()
    assert res.runtime_seconds is not None
    assert res.runtime_seconds > 0.0


def test_resource_monitor_timeout_enforcement():
    # Execute a command that sleeps longer than timeout
    import sys
    py_code = "import time; time.sleep(5)"
    with pytest.raises(ExecutionTimeoutError, match="exceeded timeout limit"):
        run_process_with_monitoring(
            args=[sys.executable, "-c", py_code],
            cwd=".",
            env={},
            timeout_seconds=1,  # 1 second timeout
            poll_interval_sec=0.05
        )

