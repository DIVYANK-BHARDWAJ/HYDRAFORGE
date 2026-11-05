# HYDRAFORGE — The Intelligence Evaluation Engine

> **Train anywhere. Predict anywhere. Prove your model.**  
> Official automated evaluation platform for the **BASINSHIFT** Hydrological Machine Learning Challenge.

---

## 🌊 Overview

**HYDRAFORGE** is an automated, secure evaluation platform designed to benchmark machine-learning models predicting river discharge and flood events. It accepts participant GitHub repositories and evaluates them under strict airgapped conditions against unseen benchmark test splits and hidden ground-truth labels.

### Six Deterministic Evaluation Dimensions (100 Points Total)

| Dimension | Weight | Primary Metric Formulation | Test Split |
| :--- | :---: | :--- | :--- |
| **Forecast Skill** | 35 pts | Persistence-relative Kling-Gupta Efficiency (KGE) | Test A (Temporal Holdout) |
| **Event Detection** | 20 pts | Precision-Recall AUC for Q95 and Q99 Flood Peaks | Test A (Temporal Holdout) |
| **Generalization** | 15 pts | KGE Retention on Ungauged, Unseen River Basins | Test B (Spatial Holdout) |
| **Calibration & Uncertainty** | 15 pts | Continuous Ranked Probability Score (CRPS) & Coverage Error | Test A (Probabilistic) |
| **Robustness** | 10 pts | Relative Performance Degradation under Sensor Noise & Loss | Test C (Input Perturbations) |
| **Efficiency** | 5 pts | Wall-Clock Latency per Prediction & Peak RAM Usage | Real-Time Hardware Telemetry |

---

## 🚀 Key Architectural Features

1. **Strict 2-Field Participant Intake**: Fast registration via `team_name` and `repository_url`. The server discovers default branches and securely locks the immutable 40-character HEAD commit SHA. Zero participant code executes at intake.
2. **Dynamic Repository Discovery**: AST inspection identifying model entry points, argument patterns, and dependency configurations without enforcing fixed filenames (`predict.py`, `model.py`, or custom layouts).
3. **Airgapped Container Sandbox**: Docker isolation running under an unprivileged user (`UID 10001:10001`), `--network none`, read-only root filesystem, dropped capabilities, and strict cgroups CPU/memory caps.
4. **Durable Asynchronous Job Queue**: Database-backed priority queue supporting atomic claims, worker leases, periodic heartbeats, dead-letter transitions, and automatic stale lease recovery.
5. **Dual Database Engine**: Native support for **Neon Serverless PostgreSQL** and local SQLite with WAL mode.
6. **Zero-Leakage Benchmark Architecture**: Strict temporal and geographical isolation with complete hidden label shielding.
7. **Participant Reference SDK**: Reference model, sample input/output datasets, and a local validation CLI (`scripts/validate_submission.py`).

---

## 💻 Quickstart

### 1. Local Setup
```bash
# Clone the repository
git clone https://github.com/DIVYANK-BHARDWAJ/HYDRAFORGE.git
cd HYDRAFORGE

# Install Python dependencies
pip install -r requirements.txt psycopg2-binary

# Start backend server
python -m hydraforge.cli.main serve --host 127.0.0.1 --port 5000
```

### 2. Frontend Dashboard
```bash
cd frontend
npm install
npm run build    # Or npm run dev for live development
```

### 3. Run Production Stack with Docker Compose
```bash
# Production stack with API, Worker Daemon, and Frontend
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 🧪 Testing & Verification

Run the comprehensive test suite (165+ tests):
```bash
# Run all tests
python -m pytest tests/ -v

# Run the 10-Scenario Competition Simulation
python -m pytest tests/test_competition_simulation.py -v

# Validate a participant predictions file
python scripts/validate_submission.py examples/sample_predictions_valid.json
```

---

## 📚 Documentation Suite

Complete technical and operational documentation is located in [`docs/`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/):
- [Final Codebase Audit](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/FINAL_CODEBASE_AUDIT.md)
- [System Architecture](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/FINAL_ARCHITECTURE.md)
- [REST API Reference](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/FINAL_API_REFERENCE.md)
- [Participant Guide](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/PARTICIPANT_GUIDE.md)
- [Organizer Operations Guide](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/ORGANIZER_GUIDE.md)
- [Standardized Inference Contract](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/INFERENCE_CONTRACT.md)
- [Scoring Policy & Formulas](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/SCORING_POLICY.md)
- [Scoring Validation Report](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/SCORING_VALIDATION_REPORT.md)
- [Data Provenance & Caravan Staging Report](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/DATA_PROVENANCE_REPORT.md)
- [Security Threat Model](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/SECURITY_THREAT_MODEL.md)
- [Sandbox Security Assessment](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/SANDBOX_SECURITY_ASSESSMENT.md)
- [Production Deployment Guide](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/DEPLOYMENT_GUIDE.md)
- [Operations & Incident Runbook](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/OPERATIONS_RUNBOOK.md)
- [Backup & Disaster Recovery Plan](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/BACKUP_AND_RECOVERY.md)
- [End-to-End Acceptance Report](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/END_TO_END_ACCEPTANCE_REPORT.md)
- [Final Master Completion Report](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/docs/FINAL_COMPLETION_REPORT.md)
