"""HYDRAFORGE API Routes Subpackage."""

from hydraforge.api.routes.health import health_bp
from hydraforge.api.routes.overview import overview_bp
from hydraforge.api.routes.evaluations import evaluations_bp
from hydraforge.api.routes.leaderboard import leaderboard_bp
from hydraforge.api.routes.benchmark import benchmark_bp
from hydraforge.api.routes.system import system_bp
from hydraforge.api.routes.submissions import submissions_bp
from hydraforge.api.routes.organizer import organizer_bp

__all__ = [
    "health_bp",
    "overview_bp",
    "evaluations_bp",
    "leaderboard_bp",
    "benchmark_bp",
    "system_bp",
    "submissions_bp",
    "organizer_bp",
]

