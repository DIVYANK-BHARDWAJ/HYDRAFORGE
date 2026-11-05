"""Database Repository for Evaluation Jobs, Results, and Leaderboards."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydraforge.database.connection import DatabaseManager
from hydraforge.database.models import SubmissionRecord
from hydraforge.evaluation.job import EvaluationJob, JobStatus


class EvaluationRepository:
    """Provides high-level transactional data access for jobs and scores."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager()

    def insert_job(
        self,
        job: EvaluationJob,
        submission_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Insert a newly created evaluation job."""
        meta_str = json.dumps(submission_metadata) if submission_metadata else None
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_jobs (
                    job_id, repository_url, commit_sha, submission_metadata,
                    contract_version, benchmark_version, scoring_version,
                    execution_backend, job_status, created_at, started_at,
                    completed_at, failure_reason, final_score, report_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.job_id,
                    job.repository_url,
                    job.commit_sha,
                    meta_str,
                    job.contract_version,
                    job.benchmark_version,
                    job.scoring_config_version,
                    job.execution_backend,
                    job.status.value,
                    job.created_at,
                    job.started_at,
                    job.completed_at,
                    job.failure_reason,
                    job.final_score,
                    job.score_report_hash,
                )
            )

    def update_job(self, job: EvaluationJob) -> None:
        """Update job lifecycle status, timestamps, and score."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE evaluation_jobs SET
                    job_status = ?,
                    started_at = ?,
                    completed_at = ?,
                    failure_reason = ?,
                    final_score = ?,
                    report_hash = ?
                WHERE job_id = ?;
                """,
                (
                    job.status.value,
                    job.started_at,
                    job.completed_at,
                    job.failure_reason,
                    job.final_score,
                    job.score_report_hash,
                    job.job_id,
                )
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single job record by ID."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_jobs WHERE job_id = ?;", (job_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("submission_metadata"):
                try:
                    d["submission_metadata"] = json.loads(d["submission_metadata"])
                except Exception:
                    pass
            return d

    def list_jobs(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List evaluation jobs ordered by creation timestamp descending."""
        query = "SELECT * FROM evaluation_jobs"
        params: List[Any] = []
        if status:
            query += " WHERE job_status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get("submission_metadata"):
                    try:
                        d["submission_metadata"] = json.loads(d["submission_metadata"])
                    except Exception:
                        pass
                results.append(d)
            return results

    def save_evaluation_result(
        self,
        job_id: str,
        total_score: float,
        dimensions: Dict[str, float],
        full_report_json: str
    ) -> str:
        """Save detailed dimensional scores and full JSON report for a completed job."""
        result_id = f"res_{uuid.uuid4().hex[:12]}"
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluation_results (
                    result_id, job_id, total_score, forecast_skill,
                    event_detection, generalization, calibration,
                    robustness, efficiency, full_report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    result_id,
                    job_id,
                    total_score,
                    dimensions.get("forecast_skill", 0.0),
                    dimensions.get("event_detection", 0.0),
                    dimensions.get("generalization", 0.0),
                    dimensions.get("calibration_and_uncertainty", 0.0),
                    dimensions.get("robustness", 0.0),
                    dimensions.get("efficiency", 0.0),
                    full_report_json
                )
            )
        return result_id

    def get_evaluation_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch result record and parsed report JSON for a job."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_results WHERE job_id = ?;", (job_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["full_report"] = json.loads(d["full_report_json"])
            except Exception:
                d["full_report"] = {}
            return d

    def get_leaderboard(
        self,
        benchmark_version: str = "1.0.0"
    ) -> List[Dict[str, Any]]:
        """Fetch ranked leaderboard of completed and valid evaluations only."""
        query = """
        SELECT
            j.job_id,
            j.repository_url,
            j.commit_sha,
            j.submission_metadata,
            j.completed_at,
            j.benchmark_version,
            j.scoring_version,
            r.total_score,
            r.forecast_skill,
            r.event_detection,
            r.generalization,
            r.calibration,
            r.robustness,
            r.efficiency
        FROM evaluation_jobs j
        JOIN evaluation_results r ON j.job_id = r.job_id
        WHERE j.job_status = 'COMPLETED'
          AND j.final_score IS NOT NULL
          AND j.benchmark_version = ?
        ORDER BY r.total_score DESC, j.completed_at ASC;
        """
        with self.db.connect() as conn:
            rows = conn.execute(query, (benchmark_version,)).fetchall()
            leaderboard = []
            for rank, r in enumerate(rows, start=1):
                d = dict(r)
                meta = {}
                if d.get("submission_metadata"):
                    try:
                        meta = json.loads(d["submission_metadata"])
                    except Exception:
                        pass
                leaderboard.append({
                    "rank": rank,
                    "job_id": d["job_id"],
                    "team_name": meta.get("team_name", "Anonymous"),
                    "submission_name": meta.get("submission_name", d["job_id"]),
                    "repository_url": d["repository_url"],
                    "commit_sha": d["commit_sha"],
                    "total_score": round(d["total_score"], 2),
                    "forecast_skill": round(d["forecast_skill"], 2),
                    "event_detection": round(d["event_detection"], 2),
                    "generalization": round(d["generalization"], 2),
                    "calibration": round(d["calibration"], 2),
                    "robustness": round(d["robustness"], 2),
                    "efficiency": round(d["efficiency"], 2),
                    "completed_at": d["completed_at"],
                    "benchmark_version": d["benchmark_version"],
                    "scoring_version": d["scoring_version"]
                })
            return leaderboard

    def get_overview_stats(self) -> Dict[str, Any]:
        """Fetch high-level overview metrics for the dashboard."""
        with self.db.connect() as conn:
            total_jobs = conn.execute("SELECT COUNT(*) FROM evaluation_jobs;").fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM evaluation_jobs WHERE job_status = 'COMPLETED';"
            ).fetchone()[0]
            failed = conn.execute(
                """
                SELECT COUNT(*) FROM evaluation_jobs
                WHERE job_status IN (
                    'REPOSITORY_REJECTED', 'SUBMISSION_REJECTED',
                    'UNSAFE_EXECUTION_ENVIRONMENT', 'EXECUTION_FAILED',
                    'RESOURCE_LIMIT_EXCEEDED', 'INVALID_PREDICTIONS', 'SCORING_FAILED'
                );
                """
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM evaluation_jobs WHERE job_status IN ('CREATED', 'QUEUED', 'EXECUTING');"
            ).fetchone()[0]
            leaderboard_size = completed

            # Average score of completed jobs
            avg_score_row = conn.execute(
                "SELECT AVG(total_score) FROM evaluation_results;"
            ).fetchone()[0]
            avg_score = round(float(avg_score_row), 2) if avg_score_row is not None else None

            return {
                "total_jobs": total_jobs,
                "completed_jobs": completed,
                "failed_jobs": failed,
                "pending_jobs": pending,
                "leaderboard_size": leaderboard_size,
                "average_score": avg_score
            }

    # =========================================================================
    # Participant Submissions Management (Phase 4B)
    # =========================================================================

    def insert_submission(self, sub: SubmissionRecord) -> str:
        """Insert a newly registered team submission into the submissions table."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO submissions (
                    submission_id, team_name, repository_url, deployed_website_url,
                    commit_sha, default_branch, website_status,
                    team_leader, contact_email, team_members, institution,
                    project_name, project_description, programming_language, model_architecture,
                    training_datasets, dataset_sources, dataset_licenses, pretrained_models,
                    inference_time_data, provenance_notes, declaration_status, submitted_at,
                    verification_status, verification_details, organizer_review_status,
                    organizer_notes, submission_status, linked_evaluation_job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sub.submission_id,
                    sub.team_name,
                    sub.repository_url,
                    sub.deployed_website_url,
                    sub.commit_sha,
                    sub.default_branch,
                    sub.website_status,
                    sub.team_leader or sub.team_name,
                    sub.contact_email or "",
                    sub.team_members,
                    sub.institution,
                    sub.project_name or sub.team_name,
                    sub.project_description or "",
                    sub.programming_language or "Python",
                    sub.model_architecture or "Hydrological ML Model",
                    sub.training_datasets or "Disclosed Open Datasets",
                    sub.dataset_sources or "Disclosed Sources",
                    sub.dataset_licenses or "Open Licenses",
                    sub.pretrained_models or "None",
                    sub.inference_time_data or "None",
                    sub.provenance_notes or "Standard basin preprocessing",
                    1 if sub.declaration_status else 0,
                    sub.submitted_at,
                    sub.verification_status,
                    sub.verification_details,
                    sub.organizer_review_status,
                    sub.organizer_notes,
                    sub.submission_status,
                    sub.linked_evaluation_job_id,
                )
            )
        return sub.submission_id

    def check_duplicate_submission(self, team_name: str, repository_url: str, commit_sha: Optional[str] = None) -> bool:
        """Check if identical team and repository URL has already been submitted."""
        with self.db.connect() as conn:
            query = """
                SELECT 1 FROM submissions
                WHERE LOWER(team_name) = LOWER(?)
                  AND LOWER(repository_url) = LOWER(?)
            """
            params = [team_name.strip(), repository_url.strip()]
            if commit_sha:
                query += " AND LOWER(commit_sha) = LOWER(?)"
                params.append(commit_sha.strip())

            row = conn.execute(query, params).fetchone()
            return row is not None

    def update_submission_website(self, submission_id: str, website_status: str, details: Optional[str] = None) -> bool:
        """Update deployed website availability status."""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE submissions SET website_status = ? WHERE submission_id = ?;",
                (website_status, submission_id)
            )
            return cur.rowcount > 0

    def update_submission_verification(
        self,
        submission_id: str,
        verification_status: str,
        commit_sha: Optional[str] = None,
        default_branch: Optional[str] = None,
        verification_details: Optional[str] = None
    ) -> bool:
        """Update repository verification status and server-side captured commit SHA."""
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE submissions SET
                    verification_status = ?,
                    commit_sha = COALESCE(?, commit_sha),
                    default_branch = COALESCE(?, default_branch),
                    verification_details = ?,
                    submission_status = CASE
                        WHEN ? = 'VERIFIED' THEN 'VERIFIED'
                        WHEN ? = 'FAILED' THEN 'SUBMISSION_REJECTED'
                        ELSE submission_status
                    END
                WHERE submission_id = ?;
                """,
                (verification_status, commit_sha, default_branch, verification_details, verification_status, verification_status, submission_id)
            )
            return cur.rowcount > 0

    def get_submission(
        self,
        submission_id: str,
        include_private_notes: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch submission record by ID.
        If include_private_notes is False (public view), strips organizer_notes and contact email.
        Also joins linked evaluation job status and score if present.
        """
        query = """
        SELECT
            s.*,
            j.job_status as evaluation_job_status,
            j.final_score as evaluation_final_score,
            j.failure_reason as evaluation_failure_reason,
            j.completed_at as evaluation_completed_at
        FROM submissions s
        LEFT JOIN evaluation_jobs j ON s.linked_evaluation_job_id = j.job_id
        WHERE s.submission_id = ?;
        """
        with self.db.connect() as conn:
            row = conn.execute(query, (submission_id,)).fetchone()
            if not row:
                return None
            d = dict(row)

            # Parse team members JSON if available
            if d.get("team_members"):
                try:
                    d["team_members"] = json.loads(d["team_members"])
                except Exception:
                    pass

            if not include_private_notes:
                d.pop("organizer_notes", None)
                # Mask contact email for public privacy
                email = d.get("contact_email", "")
                if "@" in email:
                    user, domain = email.split("@", 1)
                    masked_user = user[:2] + "***" if len(user) > 2 else "***"
                    d["contact_email"] = f"{masked_user}@{domain}"

            return d

    def list_submissions(
        self,
        limit: int = 100,
        offset: int = 0,
        review_status: Optional[str] = None,
        search: Optional[str] = None,
        include_private_notes: bool = False
    ) -> List[Dict[str, Any]]:
        """List submissions with search and filter capabilities."""
        query = """
        SELECT
            s.*,
            j.job_status as evaluation_job_status,
            j.final_score as evaluation_final_score,
            j.failure_reason as evaluation_failure_reason
        FROM submissions s
        LEFT JOIN evaluation_jobs j ON s.linked_evaluation_job_id = j.job_id
        WHERE 1=1
        """
        params: List[Any] = []
        if review_status:
            query += " AND s.organizer_review_status = ?"
            params.append(review_status)
        if search:
            query += " AND (s.team_name LIKE ? OR s.project_name LIKE ? OR s.submission_id LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])

        query += " ORDER BY s.submitted_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self.db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get("team_members"):
                    try:
                        d["team_members"] = json.loads(d["team_members"])
                    except Exception:
                        pass
                if not include_private_notes:
                    d.pop("organizer_notes", None)
                    email = d.get("contact_email", "")
                    if "@" in email:
                        user, domain = email.split("@", 1)
                        masked_user = user[:2] + "***" if len(user) > 2 else "***"
                        d["contact_email"] = f"{masked_user}@{domain}"
                results.append(d)
            return results

    def update_submission_review(
        self,
        submission_id: str,
        review_status: str,
        notes: Optional[str] = None
    ) -> bool:
        """Organizer review decision: ACCEPTED, REJECTED, or UNDER_REVIEW."""
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE submissions SET
                    organizer_review_status = ?,
                    organizer_notes = COALESCE(?, organizer_notes),
                    submission_status = CASE
                        WHEN ? = 'ACCEPTED' THEN 'ACCEPTED'
                        WHEN ? = 'REJECTED' THEN 'REJECTED'
                        ELSE submission_status
                    END
                WHERE submission_id = ?;
                """,
                (review_status, notes, review_status, review_status, submission_id)
            )
            return cur.rowcount > 0

    def update_submission_notes(self, submission_id: str, notes: str) -> bool:
        """Organizer internal private notes update."""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE submissions SET organizer_notes = ? WHERE submission_id = ?;",
                (notes, submission_id)
            )
            return cur.rowcount > 0

    def update_submission_status(self, submission_id: str, new_status: str) -> bool:
        """Update the overall lifecycle status of a submission."""
        with self.db.transaction() as conn:
            cur = conn.execute(
                "UPDATE submissions SET submission_status = ? WHERE submission_id = ?;",
                (new_status, submission_id)
            )
            return cur.rowcount > 0

    def link_evaluation_job(self, submission_id: str, job_id: str) -> bool:
        """Link an executed or queued evaluation job to the submission."""
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE submissions SET
                    linked_evaluation_job_id = ?,
                    submission_status = 'EVALUATING'
                WHERE submission_id = ?;
                """,
                (job_id, submission_id)
            )
            return cur.rowcount > 0

    # -------------------------------------------------------------------------
    # Discovery Reports Management
    # -------------------------------------------------------------------------

    def insert_discovery_report(
        self,
        discovery_id: str,
        submission_id: str,
        commit_sha: str,
        status: str,
        interface_status: str,
        confidence: str,
        report_json: str,
        created_at: str,
    ) -> None:
        """Persist a dynamic discovery report associated with submission and commit."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO discovery_reports (
                    discovery_id, submission_id, commit_sha, status,
                    interface_status, confidence, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    discovery_id,
                    submission_id,
                    commit_sha,
                    status,
                    interface_status,
                    confidence,
                    report_json,
                    created_at,
                )
            )

    def get_discovery_report(self, discovery_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific discovery report by ID."""
        with self.db.readonly() as conn:
            row = conn.execute(
                "SELECT * FROM discovery_reports WHERE discovery_id = ?;",
                (discovery_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "discovery_id": row["discovery_id"],
                "submission_id": row["submission_id"],
                "commit_sha": row["commit_sha"],
                "status": row["status"],
                "interface_status": row["interface_status"],
                "confidence": row["confidence"],
                "report_json": row["report_json"],
                "created_at": row["created_at"],
            }

    def get_latest_discovery_report_for_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the latest discovery report for a submission."""
        with self.db.readonly() as conn:
            row = conn.execute(
                """
                SELECT * FROM discovery_reports
                WHERE submission_id = ?
                ORDER BY created_at DESC LIMIT 1;
                """,
                (submission_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "discovery_id": row["discovery_id"],
                "submission_id": row["submission_id"],
                "commit_sha": row["commit_sha"],
                "status": row["status"],
                "interface_status": row["interface_status"],
                "confidence": row["confidence"],
                "report_json": row["report_json"],
                "created_at": row["created_at"],
            }

