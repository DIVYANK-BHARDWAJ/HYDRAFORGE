# HYDRAFORGE — Backup & Disaster Recovery Plan
**System:** HYDRAFORGE PostgreSQL Database & Leaderboard State  
**RPO:** 1 Hour | **RTO:** 15 Minutes  
**Date:** 2026-11-05  

---

## 1. Database Backup Strategy

HYDRAFORGE uses Neon Serverless PostgreSQL for production state:
1. **Automated Continuous Backups**: Neon maintains continuous point-in-time recovery (PITR) with branch snapshots.
2. **Scheduled Logical Dump**:
   ```bash
   pg_dump "$DATABASE_URL" --format=custom --file="backups/hydraforge_$(date +%Y%m%d_%H%M%S).dump"
   ```

---

## 2. Disaster Recovery & Restoration Procedure

To restore the competition state from a logical dump:
1. Provision a new PostgreSQL instance or create a new branch in Neon.
2. Restore the dump:
   ```bash
   pg_restore --clean --if-exists --no-owner --dbname="$NEW_DATABASE_URL" backups/hydraforge_latest.dump
   ```
3. Run migration verification:
   ```bash
   DATABASE_URL="$NEW_DATABASE_URL" python scripts/verify_db_connection.py
   ```
4. Verify table integrity and leaderboard counts:
   ```bash
   DATABASE_URL="$NEW_DATABASE_URL" python -m pytest tests/test_database.py
   ```
