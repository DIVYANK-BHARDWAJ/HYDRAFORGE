"""
scripts/verify_workflow.py
Automated End-to-End Workflow Verification for HYDRAFORGE Phase 4B Correction.
Exercises the strict 3-field participant registration, server-side GitHub commit capture,
deployed website validation, status tracking, organizer review, and fail-closed evaluation.
"""

import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hydraforge.api.main import create_app
from hydraforge.database.connection import DatabaseManager
from hydraforge.submission.github_verifier import set_mock_github_resolver
from hydraforge.submission.website_verifier import set_mock_website_checker


def run_verification():
    print("=" * 70)
    print("HYDRAFORGE PHASE 4B CORRECTION: END-TO-END WORKFLOW VERIFICATION")
    print("=" * 70)

    # Mock external GitHub and Website reachability for deterministic local verification
    set_mock_github_resolver(lambda u: (
        True,
        "main",
        "d4e5f6a1b2c30718293a4b5c6d7e8f9012345678",
        "Public repository verified on GitHub."
    ))
    set_mock_website_checker(lambda u: (
        True,
        "ONLINE",
        "HTTP 200 OK (latency: 42ms)"
    ))

    # 1. Initialize application
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # Step 1: Open Landing Page
    print("\n[Step 1] Participant opens landing page (GET /)...")
    res1 = client.get("/")
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
    assert "HYDRAFORGE" in res1.data.decode("utf-8")
    print("  -> OK: Public landing page served successfully (HTTP 200).")

    # Step 2: Fill out strict 3-field registration form & submit
    print("\n[Step 2] Participant fills out strictly 3 fields (team, repo, website)...")
    submission_data = {
        "team_name": "GlacierAI",
        "repository_url": "https://github.com/glacier-ai/glacierflow-tcn",
        "deployed_website_url": "https://glacier-flow.example.org"
    }

    res2 = client.post("/api/v1/submissions", json=submission_data)
    assert res2.status_code == 201, f"Expected 201, got {res2.status_code}: {res2.data}"
    reg_result = res2.get_json()

    # Step 3: Server-side GitHub commit capture & unique ID
    submission_id = reg_result["submission_id"]
    print(f"\n[Step 3] Generated unique Submission ID: {submission_id}")
    assert submission_id.startswith("sub_")
    assert reg_result["commit_sha"] == "d4e5f6a1b2c30718293a4b5c6d7e8f9012345678"
    assert reg_result["default_branch"] == "main"
    assert reg_result["website_status"] == "ONLINE"
    print(f"  -> OK: Server resolved HEAD commit SHA without participant token: {reg_result['commit_sha']}")
    print(f"  -> OK: Deployed website verified: {reg_result['deployed_website_url']} ({reg_result['website_status']})")

    # Step 4: Participant checks submission status
    print("\n[Step 4] Participant queries public status (GET /status)...")
    res_stat = client.get(f"/api/v1/submissions/{submission_id}/status")
    assert res_stat.status_code == 200
    stat_data = res_stat.get_json()
    print(f"  -> Status: {stat_data['submission_status']}, Verification: {stat_data['verification_status']}")
    assert stat_data["verification_status"] == "VERIFIED"
    assert stat_data["deployed_website_url"] == "https://glacier-flow.example.org"
    assert "organizer_notes" not in stat_data
    print("  -> OK: Safe participant status verified (internal notes shielded).")

    # Step 5: Organizer logs in
    print("\n[Step 5] Organizer authenticates (POST /api/v1/organizer/login)...")
    login_res = client.post("/api/v1/organizer/login", json={
        "username": "organizer",
        "password": "basinshift2026organizer"
    })
    assert login_res.status_code == 200
    token = login_res.get_json()["token"]
    org_headers = {"Authorization": f"Bearer {token}"}
    print(f"  -> OK: Authorized session token issued ({token[:16]}...).")

    # Step 6: Organizer inspects submission in console
    print("\n[Step 6] Organizer inspects submission, repo URL, website URL, and commit...")
    inspect_res = client.get(f"/api/v1/organizer/submissions/{submission_id}", headers=org_headers)
    assert inspect_res.status_code == 200
    sub_detail = inspect_res.get_json()
    print(f"  -> Team: {sub_detail['team_name']}")
    print(f"  -> Repository: {sub_detail['repository_url']}")
    print(f"  -> Deployed Website: {sub_detail['deployed_website_url']}")
    print(f"  -> Captured Commit: {sub_detail['commit_sha']}")
    print("  -> OK: Submission metadata cleanly displayed in organizer console.")

    # Step 7: Organizer accepts submission & records review notes
    print("\n[Step 7] Organizer accepts submission and adds internal notes...")
    note_res = client.patch(
        f"/api/v1/organizer/submissions/{submission_id}/notes",
        headers=org_headers,
        json={"notes": "Public website and repository validated."}
    )
    assert note_res.status_code == 200

    accept_res = client.patch(
        f"/api/v1/organizer/submissions/{submission_id}/status",
        headers=org_headers,
        json={"status": "ACCEPTED"}
    )
    assert accept_res.status_code == 200
    print("  -> OK: Submission review status updated to ACCEPTED.")

    # Step 8: Organizer attempts evaluation (fail-closed check with captured commit)
    print("\n[Step 8] Organizer attempts evaluation while Docker daemon is offline...")
    eval_res = client.post(
        f"/api/v1/organizer/submissions/{submission_id}/evaluate",
        headers=org_headers,
        json={"is_trusted": False}
    )
    assert eval_res.status_code == 503, f"Expected 503, got {eval_res.status_code}"
    eval_err = eval_res.get_json()
    print(f"  -> Gating Result: {eval_err['error']}")
    print(f"  -> Message: {eval_err['message']}")
    print(f"  -> State Preserved: {eval_err['submission_status']}")
    assert eval_err["error"] == "SAFE_WORKER_UNAVAILABLE"
    assert "SAFE EXECUTION WORKER UNAVAILABLE" in eval_err["submission_status"]

    # Final check on participant status: reflects held state
    final_stat = client.get(f"/api/v1/submissions/{submission_id}/status").get_json()
    assert "SAFE EXECUTION WORKER UNAVAILABLE" in final_stat["submission_status"]
    print("  -> OK: Submission anchored to captured commit SHA and safely held without data loss.")

    print("\n" + "=" * 70)
    print("ALL STEPS OF THE END-TO-END WORKFLOW VERIFIED SUCCESSFULLY (PASS)")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
