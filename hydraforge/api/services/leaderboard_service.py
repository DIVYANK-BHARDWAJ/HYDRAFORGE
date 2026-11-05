"""Leaderboard Service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from hydraforge.database.repository import EvaluationRepository


class LeaderboardService:
    """Provides ranked leaderboard statistics from database."""

    def __init__(self, repository: Optional[EvaluationRepository] = None) -> None:
        self.repo = repository or EvaluationRepository()

    def get_leaderboard(self, benchmark_version: str = "1.0.0") -> List[Dict[str, Any]]:
        return self.repo.get_leaderboard(benchmark_version=benchmark_version)

