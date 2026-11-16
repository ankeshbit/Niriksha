# Machine Learning Model Readiness & Governance Policy

## Legal Metrology Readability Decision Governance

### 1. Executive Summary & Statutory Context
Under Rules 6 and 7 of the **Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)**, every pre-packaged commodity must display mandatory statutory declarations (such as MRP, Net Quantity, Manufacturer details, Consumer Care, and Month/Year of Manufacture) in a manner that is **conspicuous, legible, and prominent**.

Declaring a product non-compliant can result in legal notices, product seizures, compounding fees, or prosecution under Section 36(1) of the Legal Metrology Act, 2009. Consequently:
- Automated machine learning predictions must **NEVER** convert optical degradation or low model confidence into an automatic legal violation.
- Models trained on synthetic, simulated, or demonstration datasets must **NEVER** independently certify that a declaration is legally compliant or bypass human inspector adjudication.

---

### 2. Audit of Current Baseline Model (`readability_model.joblib`)
As documented in `backend/ml_models/model_metadata.json`:
- **Training Data Status**: `DEMONSTRATION DATA -- NOT REAL-WORLD TRAINING DATA`.
- **Dataset Size**: 18 packages total (12 train, 2 validation, 4 test).
- **Validation Metrics**:
  - Validation Accuracy: 66.7%
  - Validation Macro F1: 0.50
  - Validation Recall for `NOT_READABLE`: **0.00%** (The model failed to detect any unreadable declaration).
- **Conclusion**: The baseline model is demonstrational only and **unsuitable for authoritative statutory decisions**.

---

### 3. Safety Controls Implemented

1. **Synthetic Model Gate**:
   - The analyzer checks metadata for demonstration or synthetic markers (`is_synthetic_model = True`).
   - Synthetic models are restricted strictly to **advisory and telemetry purposes**.
   - Synthetic predictions **CANNOT** independently classify a declaration as `READABLE` or clear manual review requirements.

2. **Feature Flag Gate (`ML_READABILITY_MODEL_ENABLED`)**:
   - Configured in `backend/config.py`.
   - Defaults to `False`.
   - Even when set to `True`, the model must pass validation readiness checks before it can influence decisions.

3. **Deterministic Authority**:
   - High-confidence readability is granted solely on objective, deterministic optical properties:
     - OCR confidence $\ge 0.85$
     - Local crop Laplacian variance (sharpness) $\ge 35.0$
     - Local Michelson contrast $\ge 0.15$
   - Where optical quality is borderline or uncertain ($0.50 \le \text{OCR} < 0.85$), the system routes to `MANUAL_VERIFICATION_REQUIRED` (`requires_manual_verification = True`).

4. **Anti-Fabrication & Non-Violation Invariant**:
   - An optical defect, OCR failure, or low-confidence model prediction is an observation limitation, not evidence of a manufacturer statutory violation.
   - Such cases route to `MANUAL_VERIFICATION_REQUIRED` or `UNREADABLE`, prompting the inspector to verify the physical package.

---

### 4. Prerequisites for Enabling a Production Readability Model

Before toggling `ML_READABILITY_MODEL_ENABLED = True` in production, the model must be trained and validated against the following empirical criteria:

| Category | Requirement | Acceptance Threshold |
| :--- | :--- | :--- |
| **Dataset Scale** | Real-world Indian retail package images across various formats (pouches, bottles, boxes, cans, blister packs) | Minimum 1,500 unique packages / 5,000+ localized crops |
| **Ground Truth Quality** | Double-blind human annotations verified by certified Legal Metrology Inspectors | Inter-annotator agreement (Cohen's Kappa) $\ge 0.85$ |
| **Safety Recall** | Test recall on `NOT_READABLE` class (preventing false compliant classifications) | $\ge 0.95$ (95%) |
| **Classification F1** | Macro F1 score across all classes (`READABLE`, `PARTIALLY_READABLE`, `NOT_READABLE`) | $\ge 0.90$ (90%) |
| **Out-of-Distribution Robustness** | Stress testing under glare, angle distortion, shadows, and low illumination | Accuracy degradation $\le 10\%$ under adverse lighting |
| **Script Diversity** | Evaluation across Hindi, English, and regional Indian scripts | Consistent performance across multi-script labels |
| **Regulatory Sign-Off** | Formal review and documentation approved by the Department of Consumer Affairs (DoCA) | Documented compliance sign-off |
