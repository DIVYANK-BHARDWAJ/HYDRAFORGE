"""
tests/test_submissions_portal.py
Comprehensive unit and integration tests for HYDRAFORGE Final Mandate:
- Strict 2-field participant submission contract (team_name, repository_url ONLY)
- Rejection of extraneous/unexpected fields (deployed_website_url, commit_sha, etc.)
- Server-side GitHub HEAD commit SHA capture without user tokens
- Comprehensive SSRF defenses on repository URLs
- Safe preservation of submissions when GitHub is offline (no fabricated commit SHAs)
- Anchoring evaluations to captured immutable commit SHA
- Organizer console review, notes privacy, and fail-closed Docker gating
"""

import gc
import json
import tempfile
from pathlib import Path
import pytest

from hydraforge.api.auth import authenticate_organizer, verify_organizer_token
from hydraforge.api.main import create_app
from hydraforge.database.connection import DatabaseManager
from hydraforge.database.models import SubmissionRecord
from hydraforge.database.repository import EvaluationRepository
from hydraforge.submission.github_verifier import set_mock_github_resolver
from hydraforge.submission.website_verifier import set_mock_website_checker


@pytest.fixture
def client_and_repo():
    """Create a Flask test client backed by a temporary SQLite database."""
    tmp_dir = tempfile.TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "test_portal_hydraforge.db"
    app = create_app(db_path=db_path)
    app.config["TESTING"] = True

    repo = EvaluationRepository()
    with app.test_client() as test_client:
        yield test_client, repo

    DatabaseManager.set_default_path(None)
    set_mock_github_resolver(None)
    set_mock_website_checker(None)
    gc.collect()
    try:
        tmp_dir.cleanup()
    except Exception:
        pass


@pytest.fixture
def valid_two_field_payload():
    """Standard valid strict 2-field participant submission payload."""
    return {
        "team_name": "AlpineHydro",
        "repository_url": "https://github.com/alpine-hydro/topoflow-gnn",
    }


def test_valid_two_field_submission(client_and_repo, valid_two_field_payload):
    """Test successful submission with exactly the two required fields."""
    client, _ = client_and_repo

    set_mock_github_resolver(lambda u: (
        True,
        "main",
        "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
        "Repository verified."
    ))

    res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    assert res.status_code == 201
    data = res.get_json()
    assert "submission_id" in data
    assert data["submission_id"].startswith("sub_")
    assert data["team_name"] == "AlpineHydro"
    assert data["repository_url"] == "https://github.com/alpine-hydro/topoflow-gnn"
    assert data["commit_sha"] == "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
    assert data["default_branch"] == "main"
    assert data["verification_status"] == "VERIFIED"


def test_missing_team_name(client_and_repo, valid_two_field_payload):
    """Reject submission missing required team name."""
    client, _ = client_and_repo
    valid_two_field_payload["team_name"] = ""
    res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    assert res.status_code == 400
    assert "Team name is required" in res.get_json()["message"]


def test_missing_repository_url(client_and_repo, valid_two_field_payload):
    """Reject submission missing repository URL."""
    client, _ = client_and_repo
    del valid_two_field_payload["repository_url"]
    res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    assert res.status_code == 400
    assert "GitHub repository URL is required" in res.get_json()["message"]


def test_extra_fields_strictly_rejected(client_and_repo, valid_two_field_payload):
    """Extra fields like deployed_website_url, email, commit_sha must be strictly rejected."""
    client, _ = client_and_repo

    # Payload with extraneous fields
    payload = dict(valid_two_field_payload)
    payload["deployed_website_url"] = "https://alpine-hydro.example.com"
    payload["commit_sha"] = "user_supplied_hash_ignored"

    res = client.post("/api/v1/submissions", json=payload)
    assert res.status_code == 400
    msg = res.get_json()["message"]
    assert "Unexpected field(s)" in msg
    assert "deployed_website_url" in msg


def test_server_side_github_verification_capture(client_and_repo, valid_two_field_payload):
    """Verify server resolves default branch and latest commit SHA automatically."""
    client, _ = client_and_repo

    captured_sha = "9f8e7d6c5b4a32109f8e7d6c5b4a32109f8e7d6c"
    set_mock_github_resolver(lambda u: (
        True,
        "production",
        captured_sha,
        "Resolved from GitHub default branch"
    ))

    res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["commit_sha"] == captured_sha
    assert data["default_branch"] == "production"
    assert data["verification_status"] == "VERIFIED"


def test_github_verification_failure_preserves_submission(client_and_repo, valid_two_field_payload):
    """
    When GitHub is unreachable or invalid, submission is preserved safely.
    It must NEVER fabricate a fake commit SHA.
    """
    client, _ = client_and_repo

    set_mock_github_resolver(lambda u: (
        False,
        None,
        None,
        "Could not connect to GitHub"
    ))

    res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["verification_status"] in ("PENDING", "FAILED")
    assert data["commit_sha"] is None
    assert "Could not connect to GitHub" in data["verification_details"]


def test_repository_url_ssrf_direct_private_ip_rejected(client_and_repo, valid_two_field_payload):
    """Direct private IP literals in repository_url must be rejected immediately."""
    client, _ = client_and_repo

    private_ips = [
        "http://127.0.0.1/admin/repo.git",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5:8080/repo.git",
        "http://192.168.1.1/repo.git",
        "http://172.16.0.100/repo.git",
    ]

    for bad_url in private_ips:
        valid_two_field_payload["repository_url"] = bad_url
        res = client.post("/api/v1/submissions", json=valid_two_field_payload)
        assert res.status_code == 400
        msg = res.get_json()["message"]
        assert "invalid" in msg.lower() or "not a recognized github" in msg.lower() or "rejected" in msg.lower()


def test_public_status_privacy_and_notes_shielded(client_and_repo, valid_two_field_payload):
    """Public status endpoint returns public metadata and masks private notes."""
    client, repo = client_and_repo

    set_mock_github_resolver(lambda u: (
        True, "main", "1" * 40, "VERIFIED"
    ))

    res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    sub_id = res.get_json()["submission_id"]

    repo.update_submission_notes(sub_id, "CONFIDENTIAL ORGANIZER NOTE: Checked repository.")

    stat_res = client.get(f"/api/v1/submissions/{sub_id}/status")
    assert stat_res.status_code == 200
    data = stat_res.get_json()
    assert data["submission_id"] == sub_id
    assert data["team_name"] == "AlpineHydro"
    assert "organizer_notes" not in data
    assert "CONFIDENTIAL" not in json.dumps(data)


def test_organizer_authentication_and_review(client_and_repo, valid_two_field_payload):
    """Organizer can review, update notes, and update status with auth token."""
    client, _ = client_and_repo

    set_mock_github_resolver(lambda u: (
        True, "main", "c" * 40, "VERIFIED"
    ))

    # 1. Submit
    sub_res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    assert sub_res.status_code == 201
    sub_id = sub_res.get_json()["submission_id"]

    # 2. Unauthorized organizer query fails
    unauth = client.get("/api/v1/organizer/submissions")
    assert unauth.status_code == 401

    # 3. Authenticate
    token = authenticate_organizer("admin", "basinshift2026")
    headers = {"Authorization": f"Bearer {token}"}

    # 4. List submissions
    list_res = client.get("/api/v1/organizer/submissions", headers=headers)
    assert list_res.status_code == 200
    subs = list_res.get_json()["submissions"]
    assert any(s["submission_id"] == sub_id for s in subs)

    # 5. Detail query
    detail_res = client.get(f"/api/v1/organizer/submissions/{sub_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.get_json()
    assert detail["submission_id"] == sub_id
    assert detail["team_name"] == "AlpineHydro"

    # 6. Update review status
    stat_update = client.patch(
        f"/api/v1/organizer/submissions/{sub_id}/status",
        headers=headers,
        json={"status": "ACCEPTED", "notes": "Approved for evaluation."}
    )
    assert stat_update.status_code == 200
    assert stat_update.get_json()["review_status"] == "ACCEPTED"


def test_evaluation_uses_captured_commit_sha(client_and_repo, valid_two_field_payload):
    """
    Evaluation execution uses the exact captured commit SHA.
    Fails closed if Docker daemon is offline.
    """
    client, _ = client_and_repo

    captured_sha = "d" * 40
    set_mock_github_resolver(lambda u: (
        True, "main", captured_sha, "VERIFIED"
    ))

    sub_res = client.post("/api/v1/submissions", json=valid_two_field_payload)
    sub_id = sub_res.get_json()["submission_id"]

    token = authenticate_organizer("admin", "basinshift2026")
    headers = {"Authorization": f"Bearer {token}"}

    # Accept submission
    client.patch(
        f"/api/v1/organizer/submissions/{sub_id}/status",
        headers=headers,
        json={"status": "ACCEPTED"}
    )

    # Trigger evaluation
    eval_res = client.post(
        f"/api/v1/organizer/submissions/{sub_id}/evaluate",
        headers=headers,
        json={"timeout_seconds": 60}
    )

    # If Docker daemon is offline, fails closed safely
    if eval_res.status_code == 503:
        assert eval_res.get_json()["error"] == "UNSAFE_EXECUTION_ENVIRONMENT"
    elif eval_res.status_code == 200:
        data = eval_res.get_json()
        assert data["commit_sha"] == captured_sha
