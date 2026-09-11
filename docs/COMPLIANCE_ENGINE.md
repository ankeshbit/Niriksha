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

### Anti-Fabrication Safeguard
**Pixel height alone is NOT physical millimeter height.** Camera zoom, distance, sensor resolution, and perspective distortion prevent arbitrary conversion of raw pixels to legal statutory millimeters.

Therefore, the engine enforces:
1. If a verified physical scale calibration reference exists (e.g. ArUco marker, fiducial scale ruler, calibrated DPI metadata):
   $$\text{Height (mm)} = \frac{\text{Pixel Height}}{\text{Pixels per mm}}$$
   The estimated millimeter height is compared against Rule 9 Table 1.
2. If no physical calibration reference exists:
   The engine **NEVER fabricates millimeters** from raw pixels. It records the measured pixel height and returns:
   - `FONT_SIZE_UNDETERMINABLE`
   - `MANUAL_VERIFICATION_REQUIRED`

---

## 3. Declaration-Level Readability Engine (`backend/readability_service.py`)

### Technical Implementation
General whole-image quality is distinct from declaration-level readability. The readability engine crops the localized bounding box of each mandatory declaration and evaluates:
1. **Laplacian Variance:** Measures high-frequency edge transition sharpness to quantify localized optical blur.
2. **RMS & Michelson Contrast:** Measures luminance range between foreground characters and background packaging.
3. **Character Visibility & OCR Confidence:** Evaluates optical character recognition confidence score.

### Statutory Safety Rule
An unreadable crop, low OCR confidence, or optical blur **MUST NEVER** be converted into an automatic legal violation. Technical observation defects route directly to:
- `READABLE`
- `POOR_READABILITY`
- `UNREADABLE`
- `UNCERTAIN`
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
