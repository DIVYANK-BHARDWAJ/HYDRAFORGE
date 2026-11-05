# HYDRAFORGE — Scoring Specification & Metric Engine Reference

**Document Version:** 1.0.0-PROVISIONAL  
**Challenge:** BASINSHIFT — The Global Flood Intelligence Challenge  
**Authority:** Technical Architecture & ML Infrastructure  
**Status:** PROVISIONAL — Subject to Formal Organizing Committee Approval  

---

## 1. Overview & Evaluation Principles

HYDRAFORGE implements an automated, deterministic, baseline-anchored evaluation engine designed to assess participant hydrological forecasting models across six designated dimensions:

| Dimension | Provisional Weight | Primary Focus | Anchor Baseline |
|---|---:|---|---|
| 1. Forecast skill | 25 | Continuous discharge forecast accuracy | Persistence ($y_t$) |
| 2. High-flow event detection | 25 | Classification & probability of Q95 & Q99 events | Climatology / Zero Skill |
| 3. Out-of-distribution generalization | 20 | Transfer to unseen catchments & spatial dispersion | Temporal Holdout (Test A) |
| 4. Calibration & uncertainty | 15 | Probability Brier skill & 90% interval coverage | Nominal 90% & Climatology |
| 5. Robustness | 10 | Relative performance retention under corruptions | Paired Clean Reference |
| 6. Computational efficiency | 5 | Runtime, peak RSS memory, checkpoint disk size | Budget Ceilings |
| **Total Machine Score** | **100** | **Comprehensive Benchmark Evaluation** | **Absolute Anchors** |

### Fundamental Scoring Constraints
1. **No Participant-Relative Min-Max Normalization:** Scores are never normalized against the minimum or maximum performance of participants in a given competition batch. A submission receives the exact same score regardless of whether other competitors perform well or poorly.
2. **Benchmark Metadata Exclusivity:** All classification thresholds ($Q_{95}, Q_{99}$) and catchment attributes are supplied strictly by organizer benchmark metadata derived from historical reference periods. Thresholds are **never** estimated from test period labels or participant predictions.
3. **Missing Data Policy:** When a required prediction, split, or efficiency measurement is missing, points are never silently awarded. An explicit penalty or zero score is assigned, accompanied by a structured diagnostic warning.
4. **Finite Guarantees:** No scoring function produces `NaN`, `Infinity`, or negative scores. All dimension scores are bounded within $[0.0, \text{MaxPoints}]$.

---

## 2. Dimension 1: Forecast Skill (Provisional Weight: 25 Points)

### 2.1 Continuous Error Metrics
For true observations $y_i$ and predicted discharges $\hat{y}_i$ over $N$ samples:

- **Mean Absolute Error (MAE):**
  $$\text{MAE} = \frac{1}{N} \sum_{i=1}^N |y_i - \hat{y}_i|$$
- **Root Mean Squared Error (RMSE):**
  $$\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N (y_i - \hat{y}_i)^2}$$
- **Nash-Sutcliffe Efficiency (NSE):**
  $$\text{NSE} = 1.0 - \frac{\sum_{i=1}^N (y_i - \hat{y}_i)^2}{\sum_{i=1}^N (y_i - \bar{y})^2}$$
  where $\bar{y} = \frac{1}{N} \sum_{i=1}^N y_i$.

### 2.2 Constant Target Series Edge Case
If total sum of squares $\sum (y_i - \bar{y})^2 < 10^{-12}$, the target series has zero variance (constant river flow). In this condition:
- Standard NSE denominator is zero.
- If model predictions match the constant value within $10^{-12}$, $\text{NSE}$ is assigned $1.0$.
- Otherwise, $\text{NSE}$ is mathematically undefined (`None`), a diagnostic warning is logged, and persistence-relative skill falls back safely without division by zero.

### 2.3 Persistence-Relative Skill Formula
Using the last known river discharge at the forecast origin ($y_{persist} = y_{t}$), persistence efficiency $\text{NSE}_{persist}$ is computed. The model skill is calculated via the proposed provisional formula:

$$\text{Skill}_{\text{provisional}} = \max\left(0.0, \min\left(1.0, \frac{\text{NSE}_{model} - \text{NSE}_{persist}}{1.0 - \text{NSE}_{persist}}\right)\right) \times 25.0$$

#### Singularity Handling (Near-Zero Denominator)
If $|1.0 - \text{NSE}_{persist}| < 10^{-6}$, persistence has near-zero error.
- If the model also achieves $\text{NSE}_{model} \ge 1.0 - 10^{-6}$, full points ($25.0$) are awarded.
- Otherwise, $0.0$ points are awarded.
- An explicit diagnostic warning is emitted.

### 2.4 Aggregation Policy
- Forecast skill is computed independently per catchment.
- Overall Dimension 1 score is the **macro-average** across all evaluated catchments:
  $$\text{Score}_{\text{Skill}} = \frac{1}{|\mathcal{C}|} \sum_{c \in \mathcal{C}} \text{Skill}(c)$$
- Pooled MAE, RMSE, and NSE across all combined records are reported for secondary diagnostic transparency.

---

## 3. Dimension 2: High-Flow Event Detection (Provisional Weight: 25 Points)

Evaluates rare event forecasting across two severity tiers:
- **Tier 1 (High-Flow, $Q_{95}$):** Provisional sub-weight 15.0 points.
- **Tier 2 (Extreme-Flow, $Q_{99}$):** Provisional sub-weight 10.0 points.

### 3.1 Threshold Application
- High-flow indicator: $y_{event, 95} = \mathbb{I}(y \ge T_{Q95})$.
- Extreme-flow indicator: $y_{event, 99} = \mathbb{I}(y \ge T_{Q99})$.
- $T_{Q95}$ and $T_{Q99}$ are supplied by benchmark metadata.

### 3.2 Evaluated Metrics
For each event tier:
1. **Confusion Matrix at Alert Probability Threshold (0.50):**
   - True Positives ($TP$), False Positives ($FP$), False Negatives ($FN$), True Negatives ($TN$).
   - Precision: $P = \frac{TP}{TP + FP}$ (0.0 if $TP+FP=0$).
   - Recall: $R = \frac{TP}{TP + FN}$ (undefined if $TP+FN=0$).
   - F1-Score: $F_1 = \frac{2 P R}{P + R}$ (0.0 if $P+R=0$).
2. **Area Under Precision-Recall Curve (AUPRC):**
   - Integrated via trapezoidal numerical quadrature over precision-recall frontiers sorted by predicted probability.
   - Normalized relative to event prevalence $\pi = \frac{P}{N}$:
     $$\text{AUPRC}_{\text{norm}} = \max\left(0.0, \frac{\text{AUPRC} - \pi}{1.0 - \pi}\right)$$
     An inverted or random classifier achieving $\text{AUPRC} \le \pi$ receives $0.0$.
3. **Brier Score (BS):**
   $$\text{BS} = \frac{1}{N} \sum_{i=1}^N (\hat{p}_i - y_{event, i})^2 \in [0.0, 1.0]$$
   Brier Skill: $\text{BSS} = \max(0.0, 1.0 - \text{BS})$.

### 3.3 Zero Positive Event Handling
When zero positive events occur in an evaluation partition ($TP + FN = 0$):
- F1 and AUPRC are mathematically undefined.
- The evaluation engine does not crash or penalize participants arbitrarily.
- A warning is recorded: `"Zero actual positive events; scoring exclusively on probability calibration (Brier skill)."`
- Points are determined purely by Brier probability calibration.

### 3.4 Tier Combination Formula
For each tier ($k \in \{Q95, Q99\}$):
$$\text{Score}_k = \text{MaxPoints}_k \times \left(0.60 \times \text{DiscriminativeSkill}_k + 0.40 \times \text{BrierSkill}_k\right)$$
$$\text{Score}_{\text{Event}} = \min(25.0, \text{Score}_{Q95} + \text{Score}_{Q99})$$

---

## 4. Dimension 3: Out-of-Distribution Generalization (Provisional Weight: 20 Points)

### 4.1 Evaluation Partitions
- **Test B (Geographic Holdout):** Catchments completely excluded from training.
- **Reference Split (Test A or Val):** Historical catchments evaluated on holdout periods.

### 4.2 Metrics & Formulation
1. **Unseen Catchment Macro-Skill:** Macro-average forecast skill across all Test B basins: $\text{Skill}_{norm}(Test\_B) \in [0.0, 1.0]$.
2. **Transfer Retention Ratio:**
   $$\text{Retention} = \min\left(1.0, \max\left(0.0, \frac{\text{Skill}_{norm}(Test\_B)}{\text{Skill}_{norm}(Ref)}\right)\right)$$
3. **Regional Performance & Dispersion:**
   - Catchments are grouped by their official benchmark `region`.
   - Missing region metadata is flagged in warnings; regions are never fabricated.
   - Regional dispersion standard deviation $\sigma_{region}$ is computed across regional mean skills.
   - A dispersion penalty $\text{Penalty}_{disp} = \min(0.20, \frac{\sigma_{region}}{25.0})$ is applied to discourage models that succeed in one climate zone while catastrophically failing in another.

### 4.3 Generalization Score Formula
$$\text{Score}_{\text{Gen}} = 20.0 \times \max\left(0.0, \text{Skill}_{norm}(Test\_B) \times (0.80 + 0.20 \times \text{Retention}) - \text{Penalty}_{disp}\right)$$

---

## 5. Dimension 4: Calibration and Uncertainty (Provisional Weight: 15 Points)

*Note: CRPS is deliberately excluded because participant models submit prediction intervals and discrete exceedance probabilities rather than full parametric distributions.*

### 5.1 Probability Calibration (7.5 Points)
- Evaluates mean Brier score for high-flow and extreme-flow exceedance probabilities:
  $$\text{BS}_{mean} = \frac{\text{BS}_{Q95} + \text{BS}_{Q99}}{2.0}$$
  $$\text{Score}_{prob} = 7.5 \times \max(0.0, 1.0 - \text{BS}_{mean})$$

### 5.2 Prediction Interval Calibration & Sharpness (7.5 Points)
For nominal coverage target $\alpha_{nom} = 0.90$ (90% central interval):
1. **Empirical Coverage:**
   $$\text{Coverage} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(lower_i \le y_i \le upper_i)$$
2. **Coverage Error Penalty:**
   $$\text{Score}_{cov} = \max(0.0, 1.0 - 2.0 \times |\text{Coverage} - 0.90|)$$
3. **Sharpness Normalization:**
   Normalized interval width $\bar{W}_{norm} = \frac{\frac{1}{N}\sum (upper_i - lower_i)}{\bar{y}_{obs}}$.
   $$\text{Factor}_{sharp} = \begin{cases} 1.0 & \text{if } \bar{W}_{norm} \le 1.5 \\ \max\left(0.10, \exp\left(-\frac{\bar{W}_{norm} - 1.5}{3.0}\right)\right) & \text{if } \bar{W}_{norm} > 1.5 \end{cases}$$
4. **Degenerate Interval Handling:**
   Intervals where $lower > upper$ or values are non-finite are counted as misses and directly penalize valid sample proportion:
   $$\text{Score}_{int} = 7.5 \times \text{Score}_{cov} \times \text{Factor}_{sharp} \times \frac{N_{valid}}{N}$$

---

## 6. Dimension 5: Robustness (Provisional Weight: 10 Points)

### 6.1 Paired Clean vs. Corrupted Cases
- Evaluated on Test C cases strictly paired to corresponding clean cases via `clean_case_id`.
- Unpaired corrupted cases are excluded from scoring and logged in diagnostic warnings.

### 6.2 Corruption Families
- `missing_discharge`: River flow observations withheld prior to forecast origin.
- `input_noise`: Additive Gaussian perturbation on meteorological forcings.
- `reporting_delay`: Latency lag in meteorological observations.

### 6.3 Retention Formula
For each corruption family $f$:
$$\Delta \text{MAE}_f = \text{MAE}_{corrupt, f} - \text{MAE}_{clean, f}$$
$$\text{Retention}_f = \begin{cases} 1.0 & \text{if } \Delta \text{MAE}_f \le 0 \\ \max\left(0.0, 1.0 - \frac{\Delta \text{MAE}_f}{\max(\text{MAE}_{clean, f}, 1.0)}\right) & \text{if } \Delta \text{MAE}_f > 0 \end{cases}$$

$$\text{Score}_{\text{Rob}} = 10.0 \times \frac{1}{|F|} \sum_{f \in F} \text{Retention}_f$$

---

## 7. Dimension 6: Efficiency (Provisional Weight: 5 Points)

| Metric | Target Budget | Max Limit | Points |
|---|---|---|---:|
| Inference Runtime | $\le 60$ seconds | 300 seconds | 2.5 |
| Peak RSS Memory | $\le 1024$ MB | 4096 MB | 1.5 |
| Checkpoint Artifact Size | $\le 100$ MB | 500 MB | 1.0 |
| **Total** | | | **5.0** |

- **Unavailable Measurements:** An unmeasured or `None` value is explicitly distinguished from `0.0`. It receives $0.0$ points with an accompanying diagnostic warning.
- **Linear Decay:** Performance between target budget and max limit decays linearly. Exceeding max limit awards $0.0$ points.

---

## 8. Summary of Explicit Organizer Decisions Requiring Approval

1. **Threshold Quantiles:** Formally freeze $Q_{95}$ and $Q_{99}$ as the high-flow and extreme-flow benchmark thresholds.
2. **NSE Normalization Baseline:** Formally approve the persistence-relative skill formula $\max(0, \frac{\text{NSE}_{m} - \text{NSE}_{p}}{1 - \text{NSE}_{p}})$.
3. **Nominal Coverage:** Approve 90% as the standard required prediction interval coverage.
4. **Dimension Weight Distribution:** Approve the provisional $25 / 25 / 20 / 15 / 10 / 5$ breakdown.

