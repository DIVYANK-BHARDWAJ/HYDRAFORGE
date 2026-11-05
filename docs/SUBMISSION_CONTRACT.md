# HYDRAFORGE — Participant Submission Contract & Data Interface

**Contract Version:** 1.0.0  
**Challenge:** BASINSHIFT — The Global Flood Intelligence Challenge  
**Applicability:** Automated Evaluator & Participant Repositories  

---

## 1. Overview

To participate in the BASINSHIFT challenge, participant repositories must conform strictly to this versioned specification. The automated evaluator (`HYDRAFORGE`) executes submissions in an isolated environment with network disabled and validates all output artifacts against this contract.

---

## 2. Submission Artifacts

A valid submission consists of:
1. An executable GitHub repository cloned at an **immutable 40-character commit SHA**.
2. A root file named `submission_manifest.json`.
3. An entrypoint script (`run_forecast.py` by default) that reads evaluation inputs and writes `predictions.json`.

---

## 3. Schemas

### 3.1 `submission_manifest.json`

Declared at the repository root:

```json
{
  "team_name": "Hydrological Intelligence Lab",
  "submission_name": "HydroTransformer-OOD-v2",
  "contract_version": "1.0.0",
  "repository_url": "https://github.com/example-team/hydro-forecast",
  "commit_sha": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
  "dataset_declarations": {
    "training_datasets": ["Caravan v1.0", "ERA5-Land reanalysis"],
    "licenses": ["CC-BY 4.0", "Copernicus Open Access"],
    "temporal_coverage": "1990-01-01 to 2015-12-31",
    "preprocessing": "Standardized MinMax on training set; 30-day lag features"
  },
  "pretrained_models": ["chronos-bolt-base", "custom-lstm-weights.pt"],
  "entrypoint": "run_forecast.py"
}
```

### 3.2 Evaluation Input Records (`inputs.json`)

Mounted read-only into the evaluation environment at inference time:

```json
[
  {
    "case_id": "CASE_2026_0001",
    "catchment_id": "BASIN_0412",
    "forecast_origin": "2026-04-15T00:00:00Z",
    "horizons": [1, 3, 7],
    "discharge_history": [12.4, 13.1, 12.8, 14.5, 15.2],
    "forcing_history": {
      "precipitation_mm": [0.0, 2.5, 14.2, 28.6, 5.1],
      "temperature_c": [12.1, 11.5, 9.8, 8.4, 10.2],
      "solar_radiation_wm2": [180.5, 120.3, 85.0, 92.4, 160.1]
    },
    "attributes": {
      "area_km2": 450.2,
      "mean_elevation_m": 820.0,
      "mean_slope_m_per_km": 14.2,
      "soil_conductivity": 0.45
    },
    "split": "test_b",
    "region": "Alps",
    "is_corrupted": false
  }
]
```

### 3.3 Output Prediction Records (`predictions.json`)

Written by participant code to the designated output volume:

```json
[
  {
    "case_id": "CASE_2026_0001",
    "catchment_id": "BASIN_0412",
    "forecast_origin": "2026-04-15T00:00:00Z",
    "horizon": 1,
    "predicted_discharge": 18.42,
    "high_flow_probability": 0.32,
    "extreme_flow_probability": 0.04,
    "prediction_interval_lower": 14.10,
    "prediction_interval_upper": 23.50,
    "nominal_interval_coverage": 0.90
  },
  {
    "case_id": "CASE_2026_0001",
    "catchment_id": "BASIN_0412",
    "forecast_origin": "2026-04-15T00:00:00Z",
    "horizon": 3,
    "predicted_discharge": 22.15,
    "high_flow_probability": 0.68,
    "extreme_flow_probability": 0.18,
    "prediction_interval_lower": 16.50,
    "prediction_interval_upper": 29.80,
    "nominal_interval_coverage": 0.90
  },
  {
    "case_id": "CASE_2026_0001",
    "catchment_id": "BASIN_0412",
    "forecast_origin": "2026-04-15T00:00:00Z",
    "horizon": 7,
    "predicted_discharge": 16.05,
    "high_flow_probability": 0.15,
    "extreme_flow_probability": 0.01,
    "prediction_interval_lower": 11.20,
    "prediction_interval_upper": 22.40,
    "nominal_interval_coverage": 0.90
  }
]
```

---

## 4. Contract Validation Rules

Submissions that violate any of the following constraints are rejected immediately:

1. **Centrally Configured Supported Horizons:**
   All predictions must specify a horizon from the official configuration: `[1, 3, 7]` days. Hardcoded or unsupported horizons cause validation failure.
2. **Finite Floating-Point Values:**
   `NaN`, `+Infinity`, `-Infinity`, or unparseable numeric strings are strictly forbidden.
3. **Non-Negative River Discharge:**
   `predicted_discharge` must be $\ge 0.0$. Negative flows are rejected.
4. **Probability Bounds:**
   Both `high_flow_probability` and `extreme_flow_probability` must lie in $[0.0, 1.0]$.
5. **Interval Ordering & Bounds:**
   `prediction_interval_lower` must be $\ge 0.0$ and $\le prediction_interval_upper$.
6. **No Duplicate Predictions:**
   Exactly one prediction per `(case_id, horizon)` pair is permitted.
7. **Completeness (No Missing Cases):**
   Every evaluation case and required horizon provided in `inputs.json` must have a matching prediction record.
8. **No Unknown Cases:**
   Predictions referencing cases not in `inputs.json` are rejected.

---

## 5. Security & Isolation Controls

1. **Hidden Ground Truth:** Hidden labels reside strictly in organizer-secured storage. Participant containers/processes receive **only** `inputs.json`.
2. **Offline Inference:** All network calls (`curl`, `requests`, sockets) during evaluation are disabled.
3. **Execution Ceilings:** Max runtime: 300 seconds; Memory ceiling: 4096 MB RSS.
4. **Audit Cryptography:** The final evaluation report is fingerprinted with an immutable SHA-256 digest of predictions, environment stats, and scoring metrics.

