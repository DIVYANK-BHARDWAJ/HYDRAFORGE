# HYDRAFORGE — Data Provenance & Caravan Staging Report
**Dataset:** Caravan / Synthetic Benchmark Suite  
**Date:** 2026-11-05  

---

## 1. Caravan Hydrological Dataset Status

> [!WARNING]
> **Status: `BLOCKED_EXTERNAL_DATA`**  
> The real-world global Caravan hydrological benchmark dataset (100+ GB across global river basins) is not bundled directly inside this source repository to prevent excessive repository bloat.

### Staging Instructions for Production Data:
To stage the official Caravan dataset for production competition runs:
1. Download the Caravan dataset archive from Zenodo / EarthArXiv:
   ```bash
   # URL: https://zenodo.org/records/7944211
   mkdir -p data/caravan
   tar -xzf caravan.tar.gz -C data/caravan/
   ```
2. Verify checksums of basin timeseries and attributes:
   ```bash
   python -m hydraforge.benchmark.validation --dataset-root data/caravan
   ```
3. Set environment variable in `.env`:
   ```bash
   CARAVAN_DATA_ROOT=/app/data/caravan
   ```

---

## 2. Synthetic Benchmark Suite (Active in Repository)

For software development, integration testing, CI/CD verification, and end-to-end simulation, HYDRAFORGE includes a mathematically validated, deterministic synthetic benchmark dataset:
- **Location:** `data/benchmark/`
- **Catchments:** 10 synthetic basins spanning 3 hydro-climatic regions (Alps, Plains, Highlands).
- **Splits:**
  - `train`: Historical training records with paired meteorology and discharge.
  - `validation`: Hyperparameter tuning split.
  - `test_a`: Standard unseen temporal period (Forecast Skill & Events).
  - `test_b`: Unseen geographic basins (Generalization).
  - `test_c`: Controlled sensor perturbations (Robustness).
- **Leakage Audit:** Cryptographically audited with zero temporal leakage (`is_leakage_free: True`).
- **Label Shielding:** Hidden labels are maintained in isolated directories (`data/benchmark/labels/`) and strictly shielded from participant containers.

