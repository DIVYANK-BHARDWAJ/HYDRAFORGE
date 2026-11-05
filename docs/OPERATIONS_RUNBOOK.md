# HYDRAFORGE — Operations & Incident Response Runbook
**Target Audience:** Site Reliability Engineers & Competition Operations  
**Date:** 2026-11-05  

---

## 1. Routine Operational Commands

### 1.1 Service Status & Health
```bash
# Check Docker compose status
docker compose -f docker-compose.prod.yml ps

# Check API health endpoint
curl -s http://localhost:5000/health | jq .

# Check queue statistics
curl -s -H "Authorization: Bearer $ORGANIZER_KEY" http://localhost:5000/api/v1/system | jq .queue_status
```

### 1.2 Database Maintenance & Queue Recovery
```bash
# Verify database connection and tables
python scripts/verify_db_connection.py

# Manually trigger stuck worker lease recovery
python -c "from hydraforge.evaluation.queue import PersistentEvaluationQueue; q = PersistentEvaluationQueue(); print('Reaped leases:', q.reap_stale_leases())"
```

---

## 2. Incident Response Playbooks

### Playbook 1: High Queue Latency / Backlog Growing
- **Symptom:** Submissions remain in `QUEUED` state for > 15 minutes.
- **Diagnosis:** Check active worker count and inspect worker container logs:
  ```bash
  docker compose -f docker-compose.prod.yml logs worker --tail=100
  ```
- **Remediation:** Scale the worker service horizontally:
  ```bash
  docker compose -f docker-compose.prod.yml up -d --scale worker=4
  ```

### Playbook 2: Stuck Worker Lease / Crashed Container
- **Symptom:** Job status is `RUNNING` or `CLAIMED` but worker has terminated.
- **Automatic Recovery:** The `PersistentEvaluationQueue.reap_stale_leases()` daemon automatically detects worker heartbeat expiration (300s timeout) and re-enqueues the job.
- **Manual Override:**
  ```bash
  python -c "from hydraforge.evaluation.queue import PersistentEvaluationQueue; q = PersistentEvaluationQueue(); q.reap_stale_leases()"
  ```

### Playbook 3: Database Connection Outage
- **Symptom:** API returns HTTP 500 with database connection errors.
- **Remediation:** Verify Neon connection string in `.env`, check network egress, and test connection with `scripts/verify_db_connection.py`.
