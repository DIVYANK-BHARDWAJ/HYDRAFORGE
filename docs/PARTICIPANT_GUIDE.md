# BASINSHIFT Challenge — Participant Guide
**Competition:** BASINSHIFT Hydrological Forecasting Challenge  
**Platform:** HYDRAFORGE  
**Contract Version:** 1.0.0  

---

## 1. Challenge Objective

Your mission is to forecast daily river discharge across diverse catchments over a 7-day lead horizon (\(h \in [1, 7]\)).

Models will be evaluated along six dimensions:
1. **Forecast Skill (35%)**: Kling-Gupta Efficiency (KGE) on unseen time periods.
2. **Event Detection (20%)**: Accurately predicting flood events exceeding the 95th and 99th historical percentiles.
3. **Generalization (15%)**: Forecasting discharge in ungauged, unseen river basins without prior local historical training data.
4. **Calibration & Uncertainty (15%)**: Proper probabilistic coverage of 10th, 50th, and 90th quantiles.
5. **Robustness (10%)**: Maintaining predictive stability when meteorological inputs experience missing data or sensor noise.
6. **Efficiency (5%)**: Inference runtime and memory efficiency.

---

## 2. Fast Registration (2 Fields Only)

Registering your submission takes less than 60 seconds:
1. Go to the **Participant Portal**.
2. Fill in exactly two fields:
   - **Team Name**: Your team or organization name.
   - **GitHub Repository URL**: A public GitHub repository link (e.g. `https://github.com/myteam/basinshift-gnn`).
3. Submit. HYDRAFORGE automatically discovers your default branch, queries the latest commit SHA, and issues a unique **Submission ID**.

> [!NOTE]
> Do NOT include API keys, secrets, credentials, or private tokens in your public repository.

---

## 3. Repository Structure & Dynamic Discovery

HYDRAFORGE does **not** enforce fixed filenames. You may use:
- `predict.py`
- `model.py`
- `src/forecast.py`
- Custom package layouts

Ensure your dependencies are declared in `requirements.txt` or `pyproject.toml`.

---

## 4. Local Validation

Before submitting, validate your model's output using our local testing CLI:
```bash
# 1. Generate predictions from sample input
python examples/baseline_submission/predict.py --input examples/sample_inputs.json --output my_predictions.json

# 2. Validate format against the contract
python scripts/validate_submission.py my_predictions.json
```

All 7 lead-day predictions must have:
- Valid timestamps matching the issue date + lead day
- Non-negative discharge values (\(Q \ge 0\))
- Monotonic quantiles (\(q_{10} \le q_{50} \le q_{90}\))
- Exceedance probabilities in \([0.0, 1.0]\)

