# NiriKsha Legal Metrology Compliance Engine

**Statutory Basis:** Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)  
**Implementation Modules:**  
- `backend/placement_service.py`
- `backend/font_size_service.py`
- `backend/readability_service.py`
- `backend/declaration_validation_service.py`
- `backend/report_service.py`

---

## 1. Placement Analysis Engine (`backend/placement_service.py`)

### Statutory Mandate
- **Rule 6 & Rule 7:** Declarations must be clearly visible and legible on the container or package.
- **Rule 12:** The declaration of Net Quantity and Commodity Name shall appear on the **Principal Display Panel (PDP)** of the package.
- Other declarations (Manufacturer/Packer details, Date of Packing, Consumer Care, MRP) may appear on the Principal Display Panel or on an **Information Panel** (back or side panel).

### Technical Implementation
The engine takes normalized OCR bounding boxes `[x1, y1, x2, y2]` along with image metadata:
- Evaluates vertical and horizontal positioning within the panel.
- Distinguishes whether the captured view is `front` (PDP), `back`, `side`, or an auxiliary angle.
- Determines whether the declaration satisfies statutory placement rules without fabricating spatial coordinates.

### Status Classifications
- `PLACEMENT_COMPLIANT`: Field detected on statutory required panel (e.g. Net Quantity on front PDP).
- `PLACEMENT_NON_COMPLIANT`: Field detected exclusively on prohibited or incorrect panel (e.g. Net Quantity missing from PDP).
- `PLACEMENT_UNCERTAIN`: Image view angle or ambiguous panel geometry prevents definitive automated classification.
- `NOT_DETERMINABLE`: Missing bounding box or missing view metadata.
- `MANUAL_VERIFICATION_REQUIRED`: Routes to inspecting officer for physical package confirmation.

---

## 2. Font Size Analysis Engine (`backend/font_size_service.py`)

### Statutory Mandate
- **Rule 9 & Table 1:** Minimum height of numerals and letters for declarations based on net quantity of commodity:

| Net Quantity (Weight in g/kg or Volume in ml/l) | Minimum Height of Numerals (mm) | Minimum Height of Letters (mm) |
|---|---|---|
| Up to 50 g / ml | 1.0 mm | 1.0 mm |
| 50 g / ml to 200 g / ml | 2.0 mm | 2.0 mm |
| 200 g / ml to 1 kg / l | 4.0 mm | 2.0 mm |
| More than 1 kg / l | 6.0 mm | 3.0 mm |

### Anti-Fabrication Safeguard & Trained ML Model Integration
**Pixel height alone is NOT physical millimeter height.** Camera zoom, distance, sensor resolution, and perspective distortion prevent arbitrary conversion of raw pixels to legal statutory millimeters.

The engine integrates the trained ML model from `NiriKsha_Font_Size_Readability_Analysis.ipynb`:
1. **Model Architecture:** `GradientBoostingRegressor` trained on 15 geometric, textual, and optical features (`pixel_height`, `pixel_width`, `aspect_ratio`, `normalized_height`, `normalized_width`, `image_width`, `image_height`, `text_length`, `char_count`, `word_count`, `avg_char_width`, `ocr_confidence`, `crop_resolution`, `sharpness`, `contrast`).
2. **Strict Calibration Precondition:** The ML model and optical metrology **require a validated physical calibration scale** (plausible range: $0.2 \le \text{pixels\_per\_mm} \le 200.0$).
3. **If Calibration Exists:**
   - Optical millimeter height is computed: $\text{Height (mm)} = \frac{\text{Pixel Height}}{\text{Pixels per mm}}$.
   - ML model executes inference to estimate character height with provenance recorded (`ml_predicted_height_mm`, `ml_model_name`, `ml_features`).
   - The result is compared against Rule 9 Table 1 statutory thresholds.
4. **If Calibration is Missing or Out of Range:**
   - The engine **NEVER fabricates millimeters** from raw pixels.
   - Outputs `FONT_SIZE_UNDETERMINABLE` and routes to `MANUAL_VERIFICATION_REQUIRED`.

---

## 3. Declaration-Level Readability Engine (`backend/readability_service.py`)

### Technical Implementation & Trained ML Model Integration
General whole-image quality is distinct from declaration-level readability. The readability engine integrates the trained model from `NiriKsha_Font_Size_Readability_Analysis.ipynb` operating on localized OCR bounding box crops:
1. **15 Extracted Features:** `sharpness_laplacian_var`, `contrast_std`, `edge_density`, `grayscale_mean`, `grayscale_std`, `noise_estimate`, `text_background_separation`, `perspective_distortion_indicator`, `ocr_confidence`, `crop_width`, `crop_height`, `crop_resolution`, `pixels_per_char`, `char_density`, `blur_score`.
2. **Quality Gate:** If `crop_resolution < 200` pixels (`MIN_TRUSTED_CROP_PIXELS`), visual features are deemed uninformative. The system routes strictly to `READABILITY_UNCERTAIN` and `MANUAL_VERIFICATION_REQUIRED`.
3. **Trained Classifier:** `LogisticRegression` with `StandardScaler` outputs predicted readability class (`READABLE`, `PARTIALLY_READABLE`, `NOT_READABLE`) and class probability.
4. **Confidence Routing:** If maximum predicted probability is below $0.55$ (`MIN_MODEL_CONFIDENCE`), the engine flags `MANUAL_VERIFICATION_REQUIRED` for inspecting officer review.
5. **Full Evidence Provenance:** Stores `ml_model_name`, `ml_confidence`, `ml_predicted_label`, and `ml_features` for tamper-evident audit trails.

### Statutory Safety Rule (No Legal Decisions in ML Layer)
An unreadable crop, low OCR confidence, optical blur, or ML classification **MUST NEVER** be converted into an automatic legal conviction or fine. The ML layer only provides visual clarity/metrology estimations. Legal compliance determinations are handled strictly by the statutory rule engine and the human inspecting officer:
- `READABLE`
- `POOR_READABILITY`
- `UNREADABLE`
- `UNCERTAIN` / `READABILITY_UNCERTAIN`
- `MANUAL_VERIFICATION_REQUIRED`

---

## 4. Misleading & Non-Standard Declaration Engine (`backend/declaration_validation_service.py`)

### Dimension Validation
Each extracted declaration is evaluated across:
1. **Presence:** Whether the field is detected on the package.
2. **Completeness:** Whether all statutory sub-components exist (e.g. premise, town, state, PIN for manufacturer).
3. **Format Standard:**
   - **MRP:** Verifies statutory qualifier (`Inclusive of all taxes` / `Incl. of all taxes`) and currency symbol.
   - **Net Quantity:** Verifies SI metric units (`g`, `kg`, `ml`, `l`). Rejects prohibited or non-standard units (e.g., `lbs`, `oz`).
   - **Dates:** Validates calendar month/year formatting and rejects future impossible packing dates.
   - **Consumer Care:** Verifies presence of at least one valid communication channel (telephone, email, or physical postal address).
4. **Verified Rule Registry:** All rules carry statutory references (e.g. `PCR_RULE_6_1_E`). Any unverified statutory claim is marked `NEEDS_LEGAL_VERIFICATION`.

---

## 5. Unified Declaration Compliance Matrix

The unified matrix provides an officer-facing summary:

$$\text{Declaration Matrix Row} = \{\text{Present}, \text{Correct}, \text{Readable}, \text{Placement}, \text{Font Size}, \text{Format}, \text{Status}\}$$

Visible directly on the mobile inspector terminal, PDF statutory reports, and DOCX inspection archives.
