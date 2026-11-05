# HYDRAFORGE — Phase 4B Implementation Report
## Public Participant Portal, Team Registration & GitHub Project Submission

**Project:** HYDRAFORGE — The Intelligence Evaluation Engine  
**Tagline:** *Train anywhere. Predict anywhere. Prove your model.*  
**Competition:** BASINSHIFT — Hydrological Forecasting Challenge  
**Date:** November 2026  
**Status:** Completed & Verified (92/92 Automated Tests Passing, 14/14 End-to-End Workflow Steps Verified)

---

## 1. Executive Summary

Phase 4B extends HYDRAFORGE with two distinct operational experiences:
1. **Public Participant Portal:** An open, unauthenticated web interface where competitive teams register, inspect submission guidelines, submit their GitHub repositories with complete dataset disclosures and declarations, and track verification/review status using unpredictable submission tokens.
2. **Private Organizer Console:** An authenticated administrative interface guarded by HMAC session tokens, enabling competition organizers to review submissions, inspect detailed training data provenance, record internal confidential review notes, accept or reject submissions, and safely trigger automated evaluations.

All existing code, schemas, benchmark suites, deterministic scoring engines, and 77 unit tests from Phases 1–4 have been strictly preserved. An additional 15 tests have been added, bringing the verified suite to **92 tests**.

---

## 2. Participant Frontend & Submission Fields

The portal provides an offline-first, responsive interface styled in dark navy and electric cyan/blue:

### Landing Page Sections
- **Hero Banner:** Challenge title, mission explanation, direct CTAs to register, inspect guidelines, and track submissions.
- **Challenge Overview:** Technical framing of river-discharge prediction across ungauged river basins under climate and distribution shift.
- **Evaluation Dimensions:** Full breakdown of the 6 evaluation axes (Forecast Skill 25 pts, Event Detection 25 pts, Generalization 20 pts, Calibration 15 pts, Robustness 10 pts, Efficiency 5 pts). Marked as provisional pending organizer ratification.
- **Submission Requirements:** Git repository format, 40-character commit SHA, `submission_manifest.json` requirements, and open dataset disclosure rules. Deadlines, awards, and team limits are marked "To be announced".

### 4-Section Team Submission Form
- **Section A — Team Information:**
  - `team_name` (Required): Name of the competitive team.
  - `team_leader` (Required): Full name of the team leader.
  - `contact_email` (Required): Primary email address (validated by RFC regex).
  - `institution` (Optional): Academic, industry, or research affiliation.
  - `team_members` (Optional): List of participating researchers and engineers.
- **Section B — Project Information:**
  - `project_name` (Required): Name of the forecasting model or architecture.
  - `project_description` (Required): Brief summary of physical inductive biases and methodology.
  - `programming_language` (Required): e.g., Python 3.11, Julia, C++.
  - `model_architecture` (Required): e.g., Spatio-temporal GNN + TCN.
  - `repository_url` (Required): Git repository URL (must be public GitHub or GitLab; SSRF, private IPs, and localhost rejected).
  - `commit_sha` (Required): Immutable 40-character hexadecimal commit SHA.
- **Section C — Dataset & Pretraining Disclosure:**
  - `training_datasets` (Required): All training datasets utilized (open dataset policy; no closed whitelist).
  - `dataset_sources` (Required): Providers/repositories (ECMWF, NCAR, Zenodo, etc.).
  - `dataset_licenses` (Required): Applicable data licenses (CC-BY 4.0, ODbL, etc.).
  - `pretrained_models` (Required): Pretrained model weights origin (or "None").
  - `inference_time_data` (Required): Covariates required at forecast origin (or "None").
  - `provenance_notes` (Required): Imputation, catchment area scaling, and temporal coverage notes.
- **Section D — Mandatory Declarations:**
  - Authority to submit code and models.
  - Complete and accurate dataset disclosures.
  - Full compliance with applicable data licenses.
  - Supplementary inference data compliance (no future targets).
  - Zero access to or training on hidden benchmark evaluation targets.
  - Agreement to published evaluation rules and platform policies.

---

## 3. Database Schema Changes

The SQLite database (`data/hydraforge.db`) was extended with a dedicated `submissions` table, physically separating participant registrations from automated evaluation jobs:

```sql
CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    team_name TEXT NOT NULL,
    team_leader TEXT NOT NULL,
    contact_email TEXT NOT NULL,
    team_members TEXT,
    institution TEXT,
    project_name TEXT NOT NULL,
    project_description TEXT NOT NULL,
    repository_url TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    programming_language TEXT NOT NULL,
    model_architecture TEXT NOT NULL,
    training_datasets TEXT NOT NULL,
    dataset_sources TEXT NOT NULL,
    dataset_licenses TEXT NOT NULL,
    pretrained_models TEXT NOT NULL,
    inference_time_data TEXT NOT NULL,
    provenance_notes TEXT NOT NULL,
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
```

---

## 4. Backend REST API Endpoints

### Public Participant Endpoints
| Method | Route | Description | Privacy / Security Guard |
|---|---|---|---|
| `POST` | `/api/v1/submissions` | Register new submission | Validates URL/SHA, generates unpredictable ID, never executes code |
| `GET` | `/api/v1/submissions/<id>/status` | Public status check | Masks email, strictly strips internal organizer notes |
| `GET` | `/api/v1/submissions/<id>/confirmation` | Submission receipt | Safe confirmation information |
| `POST` | `/api/v1/submissions/<id>/verify` | Safe metadata verification | Tests URL/SHA format without executing scripts |

### Private Organizer Endpoints
| Method | Route | Description | Auth Requirement |
|---|---|---|---|
| `POST` | `/api/v1/organizer/login` | Authenticate organizer | Verifies credentials, returns session Bearer token |
| `GET` | `/api/v1/organizer/submissions` | List all submissions | Requires `@require_organizer_auth`, includes private notes |
| `GET` | `/api/v1/organizer/submissions/<id>` | Full submission inspection | Complete dataset disclosures & audit trail |
| `PATCH` | `/api/v1/organizer/submissions/<id>/status` | Review decision | Update status to `ACCEPTED` or `REJECTED` |
| `PATCH` | `/api/v1/organizer/submissions/<id>/notes` | Internal review notes | Private organizer comments (never public) |
| `POST` | `/api/v1/organizer/submissions/<id>/evaluate` | Trigger evaluation | **Fail-closed:** Blocks if Docker daemon is offline |

---

## 5. Security, Isolation & Privacy Controls

1. **Fail-Closed Execution Invariant:**
   If the approved container worker (Docker) is offline, untrusted participant code is never executed. Instead of crashing or failing the submission, the platform records:
   `EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE`.
   Submissions remain safely preserved in the organizer review queue.
2. **Local Trusted Runner Guard:**
   `LocalTestRunner` strictly checks that repository paths reside inside the project's developer `tests/fixtures/` directory. Even if a participant or caller passes `--trusted`, arbitrary local repositories outside test fixtures are rejected with `UnsafeExecutionEnvironmentError`.
3. **Internal Notes Privacy:**
   `organizer_notes` are stored in the database but stripped by default in all public DAO queries (`get_submission`, `list_submissions`). Contact emails are masked (`sa***@institution.edu`) on public status lookups.
4. **Organizer Authentication:**
   Protected by `require_organizer_auth` decorator verifying HTTP Bearer tokens or `X-Organizer-Key` headers. Rejects unauthenticated requests with HTTP `401 Unauthorized`.
5. **No Credential Ingestion:**
   Participant submissions containing GitHub personal access tokens (`ghp_`, `github_pat_`) or Bearer tokens are rejected on registration.

---

## 6. Submission Lifecycle State Machine

```
               [Public Registration]
                         │
                         ▼
                     SUBMITTED
                         │
                         ▼
               VERIFICATION_PENDING
                         │
                         ▼
                     VERIFIED
                         │
                         ▼
                   UNDER_REVIEW
                   ┌─────┴─────┐
                   ▼           ▼
               ACCEPTED     REJECTED
                   │
                   ▼ (Organizer Trigger)
          [Safe Worker Check]
           ├── Docker Offline  ──► EVALUATION PENDING — SAFE WORKER UNAVAILABLE (Held)
           └── Docker Online   ──► EVALUATION_QUEUED
                                         │
                                         ▼
                                     EVALUATING
                                   ┌─────┴─────┐
                                   ▼           ▼
                          EVALUATION_COMPLETED  EVALUATION_FAILED
```

---

## 7. Verification & Automated Test Output

Total Suite: **92 Automated Tests** (100% Pass Rate).  
Runtime: **17.25 seconds**.

```text
tests/test_api.py (9 tests) PASSED
tests/test_baselines.py (5 tests) PASSED
tests/test_benchmark.py (8 tests) PASSED
tests/test_cli.py (6 tests) PASSED
tests/test_database.py (6 tests) PASSED
tests/test_metrics.py (19 tests) PASSED
tests/test_runner.py (4 tests) PASSED
tests/test_schema.py (9 tests) PASSED
tests/test_security.py (5 tests) PASSED
tests/test_submission.py (6 tests) PASSED
tests/test_submissions_portal.py (15 tests) PASSED:
  - test_valid_team_submission PASSED
  - test_missing_team_name PASSED
  - test_missing_project_name PASSED
  - test_invalid_email PASSED
  - test_invalid_repository_url_ssrf PASSED
  - test_invalid_commit_sha PASSED
  - test_missing_dataset_disclosures PASSED
  - test_missing_declarations PASSED
  - test_duplicate_submission PASSED
  - test_submission_id_uniqueness PASSED
  - test_public_status_privacy_and_internal_notes_shielded PASSED
  - test_organizer_authentication_and_authorization PASSED
  - test_organizer_review_and_internal_notes_lifecycle PASSED
  - test_evaluation_blocked_when_safe_worker_unavailable PASSED
  - test_trusted_fixture_cannot_execute_arbitrary_repo PASSED

============================= 92 passed in 17.25s =============================
```

### End-to-End Workflow Verification Output (`scripts/verify_workflow.py`):
```text
======================================================================
HYDRAFORGE PHASE 4B: END-TO-END APPLICATION WORKFLOW VERIFICATION
======================================================================
[Step 1] Participant opens landing page (GET /)...
  -> OK: Public landing page served successfully (HTTP 200).
[Steps 2-6] Participant fills out team, project, dataset disclosures & declarations...
[Step 7] Generated unique unpredictable Submission ID: sub_63be1ec38c154c709121767411cb4df9
  -> OK: Cryptographically secure identifier created.
[Step 8] Participant receives submission confirmation (GET /confirmation)...
  -> OK: Confirmation verified for team 'GlacierAI'.
[Step 9] Participant queries public status (GET /status)...
  -> Status: UNDER_REVIEW, Verification: VERIFIED
  -> OK: Safe participant status verified (internal notes shielded).
[Step 10] Organizer authenticates (POST /api/v1/organizer/login)...
  -> OK: Authorized session token issued (org_0f14102f8439...).
[Step 11] Organizer inspects submission and dataset disclosures...
  -> Datasets Disclosed: Caravan Extension, CAMELS-CH, Swiss Federal FOEN Discharge
  -> Licenses: Open Government Data Switzerland, CC-BY 4.0
  -> OK: Complete provenance notes accessible to organizer.
[Step 12] Organizer accepts submission and adds internal notes...
  -> OK: Submission status updated to ACCEPTED.
[Steps 13-14] Organizer attempts evaluation while Docker daemon is offline...
  -> Gating Result: SAFE_WORKER_UNAVAILABLE
  -> Message: EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE
  -> Submission State Preserved: EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE
  -> OK: Submission preserved safely in review queue without data loss.
======================================================================
ALL 14 STEPS OF THE END-TO-END WORKFLOW VERIFIED SUCCESSFULLY (PASS)
======================================================================
```

---

## 8. Known Limitations & Production Readiness

1. **Docker Daemon Offline in Test Environment:**  
   Docker Desktop daemon is offline on this host machine. The platform strictly enforces fail-closed behavior: untrusted code execution is blocked and submissions remain held in `EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE`. To enable container execution, start Docker Desktop (`dockerd`) and ensure the engine socket is reachable.
2. **Email Delivery:**  
   Confirmations are recorded in the database and surfaced via `/confirmation` and status lookup. SMTP email delivery hooks can be plugged into `SubmissionService.register_submission`.

