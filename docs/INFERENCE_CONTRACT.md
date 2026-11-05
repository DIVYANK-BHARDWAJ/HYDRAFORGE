# HYDRAFORGE — Standardized Inference Contract
**Specification Version:** 1.0.0  
**Format:** JSON / UTF-8  

---

## 1. Input Specification

When invoked by the isolated evaluation worker, models receive a JSON payload with:
- `contract_version`: `"1.0.0"`
- `horizon_days`: 7
- `issue_time`: ISO-8601 UTC timestamp
- `catchment_id`: String identifier (e.g. `basin_042`)
- `historical_data`: Array of daily observations prior to the forecast origin:
  - `timestamp`: ISO-8601 date
  - `precipitation_mm`: Total precipitation (mm)
  - `temperature_c`: Mean daily temperature (°C)
  - `pet_mm`: Potential evapotranspiration (mm)
  - `discharge_m3_s`: Observed river discharge (\(m^3/s\))
- `meteorological_forecast`: Array of 7 future forcing records:
  - `forecast_timestamp`: Future date
  - `lead_day`: Integer \(1 \dots 7\)
  - `precipitation_mm`: Forecasted precipitation
  - `temperature_c`: Forecasted temperature
  - `pet_mm`: Forecasted PET
- `static_attributes`: Geophysical constants:
  - `catchment_area_km2`, `elevation_m`, `soil_permeability`, etc.

---

## 2. Output Specification

The model must produce a single JSON object with:
- `contract_version`: `"1.0.0"`
- `predictions`: Array of 7 records:
  - `forecast_timestamp`: Matching the corresponding meteorological forecast timestamp
  - `lead_day`: Integer \(1 \dots 7\)
  - `predicted_discharge_m3_s`: Point forecast in \(m^3/s \ge 0\)
  - `quantile_10`: 10th percentile lower bound
  - `quantile_50`: 50th percentile (median)
  - `quantile_90`: 90th percentile upper bound
  - `prob_exceed_q95`: Flood threshold exceedance probability \([0.0, 1.0]\)
  - `prob_exceed_q99`: Extreme flood threshold exceedance probability \([0.0, 1.0]\)

---

## 3. Strict Invariant Rules

1. **Finite Numbers**: NaN, Infinity, and nulls are strictly prohibited.
2. **Non-Negativity**: Discharge \(Q \ge 0\).
3. **Quantile Monotonicity**: \(q_{10} \le q_{50} \le q_{90}\).
4. **Probability Bounds**: \(0.0 \le p \le 1.0\).
5. **Coverage**: Exactly 7 records matching requested lead days \(1 \dots 7\).
