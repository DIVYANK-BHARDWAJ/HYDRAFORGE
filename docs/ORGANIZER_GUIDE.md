# HYDRAFORGE — Organizer Operations Guide
**Role:** Challenge Organizer / Competition Administrator  
**Date:** 2026-11-05  

---

## 1. Accessing Organizer Console

1. Navigate to `/` in your browser.
2. Click on the **Organizer Console** tab.
3. Authenticate using organizer credentials:
   - Default Username: `organizer`
   - Password: configured via `HYDRAFORGE_ORGANIZER_PASS` in `.env`
   - Alternatively, supply master API key via `HYDRAFORGE_ORGANIZER_KEY`.

---

## 2. Reviewing Submissions

1. The Organizer Console displays all participant registrations with:
   - Team Name
   - GitHub Repository URL
   - Immutable captured commit SHA
   - Default branch
   - Automated verification status (`VERIFIED` or `FAILED`)
2. Review the repository contents:
   - Ensure the repository contains legitimate modeling code.
   - Verify dependencies are safe and standard.
3. Change review status to **`ACCEPTED`** or **`REJECTED`**.
4. Add internal notes (visible only to organizers; strictly shielded from public APIs).

---

## 3. Triggering & Monitoring Evaluations

1. Once a submission is `ACCEPTED`, click **Evaluate**.
2. The submission is queued in the `evaluation_queue`.
3. An active worker claims the job, provisions an isolated sandbox, and executes the evaluation.
4. View real-time evaluation logs and progress under **System Status** and **Job Logs**.
5. Once completed, scores appear automatically on the **Official Leaderboard**.

---

## 4. Leaderboard Governance

- Submissions evaluated against the standard benchmark receive an official composite score \(S \in [0, 100]\).
- Only the highest-scoring verified submission per team is displayed on the public leaderboard.
- Organizers may manually trigger re-evaluations if needed.
