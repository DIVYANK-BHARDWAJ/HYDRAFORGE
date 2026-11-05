"""
tests/test_api.py
Comprehensive integration tests for the HYDRAFORGE Flask REST API.
Tests all endpoints, security fail-closed semantics, and trusted fixture runs.
"""

import gc
import json
import tempfile
from pathlib import Path
import pytest

from hydraforge.api.main import create_app
from hydraforge.database.connection import DatabaseManager
from hydraforge.database.repository import EvaluationRepository


@pytest.fixture
def client():
    """Create a Flask test client backed by a temporary SQLite database."""
    tmp_dir = tempfile.TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "test_api_hydraforge.db"
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        yield test_client

    DatabaseManager.set_default_path(None)
    gc.collect()
    try:
        tmp_dir.cleanup()
    except Exception:
        pass


def test_health_endpoint(client):
    """GET /health returns healthy status and platform versions."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"].lower() == "healthy"
    assert "version" in data


def test_dashboard_routes(client):
    """GET / and GET /dashboard return 200."""
    res1 = client.get("/")
    assert res1.status_code == 200

    res2 = client.get("/dashboard")
    assert res2.status_code == 200


def test_overview_endpoint(client):
    """GET /api/v1/overview returns statistics object."""
    res = client.get("/api/v1/overview")
    assert res.status_code == 200
    data = res.get_json()
    assert "total_evaluation_jobs" in data
    assert "completed_evaluations" in data


def test_leaderboard_endpoint(client):
    """GET /api/v1/leaderboard returns ranked submissions list."""
    res = client.get("/api/v1/leaderboard")
    assert res.status_code == 200
    data = res.get_json()
    assert "leaderboard" in data
    assert isinstance(data["leaderboard"], list)


def test_benchmark_endpoint(client):
    """GET /api/v1/benchmark returns dataset summary and leakage audit."""
    res = client.get("/api/v1/benchmark")
    assert res.status_code == 200
    data = res.get_json()
    assert "split_manifests" in data
    assert "leakage_audit" in data
    # Ensure hidden labels are never exposed
    assert "test_a_labels" not in data
    assert "labels" not in data


def test_system_endpoint(client):
    """GET /api/v1/system returns system diagnostics and security status."""
    res = client.get("/api/v1/system")
    assert res.status_code == 200
    data = res.get_json()
    assert "database_status" in data
    assert "execution_backends" in data
    assert "security_warnings" in data


def test_submit_evaluation_validation_errors(client):
    """POST /api/v1/evaluations rejects missing or invalid inputs."""
    # Missing repo_url
    res1 = client.post("/api/v1/evaluations", json={"commit_sha": "a" * 40})
    assert res1.status_code == 400

    # Missing commit_sha
    res2 = client.post("/api/v1/evaluations", json={"repository_url": "https://github.com/org/repo.git"})
    assert res2.status_code == 400

    # Malicious SSRF URL
    res3 = client.post("/api/v1/evaluations", json={
        "repository_url": "http://169.254.169.254/latest/meta-data/",
        "commit_sha": "a" * 40
    })
    assert res3.status_code == 400
    assert "REPOSITORY_REJECTED" in res3.get_json()["error"]


def test_submit_evaluation_fail_closed_untrusted_when_docker_offline(client):
    """POST /api/v1/evaluations fails closed when untrusted and Docker is unavailable."""
    res = client.post("/api/v1/evaluations", json={
        "repository_url": "https://github.com/hydro-team/model.git",
        "commit_sha": "a" * 40,
        "is_trusted": False
    })
    # Since Docker is offline in this environment, must return 503 with UNSAFE_EXECUTION_ENVIRONMENT
    assert res.status_code == 503
    data = res.get_json()
    assert data["error"] == "UNSAFE_EXECUTION_ENVIRONMENT"


def test_submit_and_query_trusted_mock_evaluation(client):
    """POST /api/v1/evaluations executes trusted mock fixture and updates database."""
    mock_dir = Path("tests/fixtures/mock_submission").resolve()

    res = client.post("/api/v1/evaluations", json={
        "repository_url": str(mock_dir),
        "commit_sha": "0" * 40,
        "is_trusted": True,
        "metadata": {
            "team_name": "MockTestingLab",
            "submission_name": "MockBaseline"
        }
    })

    assert res.status_code == 201
    data = res.get_json()
    assert "job_id" in data
    assert data["status"] == "COMPLETED"
    assert data["final_score"] is not None
    job_id = data["job_id"]

    # Query single evaluation
    res_get = client.get(f"/api/v1/evaluations/{job_id}")
    assert res_get.status_code == 200
    job_data = res_get.get_json()
    assert job_data["job_id"] == job_id
    assert job_data["job_status"] == "COMPLETED"

    # Query report
    res_rep = client.get(f"/api/v1/evaluations/{job_id}/report")
    assert res_rep.status_code == 200
    rep_data = res_rep.get_json()
    assert rep_data["job_id"] == job_id
    assert "status" in rep_data

    # Query leaderboard - should now include this submission
    res_lb = client.get("/api/v1/leaderboard")
    assert res_lb.status_code == 200
    lb = res_lb.get_json()["leaderboard"]
    assert any(entry["job_id"] == job_id for entry in lb)
