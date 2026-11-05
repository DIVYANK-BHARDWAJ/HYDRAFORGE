"""Database Schema Migrations and DDL Definitions."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from hydraforge.database.connection import DatabaseManager


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS evaluation_jobs (
    job_id TEXT PRIMARY KEY,
    repository_url TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    submission_metadata TEXT,
    contract_version TEXT NOT NULL,
    benchmark_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    execution_backend TEXT NOT NULL,
    job_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    failure_reason TEXT,
    final_score REAL,
    report_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON evaluation_jobs(job_status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON evaluation_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_commit ON evaluation_jobs(commit_sha);

CREATE TABLE IF NOT EXISTS evaluation_results (
    result_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE,
    total_score REAL NOT NULL,
    forecast_skill REAL NOT NULL,
    event_detection REAL NOT NULL,
    generalization REAL NOT NULL,
    calibration REAL NOT NULL,
    robustness REAL NOT NULL,
    efficiency REAL NOT NULL,
    full_report_json TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES evaluation_jobs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_results_score ON evaluation_results(total_score DESC);

CREATE TABLE IF NOT EXISTS system_metadata (
    metadata_key TEXT PRIMARY KEY,
    metadata_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    team_name TEXT NOT NULL,
    repository_url TEXT NOT NULL,
    deployed_website_url TEXT NOT NULL,
    commit_sha TEXT,
    default_branch TEXT DEFAULT 'main',
    website_status TEXT DEFAULT 'PENDING',
    team_leader TEXT,
    contact_email TEXT,
    team_members TEXT,
    institution TEXT,
    project_name TEXT,
    project_description TEXT,
    programming_language TEXT,
    model_architecture TEXT,
    training_datasets TEXT,
    dataset_sources TEXT,
    dataset_licenses TEXT,
    pretrained_models TEXT,
    inference_time_data TEXT,
    provenance_notes TEXT,
    declaration_status INTEGER NOT NULL DEFAULT 1,
    submitted_at TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'PENDING',
    verification_details TEXT,
    organizer_review_status TEXT NOT NULL DEFAULT 'UNDER_REVIEW',
    organizer_notes TEXT,
    submission_status TEXT NOT NULL DEFAULT 'SUBMITTED',
    linked_evaluation_job_id TEXT,
    FOREIGN KEY(linked_evaluation_job_id) REFERENCES evaluation_jobs(job_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_submissions_created ON submissions(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_review ON submissions(organizer_review_status);
CREATE INDEX IF NOT EXISTS idx_submissions_team ON submissions(team_name);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(submission_status);

CREATE TABLE IF NOT EXISTS discovery_reports (
    discovery_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    status TEXT NOT NULL,
    interface_status TEXT NOT NULL,
    confidence TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_discovery_sub ON discovery_reports(submission_id);
CREATE INDEX IF NOT EXISTS idx_discovery_commit ON discovery_reports(commit_sha);

CREATE TABLE IF NOT EXISTS evaluation_queue (
    queue_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE,
    submission_id TEXT,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    claimed_by TEXT,
    claimed_at TEXT,
    heartbeat_at TEXT,
    lease_timeout_seconds INTEGER NOT NULL DEFAULT 300,
    enqueued_at TEXT NOT NULL,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY(job_id) REFERENCES evaluation_jobs(job_id) ON DELETE CASCADE,
    FOREIGN KEY(submission_id) REFERENCES submissions(submission_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_queue_status_prio ON evaluation_queue(status, priority DESC, enqueued_at ASC);
CREATE INDEX IF NOT EXISTS idx_queue_claimed_hb ON evaluation_queue(claimed_by, heartbeat_at);

CREATE TABLE IF NOT EXISTS organizer_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'organizer',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_username ON organizer_users(username);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    target_id TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);
"""


def apply_migrations(db_manager: Optional[DatabaseManager] = None) -> None:
    """Apply DDL migrations idempotently and record schema version."""
    manager = db_manager or DatabaseManager()
    with manager.transaction() as conn:
        conn.executescript(SCHEMA_DDL)
        if getattr(manager, "is_postgres", False):
            conn.execute(
                """
                INSERT INTO system_metadata (metadata_key, metadata_value, updated_at)
                VALUES ('schema_version', '3', CURRENT_TIMESTAMP)
                ON CONFLICT (metadata_key) DO NOTHING;
                """
            )
        else:
            conn.execute(
                """
                INSERT OR IGNORE INTO system_metadata (metadata_key, metadata_value, updated_at)
                VALUES ('schema_version', '3', datetime('now', 'utc'));
                """
            )
            # Migrate existing submissions table if missing Phase 4B correction columns
            try:
                cur = conn.execute("PRAGMA table_info(submissions);")
                columns = [row["name"] for row in cur.fetchall()]
                if "deployed_website_url" not in columns:
                    conn.execute("ALTER TABLE submissions ADD COLUMN deployed_website_url TEXT DEFAULT '';")
                if "default_branch" not in columns:
                    conn.execute("ALTER TABLE submissions ADD COLUMN default_branch TEXT DEFAULT 'main';")
                if "website_status" not in columns:
                    conn.execute("ALTER TABLE submissions ADD COLUMN website_status TEXT DEFAULT 'PENDING';")
            except Exception:
                pass
