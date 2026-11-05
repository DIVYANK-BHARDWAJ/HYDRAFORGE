"""Report Service: Formats evaluation results into Markdown and JSON."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from hydraforge.database.repository import EvaluationRepository


class ReportService:
    def __init__(self, repository: Optional[EvaluationRepository] = None) -> None:
        self.repo = repository or EvaluationRepository()

    def get_formatted_report(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self.repo.get_job(job_id)
        if not job:
            return None
        res = self.repo.get_evaluation_result(job_id)
        return {
            "job": job,
            "result": res
        }

