# HYDRAFORGE — Final System Architecture
**System:** HYDRAFORGE Intelligent ML Evaluation Engine  
**Challenge:** BASINSHIFT  
**Date:** 2026-11-05  

---

## 1. System Topology

HYDRAFORGE is engineered as an asynchronous, event-driven, decoupled ML evaluation system:

```mermaid
flowchart TD
    subgraph Public Participant Domain
        P[Participant Team] -->|1. Submit (team_name, repo_url)| WebUI[Participant Portal Web UI]
        WebUI -->|REST API| API[HYDRAFORGE API Server]
    end

    subgraph Evaluation Core
        API -->|2. Server-side GitHub Verification| GH[GitHub API / Git Discovery]
        GH -->|3. Record Commit SHA| DB[(PostgreSQL / SQLite)]
        API -->|4. Store Submission Record| DB
        Org[Organizer] -->|5. Review & Authorize| API
        API -->|6. Enqueue Job| Q[Persistent Evaluation Queue]
    end

    subgraph Isolated Worker Fleet
        W[Evaluation Worker Daemon] -->|7. Atomic Lease Claim| Q
        W -->|8. Renew Heartbeat| Q
        W -->|9. Inspect Repo Layout| Disc[Discovery Engine]
        W -->|10. Deliver Label-Free Inputs| Cont[Airgapped Docker Sandbox]
        Cont -->|11. Generate Predictions| Output[Predictions JSON]
        W -->|12. Validate Predictions| Val[Prediction Validator]
        W -->|13. 6-Axis Evaluation| Scoring[HydraForge Evaluator]
        Scoring -->|14. Store Scores & Leaderboard| DB
    end
```

---

## 2. Key Components

### 2.1 Participant Submission Intake
- **Endpoint**: `POST /api/v1/submissions`
- **Fields**: Whitelisted strictly to `team_name` and `repository_url`.
- **SSRF Defense**: IP address resolution filter rejecting private subnets, loopbacks (`127.0.0.1`), link-local (`169.254.169.254`), and non-HTTPS protocols.
- **Commit Pinning**: Server queries GitHub default branch and records immutable 40-character HEAD commit SHA. Zero participant code executes at intake.

### 2.2 Persistent Job Queue
- **Engine**: Database-backed table `evaluation_queue`.
- **Atomic Claiming**: Uses database transactions with priority ordering (`priority DESC, enqueued_at ASC`).
- **Heartbeat Leases**: Active workers send heartbeats every 60 seconds; leases expire after 300 seconds.
- **Dead-Letter Handling**: Failed executions retry up to 3 times before transitioning to `DEAD_LETTER`.

### 2.3 Sandboxed Execution Isolation
- Non-root UID/GID: `10001:10001`
- Network: Disabled (`--network none`)
- Root Filesystem: Read-only (`--read-only`)
- Memory & CPU Limits: Hard caps (4 GB RAM, 2.0 CPUs, 300s timeout)
- Capabilities: All Linux capabilities dropped (`--cap-drop ALL`, `no-new-privileges`)

### 2.4 Six-Axis Scoring Architecture
The final score \(S \in [0, 100]\) is the sum of six deterministic axes:
1. **Forecast Skill** (35 pts): Kling-Gupta Efficiency (KGE) on Test A.
2. **Event Detection** (20 pts): Precision-Recall AUC for Q95 and Q99 flood peaks.
3. **Generalization** (15 pts): Performance on unseen catchments (Test B).
4. **Calibration** (15 pts): Coverage error and CRPS of probabilistic quantiles.
5. **Robustness** (10 pts): Performance degradation under sensor corruptions (Test C).
6. **Efficiency** (5 pts): Wall-clock inference latency and peak memory usage.

