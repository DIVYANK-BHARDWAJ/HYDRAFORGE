"""HYDRAFORGE REST API Application Entrypoint."""

from __future__ import annotations

from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from hydraforge.api.routes import (
    benchmark_bp,
    evaluations_bp,
    health_bp,
    leaderboard_bp,
    organizer_bp,
    overview_bp,
    submissions_bp,
    system_bp,
)
from hydraforge.database.migrations import apply_migrations


def create_app(db_path: Path | None = None) -> Flask:
    """Create and configure the Flask REST application."""
    app = Flask(__name__)
    CORS(app)

    # Initialize SQLite database schema
    from hydraforge.database.connection import DatabaseManager
    if db_path:
        DatabaseManager.set_default_path(db_path)
    db_mgr = DatabaseManager(db_path)
    apply_migrations(db_mgr)

    # Register API Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(overview_bp)
    app.register_blueprint(evaluations_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(benchmark_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(organizer_bp)

    # Serve Organizer Frontend Dashboard
    dist_dir = Path("frontend/dist").resolve()
    web_dir = Path(__file__).resolve().parent / "web"
    web_dir.mkdir(parents=True, exist_ok=True)

    @app.route("/", methods=["GET"])
    @app.route("/dashboard", methods=["GET"])
    def index():
        if dist_dir.exists() and (dist_dir / "index.html").exists():
            return send_from_directory(dist_dir, "index.html")
        index_file = web_dir / "index.html"
        if index_file.exists():
            return send_from_directory(web_dir, "index.html")
        return jsonify({
            "message": "HYDRAFORGE API Server running. Open /api/v1/overview for telemetry.",
            "endpoints": [
                "/health",
                "/api/v1/overview",
                "/api/v1/evaluations",
                "/api/v1/leaderboard",
                "/api/v1/benchmark",
                "/api/v1/system"
            ]
        })

    @app.route("/assets/<path:filename>", methods=["GET"])
    def serve_assets(filename: str):
        if dist_dir.exists() and (dist_dir / "assets").exists():
            return send_from_directory(dist_dir / "assets", filename)
        if (web_dir / "assets").exists():
            return send_from_directory(web_dir / "assets", filename)
        return jsonify({"error": "NOT_FOUND"}), 404

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({"error": "NOT_FOUND", "message": "The requested resource was not found."}), 404

    @app.errorhandler(500)
    def handle_server_error(e):
        return jsonify({"error": "INTERNAL_SERVER_ERROR", "message": "An internal server error occurred."}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)
