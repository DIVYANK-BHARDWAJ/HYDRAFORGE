# HYDRAFORGE — Final REST API Reference
**Version:** 1.0.0-PROD  
**Base URL:** `/api/v1`  

---

## 1. Public Participant Endpoints

### 1.1 Register Submission
- **Route:** `POST /api/v1/submissions`
- **Request Body (Strict 2-Field Whitelist):**
```json
{
  "team_name": "AlpineHydro",
  "repository_url": "https://github.com/alpine-hydro/topoflow-gnn"
}
```
- **Response (201 Created):**
```json
{
  "submission_id": "sub_a1b2c3d4e5f6",
  "team_name": "AlpineHydro",
  "repository_url": "https://github.com/alpine-hydro/topoflow-gnn",
  "commit_sha": "4a5b6c7d8e9f0123456789abcdef0123456789ab",
  "default_branch": "main",
  "verification_status": "VERIFIED",
  "verification_details": "Successfully resolved repository head commit",
  "submitted_at": "2026-11-05T08:30:00Z",
  "submission_status": "SUBMITTED",
  "message": "Submission received successfully. Store your Submission ID safely to check verification status and evaluation progress on the participant portal."
}
```

### 1.2 Check Public Submission Status
- **Route:** `GET /api/v1/submissions/{submission_id}/status`
- **Response (200 OK):**
```json
{
  "submission_id": "sub_a1b2c3d4e5f6",
  "team_name": "AlpineHydro",
  "submission_status": "SUBMITTED",
  "verification_status": "VERIFIED",
  "submitted_at": "2026-11-05T08:30:00Z"
}
```

### 1.3 Leaderboard
- **Route:** `GET /api/v1/leaderboard`
- **Query Params:** `benchmark_version` (default: "1.0.0")
- **Response (200 OK):** Returns ranked verified submissions with total scores and 6-axis breakdowns.

---

## 2. Private Organizer Endpoints (Authentication Required)

All organizer endpoints require an `Authorization: Bearer <token>` or `X-API-Key: <key>` header.

### 2.1 Organizer Login
- **Route:** `POST /api/v1/organizer/login`
- **Request Body:**
```json
{
  "username": "organizer",
  "password": "<ORGANIZER_PASS>"
}
```
- **Response (200 OK):**
```json
{
  "status": "authenticated",
  "token": "org_abcdef...",
  "token_type": "Bearer"
}
```

### 2.2 List Submissions for Review
- **Route:** `GET /api/v1/organizer/submissions`
- **Query Params:** `limit`, `offset`, `status`, `search`
- **Response (200 OK):** Includes internal organizer notes, review status, and commit SHAs.

### 2.3 Update Review Status
- **Route:** `PATCH /api/v1/organizer/submissions/{submission_id}/status`
- **Request Body:**
```json
{
  "status": "ACCEPTED",
  "notes": "Verified model code and project description. Approved for benchmark evaluation."
}
```

### 2.4 Trigger Evaluation
- **Route:** `POST /api/v1/organizer/submissions/{submission_id}/evaluate`
- **Response (202 Accepted):** Returns evaluation job ID and queues the job in `evaluation_queue`.

---

## 3. System & Health Endpoints

### 3.1 Health Check
- **Route:** `GET /health`
- **Response (200 OK):**
```json
{
  "status": "HEALTHY",
  "timestamp": "2026-11-05T08:30:00Z",
  "database": "CONNECTED",
  "version": "1.0.0"
}
```

### 3.2 System Status
- **Route:** `GET /api/v1/system`
- **Response (200 OK):** Execution backends, Docker daemon status, active worker count, benchmark version.

