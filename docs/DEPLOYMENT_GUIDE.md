# HYDRAFORGE — Production Deployment Guide
**System:** HYDRAFORGE Evaluation Platform  
**Target Architecture:** Docker Compose / Cloud Kubernetes / AWS ECS  
**Date:** 2026-11-05  

---

## 1. Live Deployment Readiness & Status

> [!NOTE]
> **Status: `BLOCKED_EXTERNAL_REQUIREMENTS`**  
> All container definitions (`Dockerfile.api`, `Dockerfile.worker`, `frontend/Dockerfile`), Compose manifests (`docker-compose.yml`, `docker-compose.prod.yml`), and database connection adapters have been verified and built. However, live automated provisioning to external cloud infrastructure (e.g. AWS ECS, GCP Cloud Run) is blocked due to the absence of external cloud credentials in this local sandbox environment.

The instructions below detail how to deploy HYDRAFORGE to production once credentials and domain DNS are provisioned.

---

## 2. Environment Configuration

1. Create production `.env` from template:
   ```bash
   cp .env.example .env
   ```
2. Populate the required configuration variables:
   ```bash
   # Neon Serverless PostgreSQL / AWS RDS URL
   DATABASE_URL=postgresql://neondb_owner:<PASSWORD>@ep-misty-art-ao1lof4u-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

   # Cryptographic secrets
   HYDRAFORGE_SECRET_KEY=<SECURE_RANDOM_256BIT_HEX>
   HYDRAFORGE_ORGANIZER_USER=admin
   HYDRAFORGE_ORGANIZER_PASS=<STRONG_ORGANIZER_PASSWORD>
   HYDRAFORGE_ORGANIZER_KEY=<SECURE_API_BEARER_KEY>

   # Isolation configuration
   EXECUTION_BACKEND=docker
   DOCKER_NETWORK=none
   LEASE_TIMEOUT_SECONDS=300
   ```

---

## 3. Production Deployment with Docker Compose

Run the hardened production stack:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Verified Service Stack:
- **`hydraforge_api_prod`**: Gunicorn WSGI server, 4 worker threads, read-only root filesystem, dropped capabilities, unprivileged user `10001:10001`.
- **`hydraforge_worker_prod`**: Autonomous worker daemon leasing jobs from `evaluation_queue`, executing isolated evaluations, renewing heartbeats.
- **`hydraforge_frontend_prod`**: Unprivileged Nginx container serving compiled Vite/React static assets and reverse-proxying `/api` requests.

---

## 4. Verification Smoke Test

1. Verify API health check:
   ```bash
   curl -f http://localhost:5000/health
   ```
2. Verify Database connection & migrations:
   ```bash
   python scripts/verify_db_connection.py
   ```
3. Verify Queue processing:
   ```bash
   python scripts/verify_queue_postgres.py
   ```
