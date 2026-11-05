"""Security tests for hidden-label isolation, path traversal, and job failure invariants."""

from pathlib import Path
import pytest

from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.evaluation.orchestrator import EvaluationOrchestrator
from hydraforge.runner.errors import UnsafeExecutionEnvironmentError
from hydraforge.runner.isolation import (
    LabelLeakageSecurityViolation,
    scrub_environment,
    verify_hidden_label_shielding,
)
from hydraforge.runner.local_test_runner import LocalTestRunner
from hydraforge.submission.repository import RepositoryIntake, RepositorySecurityError
from hydraforge.submission.validation import validate_submission_package


def test_hidden_label_shielding_detects_label_exposure():
    # Input path pointing to labels directory
    with pytest.raises(LabelLeakageSecurityViolation, match="Participant input path points to organizer label storage"):
        verify_hidden_label_shielding(Path("data/benchmark/labels/test_a"), [], {})

    # Arguments exposing labels
    with pytest.raises(LabelLeakageSecurityViolation, match="Command-line arguments expose hidden ground-truth labels"):
        verify_hidden_label_shielding(Path("data/benchmark/inputs/test_a"), ["--ground-truth", "data/labels.json"], {})

    # Environment variable exposing labels
    with pytest.raises(LabelLeakageSecurityViolation, match="Environment variable .* exposes hidden label path"):
        verify_hidden_label_shielding(
            Path("data/benchmark/inputs/test_a"),
            [],
            {"HIDDEN_LABELS_PATH": "C:/data/labels/test_a/labels.json"}
        )


def test_environment_scrubbing():
    dirty_env = {
        "PATH": "C:\\Windows;C:\\Python",
        "AWS_SECRET_ACCESS_KEY": "AKIA_SECRET_12345",
        "GITHUB_TOKEN": "ghp_super_secret_token",
        "DATABASE_PASSWORD": "super_secret_db_pass",
        "HTTP_PROXY": "http://corporate-proxy:8080",
        "NORMAL_SETTING": "standard_val"
    }
    clean = scrub_environment(dirty_env)
    assert "AWS_SECRET_ACCESS_KEY" not in clean
    assert "GITHUB_TOKEN" not in clean
    assert "DATABASE_PASSWORD" not in clean
    assert "HTTP_PROXY" not in clean
    assert clean["NORMAL_SETTING"] == "standard_val"
    assert clean["HYDRAFORGE_ISOLATED"] == "1"


def test_symlink_pointing_outside_repo(tmp_path: Path):
    outside_secret = tmp_path / "secret.txt"
    outside_secret.write_text("ORGANIZER_SECRET_DATA", encoding="utf-8")

    repo_dir = tmp_path / "fake_repo"
    repo_dir.mkdir()
    symlink_path = repo_dir / "bad_link.txt"
    try:
        symlink_path.symlink_to(outside_secret)
        intake = RepositoryIntake()
        with pytest.raises(RepositorySecurityError, match="Insecure symlink detected"):
            intake.inspect_tree_safety(repo_dir)
    except OSError:
        # On some Windows configurations, creating symlinks requires privileges; skip gracefully
        pass


def test_failed_job_never_receives_score():
    job = EvaluationJob(
        job_id="job_fail_test",
        repository_url="https://github.com/team/model",
        commit_sha="a" * 40
    )
    job.transition_to(JobStatus.EXECUTION_FAILED, "Process crashed with SIGSEGV")
    assert job.status == JobStatus.EXECUTION_FAILED
    # INVARIANT: Failed jobs MUST NEVER hold a score!
    assert job.final_score is None


def test_orchestrator_end_to_end_trusted_mock_job(tmp_path: Path):
    mock_dir = Path("tests/fixtures/mock_submission").resolve()
    orchestrator = EvaluationOrchestrator(
        benchmark_root=Path("data/benchmark"),
        runner=LocalTestRunner(trusted_test_only=True),
        scratch_dir=tmp_path / "scratch"
    )

    job = orchestrator.run_job(
        repo_source=str(mock_dir),
        commit_sha="0123456789abcdef0123456789abcdef01234567",
        is_trusted=True
    )

    assert job.status == JobStatus.COMPLETED
    assert job.final_score is not None
    assert 0.0 <= job.final_score <= 100.0
    assert job.evaluation_result is not None
    assert job.score_report_hash is not None

