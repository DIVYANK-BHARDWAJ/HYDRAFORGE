# HYDRAFORGE — End-to-End Acceptance Test Report
**Suite:** `tests/test_competition_simulation.py`  
**Date:** 2026-11-05  
**Result:** 10 / 10 Scenarios Passed (100%)  

---

## 1. Scenario Verification Summary

| # | Scenario Description | Tested Behavior | Result |
| :--- | :--- | :--- | :--- |
| **1** | Valid 2-Field Intake | Registers with `team_name` & `repository_url`; auto-captures commit SHA | **PASSED** |
| **2** | Extraneous Fields Rejection | Injected `commit_sha` or extraneous keys rejected immediately | **PASSED** |
| **3** | SSRF Attack Defense | Private IPs, AWS IMDS `169.254.169.254`, and loopbacks blocked | **PASSED** |
| **4** | Inaccessible Repository | Private / non-existent repos recorded with `FAILED` verification | **PASSED** |
| **5** | Zero Code Execution on Intake | Submissions strictly save metadata; zero code executed on registration | **PASSED** |
| **6** | Dynamic Layout Discovery | Discovers custom entrypoint scripts without fixed filenames | **PASSED** |
| **7** | Strict Label Shielding | Input preparer delivers inputs with zero target discharge exposure | **PASSED** |
| **8** | Malformed Predictions Rejection | Negative discharge, inverted quantiles, and out-of-bound probs fail | **PASSED** |
| **9** | Persistent Queue Lifecycle | Atomic claim, worker heartbeats, completion, and timeout recovery | **PASSED** |
| **10** | Six-Axis Scoring & DB Save | Evaluates all 6 axes, computes final score, saves leaderboard entry | **PASSED** |

---

## 2. Test Execution Telemetry

- **Total Test Suite:** 165 Passed / 165 Total (100% Pass Rate).
- **Execution Time:** ~24 seconds.
- **Flakiness Rate:** 0.00%.

