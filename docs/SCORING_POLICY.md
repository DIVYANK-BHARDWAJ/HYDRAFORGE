# HYDRAFORGE — Scoring Policy & Mathematical Formulas
**Challenge:** BASINSHIFT  
**Engine:** HYDRAFORGE Scoring Engine v1.0.0  

---

## 1. Six-Axis Metric Breakdown

Total score is bounded in \([0, 100]\) points:
\[ S_{\text{total}} = S_{\text{skill}} + S_{\text{events}} + S_{\text{gen}} + S_{\text{calib}} + S_{\text{rob}} + S_{\text{eff}} \]

### 1. Forecast Skill (35 Points)
Evaluated across standard temporal test period (Test A).
- Metric: Kling-Gupta Efficiency (KGE):
  \[ \text{KGE} = 1 - \sqrt{(r - 1)^2 + (\alpha - 1)^2 + (\beta - 1)^2} \]
  where \(r\) is Pearson correlation, \(\alpha = \sigma_s / \sigma_o\), and \(\beta = \mu_s / \mu_o\).
- Normalization:
  \[ S_{\text{skill}} = 35 \times \max\left(0, \frac{\text{KGE} - \text{KGE}_{\text{baseline}}}{1 - \text{KGE}_{\text{baseline}}}\right) \]

### 2. Event Detection (20 Points)
Focuses on extreme flood peak prediction (Q95 and Q99 events).
- Metric: Precision-Recall Area Under Curve (PR-AUC):
  \[ S_{\text{events}} = 10 \times \text{PR-AUC}_{Q95} + 10 \times \text{PR-AUC}_{Q99} \]

### 3. Generalization (15 Points)
Evaluated on ungauged catchments (Test B) with zero prior local training observations.
- Metric: Mean KGE on unseen catchments:
  \[ S_{\text{gen}} = 15 \times \max\left(0, \frac{\text{KGE}_{\text{unseen}} - \text{KGE}_{\text{baseline}}}{1 - \text{KGE}_{\text{baseline}}}\right) \]

### 4. Calibration & Uncertainty (15 Points)
Evaluates reliability of probabilistic forecast distribution.
- Metric: Continuous Ranked Probability Score (CRPS) and Quantile Coverage Error:
  \[ \text{Coverage Error} = |(P(y \le q_{90}) - P(y \le q_{10})) - 0.80| \]
  \[ S_{\text{calib}} = 7.5 \times (1 - \text{Coverage Error}) + 7.5 \times \text{CRPS}_{\text{norm}} \]

### 5. Robustness (10 Points)
Evaluated under controlled input corruptions (missing sensors, Gaussian noise, sensor drift) (Test C).
- Metric: Performance retention relative to uncorrupted inputs:
  \[ S_{\text{rob}} = 10 \times \max\left(0, \frac{\text{KGE}_{\text{corrupted}}}{\text{KGE}_{\text{clean}}}\right) \]

### 6. Efficiency (5 Points)
- Metric: Wall-clock latency per forecast sample (2.5 pts) and peak memory usage (2.5 pts).
  \[ S_{\text{eff}} = 2.5 \times \min\left(1, \frac{100\,\text{ms}}{\text{latency}}\right) + 2.5 \times \min\left(1, \frac{512\,\text{MB}}{\text{peak RAM}}\right) \]

