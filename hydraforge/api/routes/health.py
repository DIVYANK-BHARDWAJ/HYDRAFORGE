"""Health API Route."""

from __future__ import annotations

import sys
from flask import Blueprint, jsonify

from hydraforge import __version__
from hydraforge.database.connection import DatabaseManager

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def get_health():
    """Return health status of API and database."""
    db_ok = True
    try:
        db = DatabaseManager()
        with db.connect() as conn:
            conn.execute("SELECT 1;").fetchone()
    except Exception:
        db_ok = False

    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "application": "HYDRAFORGE",
        "version": __version__,
        "python_version": sys.version.split()[0],
        "api_status": "operational",
        "database_status": "connected" if db_ok else "error"
    }), 200
