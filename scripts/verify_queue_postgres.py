import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from hydraforge.database.connection import DatabaseManager
from hydraforge.database.repository import EvaluationRepository
from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.evaluation.queue import PersistentEvaluationQueue, QueueStatus

db_url = "postgresql://neondb_owner:npg_x5dXuDFNvaW8@ep-misty-art-ao1lof4u-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
os.environ["DATABASE_URL"] = db_url

mgr = DatabaseManager()
repo = EvaluationRepository(db_manager=mgr)
queue = PersistentEvaluationQueue(db_manager=mgr)

test_job_id = f"job_neon_{int(datetime.now(timezone.utc).timestamp())}"
job = EvaluationJob(
    job_id=test_job_id,
    repository_url="https://github.com/basinshift/neon-test",
    commit_sha="b" * 40,
    contract_version="1.0.0",
    benchmark_version="1.0.0",
    scoring_config_version="1.0.0",
    execution_backend="docker",
    status=JobStatus.QUEUED,
    created_at=datetime.now(timezone.utc).isoformat(),
)
repo.insert_job(job)
print(f"1. Inserted job '{test_job_id}' into Neon evaluation_jobs.")

qid = queue.enqueue(test_job_id, priority=5)
print(f"2. Enqueued job into Neon evaluation_queue (queue_id: {qid}).")

claimed = queue.claim_next_job(worker_id="neon_worker_01")
assert claimed is not None and claimed.job_id == test_job_id
print(f"3. Atomically claimed job by 'neon_worker_01'.")

hb_ok = queue.heartbeat(qid, "neon_worker_01")
assert hb_ok
print("4. Successfully issued lease heartbeat on Neon PostgreSQL.")

comp_ok = queue.mark_completed(qid, "neon_worker_01")
assert comp_ok
print("5. Successfully transitioned job to COMPLETED on Neon PostgreSQL.")

status_counts = queue.get_queue_status()
print(f"6. Queue status counts on Neon: {status_counts}")
print("ALL NEON POSTGRESQL QUEUE OPERATIONS VERIFIED SUCCESSFULLY!")

