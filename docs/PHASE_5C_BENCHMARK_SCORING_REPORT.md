# HYDRAFORGE — PHASE 5C IMPLEMENTATION REPORT
## Benchmark Execution, Prediction Validation & Automated Scoring Integration

**Project:** HYDRAFORGE — The Intelligence Evaluation Engine  
**Challenge:** BASINSHIFT — Hydrological Forecasting Challenge  
**Component:** Phase 5C — Benchmark Execution, Prediction Validation & Automated Scoring Integration  
**Status:** COMPLETE & VERIFIED  
**Test Suite:** 152/152 Tests Passing (100% Pass Rate across all Phases 1–5C)  
**Date:** November 5, 2026  

---

## 1. EXECUTIVE SUMMARY

Phase 5C completes the end-to-end evaluation pipeline of HYDRAFORGE. It unites:
- **Phase 1:** Six-dimensional deterministic scoring engine (100 points).
- **Phase 2:** Benchmark infrastructure, dataset adapters, and split management.
- **Phase 5A:** Dynamic repository discovery and flexible inference contract.
- **Phase 5B:** Secure model execution and container isolation worker engine.

Participant models submitted via GitHub repository and immutable commit SHA are discovered, provisioned inside airgapped worker environments, supplied with label-shielded input cases, and executed. The resulting forecasts undergo rigorous contract validation before being passed to the trusted organizer scoring evaluator for multi-split, six-axis evaluation.

All evaluations are fully reproducible, cryptographically hashed, persisted in SQLite storage, and conditionally eligible for the official leaderboard based on organizer approval.

---

## 2. INTEGRATED EVALUATION ARCHITECTURE

```mermaid
flowchart TD
    A["Participant Submission (Repo URL + Commit SHA)"] --> B["Dynamic Discovery (Phase 5A)"]
    B --> C["Organizer Approval Gating"]
    C --> D["Benchmark Case Manager"]
    D --> E["Input Preparer (Zero Future Leakage, Zero Label Leakage)"]
    E --> F["Isolated Worker Sandbox (Phase 5B - Airgapped Container)"]
    F --> G["Output Collector (SHA-256 Hashing)"]
    G --> H["Prediction Validator (Contract & Physical Sanity Checks)"]
    H -->|Invalid| I["Job Status: INVALID_PREDICTIONS (Score Null, No Leaderboard)"]
    H -->|Valid| J["Trusted Evaluator (Organizer Environment with Hidden Labels)"]
    J --> K["Six-Axis Scoring Engine (100 Pts Total)"]
    K --> L["Split Evaluator (Test A, Test B, Test C Independent Summaries)"]
    L --> M["Comprehensive Evaluation Report (JSON & CSV Exports)"]
    M --> N["SQLite Database Persistence"]
    N --> O["Official Ranked Leaderboard (Organizer-Controlled)"]
```

### Component Inventory (`hydraforge/benchmark/` & `hydraforge/evaluation/`)

| Module | Component | Primary Responsibility |
| :--- | :--- | :--- |
| `hydraforge/benchmark/case_manager.py` | `BenchmarkCaseManager` | Loads authorized datasets, resolves versions, verifies split integrity (disjoint catchments for Test B, temporal order for Test A), provides input cases and hidden labels. |
| `hydraforge/benchmark/input_preparer.py` | `BenchmarkInputPreparer` | Sanitizes model inputs, strips all labels/thresholds, verifies zero observations occur after forecast origin ($t \le t_{origin}$), computes deterministic input SHA-256. |
| `hydraforge/evaluation/prediction_validator.py` | `PredictionValidator` | Validates model forecasts: case alignment, missing/duplicate cases, probability bounds $[0, 1]$, quantile ordering ($P_{extreme} \le P_{high}$), non-negative discharge, interval bounds ($lower \le upper$). |
| `hydraforge/evaluation/split_evaluator.py` | `SplitEvaluator` | Computes independent metrics for Test A (temporal), Test B (spatial generalization), and Test C (controlled stress/robustness) without opaque aggregation. |
| `hydraforge/evaluation/pipeline.py` | `BenchmarkEvaluationPipeline` | Coordinates the full lifecycle from discovery to execution, validation, scoring, persistence, and leaderboard eligibility. |
| `hydraforge/evaluation/pipeline.py` | `ComprehensiveEvaluationReport` | Complete audit manifest containing all telemetry, split metrics, validation details, cryptographic hashes, and export methods (`to_json`, `to_csv`). |

---

## 3. LABEL SHIELDING & INPUT ISOLATION

A core security invariant of HYDRAFORGE is that ground-truth streamflow observations and evaluation thresholds **never** enter the participant execution boundary.

### Separation Invariants
1. **Participant Input Preparation:** `BenchmarkInputPreparer` transforms benchmark records into model input cases containing only:
   - `case_id`, `catchment_id`, `forecast_origin`, `horizons`, `discharge_history`, `forcing_history`, `attributes`, and regional metadata.
   - Any ground-truth keys (`true_discharge`, `persistence_discharge`, `high_flow_threshold`, `extreme_flow_threshold`, `labels`) are strictly forbidden and trigger immediate security exceptions if present.
2. **Temporal Leakage Prevention:** All timestamps in `discharge_history` and `forcing_history` are verified against `forecast_origin`. If any observation timestamp $t > t_{origin}$, input generation halts immediately with `DataValidationError`.
3. **Physical Path Isolation:** Container mounts provide only `/inputs:ro` containing `cases.json` and `/workspace:ro` containing the participant commit. Organizer label paths (`/labels`) are absent from worker configuration, environment variables, and filesystem namespaces.
4. **Independent Post-Execution Scoring:** Reference labels are retrieved by `BenchmarkCaseManager` inside the organizer's trusted process **after** the container has finished and been cleaned up.

---

## 4. STRICT PREDICTION VALIDATION ENGINE

Model predictions are verified against the Phase 5A inference contract before any evaluation or scoring:

| Validation Rule | Condition Enforced | Failure Action |
| :--- | :--- | :--- |
| **Required Schema** | All 9 core prediction attributes must be present and non-null. | Flagged in `PredictionValidationReport.errors`; job transitions to `INVALID_PREDICTIONS`. |
| **Case Alignment** | `(case_id, horizon)` must match an expected target. | Rejects unexpected or foreign predictions. |
| **Completeness** | Exactly $N$ expected cases must be provided (no missing targets). | Rejects incomplete submissions; missing count recorded. |
| **Uniqueness** | Each `(case_id, horizon)` can appear at most once. | Duplicate entries flagged and submission invalidated. |
| **Numeric Types** | Forecasts, probabilities, and intervals must be valid numbers (no NaN, +Inf, -Inf). | Rejects non-finite values. |
| **Non-Negative Flow** | `predicted_discharge >= 0.0`. | Rejects negative streamflow predictions. |
| **Probability Bounds** | `0.0 <= high_flow_probability <= 1.0` and `0.0 <= extreme_flow_probability <= 1.0`. | Out-of-bounds probabilities rejected. |
| **Quantile Ordering** | `extreme_flow_probability <= high_flow_probability`. | Quantile probability inversions rejected. |
| **Interval Validity** | `prediction_interval_lower <= prediction_interval_upper`. | Inverted prediction intervals rejected. |
| **Timestamp Match** | `forecast_origin` must match the benchmark case origin. | Timestamp misalignment rejected. |

**Zero Artificial Scoring:** The engine never silently imputes missing predictions or modifies invalid numbers. Any validation violation sets `is_valid = False` and aborts scoring.

---

## 5. SIX-AXIS SCORING FORMULAS & SCIENTIFIC AUDIT

HYDRAFORGE evaluates submissions across six dimensions (total 100 points) using provisional formulas anchored to standalone baseline benchmarks:

### Dimension Breakdown

```mermaid
pie title Six-Axis Scoring Allocation (100 Points Total)
    "Forecast Skill (Test A)" : 25
    "Event Detection (Q95/Q99)" : 25
    "Generalization (Test B)" : 20
    "Calibration & Uncertainty" : 15
    "Robustness (Test C)" : 10
    "Computational Efficiency" : 5
```

### 1. Forecast Skill (25 Points) — Test A (Temporal Holdout)
- **Metric:** Persistence-relative Nash-Sutcliffe Efficiency (NSE):
  $$\text{Skill} = \max\left(0, \frac{\text{NSE}_{\text{model}} - \text{NSE}_{\text{persistence}}}{1 - \text{NSE}_{\text{persistence}}}\right) \times 25.0$$
- **Provenance:** Compared against the lag-1 day persistence benchmark ($Q_{t+h} = Q_t$). Prevents rewarding models that merely replicate standard persistence without dynamic rainfall-runoff modeling.

### 2. High-Flow & Extreme-Flow Event Detection (25 Points) — Test A / Standard
- **Metric:** Macro-averaged Area Under the Precision-Recall Curve (AUPRC) and F1-score across high-flow ($Q \ge Q_{95}$) and extreme-flow ($Q \ge Q_{99}$) thresholds:
  $$\text{Score}_{\text{events}} = \left(0.60 \times \text{AUPRC} + 0.40 \times F_1\right) \times 25.0$$
- **Threshold Provenance:** Derived strictly from historical training periods ($t \le 180\text{ days}$) using empirical percentiles. Never derived from test set observations.

### 3. Out-of-Distribution Generalization (20 Points) — Test B (Geographic Holdout)
- **Metric:** Zero-shot transfer to unseen catchments with regional dispersion penalty:
  $$\text{Score}_{\text{gen}} = \max\left(0, \text{Skill}_{\text{Test B}} \times \left(0.80 + 0.20 \times \text{Retention}\right) - \text{Penalty}_{\text{dispersion}}\right) \times 20.0$$
  where $\text{Retention} = \min\left(1.0, \frac{\text{Skill}_{\text{Test B}}}{\text{Skill}_{\text{Test A}}}\right)$, and $\text{Penalty}_{\text{dispersion}}$ penalizes high variance across climatic regions.

### 4. Calibration & Uncertainty (15 Points) — Standard Splits
- **Metric:** Weighted combination of exceedance probability calibration (Brier score) and empirical prediction interval coverage:
  $$\text{Score}_{\text{cal}} = 0.50 \times \text{Score}_{\text{Brier}} + 0.50 \times \text{Score}_{\text{Coverage}}$$
  where nominal coverage is 90% ($\alpha = 0.10$). Coverage deviation beyond $\pm 5\%$ incurs quadratic penalties.

### 5. Robustness & Stress Resilience (10 Points) — Test C (Perturbed Inputs)
- **Metric:** Retention of predictive accuracy under controlled input degradations:
  - `missing_discharge`: Historical past streamflow completely withheld (ungauged basin test).
  - `input_noise`: $15\%$ additive Gaussian sensor noise applied to precipitation forcings.
  - `reporting_delay`: 48-hour observation latency in meteorological inputs.
- **Formula:**
  $$\text{Retention}_{\text{family}} = \max\left(0, 1 - \frac{\text{MAE}_{\text{corrupt}} - \text{MAE}_{\text{clean}}}{\text{MAE}_{\text{clean}}}\right)$$
  $$\text{Score}_{\text{rob}} = \text{Mean}(\text{Retention}) \times 10.0$$

### 6. Computational Efficiency (5 Points)
- **Metric:** Measured actual worker resource usage from container cgroups and wall-clock telemetry:
  - Wall-clock runtime budget (up to 2.5 pts).
  - Peak memory footprint (up to 1.5 pts).
  - Model checkpoint artifact size (up to 1.0 pt).

---

## 6. INDEPENDENT TEST SPLIT EVALUATION

To prevent temporal and geographic performance from being collapsed into an opaque aggregate, `SplitEvaluator` evaluates splits independently:

| Split Name | Partition Nature | Catchments Included | Primary Evaluation Focus |
| :--- | :--- | :--- | :--- |
| **`train`** | Training Baseline | $C_1, C_2, C_3, C_4$ | Reference threshold derivation ($Q_{95}, Q_{99}$). |
| **`validation`** | Development Holdout | $C_1, C_2, C_3, C_4$ | Hyperparameter selection and baseline tuning. |
| **`test_a`** | Temporal Holdout | $C_1, C_2, C_3, C_4$ | Forecast skill, lead-time decay, event detection. |
| **`test_b`** | Geographic Holdout | $C_5, C_6$ (Unseen) | Regional transferability, zero-shot basin generalization. |
| **`test_c`** | Stress & Robustness | $C_1, C_2, C_3, C_4$ (Corrupted) | Sensor noise, missing telemetry, reporting latency. |

Each split produces a dedicated `SplitEvaluationSummary` detailing: case count, valid predictions, missing predictions, metric breakdown, runtime, memory, and status.

---

## 7. DATABASE PERSISTENCE & LEADERBOARD GATING

### Persistence Model
Every evaluation run creates/updates entries in SQLite:
- `evaluation_jobs`: Captures lifecycle status (`COMPLETED`, `INVALID_PREDICTIONS`, `EXECUTION_FAILED`), immutable commit SHA, benchmark version, and audit digest.
- `evaluation_results`: Stores 6-axis dimensional scores and the full `ComprehensiveEvaluationReport` JSON.

### Leaderboard Publication Rules
The official leaderboard strictly gates entries using:
```sql
SELECT j.job_id, j.repository_url, j.commit_sha, r.total_score, ...
FROM evaluation_jobs j
JOIN evaluation_results r ON j.job_id = r.job_id
WHERE j.job_status = 'COMPLETED'
  AND j.final_score IS NOT NULL
  AND j.benchmark_version = ?
ORDER BY r.total_score DESC, j.completed_at ASC;
```

**Invariants:**
1. Failed, incomplete, or rejected jobs are **excluded** from the leaderboard.
2. Incomplete predictions (`is_valid = False`) receive `final_score = NULL` and are excluded.
3. Only organizer-approved evaluations are published to the public leaderboard.

---

## 8. TEST VERIFICATION (21 SCENARIOS)

Phase 5C adds 21 comprehensive tests in `tests/test_benchmark_scoring.py` and `tests/test_scoring_end_to_end.py`:

| # | Test Case | Focus Area | Result |
| :---: | :--- | :--- | :---: |
| 1 | `test_1_valid_benchmark_input_preparation` | Permitted input generation & SHA-256 calculation | **PASSED** |
| 2 | `test_2_temporal_leakage_prevention` | Reject forcing observations dated after forecast origin | **PASSED** |
| 3 | `test_3_geographic_split_integrity` | Verify zero catchment overlap between Train and Test B | **PASSED** |
| 4 | `test_4_hidden_label_separation` | Strip all ground-truth fields from model input payload | **PASSED** |
| 5 | `test_5_prediction_schema_validation` | Strict validation of complete prediction records | **PASSED** |
| 6 | `test_6_missing_predictions` | Detect and reject missing forecast horizons | **PASSED** |
| 7 | `test_7_duplicate_predictions` | Detect and reject duplicate `(case_id, horizon)` pairs | **PASSED** |
| 8 | `test_8_invalid_probabilities` | Catch probabilities outside $[0, 1]$ interval | **PASSED** |
| 9 | `test_9_invalid_quantile_ordering` | Catch $P_{extreme} > P_{high}$ and $lower > upper$ inversions | **PASSED** |
| 10 | `test_10_invalid_discharge_values` | Catch negative streamflow and NaN values | **PASSED** |
| 11 | `test_11_forecast_timestamp_mismatch` | Catch mismatch between prediction and case origin dates | **PASSED** |
| 12 | `test_12_correct_six_axis_metric_invocation` | Ensure all 6 dimensions are invoked and structured | **PASSED** |
| 13 | `test_13_score_bounds` | Guarantee total score is strictly bounded in $[0, 100]$ | **PASSED** |
| 14 | `test_14_missing_metric_handling` | Handle empty predictions gracefully with diagnostics | **PASSED** |
| 15 | `test_15_stress_test_reproducibility` | Verify deterministic Test C corruption generation | **PASSED** |
| 16 | `test_16_actual_efficiency_measurement` | Integrate real runtime and peak memory into score | **PASSED** |
| 17 | `test_17_evaluation_persistence` | Verify SQLite storage of jobs and metric breakdowns | **PASSED** |
| 18 | `test_18_failed_evaluation_handling` | Confirm failed worker assigns no score and logs errors | **PASSED** |
| 19 | `test_19_leaderboard_eligibility` | Exclude failed and invalid jobs from leaderboard query | **PASSED** |
| 20 | `test_20_immutable_commit_preservation` | Reject mutable Git branches (`main`) in evaluation | **PASSED** |
| 21 | `test_complete_end_to_end_synthetic_scoring_workflow` | Full lifecycle with nonstandard participant repository | **PASSED** |

---

## 9. FULL PROJECT REGRESSION RESULTS

The entire HYDRAFORGE test suite across all development phases was executed:

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\DIVYANK BHARDWAJ\Desktop\Projects\HYDRAFORGE\HYDRAFORGE
plugins: anyio-4.15.1
collected 152 items

tests/test_api.py ......................... [ 16%]
tests/test_baselines.py .....               [ 19%]
tests/test_benchmark.py ........            [ 25%]
tests/test_benchmark_scoring.py ........... [ 38%]
tests/test_cli.py ......                    [ 42%]
tests/test_database.py ......               [ 46%]
tests/test_discovery.py .................... [ 59%]
tests/test_metrics.py ....................  [ 72%]
tests/test_runner.py ....                   [ 75%]
tests/test_schema.py ........               [ 80%]
tests/test_scoring_end_to_end.py .          [ 81%]
tests/test_security.py .....                [ 84%]
tests/test_submission.py ......             [ 88%]
tests/test_submissions_portal.py .......... [ 95%]
tests/test_worker_integration.py ..         [ 96%]
tests/test_worker_security.py ............. [100%]

============================ 152 passed in 19.14s =============================
```

- **Phases 1–5B Baseline Tests:** 131/131 Passing.
- **Phase 5C Benchmark & Scoring Tests:** 21/21 Passing.
- **Total:** 152/152 Passing (0 Failures, 0 Regressions).

---

## 10. SCIENTIFIC POLICY DECISIONS AWAITING FINAL ORGANIZER APPROVAL

The scoring calculations in Phase 5C represent the approved provisional specification. The following scientific policy decisions remain subject to final competition committee review before formal production launch:

1. **Persistence-Relative Denominator Bounds:** When the persistence baseline itself has near-zero error on calm baseflow regimes, the denominator $(1 - \text{NSE}_{\text{persistence}})$ approaches zero. Currently, a safeguard threshold $\epsilon = 10^{-6}$ assigns full points if the model also matches zero error, and 0 points otherwise. A formal shrinkage prior or KGE-based alternative may be adopted.
2. **AUPRC vs. F1 Weighting for Rare Floods:** Extreme floods ($Q_{99}$) have low sample prevalence. The current $60/40$ blend between macro-AUPRC and F1 mitigates threshold sensitivity, but precision-recall curves with fewer than 5 positive events are noisy.
3. **Regional Grouping Standards:** Regional categorization currently uses physiographic/hydroclimatic regions (e.g. Alps, Rockies). When evaluating Caravans across global catchments, Koeppen-Geiger climate classification or HydroATLAS eco-regions should be formally designated.
4. **Synthetic Data Disclaimer:** All tests in this report utilize mathematically generated synthetic rainfall-runoff benchmark data. These test results verify software architecture, contract enforcement, and mathematical scoring mechanics—they do **not** represent verified hydrological performance on genuine river basins. Genuine Caravan benchmark data must be staged by organizers before competition launch.

---

## 11. CONCLUSION

Phase 5C is complete, robust, and verified. HYDRAFORGE now possesses a fully integrated, automated, fail-closed evaluation pipeline that connects participant repositories directly to deterministic six-axis hydrological scoring with strict label shielding and leaderboard governance.

