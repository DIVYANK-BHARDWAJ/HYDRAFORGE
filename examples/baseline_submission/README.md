# BASINSHIFT Reference Participant Submission

Welcome to the **BASINSHIFT Hydrological Forecasting Challenge**, powered by the **HYDRAFORGE Evaluation Engine**.

## Overview

This repository demonstrates a clean, eligible submission repository structure. HYDRAFORGE features an automated discovery engine that automatically identifies your entry point whether named `predict.py`, `model.py`, `inference.py`, or housed within custom Python modules.

## Contract Requirements

1. **Input Interface**:
   Your model will be passed a path or streamed benchmark test inputs structured according to the `1.0.0` specification:
   - `historical_data`: Sequence of daily hydrological observations (`precipitation_mm`, `temperature_c`, `pet_mm`, `discharge_m3_s`).
   - `meteorological_forecast`: 7-day meteorological forecast (`precipitation_mm`, `temperature_c`, `pet_mm`).
   - `catchment_id` & `static_attributes`: Geophysical properties of the catchment.

2. **Output Interface**:
   Your model must produce a valid JSON output containing:
   - `contract_version`: `"1.0.0"`
   - `predictions`: Array of 7 records (one for each lead day 1..7) with:
     - `forecast_timestamp`: ISO-8601 string matching the benchmark issue date + lead day
     - `lead_day`: Integer 1 to 7
     - `predicted_discharge_m3_s`: Point forecast (\(m^3/s \ge 0\))
     - `quantile_10`: 10th percentile (\(q_{10} \le q_{50} \le q_{90}\))
     - `quantile_50`: Median (\(q_{50} \ge 0\))
     - `quantile_90`: 90th percentile
     - `prob_exceed_q95`: Exceedance probability for 95th percentile high flows (\(0 \le p \le 1\))
     - `prob_exceed_q99`: Exceedance probability for 99th percentile extreme flows (\(0 \le p \le 1\))

## Testing Locally Before Submission

Run the reference model against the sample input:
```bash
python predict.py --input ../sample_inputs.json --output my_predictions.json
```

Validate your generated prediction payload using HYDRAFORGE's validator:
```bash
python ../../scripts/validate_submission.py my_predictions.json
```

## Submitting Your Model

Submit your GitHub repository URL on the public participant portal:
- Provide your Team Name and public GitHub Repository URL.
- The platform automatically identifies the default branch and records the immutable HEAD commit SHA.
- No secrets or credentials should ever be committed to your repository.
