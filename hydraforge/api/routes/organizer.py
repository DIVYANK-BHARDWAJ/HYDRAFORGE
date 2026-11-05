"""
hydraforge/api/routes/organizer.py
Private Organizer Submissions Management and Evaluation API.
Protected by real authentication and authorization.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from hydraforge.api.auth import authenticate_organizer, require_organizer_auth
from hydraforge.api.services.submission_service import SubmissionService

organizer_bp = Blueprint("organizer", __name__, url_prefix="/api/v1/organizer")


@organizer_bp.route("/login", methods=["POST"])
def organizer_login():
    """Authenticate organizer and return an authorized session token."""
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    ok, token = authenticate_organizer(username, password)
    if not ok:
        return jsonify({
            "error": "INVALID_CREDENTIALS",
            "message": "Invalid organizer username or password."
        }), 401

    return jsonify({
        "status": "authenticated",
        "token": token,
        "token_type": "Bearer",
        "message": "Organizer authentication successful."
    }), 200


@organizer_bp.route("/submissions", methods=["GET"])
@require_organizer_auth
def list_submissions():
    """List all participant submissions with organizer review status and notes."""
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    status = request.args.get("status")
    search = request.args.get("search")

    service = SubmissionService()
    submissions = service.organizer_list_submissions(
        limit=limit,
        offset=offset,
        status=status,
        search=search
    )
    return jsonify({
        "submissions": submissions,
        "count": len(submissions)
    }), 200


@organizer_bp.route("/submissions/<submission_id>", methods=["GET"])
@require_organizer_auth
def get_submission(submission_id: str):
    """Retrieve complete submission record including dataset disclosures and private notes."""
    service = SubmissionService()
    sub = service.organizer_get_submission(submission_id)
    if not sub:
        return jsonify({
            "error": "NOT_FOUND",
            "message": f"Submission '{submission_id}' not found."
        }), 404

    return jsonify(sub), 200


@organizer_bp.route("/submissions/<submission_id>/status", methods=["PATCH"])
@require_organizer_auth
def update_submission_status(submission_id: str):
    """Update review status (ACCEPTED or REJECTED) and optionally add review comments."""
    data = request.get_json(silent=True) or {}
    review_status = data.get("status")
    notes = data.get("notes")

    if not review_status:
        return jsonify({
            "error": "MISSING_FIELD",
            "message": "Field 'status' is required (ACCEPTED, REJECTED, UNDER_REVIEW)."
        }), 400

    service = SubmissionService()
    success, res = service.organizer_update_review(submission_id, review_status, notes)
    if not success:
        return jsonify(res), 400

    return jsonify(res), 200


@organizer_bp.route("/submissions/<submission_id>/notes", methods=["PATCH"])
@require_organizer_auth
def update_submission_notes(submission_id: str):
    """Update private internal organizer notes (never exposed through public APIs)."""
    data = request.get_json(silent=True) or {}
    notes = data.get("notes", "")

    service = SubmissionService()
    success, res = service.organizer_update_notes(submission_id, str(notes))
    if not success:
        return jsonify(res), 400

    return jsonify(res), 200


@organizer_bp.route("/submissions/<submission_id>/evaluate", methods=["POST"])
@require_organizer_auth
def evaluate_submission(submission_id: str):
    """
    Trigger automated evaluation of an accepted submission.
    Strictly fail-closed if Docker daemon is offline.
    """
    data = request.get_json(silent=True) or {}
    is_trusted = bool(data.get("is_trusted", False))

    service = SubmissionService()
    success, res = service.organizer_evaluate_submission(submission_id, is_trusted=is_trusted)

    if not success:
        status_code = 503 if res.get("error") == "SAFE_WORKER_UNAVAILABLE" else 400
        return jsonify(res), status_code

    return jsonify(res), 200

