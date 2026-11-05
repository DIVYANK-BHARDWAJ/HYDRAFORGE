# HYDRAFORGE — PHASE 5A IMPLEMENTATION REPORT
## Dynamic Repository Discovery & Inference Contract Engine

**Project:** HYDRAFORGE — The Intelligence Evaluation Engine  
**Challenge:** BASINSHIFT — Hydrological Forecasting Benchmark  
**Date:** November 2026  
**Status:** **100% COMPLETE & VERIFIED (109/109 Tests Passing — 20/20 Discovery Scenarios Verified)**

---

## 1. Executive Summary

Phase 5A establishes the automated ML evaluation foundation of HYDRAFORGE by solving the heterogeneity challenge of participant machine-learning projects. Rather than imposing rigid, artificial constraints on filenames or directory structures (such as mandating `model.py` or a predefined `src/` hierarchy), HYDRAFORGE now dynamically inspects each repository snapshot and determines how its model receives hydrological benchmark inputs and emits predictions.

### Core Principles Delivered:
1. **Zero Predefined Filename Bias:** Participants may organize code using `model.py`, `predict.py`, `inference.py`, `main.py`, deeply nested modules (`src/models/hydrology/...`), Python packages (`pyproject.toml`), or arbitrary script names without penalty.
2. **Strict Non-Execution Security Policy:** The discovery engine operates entirely statically (AST analysis, config parsing, safe text tokenization). It **never** executes participant Python files, never imports packages, never runs `setup.py`, and never executes build/shell commands.
3. **Immutable Commit Anchoring:** The discovery inspector is permanently anchored to the exact 40-character commit SHA captured during registration, immunizing evaluations against post-registration modifications or mutable branch shifts.
4. **Non-Guessing Ambiguity Policy:** If multiple candidate inference interfaces exist, the engine classifies the interface as `INTERFACE_AMBIGUOUS` and routes the submission to `NEEDS_ORGANIZER_REVIEW`. It never arbitrarily guesses an entrypoint.
5. **Standardized Hydrological Inference Contract:** Formalized a language-independent CLI file-in / file-out contract (`--input <path> --output <path>`) accompanied by an in-memory Python adapter specification.

---

## 2. Discovery Pipeline Architecture

The discovery subsystem resides in `hydraforge/discovery/` and consists of six specialized components:

```
                  ┌────────────────────────────────────────────────────────┐
                  │ Immutable Commit Snapshot (RepositoryIntake / Git SHA)  │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
                       ┌─────────────────────┴──────────────────────┐
                       │                                            │
                       ▼                                            ▼
        ┌─────────────────────────────┐              ┌─────────────────────────────┐
        │       FileClassifier        │              │      ManifestDetector       │
        │ - Size & depth enforcement  │              │ - requirements.txt          │
        │ - Prunes .git / venv / node │              │ - pyproject.toml            │
        │ - Insecure symlink audits   │              │ - setup.cfg / setup.py AST  │
        │ - Categorizes file types    │              │ - conda / Pipfile / Docker  │
        └──────────────┬──────────────┘              └──────────────┬──────────────┘
                       │                                            │
                       └─────────────────────┬──────────────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │     DocumentationParser     │
                              │ - README / docs extraction  │
                              │ - Code fence shell commands │
                              │ - Training vs. Inference    │
                              │ - Malicious threat scanner  │
                              └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │     EntrypointDiscovery     │
                              │ - Console script resolution │
                              │ - Python AST syntax audit   │
                              │ - Argument parser detection │
                              │ - Disambiguation logic      │
                              └──────────────┬──────────────┘
                                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │     RepositoryInspector     │
                              │ - Synthesizes final report  │
                              │ - Formulates CLI mapping    │
                              │ - Persists to SQLite DB     │
                              └─────────────────────────────┘
```

### Module Breakdown

| Module | Location | Purpose |
|---|---|---|
| [`discovery_models.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/discovery_models.py) | `hydraforge/discovery/` | Dataclasses, schemas, and enums for reports, entrypoints, commands, and statuses. |
| [`contract.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/contract.py) | `hydraforge/discovery/` | Formal HYDRAFORGE Standardized Hydrological Inference Contract specification. |
| [`file_classifier.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/file_classifier.py) | `hydraforge/discovery/` | Unprivileged filesystem walker enforcing bounds (size, files, depth) and symlink safety. |
| [`manifest_detector.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/manifest_detector.py) | `hydraforge/discovery/` | Static manifest parser for requirements, pyproject.toml, setup.cfg, and setup.py AST. |
| [`documentation_parser.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/documentation_parser.py) | `hydraforge/discovery/` | Markdown code block extractor distinguishing training vs. inference and flagging malicious commands. |
| [`entrypoint_discovery.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/entrypoint_discovery.py) | `hydraforge/discovery/` | Synthesizes manifests, docs, and AST analysis to detect interfaces without guessing. |
| [`repository_inspector.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/repository_inspector.py) | `hydraforge/discovery/` | Master coordinator compiling discovery reports and managing database persistence. |
| [`discovery_report.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/hydraforge/discovery/discovery_report.py) | `hydraforge/discovery/` | Markdown and JSON serializers for organizer presentation and auditing. |

---

## 3. Supported File Formats & Manifests

The discovery engine recognizes and parses the following configuration and source formats:

1. **Python Dependencies & Manifests:**
   - `requirements.txt`, `requirements-*.txt`: Extracts pinned and unpinned dependencies while ignoring comments, options (`-r`, `-i`), and index URLs.
   - `pyproject.toml`: Uses standard Python 3.11 `tomllib` to extract PEP 621 `[project.dependencies]`, `[project.scripts]`, `[tool.poetry.dependencies]`, and `[tool.poetry.scripts]`.
   - `setup.cfg`: Uses `configparser` to extract `[options]install_requires`, `[options.entry_points]`, and Python version constraints.
   - `setup.py`: **Static AST parser (`ast.parse`)**. Inspects calls to `setup(install_requires=..., entry_points=...)` without ever executing or importing `setup.py`.
   - `Pipfile`: Parses packages via TOML.
   - `environment.yml` / `conda.yaml`: Uses `yaml.safe_load` to extract conda and nested pip dependencies.
2. **Container & Build Manifests:**
   - `Dockerfile`, `Containerfile`: Static regex extraction of `ENTRYPOINT`, `CMD`, and base images.
   - `Makefile`: Regex extraction of targets (`train:`, `predict:`, `eval:`, `test:`).
3. **Documentation:**
   - `README.md`, `README.rst`, `README.txt`, `README`, `docs/*.md`.

---

## 4. Entry-Point Detection Methodology

To determine how a participant repository expects to be executed, `EntrypointDiscovery` performs three-stage cross-evidence synthesis:

1. **Manifest Script Detection:**
   - Checks package scripts declared in `[project.scripts]` or `setup.cfg`.
   - Automatically maps entrypoint targets (e.g. `hydropkg.infer:run_forecast`) to corresponding filesystem modules (`hydropkg/infer.py` or `src/hydropkg/infer.py`).
2. **Documentation Command Extraction:**
   - Scans code blocks in README documentation for `python <script> ...` commands.
   - Categorizes commands by semantic intent:
     - `TRAINING`: Presence of `train`, `fit`, `epochs`, `batch-size`, `optimizer`.
     - `INFERENCE`: Presence of `predict`, `forecast`, `infer`, `eval`, `--input`, `--output`.
     - `TEST`: `pytest`, `unittest`.
     - `BUILD`: `pip install`, `docker build`.
   - Distinguishes training commands from inference commands to prevent evaluating `train.py`.
3. **Static AST Analysis of Source Files:**
   - Detects `if __name__ == '__main__':` entry guards.
   - Detects CLI frameworks: `argparse.ArgumentParser`, `click.command`, `sys.argv`.
   - Inspects `add_argument()` calls to detect input flags (`--input`, `--data`, `--cases`) and output flags (`--output`, `--predictions`).
   - Detects inference functions: `def predict(...)`, `def forecast(...)` or class methods `Model.predict(...)`.

### Fail-Closed Ambiguity Resolution
- **Single unambiguous inference target:** Classified as `INTERFACE_IDENTIFIED` with confidence `HIGH` or `MEDIUM`.
- **Multiple candidate inference targets:** Classified as `INTERFACE_AMBIGUOUS` with status `NEEDS_ORGANIZER_REVIEW`. All candidates are preserved in the report.
- **Zero candidate inference targets:** Classified as `INTERFACE_NOT_FOUND` with status `DISCOVERY_PARTIAL` (if code exists) or `DISCOVERY_FAILED`.

---

## 5. HYDRAFORGE Standardized Inference Contract

### Contract Specification Summary

| Field | Type | Description |
|---|---|---|
| **Input: `case_id`** | `str` | Unique benchmark case identifier. |
| **Input: `catchment_id`** | `str` | Basin identifier (e.g., CAMELS or Caravan station ID). |
| **Input: `forecast_origin`** | `str` | ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`). |
| **Input: `horizons`** | `List[int]` | Forecast lead times (default: `[1, 3, 7]` days). |
| **Input: `discharge_history`** | `List[float]` | Permitted historical observed discharge up to forecast origin. |
| **Input: `forcing_history`** | `Dict[str, List[float]]` | Meteorological forcings: `precipitation`, `temperature`, `potential_evaporation`. |
| **Input: `attributes`** | `Dict[str, float]` | Static catchment properties: area, mean elevation, aridity index. |
| **Output: `predicted_discharge`** | `float` | Non-negative forecast discharge in $m^3/s$ (or $mm/day$). |
| **Output: `high_flow_probability`** | `float` | Probability in $[0, 1]$ of exceeding Q95 threshold. |
| **Output: `extreme_flow_probability`** | `float` | Probability in $[0, 1]$ of exceeding Q99 threshold. |
| **Output: `prediction_interval_lower`**| `float` | Non-negative lower prediction bound (5th percentile). |
| **Output: `prediction_interval_upper`**| `float` | Non-negative upper prediction bound (95th percentile). |

### Interface Strategy Recommendation
- **Recommended Interface:** **Option A (CLI file-in / file-out via `--input <path> --output <path>`)**.
- **Rationale:**
  1. Completely language and framework agnostic (supports PyTorch, TensorFlow, JAX, XGBoost, C++, Rust, R, ONNX).
  2. Eliminates Python runtime import collisions and CUDA/GPU driver version mismatches.
  3. Maps cleanly to container volume mounts (`docker run -v input:ro -v output:rw`).
  4. Participant crash (segfault, out-of-memory) terminates only the child container, preserving platform stability.
- **Python Function Support:** For participant projects exposing an in-memory `def predict(case_dict)`, HYDRAFORGE synthesizes a zero-dependency CLI wrapper shim (`hydraforge_shim.py`) inside the container at runtime. Participant files are **never modified or renamed**.

---

## 6. Discovery Status Definitions

| Status | Code | Meaning |
|---|---|---|
| **Overall Status** | `DISCOVERY_SUCCESS` | Repository inspected successfully; single unambiguous inference interface identified. |
| | `DISCOVERY_PARTIAL` | Repository inspected, but no inference entrypoint could be found. |
| | `DISCOVERY_FAILED` | Inspection failed due to resource limits, invalid Git SHA, or filesystem error. |
| | `NEEDS_ORGANIZER_REVIEW` | Ambiguous entrypoints or security warnings require manual organizer inspection. |
| **Interface Status** | `INTERFACE_IDENTIFIED` | Exact entrypoint and argument structure mapped. |
| | `INTERFACE_AMBIGUOUS` | Multiple conflicting inference entrypoints detected. |
| | `INTERFACE_NOT_FOUND` | No inference entrypoint detected in code, manifests, or docs. |
| **Confidence Level** | `HIGH` | Verified CLI arguments (`--input`/`--output`) or explicit package script. |
| | `MEDIUM` | Inferred CLI arguments or documented README command. |
| | `LOW` | Inferred in-memory callable or partial AST evidence. |
| | `NONE` | No evidence found or inspection failed. |

---

## 7. Security Architecture

1. **Zero Execution Guarantee:**
   - Participant Python files are **never executed or imported**.
   - Shell scripts and Makefile targets are **never invoked**.
   - `setup.py` is inspected via Python's built-in `ast.parse` module; arbitrary code inside `setup.py` (e.g. `os.system(...)`) is never run.
2. **Resource Throttling:**
   - Maximum repository size: **100 MB** (configurable).
   - Maximum file count: **2,000 files**.
   - Maximum individual file size: **10 MB** (oversized binary files skipped with warning).
   - Maximum directory depth: **8 levels**.
   - Maximum inspection duration: **30.0 seconds**.
3. **Symlink Defense:**
   - Any symlink that resolves outside the inspected repository root is detected via `Path.resolve()` and rejected with a security warning. It is **never traversed**.
4. **Documentation Threat Detection:**
   - Scans documentation code blocks for destructive commands (`rm -rf /`, `curl | bash`, reverse shells, `sudo`, fork bombs).
   - Automatically marks submission with `NEEDS_ORGANIZER_REVIEW` and generates audit alerts.
5. **No Label Access:**
   - The discovery engine operates strictly within the repository snapshot and has zero access to hidden benchmark evaluation targets or ground truth directories.

---

## 8. Example Discovery Reports for 3 Representative Repository Layouts

### Example 1: Standard Python CLI Repository
```markdown
# HYDRAFORGE Repository Discovery Report
**Discovery ID:** `disc_8f3a12b0e419`  
**Submission ID:** `sub_alpine_hydro`  
**Repository:** `https://github.com/alpine-hydro/topoflow-gnn`  
**Commit SHA:** `a1b2c3d4e5f60718293a4b5c6d7e8f9012345678`  

## Discovery Status Overview
- **Overall Status:** `DISCOVERY_SUCCESS`
- **Interface Classification:** `INTERFACE_IDENTIFIED`
- **Confidence Level:** `HIGH`

## Repository Structure
- **Total Files Scanned:** 14
- **Total Size:** 48.2 KB
- **Source Files:** 6
- **Manifests Found:** 1 (requirements.txt)
- **Detected Languages:** python

## Detected Manifests & Dependencies
- **requirements.txt** (`requirements.txt`): 4 dependencies (torch>=2.1.0, numpy>=1.24, pandas>=2.0, scipy>=1.11)

## Candidate Inference Commands
- `python main.py --input /data/cases.json --output /out/predictions.json` (from `README.md`)

## Candidate Entrypoints
- `main.py` (cli_script) — Purpose: `INFERENCE` [Confidence: HIGH]

## Proposed Interface Mapping
- **Interface Type:** `CLI_FILE_IN_OUT`
- **Executable Target:** `main.py`
- **Input Mechanism:** `--input <benchmark_input_path>`
- **Output Mechanism:** `--output <predictions_output_path>`
- **Command Template:** `python main.py --input {input_file} --output {output_file}`
- **Requires Adapter:** False
```

### Example 2: Package Structure with `pyproject.toml`
```markdown
# HYDRAFORGE Repository Discovery Report
**Discovery ID:** `disc_4c9d71e2a088`  
**Submission ID:** `sub_swiss_glacier`  
**Repository:** `https://github.com/glacier-ai/glacierflow`  
**Commit SHA:** `d4e5f6a1b2c30718293a4b5c6d7e8f9012345678`  

## Discovery Status Overview
- **Overall Status:** `DISCOVERY_SUCCESS`
- **Interface Classification:** `INTERFACE_IDENTIFIED`
- **Confidence Level:** `HIGH`

## Repository Structure
- **Total Files Scanned:** 22
- **Source Files:** 12
- **Manifests Found:** 2 (pyproject.toml, environment.yml)
- **Detected Languages:** python, toml, yaml

## Detected Manifests & Dependencies
- **pyproject.toml** (`pyproject.toml`): 3 dependencies (xarray>=2023.1, torch>=2.0, netcdf4)
  - Declared Entrypoints: `{'glacier-forecast': 'glacierflow.infer:run_forecast'}`
- **environment.yml** (`conda.yaml`): 4 dependencies

## Candidate Entrypoints
- `glacierflow/infer.py` (package_script) — Purpose: `INFERENCE` [Confidence: HIGH]

## Proposed Interface Mapping
- **Interface Type:** `CLI_INFERRED`
- **Executable Target:** `glacierflow/infer.py`
- **Input Mechanism:** `--input <benchmark_input_path>`
- **Output Mechanism:** `--output <predictions_output_path>`
- **Command Template:** `python glacierflow/infer.py --input {input_file} --output {output_file}`
- **Requires Adapter:** False
```

### Example 3: Ambiguous Multi-Model Ensemble
```markdown
# HYDRAFORGE Repository Discovery Report
**Discovery ID:** `disc_11e8a9f4c330`  
**Submission ID:** `sub_ensemble_hydro`  
**Repository:** `https://github.com/ensemble-hydro/dual-forecast`  
**Commit SHA:** `9f8e7d6c5b4a32109f8e7d6c5b4a32109f8e7d6c`  

## Discovery Status Overview
- **Overall Status:** `NEEDS_ORGANIZER_REVIEW`
- **Interface Classification:** `INTERFACE_AMBIGUOUS`
- **Confidence Level:** `LOW`

## Repository Structure
- **Total Files Scanned:** 8
- **Source Files:** 4
- **Manifests Found:** 1 (requirements.txt)

## Candidate Entrypoints
- `predict_xgb.py` (ast_inferred) — Purpose: `INFERENCE` [Confidence: HIGH]
- `predict_lstm.py` (ast_inferred) — Purpose: `INFERENCE` [Confidence: HIGH]

## Proposed Interface Mapping
*No automated interface mapping available.*

## Warnings & Security Notices
- ⚠️ Ambiguous inference interface: detected 2 candidate entrypoints (predict_xgb.py, predict_lstm.py). Manual organizer clarification required.
```

---

## 9. Test Verification Summary

The discovery test suite ([`test_discovery.py`](file:///c:/Users/DIVYANK%20BHARDWAJ/Desktop/Projects/HYDRAFORGE/HYDRAFORGE/tests/test_discovery.py)) comprehensively covers all 20 specified synthetic repository configurations:

| # | Scenario Tested | Status |
|---|---|---|
| 1 | Standard Python repository with `requirements.txt` and `main.py` | **PASSED** |
| 2 | Nonstandard filenames (`streamflow_synthesizer_v3.py`) | **PASSED** |
| 3 | Deeply nested source directory hierarchy (`src/models/hydrology/...`) | **PASSED** |
| 4 | Python package with `pyproject.toml` console scripts | **PASSED** |
| 5 | Repository with only `requirements.txt` and no README | **PASSED** |
| 6 | Repository with multiple manifests simultaneously (`pyproject.toml`, `requirements.txt`, `environment.yml`) | **PASSED** |
| 7 | Explicit inference command documented in README code fence | **PASSED** |
| 8 | Distinguishing separate training commands from inference commands | **PASSED** |
| 9 | Multiple candidate entrypoints (correctly flagged ambiguous without guessing) | **PASSED** |
| 10 | Repository with zero documentation / missing README | **PASSED** |
| 11 | Repository with no recognizable inference interface (utility only) | **PASSED** |
| 12 | Misleading filenames (e.g. empty `model.py` with real entrypoint in `pipeline_exec.py`) | **PASSED** |
| 13 | Oversized binary file handling (skipped with warning) | **PASSED** |
| 14 | Excessive file count enforcement (`RepositoryLimitsExceededError`) | **PASSED** |
| 15 | Insecure symlinks resolving outside repository root (flagged & pruned) | **PASSED** |
| 16 | Malicious README commands (`rm -rf /`, `curl \| bash`) detected and flagged | **PASSED** |
| 17 | Malicious `setup.py` scripts parsed via AST without executing code | **PASSED** |
| 18 | Malformed configuration files (syntax errors handled gracefully) | **PASSED** |
| 19 | Captured commit SHA anchoring (validation strictly against requested hash) | **PASSED** |
| 20 | Ambiguous interface formatting and markdown audit generation | **PASSED** |

### Complete Regression Status
```
============================ 109 passed in 23.01s =============================
```
- Existing Phase 1–4B tests: **89 passed**
- Phase 5A discovery tests: **20 passed**
- Total test count: **109 passed (100% PASS)**

---

## 10. Known Limitations & Future Phase 5B Integration

1. **AST Dynamic Import Limitations:** Extremely dynamic repositories that configure CLI parsers using `getattr(sys.modules[...])` or runtime `eval` may not reveal argument flags via static AST. For these repositories, HYDRAFORGE safely falls back to `CLI_INFERRED` or flags `NEEDS_ORGANIZER_REVIEW`.
2. **C++/Compiled Binaries:** Repositories compiling native binaries via `make` or CMake require Docker build integration in Phase 5B.
3. **Phase 5B Requirements:** Phase 5A produces the structured `DiscoveryReport` and `ProposedInterfaceMapping`. Phase 5B will consume this mapping to generate the ephemeral container runtime command and execute isolated evaluations.

