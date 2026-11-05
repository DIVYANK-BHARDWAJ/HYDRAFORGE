"""
tests/test_database.py
Comprehensive unit tests for the HYDRAFORGE SQLite database layer.
Tests connection initialization, schema migrations, evaluation job persistence,
results storage, log/report retrieval, overview stats, and leaderboard queries.
"""

import json
import tempfile
import pytest
from pathlib import Path

from hydraforge.database.connection import DatabaseManager
from hydraforge.database.migrations import apply_migrations
from hydraforge.database.repository import EvaluationRepository
from hydraforge.evaluation.job import EvaluationJob, JobStatus


@pytest.fixture
def temp_db():
    """Create a temporary database file and initialize migrations."""
    import gc
    tmp_dir = tempfile.TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "test_hydraforge.db"
    db_mgr = DatabaseManager(db_path=db_path)
    apply_migrations(db_mgr)
    repo = EvaluationRepository(db_mgr)
    try:
        yield repo, db_mgr
    finally:
        del repo
        del db_mgr
        gc.collect()
        try:
            tmp_dir.cleanup()
        except Exception:
            pass


def test_database_migrations_applied(temp_db):
    """Test that migrations create all required tables and record schema version."""
    repo, db_mgr = temp_db
    with db_mgr.connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cur.fetchall()]
        assert "evaluation_jobs" in tables
        assert "evaluation_results" in tables
        assert "system_metadata" in tables

        cur.execute("SELECT metadata_value FROM system_metadata WHERE metadata_key = 'schema_version';")
        row = cur.fetchone()
        assert row is not None
        assert int(row["metadata_value"]) >= 1


def test_job_create_and_get(temp_db):
    """Test creating an evaluation job record and retrieving it."""
    repo, _ = temp_db
    job = EvaluationJob(
        job_id="job-test-001",
        repository_url="https://github.com/hydra-team/test-model.git",
        commit_sha="a" * 40,
        status=JobStatus.CREATED,
        execution_backend="docker",
    )

    metadata = {
        "team_name": "RiverWatchers",
        "submission_name": "HydroTransformer-v1",
    }

    repo.insert_job(job, submission_metadata=metadata)

    retrieved = repo.get_job("job-test-001")
    assert retrieved is not None
    assert retrieved["job_id"] == "job-test-001"
    assert retrieved["submission_metadata"]["team_name"] == "RiverWatchers"
    assert retrieved["job_status"] == JobStatus.CREATED.value
    assert retrieved["execution_backend"] == "docker"


def test_job_update_lifecycle(temp_db):
    """Test updating job state, completion timestamps, and final score."""
    repo, _ = temp_db
    job = EvaluationJob(
        job_id="job-test-002",
        repository_url="https://github.com/hydra-team/test-model.git",
        commit_sha="b" * 40,
        status=JobStatus.CREATED,
    )
    repo.insert_job(job)

    # Transition to executing
    job.transition_to(JobStatus.EXECUTING)
    repo.update_job(job)

    j1 = repo.get_job("job-test-002")
    assert j1["job_status"] == JobStatus.EXECUTING.value
    assert j1["started_at"] is not None

    # Transition to completed
    job.transition_to(JobStatus.COMPLETED)
    job.final_score = 85.5
    job.score_report_hash = "f" * 64
    repo.update_job(job)

    j2 = repo.get_job("job-test-002")
    assert j2["job_status"] == JobStatus.COMPLETED.value
    assert j2["final_score"] == 85.5
    assert j2["report_hash"] == "f" * 64
    assert j2["completed_at"] is not None


def test_save_and_get_evaluation_result(temp_db):
    """Test saving a full 6-dimensional evaluation result and retrieving it."""
    repo, _ = temp_db
    job = EvaluationJob(
        job_id="job-test-003",
        repository_url="https://github.com/hydra-team/test-model.git",
        commit_sha="c" * 40,
        status=JobStatus.COMPLETED,
    )
    job.final_score = 78.50
    repo.insert_job(job)

    dimensions = {
        "forecast_skill": 20.0,
        "event_detection": 21.0,
        "generalization": 16.0,
        "calibration_and_uncertainty": 12.5,
        "robustness": 6.0,
        "efficiency": 3.0,
    }
    report_json = json.dumps({
        "job_id": "job-test-003",
        "total_score": 78.50,
        "dimensions": dimensions,
    })

    result_id = repo.save_evaluation_result(
        job_id="job-test-003",
        total_score=78.50,
        dimensions=dimensions,
        full_report_json=report_json,
    )
    assert result_id.startswith("res_")

    retrieved = repo.get_evaluation_result("job-test-003")
    assert retrieved is not None
    assert retrieved["total_score"] == 78.50
    assert retrieved["forecast_skill"] == 20.0
    assert retrieved["event_detection"] == 21.0
    assert retrieved["generalization"] == 16.0
    assert retrieved["calibration"] == 12.5
    assert retrieved["robustness"] == 6.0
    assert retrieved["efficiency"] == 3.0
    assert retrieved["full_report"]["total_score"] == 78.50


def test_leaderboard_query(temp_db):
    """Test leaderboard retrieval with multiple submissions, ordering, and ranking."""
    repo, _ = temp_db

    teams = [
        ("job-01", "TeamA", "ModelA", 82.5),
        ("job-02", "TeamB", "ModelB", 91.0),
        ("job-03", "TeamC", "ModelC", 87.0),
    ]

    for jid, team, model, score in teams:
        job = EvaluationJob(
            job_id=jid,
            repository_url=f"https://github.com/team/{team}.git",
            commit_sha="d" * 40,
            status=JobStatus.COMPLETED,
        )
        job.final_score = score
        repo.insert_job(job, submission_metadata={"team_name": team, "submission_name": model})

        dims = {
            "forecast_skill": score * 0.25,
            "event_detection": score * 0.25,
            "generalization": score * 0.20,
            "calibration_and_uncertainty": score * 0.15,
            "robustness": score * 0.10,
            "efficiency": score * 0.05,
        }
        repo.save_evaluation_result(jid, score, dims, json.dumps({"score": score}))

    # Query leaderboard
    leaderboard = repo.get_leaderboard()
    assert len(leaderboard) == 3
    assert leaderboard[0]["rank"] == 1
    assert leaderboard[0]["team_name"] == "TeamB"
    assert leaderboard[0]["total_score"] == 91.0

    assert leaderboard[1]["rank"] == 2
    assert leaderboard[1]["team_name"] == "TeamC"
    assert leaderboard[1]["total_score"] == 87.0

    assert leaderboard[2]["rank"] == 3
    assert leaderboard[2]["team_name"] == "TeamA"
    assert leaderboard[2]["total_score"] == 82.5


def test_overview_counts(temp_db):
    """Test overview statistics aggregation."""
    repo, _ = temp_db

    j1 = EvaluationJob(job_id="j1", repository_url="https://github.com/t/1.git", commit_sha="e"*40, status=JobStatus.COMPLETED)
    j1.final_score = 80.0
    repo.insert_job(j1)
    repo.save_evaluation_result("j1", 80.0, {}, "{}")

    j2 = EvaluationJob(job_id="j2", repository_url="https://github.com/t/2.git", commit_sha="f"*40, status=JobStatus.EXECUTING)
    repo.insert_job(j2)

    j3 = EvaluationJob(job_id="j3", repository_url="https://github.com/t/3.git", commit_sha="1"*40, status=JobStatus.UNSAFE_EXECUTION_ENVIRONMENT)
    repo.insert_job(j3)

    stats = repo.get_overview_stats()
    assert stats["total_jobs"] == 3
    assert stats["completed_jobs"] == 1
    assert stats["pending_jobs"] == 1
    assert stats["failed_jobs"] == 1
    assert stats["leaderboard_size"] == 1
    assert stats["average_score"] == 80.0
