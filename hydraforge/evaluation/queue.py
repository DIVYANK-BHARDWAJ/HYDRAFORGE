"""
hydraforge/evaluation/queue.py
Durable Database-Backed Evaluation Queue with Atomic Leases, Heartbeats, and Crash Recovery.
Works identically across SQLite and PostgreSQL.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from hydraforge.database.connection import DatabaseManager


class QueueStatus(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


@dataclass
class QueueItem:
    queue_id: str
    job_id: str
    submission_id: Optional[str]
    status: QueueStatus
    priority: int
    attempts: int
    max_attempts: int
    claimed_by: Optional[str]
    claimed_at: Optional[str]
    heartbeat_at: Optional[str]
    lease_timeout_seconds: int
    enqueued_at: str
    completed_at: Optional[str]
    error_message: Optional[str]


class PersistentEvaluationQueue:
    """
    Persistent, transactional job queue with worker leases, heartbeats,
    exponential retries, dead-letter storage, and stale lease recovery.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager()

    def enqueue(
        self,
        job_id: str,
        submission_id: Optional[str] = None,
        priority: int = 0,
        max_attempts: int = 3,
        lease_timeout_seconds: int = 300
    ) -> str:
        """Enqueue an evaluation job for asynchronous execution."""
        queue_id = f"q_{uuid.uuid4().hex[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_queue (
                    queue_id, job_id, submission_id, status, priority,
                    attempts, max_attempts, claimed_by, claimed_at,
                    heartbeat_at, lease_timeout_seconds, enqueued_at,
                    completed_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, NULL, NULL);
                """,
                (
                    queue_id,
                    job_id,
                    submission_id,
                    QueueStatus.QUEUED.value,
                    priority,
                    0,
                    max_attempts,
                    lease_timeout_seconds,
                    now_iso,
                )
            )
        return queue_id

    def claim_next_job(
        self,
        worker_id: str,
        lease_seconds: Optional[int] = None
    ) -> Optional[QueueItem]:
        """
        Atomically claim the highest-priority queued job.
        Ensures strict mutual exclusion between workers.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self.db.transaction() as conn:
            # 1. Recover stale leases first within the transaction
            self._recover_stale_leases_tx(conn, now)

            # 2. Select next eligible job
            row = conn.execute(
                """
                SELECT * FROM evaluation_queue
                WHERE status = ?
                ORDER BY priority DESC, enqueued_at ASC
                LIMIT 1;
                """,
                (QueueStatus.QUEUED.value,)
            ).fetchone()

            if not row:
                return None

            item_dict = dict(row)
            queue_id = item_dict["queue_id"]
            timeout_sec = lease_seconds or int(item_dict.get("lease_timeout_seconds", 300))

            # 3. Atomically claim
            conn.execute(
                """
                UPDATE evaluation_queue
                SET status = ?,
                    claimed_by = ?,
                    claimed_at = ?,
                    heartbeat_at = ?,
                    lease_timeout_seconds = ?
                WHERE queue_id = ? AND status = ?;
                """,
                (
                    QueueStatus.CLAIMED.value,
                    worker_id,
                    now_iso,
                    now_iso,
                    timeout_sec,
                    queue_id,
                    QueueStatus.QUEUED.value,
                )
            )

            # Re-read claimed record
            claimed_row = conn.execute(
                "SELECT * FROM evaluation_queue WHERE queue_id = ?;",
                (queue_id,)
            ).fetchone()

            if not claimed_row:
                return None

            return self._row_to_item(claimed_row)

    def heartbeat(self, queue_id: str, worker_id: str) -> bool:
        """Renew the worker lease heartbeat timestamp."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE evaluation_queue
                SET heartbeat_at = ?
                WHERE queue_id = ? AND claimed_by = ?
                  AND status IN (?, ?);
                """,
                (
                    now_iso,
                    queue_id,
                    worker_id,
                    QueueStatus.CLAIMED.value,
                    QueueStatus.RUNNING.value,
                )
            )
            return cur.rowcount > 0

    def mark_running(self, queue_id: str, worker_id: str) -> bool:
        """Transition claimed job to running state."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE evaluation_queue
                SET status = ?, heartbeat_at = ?
                WHERE queue_id = ? AND claimed_by = ? AND status = ?;
                """,
                (
                    QueueStatus.RUNNING.value,
                    now_iso,
                    queue_id,
                    worker_id,
                    QueueStatus.CLAIMED.value,
                )
            )
            return cur.rowcount > 0

    def mark_completed(self, queue_id: str, worker_id: str) -> bool:
        """Mark job successfully completed."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE evaluation_queue
                SET status = ?, completed_at = ?, heartbeat_at = ?
                WHERE queue_id = ? AND claimed_by = ?;
                """,
                (
                    QueueStatus.COMPLETED.value,
                    now_iso,
                    now_iso,
                    queue_id,
                    worker_id,
                )
            )
            return cur.rowcount > 0

    def mark_failed(
        self,
        queue_id: str,
        worker_id: str,
        error_message: str
    ) -> bool:
        """
        Record failure. If retry budget remains, re-enqueue.
        Otherwise transition to DEAD_LETTER.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_queue WHERE queue_id = ?;",
                (queue_id,)
            ).fetchone()
            if not row:
                return False

            item = dict(row)
            attempts = int(item.get("attempts", 0)) + 1
            max_attempts = int(item.get("max_attempts", 3))

            if attempts >= max_attempts:
                new_status = QueueStatus.DEAD_LETTER.value
            else:
                new_status = QueueStatus.QUEUED.value

            conn.execute(
                """
                UPDATE evaluation_queue
                SET status = ?,
                    attempts = ?,
                    error_message = ?,
                    claimed_by = NULL,
                    claimed_at = NULL,
                    heartbeat_at = NULL,
                    completed_at = CASE WHEN ? = ? THEN ? ELSE NULL END
                WHERE queue_id = ?;
                """,
                (
                    new_status,
                    attempts,
                    error_message,
                    new_status,
                    QueueStatus.DEAD_LETTER.value,
                    now_iso,
                    queue_id,
                )
            )
            return True

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE evaluation_queue
                SET status = ?, completed_at = ?, error_message = 'Job cancelled by organizer.'
                WHERE job_id = ? AND status IN (?, ?);
                """,
                (
                    QueueStatus.CANCELLED.value,
                    now_iso,
                    job_id,
                    QueueStatus.QUEUED.value,
                    QueueStatus.CLAIMED.value,
                )
            )
            return cur.rowcount > 0

    def reap_stale_leases(self) -> int:
        """Public method to manually trigger crash recovery and lease reaping."""
        now = datetime.now(timezone.utc)
        with self.db.transaction() as conn:
            return self._recover_stale_leases_tx(conn, now)

    def _recover_stale_leases_tx(self, conn: Any, now: datetime) -> int:
        """Internal lease recovery logic executed inside caller transaction."""
        reaped = 0
        rows = conn.execute(
            """
            SELECT * FROM evaluation_queue
            WHERE status IN (?, ?);
            """,
            (QueueStatus.CLAIMED.value, QueueStatus.RUNNING.value)
        ).fetchall()

        for r in rows:
            item = dict(r)
            hb_str = item.get("heartbeat_at") or item.get("claimed_at")
            timeout_sec = int(item.get("lease_timeout_seconds", 300))

            if not hb_str:
                continue

            try:
                hb_dt = datetime.fromisoformat(hb_str)
                if hb_dt.tzinfo is None:
                    hb_dt = hb_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            # Check if lease expired
            if (now - hb_dt).total_seconds() > timeout_sec:
                attempts = int(item.get("attempts", 0)) + 1
                max_attempts = int(item.get("max_attempts", 3))
                qid = item["queue_id"]

                if attempts >= max_attempts:
                    status = QueueStatus.DEAD_LETTER.value
                    err = f"Worker lease timed out after {timeout_sec}s. Exceeded max attempts ({attempts}/{max_attempts})."
                else:
                    status = QueueStatus.QUEUED.value
                    err = f"Worker lease timed out after {timeout_sec}s. Re-queued for attempt {attempts + 1}."

                conn.execute(
                    """
                    UPDATE evaluation_queue
                    SET status = ?,
                        attempts = ?,
                        error_message = ?,
                        claimed_by = NULL,
                        claimed_at = NULL,
                        heartbeat_at = NULL
                    WHERE queue_id = ?;
                    """,
                    (status, attempts, err, qid)
                )
                reaped += 1

        return reaped

    def get_queue_status(self) -> Dict[str, int]:
        """Return counts of jobs by status."""
        counts = {s.value: 0 for s in QueueStatus}
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM evaluation_queue GROUP BY status;"
            ).fetchall()
            for r in rows:
                row_dict = dict(r)
                stat = row_dict["status"]
                if stat in counts:
                    counts[stat] = int(row_dict["count"])
        return counts

    def get_queue_item(self, queue_id: str) -> Optional[QueueItem]:
        """Fetch a specific queue record by ID."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_queue WHERE queue_id = ?;",
                (queue_id,)
            ).fetchone()
            return self._row_to_item(row) if row else None

    def get_item_by_job_id(self, job_id: str) -> Optional[QueueItem]:
        """Fetch queue record for a job ID."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_queue WHERE job_id = ?;",
                (job_id,)
            ).fetchone()
            return self._row_to_item(row) if row else None

    @staticmethod
    def _row_to_item(row: Any) -> QueueItem:
        d = dict(row)
        return QueueItem(
            queue_id=d["queue_id"],
            job_id=d["job_id"],
            submission_id=d.get("submission_id"),
            status=QueueStatus(d["status"]),
            priority=int(d.get("priority", 0)),
            attempts=int(d.get("attempts", 0)),
            max_attempts=int(d.get("max_attempts", 3)),
            claimed_by=d.get("claimed_by"),
            claimed_at=d.get("claimed_at"),
            heartbeat_at=d.get("heartbeat_at"),
            lease_timeout_seconds=int(d.get("lease_timeout_seconds", 300)),
            enqueued_at=d["enqueued_at"],
            completed_at=d.get("completed_at"),
            error_message=d.get("error_message"),
        )

