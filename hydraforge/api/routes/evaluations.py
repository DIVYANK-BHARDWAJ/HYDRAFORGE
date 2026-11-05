"""Evaluations Submission and Tracking API Routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from hydraforge.api.services.evaluation_service import EvaluationService

evaluations_bp = Blueprint("evaluations", __name__, url_prefix="/api/v1")


@evaluations_bp.route("/evaluations", methods=["POST"])
def submit_evaluation():
    """Submit a repository for evaluation."""
    data = request.get_json(silent=True) or {}
    repo_url = data.get("repository_url", "")
    commit_sha = data.get("commit_sha", "")
    submission_metadata = data.get("metadata", {})
    is_trusted = bool(data.get("is_trusted", False))

    if not repo_url:
        return jsonify({"error": "VALIDATION_ERROR", "message": "repository_url is required."}), 400
    if not commit_sha:
        return jsonify({"error": "VALIDATION_ERROR", "message": "commit_sha is required."}), 400

    service = EvaluationService()
    success, res = service.submit_evaluation(
        repository_url=repo_url,
        commit_sha=commit_sha,
        submission_metadata=submission_metadata,
        is_trusted=is_trusted
    )

    if not success:
        status_code = 400 if res.get("error") == "REPOSITORY_REJECTED" else 503
        return jsonify(res), status_code

    return jsonify(res), 201


@evaluations_bp.route("/evaluations", methods=["GET"])
def list_evaluations():
    """List evaluation jobs."""
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    service = EvaluationService()
    jobs = service.list_jobs(limit=limit, offset=offset)
    return jsonify({"jobs": jobs, "count": len(jobs)}), 200


@evaluations_bp.route("/evaluations/<job_id>", methods=["GET"])
def get_evaluation(job_id: str):
    """Get single evaluation job by ID."""
    service = EvaluationService()
    job = service.get_job_details(job_id)
    if not job:
        return jsonify({"error": "NOT_FOUND", "message": f"Job '{job_id}' not found."}), 404
    return jsonify(job), 200


@evaluations_bp.route("/evaluations/<job_id>/report", methods=["GET"])
def get_evaluation_report(job_id: str):
    """Get detailed report for job."""
    service = EvaluationService()
    report = service.get_job_report(job_id)
    if not report:
        return jsonify({"error": "NOT_FOUND", "message": f"Report for '{job_id}' not found."}), 404
    return jsonify(report), 200

