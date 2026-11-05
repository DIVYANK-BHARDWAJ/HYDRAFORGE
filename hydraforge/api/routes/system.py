"""System Status and Environmental Health API Route."""

from __future__ import annotations

import sys
import psutil
from flask import Blueprint, jsonify

from hydraforge import __version__
from hydraforge.database.connection import DatabaseManager
from hydraforge.runner.docker_runner import DockerRunner

system_bp = Blueprint("system", __name__, url_prefix="/api/v1")


@system_bp.route("/system", methods=["GET"])
def get_system_status():
    """Return diagnostic system telemetry and security readiness."""
    # 1. DB Status
    db_ok = True
    try:
        db = DatabaseManager()
        with db.connect() as conn:
            conn.execute("SELECT 1;").fetchone()
    except Exception:
        db_ok = False

    # 2. Docker daemon status
    docker = DockerRunner()
    docker_available = docker.is_docker_daemon_available()

    # 3. CPU and RAM telemetry
    cpu_count = psutil.cpu_count(logical=True)
    memory = psutil.virtual_memory()

    security_warnings = []
    if not docker_available:
        security_warnings.append(
            "CRITICAL: Docker daemon is offline. Untrusted submission execution is locked (fail-closed)."
        )

    return jsonify({
        "application": "HYDRAFORGE",
        "version": __version__,
        "python_version": sys.version.split()[0],
        "database_status": "connected" if db_ok else "error",
        "execution_backends": {
            "docker_daemon_available": docker_available,
            "docker_runner_ready": docker_available,
            "local_test_runner_available": True,
            "untrusted_execution_ready": docker_available
        },
        "hardware_telemetry": {
            "cpu_cores_logical": cpu_count,
            "total_memory_mb": round(memory.total / (1024 * 1024), 1),
            "available_memory_mb": round(memory.available / (1024 * 1024), 1),
            "memory_usage_percent": memory.percent
        },
        "benchmark_readiness": {
            "synthetic_suite_ready": True,
            "genuine_caravan_ready": False
        },
        "security_warnings": security_warnings
    }), 200
