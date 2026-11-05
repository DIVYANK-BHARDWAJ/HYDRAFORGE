"""
hydraforge/api/routes/submissions.py
Public Participant Submissions REST API.
Handles team registration, dataset disclosures, verification, and status tracking.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from hydraforge.api.services.submission_service import SubmissionService

submissions_bp = Blueprint("submissions", __name__, url_prefix="/api/v1")


@submissions_bp.route("/submissions", methods=["POST"])
def register_submission():
    """Register a new participant team project submission."""
    data = request.get_json(silent=True) or {}
    service = SubmissionService()

    success, result = service.register_submission(data)
    if not success:
        status_code = 400 if result.get("error") == "VALIDATION_ERROR" else 500
        return jsonify(result), status_code

    return jsonify(result), 201


@submissions_bp.route("/submissions/<submission_id>/status", methods=["GET"])
def get_submission_status(submission_id: str):
    """Return safe participant-visible status without exposing internal notes or private data."""
    service = SubmissionService()
    status_info = service.get_public_status(submission_id)
    if not status_info:
        return jsonify({
            "error": "NOT_FOUND",
            "message": f"No submission found with ID '{submission_id}'."
        }), 404

    return jsonify(status_info), 200


@submissions_bp.route("/submissions/<submission_id>/confirmation", methods=["GET"])
def get_submission_confirmation(submission_id: str):
    """Return submission receipt confirmation details."""
    service = SubmissionService()
    conf = service.get_confirmation(submission_id)
    if not conf:
        return jsonify({
            "error": "NOT_FOUND",
            "message": f"No submission found with ID '{submission_id}'."
        }), 404

    return jsonify(conf), 200


@submissions_bp.route("/submissions/<submission_id>/verify", methods=["POST"])
def verify_submission(submission_id: str):
    """
    Perform repository and commit metadata verification only.
    Never executes untrusted participant code.
    """
    service = SubmissionService()
    success, res = service.verify_submission(submission_id)
    if not success:
        return jsonify(res), 400
    return jsonify(res), 200

