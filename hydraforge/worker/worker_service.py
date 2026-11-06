"""
hydraforge/worker/worker_service.py
Evaluation Worker Daemon Service.
Continuously polls the persistent evaluation queue, claims jobs via leases,
renews heartbeats asynchronously, executes evaluations via BenchmarkEvaluationPipeline,
and records comprehensive results.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
import time
import uuid
from typing import Optional

from hydraforge.database.connection import DatabaseManager
from hydraforge.database.repository import EvaluationRepository
from hydraforge.evaluation.pipeline import BenchmarkEvaluationPipeline
from hydraforge.evaluation.queue import PersistentEvaluationQueue, QueueItem, QueueStatus


class EvaluationWorkerDaemon:
    """
    Autonomous worker daemon that leases and processes jobs from the persistent queue.
    Includes background heartbeating, safe signal handling, and fail-closed isolation.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        poll_interval: float = 2.0,
        lease_seconds: int = 300,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.worker_id = worker_id or f"worker_{socket.gethostname()}_{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.db = db_manager or DatabaseManager()
        self.repo = EvaluationRepository(db_manager=self.db)
        self.queue = PersistentEvaluationQueue(db_manager=self.db)
        self.pipeline = BenchmarkEvaluationPipeline(repository=self.repo)

        self._stop_event = threading.Event()
        self._current_job: Optional[QueueItem] = None
        self._heartbeat_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Run the worker loop until stopped."""
        print(f"[{self.worker_id}] Evaluation worker daemon started.")
        self._register_signals()

        while not self._stop_event.is_set():
            try:
                # 1. Periodically check and reap stale crashed leases
                self.queue.reap_stale_leases()

                # 2. Try claiming next queued job
                item = self.queue.claim_next_job(
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds
                )

                if not item:
                    time.sleep(self.poll_interval)
                    continue

                # 3. Process claimed job
                self._process_claimed_job(item)

            except Exception as e:
                print(f"[{self.worker_id}] Error in worker loop: {e}", file=sys.stderr)
                time.sleep(self.poll_interval)

        print(f"[{self.worker_id}] Worker daemon stopped cleanly.")

    def stop(self) -> None:
        """Signal worker to stop gracefully."""
        self._stop_event.set()

    def _process_claimed_job(self, item: QueueItem) -> None:
        """Execute a claimed evaluation job under an active heartbeat lease."""
        self._current_job = item
        queue_id = item.queue_id
        job_id = item.job_id
        print(f"[{self.worker_id}] Claimed job '{job_id}' (queue_id: {queue_id}).")

        # Mark RUNNING in queue
        self.queue.mark_running(queue_id, self.worker_id)

        # Start asynchronous heartbeat thread
        hb_stop = threading.Event()
        hb_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(queue_id, hb_stop),
            daemon=True
        )
        hb_thread.start()

        try:
            # Execute pipeline
            report = self.pipeline.evaluate_submission(
                job_id=job_id,
                submission_id=item.submission_id or "sub_direct",
                repository_url="",
                commit_sha="",
            )

            if report.status == "COMPLETED":
                self.queue.mark_completed(queue_id, self.worker_id)
                print(f"[{self.worker_id}] Completed job '{job_id}' (Score: {report.composite_score:.4f}).")
            else:
                err_msg = report.error_message or "Evaluation failed."
                self.queue.mark_failed(queue_id, self.worker_id, error_message=err_msg)
                print(f"[{self.worker_id}] Failed job '{job_id}': {err_msg}")

        except Exception as e:
            err = f"Unhandled worker exception: {str(e)}"
            self.queue.mark_failed(queue_id, self.worker_id, error_message=err)
            print(f"[{self.worker_id}] Exception evaluating job '{job_id}': {err}", file=sys.stderr)

        finally:
            hb_stop.set()
            hb_thread.join(timeout=2.0)
            self._current_job = None

    def _heartbeat_loop(self, queue_id: str, stop_event: threading.Event) -> None:
        """Periodically update heartbeat_at timestamp while job is processing."""
        interval = max(5.0, self.lease_seconds / 3.0)
        while not stop_event.is_set():
            if stop_event.wait(timeout=interval):
                break
            try:
                self.queue.heartbeat(queue_id, self.worker_id)
            except Exception:
                pass

    def _register_signals(self) -> None:
        """Register OS interrupt signals for graceful worker termination."""
        def handler(sig, frame):
            print(f"[{self.worker_id}] Caught termination signal {sig}. Initiating graceful shutdown...")
            self.stop()

        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except Exception:
            pass


if __name__ == "__main__":
    daemon = EvaluationWorkerDaemon()
    daemon.start()


