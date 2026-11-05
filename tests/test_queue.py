"""
tests/test_queue.py
Unit and Integration Tests for Persistent Database-Backed Evaluation Queue.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from hydraforge.database.connection import DatabaseManager
from hydraforge.database.migrations import apply_migrations
from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.database.repository import EvaluationRepository
from hydraforge.evaluation.queue import PersistentEvaluationQueue, QueueStatus


@pytest.fixture
def clean_queue(tmp_path: Path):
    db_file = tmp_path / "queue_test.db"
    db_mgr = DatabaseManager(db_path=db_file)
    apply_migrations(db_mgr)
    repo = EvaluationRepository(db_manager=db_mgr)
    queue = PersistentEvaluationQueue(db_manager=db_mgr)
    return queue, repo, db_mgr


def _create_mock_job(repo: EvaluationRepository, job_id: str) -> None:
    job = EvaluationJob(
        job_id=job_id,
        repository_url="https://github.com/test/repo",
        commit_sha="a" * 40,
        contract_version="1.0.0",
        benchmark_version="1.0.0",
        scoring_config_version="1.0.0",
        execution_backend="docker",
        status=JobStatus.QUEUED,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    repo.insert_job(job)


def test_enqueue_and_priority_ordering(clean_queue):
    queue, repo, _ = clean_queue
    _create_mock_job(repo, "job_low")
    _create_mock_job(repo, "job_high")
    _create_mock_job(repo, "job_med")

    # Enqueue with different priorities
    queue.enqueue("job_low", priority=1)
    queue.enqueue("job_high", priority=10)
    queue.enqueue("job_med", priority=5)

    # Worker claims next job
    claimed1 = queue.claim_next_job(worker_id="worker_alpha")
    assert claimed1 is not None
    assert claimed1.job_id == "job_high"
    assert claimed1.status == QueueStatus.CLAIMED
    assert claimed1.claimed_by == "worker_alpha"

    claimed2 = queue.claim_next_job(worker_id="worker_beta")
    assert claimed2 is not None
    assert claimed2.job_id == "job_med"

    claimed3 = queue.claim_next_job(worker_id="worker_alpha")
    assert claimed3 is not None
    assert claimed3.job_id == "job_low"

    # Queue empty now
    claimed4 = queue.claim_next_job(worker_id="worker_alpha")
    assert claimed4 is None


def test_heartbeat_and_lifecycle(clean_queue):
    queue, repo, _ = clean_queue
    _create_mock_job(repo, "job_lifecycle")
    queue_id = queue.enqueue("job_lifecycle")

    item = queue.claim_next_job("worker_1")
    assert item is not None

    # Mark running
    ok_run = queue.mark_running(queue_id, "worker_1")
    assert ok_run

    # Heartbeat
    initial_hb = queue.get_queue_item(queue_id).heartbeat_at
    time.sleep(0.01)
    ok_hb = queue.heartbeat(queue_id, "worker_1")
    assert ok_hb
    new_hb = queue.get_queue_item(queue_id).heartbeat_at
    assert new_hb != initial_hb

    # Wrong worker cannot heartbeat
    wrong_hb = queue.heartbeat(queue_id, "worker_imposter")
    assert not wrong_hb

    # Mark completed
    ok_comp = queue.mark_completed(queue_id, "worker_1")
    assert ok_comp
    final_item = queue.get_queue_item(queue_id)
    assert final_item.status == QueueStatus.COMPLETED
    assert final_item.completed_at is not None


def test_retries_and_dead_letter_queue(clean_queue):
    queue, repo, _ = clean_queue
    _create_mock_job(repo, "job_retry")
    queue_id = queue.enqueue("job_retry", max_attempts=2)

    # Attempt 1
    w1_item = queue.claim_next_job("worker_1")
    assert w1_item is not None
    queue.mark_failed(queue_id, "worker_1", error_message="Transient network glitch")

    requeued_item = queue.get_queue_item(queue_id)
    assert requeued_item.status == QueueStatus.QUEUED
    assert requeued_item.attempts == 1
    assert requeued_item.claimed_by is None

    # Attempt 2 (exhausts budget)
    w2_item = queue.claim_next_job("worker_2")
    assert w2_item is not None
    queue.mark_failed(queue_id, "worker_2", error_message="Persistent failure")

    dead_letter_item = queue.get_queue_item(queue_id)
    assert dead_letter_item.status == QueueStatus.DEAD_LETTER
    assert dead_letter_item.attempts == 2
    assert dead_letter_item.completed_at is not None
    assert "Persistent failure" in dead_letter_item.error_message


def test_stale_lease_recovery(clean_queue):
    queue, repo, db_mgr = clean_queue
    _create_mock_job(repo, "job_stuck")
    queue_id = queue.enqueue("job_stuck", lease_timeout_seconds=10, max_attempts=2)

    # Claim job with worker_crashed
    claimed = queue.claim_next_job("worker_crashed", lease_seconds=10)
    assert claimed is not None

    # Artificially age the heartbeat in the database
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    with db_mgr.transaction() as conn:
        conn.execute(
            "UPDATE evaluation_queue SET heartbeat_at = ? WHERE queue_id = ?;",
            (stale_time, queue_id)
        )

    # Trigger recovery
    reaped = queue.reap_stale_leases()
    assert reaped == 1

    recovered_item = queue.get_queue_item(queue_id)
    assert recovered_item.status == QueueStatus.QUEUED
    assert recovered_item.attempts == 1
    assert recovered_item.claimed_by is None
    assert "Worker lease timed out" in recovered_item.error_message


def test_cancel_job(clean_queue):
    queue, repo, _ = clean_queue
    _create_mock_job(repo, "job_cancel")
    queue.enqueue("job_cancel")

    ok_cancel = queue.cancel_job("job_cancel")
    assert ok_cancel

    item = queue.get_item_by_job_id("job_cancel")
    assert item.status == QueueStatus.CANCELLED

