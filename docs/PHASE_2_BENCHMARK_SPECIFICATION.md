# HYDRAFORGE — Phase 2 Benchmark Specification & Split Architecture

**Document Version:** 1.0.0  
**Challenge:** BASINSHIFT — The Global Flood Intelligence Challenge  
**Authority:** Technical Architecture & ML Infrastructure Lead  
**Status:** SPECIFICATION & OPERATIONAL GUIDELINE  

---

## 1. Benchmark Architecture & Security Isolation

The HYDRAFORGE benchmark infrastructure enforces strict physical decoupling between participant-visible inputs and organizer-held hidden ground truth labels.

```text
data/
└── benchmark/
    ├── metadata/
    │   ├── thresholds.json            # Historical reference period Q95/Q99 thresholds
    │   ├── catchments.json            # Static physical attributes (area, elevation, slope, region)
    │   ├── split_manifests.json       # Case counts, catchment rosters, and SHA-256 hashes
    │   └── leakage_audit.json         # Automated multi-point leakage audit verification
    ├── inputs/                        # PARTICIPANT VISIBLE AT INFERENCE
    │   ├── train/inputs.json          # Historical training observations
    │   ├── validation/inputs.json     # Intermediate public tuning cases
    │   ├── test_a/inputs.json         # Future temporal holdouts
    │   ├── test_b/inputs.json         # Geographic holdouts on unseen catchments
    │   └── test_c/inputs.json         # Controlled input corruptions (paired to Test A)
    └── labels/                        # ORGANIZER-ONLY HIDDEN GROUND TRUTH
        ├── train/labels.json
        ├── validation/labels.json
        ├── test_a/labels.json
        ├── test_b/labels.json
        └── test_c/labels.json
```

### Access Isolation Invariant
The `ParticipantBenchmarkLoader` is restricted to paths under `data/benchmark/inputs/`. Its programming interface has no access to the `labels/` directory, preventing unintended leakage during evaluation.

---

## 2. Benchmark Partitions & Leakage Controls

| Partition | Scope | Catchments | Temporal Window | Visibility | Target Capability Tested |
|---|---|---|---|---|---|
| **Train** | Baseline training | $\mathcal{C}_{train}$ | Historical ($t \le T_1$) | Public | Representation & hydrological learning |
| **Validation** | Tuning & selection | $\mathcal{C}_{train}$ | Intermediate ($T_1 < t \le T_2$) | Public | Model validation & hyperparameter search |
| **Test A** | Temporal Holdout | $\mathcal{C}_{train}$ | Future ($t > T_2$) | Hidden | Temporal extrapolation in familiar basins |
| **Test B** | Geographic Holdout | $\mathcal{C}_{unseen}$ | Evaluation period ($t > T_2$) | Hidden | Zero-shot geographic transfer to unseen basins |
| **Test C** | Robustness / Stress | $\mathcal{C}_{train}$ | Perturbed variants of Test A | Hidden | Resilience to missing history, noise, latency |

### Leakage Verification Protocol
1. **Zero Catchment Leakage (Test B):** $\mathcal{C}_{train} \cap \mathcal{C}_{unseen} = \emptyset$. Verified by automated set intersection.
2. **Strict Chronological Cutoff (Test A):** $\min(t_{\text{Test A}}) > \max(t_{\text{Train}})$. Target forecast origins never overlap or precede historical training bounds.
3. **Paired Corruption Integrity (Test C):** Every corrupted case strictly maintains `clean_case_id` pointing to its corresponding clean Test A case. Ground truth target discharge is identical between paired clean and corrupted cases.
4. **Window Isolation:** Splits are partitioned prior to rolling-window generation.

---

## 3. Dataset-Agnostic Ingestion & Adapter Protocol

Hydrological data sources (CAMELS, Caravan, GRDC, national telemetry) differ in column naming and file layout. HYDRAFORGE provides a canonical adapter layer:

- **Canonical Variables:** `catchment_id`, `date`, `discharge`, `precipitation`, `temperature`, `solar_radiation`, `area_km2`, `mean_elevation_m`.
- **Supported Units:**
  - River discharge: `m3/s` or `mm/d` (must be explicitly documented; ambiguous units rejected).
  - Precipitation: `mm` or `mm/d`.
  - Temperature: `degC` or `K`.
- **Integrity Checks:** Automatic detection of duplicates, chronological inversion, negative river discharge, and non-finite entries.
- **Caravan Status:** `CaravanDatasetAdapter` is implemented as an extensible interface. It confirms that genuine Caravan files are currently absent from the workspace.

---

## 4. Threshold Calculation & Provenance

Thresholds ($Q_{95}, Q_{99}$) define high-flow and extreme-flow flood events.
- **Source Rule:** Thresholds are calculated **strictly from the historical training period** ($t \le T_1$) of each catchment.
- **No Evaluation Leakage:** Test period observations and participant model outputs are never used to derive thresholds.
- **Provenance Record:** Each threshold stores:
  - Catchment identifier
  - Exact percentile value (95.0, 99.0)
  - Numeric threshold value in canonical units ($m^3/s$)
  - Reference time window and sample count
  - Mathematical method (`historical_training_empirical_percentile`)

---

## 5. Reference Baselines

Three standard reference models are integrated:
1. **PersistenceBaseline:** Predicts the most recent known discharge $q(c, t)$ for all lead times $t+h$. Falls back to training mean for ungauged cases.
2. **ClimatologyBaseline:** Predicts day-of-year seasonal mean discharge computed exclusively from the training split.
3. **GBDTBaseline (XGBoost):** Fits a gradient boosted decision tree on lagged discharge ($t-1, t-2, t-7$, 7-day rolling mean/max), meteorological forcings, and static attributes. Predicts discharge, exceedance probabilities, and residual quantile intervals.

---

## 6. Unresolved Scientific Decisions Requiring Organizer Approval

The following architectural and methodological observations were identified during Phase 1 and Phase 2 testing, and require explicit organizer decisions:

### 1. Generalization Score Returning Zero in Single-Sample / Low-Variance Slices
- **Observation:** In the Phase 1 sample report, a single-case Test B slice returned 0.0 generalization points. When an evaluation slice contains only 1 sample or a constant target series, the observed variance $SS_{tot} = \sum (y - \bar{y})^2$ is zero, making standard NSE mathematically undefined.
- **Impact:** Catchments with very short evaluation periods or near-zero flow variance trigger the zero-variance safeguard, returning undefined NSE.
- **Decision Needed:** Should Test B evaluation require a minimum record length (e.g., $N \ge 30$ days), or should the metric fall back to Normalized MAE ($\text{NMAE} = \text{MAE} / \bar{y}$) when variance is below $10^{-6}$?

### 2. Scale Dependence of the Robustness MAE Denominator
- **Observation:** The robustness degradation formula uses $\text{Retention} = 1.0 - \frac{\Delta \text{MAE}}{\max(\text{MAE}_{clean}, 1.0)}$.
- **Impact:** For large rivers (e.g., discharge $500\text{ m}^3/s$), $\text{MAE}_{clean}$ may naturally be $20\text{ m}^3/s$. For small streams (discharge $2\text{ m}^3/s$), $\text{MAE}_{clean}$ may be $0.3\text{ m}^3/s$. Using $1.0\text{ m}^3/s$ as the floor treats $1\text{ m}^3/s$ of absolute error identically across massive and tiny catchments.
- **Decision Needed:** Should robustness retention be normalized by catchment mean discharge $\bar{y}_c$ or historical interquartile range ($\text{IQR}_c$), rather than a fixed global constant?

### 3. Brier Score Overlap Between Event Detection and Calibration
- **Observation:** Brier score is currently included in both Dimension 2 (High-Flow Event Detection: 40% of Q95 and Q99 sub-scores) and Dimension 4 (Calibration and Uncertainty: 50% of the dimension).
- **Impact:** Models with well-calibrated exceedance probabilities receive score benefits in both dimensions, potentially double-counting the probability calibration signal.
- **Decision Needed:** Should Dimension 2 focus purely on discriminative classification skill (AUPRC, Recall, Precision, F1), leaving Brier score and reliability strictly to Dimension 4?

### 4. Provisional Efficiency Thresholds
- **Observation:** Efficiency thresholds are currently provisionally set to: Runtime $\le 60$s (max 300s), Peak RAM $\le 1024$MB (max 4096MB), Artifact Size $\le 100$MB (max 500MB).
- **Impact:** High-capacity neural models or ensemble approaches may require up to 2GB RAM or 500MB weights.
- **Decision Needed:** Are these resource ceilings appropriate for the target competition compute tier (CPU evaluation node)?

### 5. Official Q95/Q99 Threshold Calculation Policy
- **Observation:** Thresholds are currently computed via empirical sample percentiles (`np.percentile`).
- **Impact:** For small sample sizes, empirical percentiles can underestimate extreme return-period floods compared to extreme-value distributions (e.g., Gumbel / Generalized Extreme Value fitting).
- **Decision Needed:** Should the benchmark freeze empirical sample percentiles or fit parametric hydrological flood-frequency curves?

### 6. Catchment-Specific vs. Regional Thresholding
- **Observation:** Test B catchments are completely unseen during training. If an unseen catchment is completely ungauged, its historical discharge distribution is unknown to the participant at forecast origin.
- **Impact:** In the current synthetic benchmark, Test B thresholds are assigned from regional training proxies when local historical discharge is unmonitored.
- **Decision Needed:** Will participants be provided with pre-computed reference thresholds in metadata for unseen Test B catchments, or are they expected to estimate flood risk from catchment attributes?

