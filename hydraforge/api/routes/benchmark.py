"""Benchmark Metadata and Audit API Route."""

from __future__ import annotations

from flask import Blueprint, jsonify

from hydraforge.api.services.benchmark_service import BenchmarkService

benchmark_bp = Blueprint("benchmark", __name__, url_prefix="/api/v1")


@benchmark_bp.route("/benchmark", methods=["GET"])
def get_benchmark():
    """Return benchmark dataset details and leakage audit without exposing labels."""
    service = BenchmarkService()
    summary = service.get_benchmark_summary()
    return jsonify(summary), 200

