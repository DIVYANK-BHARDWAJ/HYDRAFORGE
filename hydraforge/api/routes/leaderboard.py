"""Leaderboard API Route."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from hydraforge.api.services.leaderboard_service import LeaderboardService

leaderboard_bp = Blueprint("leaderboard", __name__, url_prefix="/api/v1")


@leaderboard_bp.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    """Return ranked leaderboard of completed and valid evaluations."""
    version = request.args.get("version", "1.0.0")
    service = LeaderboardService()
    entries = service.get_leaderboard(benchmark_version=version)
    return jsonify({
        "benchmark_version": version,
        "entry_count": len(entries),
        "leaderboard": entries
    }), 200

