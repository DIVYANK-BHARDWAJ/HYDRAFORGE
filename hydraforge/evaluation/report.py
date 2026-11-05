"""Evaluation Report Exporter (JSON and Markdown)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from hydraforge.evaluation.job import EvaluationJob


def export_job_report_json(job: EvaluationJob, output_path: Path) -> str:
    """Serialize EvaluationJob audit trail to JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    job_dict = job.to_dict()

    content = json.dumps(job_dict, indent=2, default=str)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def export_job_report_markdown(job: EvaluationJob) -> str:
    """Format EvaluationJob summary as a GitHub-flavored markdown report."""
    md = [
        f"# HYDRAFORGE Evaluation Audit — Job `{job.job_id}`",
        "",
        f"- **Status:** `{job.status.value}`",
        f"- **Repository:** `{job.repository_url}`",
        f"- **Commit SHA:** `{job.commit_sha}`",
        f"- **Execution Backend:** `{job.execution_backend}`",
        f"- **Created:** `{job.created_at}`",
        f"- **Completed:** `{job.completed_at or 'In Progress'}`",
        f"- **Runtime:** `{job.runtime_seconds:.2f}s`" if job.runtime_seconds else "- **Runtime:** N/A",
        f"- **Peak Memory:** `{job.peak_memory_mb:.1f} MB`" if job.peak_memory_mb else "- **Peak Memory:** N/A",
        "",
        "---",
        ""
    ]

    if job.failure_reason:
        md.append(f"> [!CAUTION]\n> **Execution Terminated with Failure:** {job.failure_reason}\n")
    elif job.evaluation_result:
        res = job.evaluation_result
        md.extend([
            f"## Final Benchmark Score: **{res.total_score:.2f} / {res.max_total_score:.0f}**",
            "",
            "| Dimension | Points Awarded | Max Points | Normalized Score | Status |",
            "|---|---:|---:|---:|---|"
        ])
        for dim_name, dim_score in res.dimensions.items():
            md.append(
                f"| `{dim_name}` | {dim_score.points_awarded:.2f} | {dim_score.max_points:.0f} | "
                f"{dim_score.normalized_score:.4f} | {'Provisional' if dim_score.is_provisional else 'Final'} |"
            )
        md.append("")
        md.append(f"**Audit Digest Hash (SHA-256):** `{res.audit_hash}`\n")

    md.append("### Lifecycle Transition Log\n")
    for log_item in job.audit_log:
        md.append(f"- {log_item}")

    return "\n".join(md)

