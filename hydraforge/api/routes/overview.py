"""Overview Dashboard API Route."""

from __future__ import annotations

from flask import Blueprint, jsonify

from hydraforge.database.repository import EvaluationRepository
from hydraforge.runner.docker_runner import DockerRunner

overview_bp = Blueprint("overview", __name__, url_prefix="/api/v1")


@overview_bp.route("/overview", methods=["GET"])
def get_overview():
    """Return platform overview counters and status."""
    repo = EvaluationRepository()
    stats = repo.get_overview_stats()

    docker = DockerRunner()
    docker_available = docker.is_docker_daemon_available()

    return jsonify({
        "total_evaluation_jobs": stats["total_jobs"],
        "completed_evaluations": stats["completed_jobs"],
        "failed_evaluations": stats["failed_jobs"],
        "pending_evaluations": stats["pending_jobs"],
        "leaderboard_size": stats["leaderboard_size"],
        "average_score": stats["average_score"],
        "benchmark_version": "1.0.0",
        "scoring_version": "1.0.0",
        "execution_backend_status": {
            "docker_daemon_online": docker_available,
            "untrusted_execution_ready": docker_available,
            "trusted_local_runner_available": True
        }
    }), 200

