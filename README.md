# HYDRAFORGE — The Intelligence Evaluation Engine

> **Train anywhere. Predict anywhere. Prove your model.**  
> Official automated evaluation platform for the **BASINSHIFT** Hydrological Machine Learning Challenge.

---

## 🌊 Overview

**HYDRAFORGE** is an automated, secure evaluation platform designed to benchmark machine-learning models and forecasting agents predicting river discharge. It evaluates participant-submitted GitHub repositories against organizer-controlled, unseen benchmark cases and hidden ground-truth labels across six deterministic dimensions:

| Dimension | Provisional Weight | Metric Formulation |
|---|---:|---|
| **Forecast Skill** | 25 pts | Persistence-relative Nash-Sutcliffe Efficiency (NSE), RMSE, MAE |
| **Event Detection** | 25 pts | Q95 & Q99 Flood Peak Detection (Prevalence-Normalized AUPRC, Brier Skill, CSI) |
| **Generalization** | 20 pts | Unseen Catchment Performance Retention (Test B) & Regional Disparity Penalties |
| **Calibration & Uncertainty**| 15 pts | Continuous Ranked Probability Score (CRPS), 90% Interval Coverage Error, PIT |
| **Robustness** | 10 pts | Resistance to Paired Input Corruptions (Noise, Missingness, Bias Shifts) |
| **Efficiency** | 5 pts | Inference Latency per Sample (<50 ms target) and Peak RAM (<4 GB target) |

---

## 🚀 Key Features

- **Public Participant Portal:** Streamlined 3-field registration form (`team_name`, `repository_url`, `deployed_website_url`) with server-side HEAD commit SHA capture and SSRF protection.
- **Dynamic Repository Discovery (Phase 5A):** Language-agnostic, layout-agnostic AST inspection discovering manifests, dependency trees, and inference entrypoints without running participant code or assuming fixed filenames.
- **Standardized Hydrological Inference Contract:** Formalized CLI file-in / file-out (`--input <path> --output <path>`) and Python adapter specifications for heterogeneous ML architectures.
- **Participant Status Tracking:** Real-time lookup using cryptographically unpredictable submission tokens (`sub_...`). Private organizer notes and emails are strictly shielded.
- **Private Organizer Console:** Protected by token-based authentication (`@require_organizer_auth`), allowing organizers to inspect website reachability, captured commit SHAs, record internal review notes, accept/reject submissions, and trigger evaluations.
- **Fail-Closed Security Gating:** Untrusted participant code execution is strictly restricted to airgapped containers (`--network none`). If Docker is offline, execution fails closed and holds submissions safely without data loss.
- **Zero-Leakage Benchmark Architecture:** Multi-split management (Train, Validation, Test A, Test B, Test C) with automatic leakage audits verifying spatial and temporal isolation between training and holdout catchments.
- **Deterministic Offline Scoring:** Zero LLM or external web API calls in the scoring pipeline. 100% reproducible metric computations bounded in $[0, 100]$.

---

## 💻 Quickstart

### 1. Start Application Server & Dashboard
```bash
python -m hydraforge.cli.main serve --host 127.0.0.1 --port 5000
```
Open [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in any browser.

### 2. Participant Workflow
1. Navigate to **Challenge Portal** to review challenge objectives and evaluation dimensions.
2. Open **Register & Submit** to fill out the 4-section registration form:
   - Section A: Team Details (Leader, Contact Email, Members)
   - Section B: Project Details (Model Architecture, GitHub URL, Commit SHA)
   - Section C: Dataset Disclosures (Training Data, Sources, Licenses, Pretraining, Covariates)
   - Section D: Mandatory Declarations
3. Receive unique **Submission ID** (e.g. `sub_63be1ec38c154c70...`).
4. Monitor verification and review progress anytime in **Track Submission**.

### 3. Organizer Workflow
1. Click **Organizer Console 🔒** in the top navigation bar.
2. Authenticate using organizer credentials:
   - Default Username: `organizer`
   - Default Password: `basinshift2026organizer` (configurable via `HYDRAFORGE_ORGANIZER_PASS`)
3. Inspect submitted projects, review complete dataset provenance and licenses.
4. Record internal private notes and mark submission as **Accepted** or **Rejected**.
5. Click **Evaluate** to trigger automated container evaluation. If Docker is offline, the submission is held safely in `EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE`.

---

## 🧪 Testing & Verification

Run the entire regression test suite (109 tests covering Phases 1–5A):
```bash
python -m pytest tests/ -v
```

Execute the automated end-to-end workflow verification script:
```bash
python scripts/verify_workflow.py
```

---

## 📁 Repository Structure

```
hydraforge/
├── api/
│   ├── auth.py                 # Organizer session token & header authentication guards
│   ├── routes/                 # REST API blueprints (submissions, organizer, health, etc.)
│   ├── services/               # Submission, evaluation, leaderboard, and benchmark services
│   ├── web/index.html          # Self-contained offline Public Portal & Organizer SPA
│   └── main.py                 # Flask REST application factory
├── benchmark/                  # Benchmark loader, split manager, and synthetic generator
├── database/                   # SQLite WAL connection manager, migrations, and repository
├── discovery/                  # Dynamic repository inspector, AST classifier, and inference contract
│   ├── contract.py             # Standardized Hydrological Inference Contract
│   ├── discovery_models.py     # Discovery reports, candidate entrypoints, and enum statuses
│   ├── discovery_report.py     # Markdown & JSON report formatting helpers
│   ├── documentation_parser.py # Safe README & docs command extraction & threat detection
│   ├── entrypoint_discovery.py # AST-based inference vs. training command discovery
│   ├── file_classifier.py      # Resource-bounded filesystem scanner & symlink auditor
│   ├── manifest_detector.py    # Static dependency & manifest parser (requirements, pyproject, setup.py)
│   └── repository_inspector.py # Master coordinator orchestrating discovery pipeline
├── metrics/                    # 6-dimensional deterministic scoring functions
├── runner/                     # Docker container runner and LocalTestRunner
├── submission/                 # GitHub commit capture, website SSRF verifier, and repo checkout
frontend/                       # React 18 + TypeScript modern development workspace
scripts/
└── verify_workflow.py          # Automated end-to-end workflow verification
tests/                          # 109 unit and integration tests (20 dedicated to discovery)
docs/                           # Architecture, audit reports, and security specifications
```

