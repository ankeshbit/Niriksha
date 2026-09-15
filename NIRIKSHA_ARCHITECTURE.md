# NiriKsha — System Architecture Reference

**System Name:** NiriKsha (AI-Assisted Legal Metrology Packaged-Commodity Inspection System)  
**Problem Statement:** Smart India Hackathon (SIH) 2026 — Problem Statement 26034  
**Nodal Authority:** Department of Consumer Affairs (DoCA), Ministry of Consumer Affairs, Food & Public Distribution, Government of India  
**Statutory Framework:** Legal Metrology Act, 2009 & Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)  
**Target Architecture:** PostgreSQL-Only (Neon Serverless) + FastAPI Backend + React Native / Expo Native Android App  

---

## 1. High-Level Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                            MOBILE CLIENT (FIELD APPARATUS)                         |
|  Expo 51 / React Native 0.74 / TypeScript 5.3 (Android Native APK & PWA Fallback)  |
|                                                                                   |
|  [Camera / FileSystem]   [NetInfo & Reachability]   [AsyncStorage Draft Vault]    |
|            |                        |                         |                   |
|  (Multi-Slot Capture)      (State Transition)       (Idempotent Local Drafts)     |
|  front / back / side       OFFLINE <-> ONLINE       client_draft_id: UUID         |
+-----------------------------------------------------------------------------------+
                                         │
                 HTTPS / REST JSON (JWT Bearer / Multipart-Form)
                 Dev: 10.0.2.2:8000 (Android) / 127.0.0.1:8000 (Web/iOS)
                                         ▼
+-----------------------------------------------------------------------------------+
|                                FASTAPI APPLICATION CORE                           |
|                       Uvicorn Server / Starlette Middleware Stack                  |
|                                                                                   |
|  [CORS Middleware] ──────> [OAuth2 / JWT RBAC] ──────> [Global Exception Handler] |
|                                   │                                               |
|                    Role: INSPECTOR | SUPERVISOR | ADMIN                           |
+-----------------------------------------------------------------------------------+
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
+───────────────────+          +───────────────────+          +───────────────────+
|   ROUTER LAYER    |          |   SERVICES LAYER  |          | ANALYTICAL ENGINES|
|                   |          |                   |          |                   |
| /api/auth/*       |          | auth_service.py   |          | ocr_service.py    |
| /api/dashboard/*  |          | image_quality.py  |          |  PaddleOCR 3.x    |
| /api/inspections/*| ───────> | extraction_service| ───────> |  Tesseract OCR    |
| /api/images/*     |          | listing_service.py|          | rule_engine/      |
| /api/findings/*   |          | report_service.py |          |  engine.py (PCR)  |
| /api/reports/*    |          | font_size_service |          | font_size_service |
| /api/supervisor/* |          | readability_serv. |          | readability_serv. |
+───────────────────+          +───────────────────+          +───────────────────+
        │                                │                                │
        └────────────────────────────────┼────────────────────────────────┘
                                         ▼
+-----------------------------------------------------------------------------------+
|                            PERSISTENCE & STORAGE TIER                             |
|                                                                                   |
|  SQLAlchemy 2.0 ORM Engine  ───> Connection Pool (pool_pre_ping=True, recycle=300) |
|                                             │                                     |
|                                             ▼                                     |
|                  NEON POSTGRESQL CLUSTER (AWS us-east-2 / neondb)                 |
|                      postgresql+psycopg:// (psycopg v3 driver)                     |
|                                                                                   |
|  [users]                   [inspections]              [products]                  |
|  [product_images]          [ocr_results]              [declarations]              |
|  [rule_versions]           [compliance_checks]        [evidence]                  |
|  [inspector_reviews]       [reports]                  [audit_logs]                |
|  [product_listings]        [listing_comparisons]      [inspection_number_counters]|
|                                                                                   |
|  Local Media Artifacts:                                                           |
|    - uploads/              (Raw package photographs & bounding-box crops)        |
|    - generated_reports/    (SHA-256 sealed statutory ReportLab PDFs & DOCX files) |
+-----------------------------------------------------------------------------------+
```

---

## 2. Core Architectural Subsystems

### 2.1 Optical & Spatial Metrology Pipeline

```
[Package Image File] (JPEG / PNG)
       │
       ▼
[Image Quality Pre-Check] ──> BlurDetection2 / Laplacian Variance (Score >= 150 = PASS)
       │                      Resolution normalization (800px max analysis width)
       ▼
[Modular OCR Coordinator]
       ├──> Primary: PaddleOCR 3.x Engine (Singleton, Warmup amortized at startup)
       │        Textline orientation detection, polygon -> [x1,y1,x2,y2] mapping
       ├──> Secondary Fallback: Tesseract OCR (Pytesseract binary auto-discovery)
       └──> Fallback Segmenter: Morphological OpenCV (Detects boxes, NEVER manufactures text)
       │
       ▼
[Raw OCR Normalization] ──> Unicode NFKC, dash/quote standardization, line whitespace
       │
       ▼
[PP-Structure Layout Analysis] ──> Identifies regions: Title, Table, Address, Care, Price
       │
       ▼
[Deterministic Regex Extractor] ──> Extracts 8 statutory declaration fields:
       │    1. commodity_name
       │    2. manufacturer_details
       │    3. net_quantity
       │    4. mrp
       │    5. date_of_manufacture_packing
       │    6. consumer_care_details
       │    7. country_of_origin
       │    8. unit_sale_price
       │
       ▼
[Cross-Image Verification] ──> Compares declarations across front, back, and side views:
       │    - Agrees across views -> EXTRACTED (high confidence)
       │    - Disagrees across views (>=0.85 conf) -> CONFLICTING (flags for officer review)
       │    - Low confidence across all views -> LOW_CONFIDENCE (routes to manual verification)
       ▼
[Declarations Stored in PostgreSQL]
```

---

### 2.2 Analytical Metrology & ML Pipeline

```
[Extracted Declaration + Genuine Bounding Box + Source Image Crop]
       │
       ├─────────────────────────────────┬─────────────────────────────────┐
       ▼                                 ▼                                 ▼
[Declaration Readability]        [Placement Analysis]              [Font Size & Numeral Height]
readability_service.py           placement_service.py              font_size_service.py
       │                                 │                                 │
Crop Laplacian Variance          Principal Display Panel (PDP)     Genuine OCR bounding-box
Michelson & RMS Contrast         vs. Information Panel             pixel height measurement
LogisticRegression ML Model      Rules 6, 7 & 12 classification    GradientBoostingRegressor ML
(readability_model.joblib)       front -> PDP (Net Qty, Name)      (font_size_model.joblib)
       │                         back/side -> Info Panel                   │
       ▼                                 ▼                                 ▼
READABLE / UNCERTAIN /           PLACEMENT_COMPLIANT /             Table 1 under Rule 9 check:
MANUAL_VERIFICATION_REQ          PLACEMENT_NON_COMPLIANT /         <=50g: 1mm | 50-200g: 2mm
                                 MANUAL_VERIFICATION_REQ           200-1000g: 4mm | >1kg: 6mm
                                                                   IF UNCALIBRATED:
                                                                   FONT_SIZE_UNDETERMINABLE
       │                                 │                                 │
       └─────────────────────────────────┼─────────────────────────────────┘
                                         ▼
                 [Unified Declaration Validation Matrix]
                 Stored in declarations.validation_matrix_json:
                 | Declaration | Present | Correct | Readable | Placement | Font Size | Format | Status |
```

---

### 2.3 Deterministic Legal Metrology Rule Engine

```
[Effective Declarations] (Officer corrections take precedence over raw OCR)
       │
       ▼
[DeterministicRuleEngine] (backend/rule_engine/engine.py)
       │
       │ Iterates across 12 statutory PCR 2011 rule versions:
       │  - PCR_RULE_06_1_E (MRP & Tax Qualifier)
       │  - PCR_RULE_06_1_A (Manufacturer / Packer / Importer Complete Address)
       │  - PCR_RULE_06_1_C (Net Quantity in Standard SI Metric Units)
       │  - PCR_RULE_06_1_D (Month & Year of Manufacture / Packing)
       │  - PCR_RULE_06_1_G (Consumer Care Phone / Email / Address)
       │  - PCR_RULE_06_1_F (Generic / Common Commodity Name)
       │  - PCR_RULE_06_1_B (Country of Origin - Domestic vs Import)
       │  - PCR_RULE_UNIT_SALE_PRICE (Unit Sale Price - GSR 779(E))
       │  - DATA_QUAL_PHONE_SYNTAX (10-digit / 1800 syntax)
       │  - DATA_QUAL_DATE_PLAUSIBILITY (Chronological / Future-date check)
       │  - PCR_RULE_06_10_ECOMMERCE_DECLARATION (Online Mandatory Display)
       │  - PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING (Online Price > Package MRP)
       │
       ▼
[Evaluation Outcomes per Rule]:
       ├── PASS                         -> Statutory requirement satisfied
       ├── POTENTIAL_NON_COMPLIANCE     -> Concrete missing/non-compliant declaration
       ├── INSUFFICIENT_EVIDENCE        -> Image blurred / OCR unreadable
       ├── NEEDS_MANUAL_VERIFICATION    -> Cross-image conflict / missing origin on unverified commodity
       └── NOT_APPLICABLE               -> Rule does not apply to this commodity/mode
       │
       ▼
[ComplianceChecks Created in Database]
Each non-pass finding generates an immutable Evidence record linking photographic crop + reason.
Status: adjudication_status = "PENDING"
```

---

### 2.4 Human-in-the-Loop Adjudication & Statutory Report Sealing

```
[Compliance Checks: PENDING]
       │
       ▼
[Inspecting Officer Adjudication Screen]
Officer inspects evidence crop and executes one of 4 statutory decisions:
       ├── CONFIRMED            -> Validates violation; transitions finding to CONFIRMED
       ├── DISMISSED            -> Overrules system finding with mandatory statutory justification
       ├── CORRECTED            -> Corrects extracted value; auto-re-evaluates dependent rules
       └── NOT_APPLICABLE       -> Marks requirement legally exempt for this product
       │
       ▼
[Finalization Gate]
POST /api/inspections/{id}/finalize
Pre-condition: Zero findings with adjudication_status == 'PENDING'
       │
       ├── If any PENDING -> HTTP 400 Bad Request (Blocks report generation)
       └── All RESOLVED   -> Overall Status computed:
                             - NO_POTENTIAL_VIOLATIONS (all PASS or DISMISSED/NOT_APPLICABLE)
                             - POTENTIAL_NON_COMPLIANCE (at least one CONFIRMED)
                             - INSUFFICIENT_EVIDENCE
       │
       ▼
[Statutory Report Generation]
ReportLab multi-page A4 PDF generated:
  1. Header & Official Ministry Emblem
  2. Inspection Metadata & Officer Identity
  3. Product & Commodity Identification
  4. Packaging Panel Images Plate
  5. Sealed Declarations Table
  6. Multi-dimensional Compliance Matrix
  7. Adjudicated Findings & Legal References
  8. Photographic Evidence Bounding-Box Crops
  9. Statutory Disclaimer (Rule 19 Physical Limitation)
  10. Inspecting Officer Cryptographic Sign-Off Box
       │
       ▼
[Cryptographic Sealing]
SHA-256 digest calculated over exact PDF binary -> saved in reports.pdf_hash.
Stored immutably on disk at generated_reports/LM_Report_{inspection_number}_v{version}.pdf.
Editable DOCX mirror generated via python-docx.
```

---

### 2.5 Offline Resilience & Sync Architecture

```
[Field Inspector Device (Offline in Warehouse / Rural Market)]
       │
       ├── 1. Inspector enters product details & location in NewInspectionScreen
       ├── 2. AsyncStorage stores draft with client_draft_id = "draft-UUID"
       ├── 3. Native camera captures front, back, side panels
       ├── 4. Local on-device image quality assessment runs
       └── 5. Draft status = READY_FOR_SYNC
       │
       ▼
[Network Restoration: NetInfo detects ONLINE state]
       │
       ▼
[Automatic Sync Engine (syncService.ts)]
       ├── Step 1: POST /api/inspections with client_draft_id
       │           (Backend checks client_draft_id index; if exists, returns existing inspection - NO DUPLICATES)
       ├── Step 2: Upload images one-by-one via POST /api/inspections/{id}/images
       │           (If ANY image fails: sync aborts, rolls back to READY_FOR_SYNC, local images preserved)
       ├── Step 3: Once ALL images confirmed -> Trigger POST /api/inspections/{id}/ocr
       └── Step 4: UI transitions to AnalyzingScreen -> ExtractedDeclarationsScreen
```

---

### 2.6 Supervisor Management & Audit Subsystem

```
[Supervisor / Admin Officer (Role: SUPERVISOR or ADMIN)]
       │
       ├── GET /api/supervisor/dashboard
       │     Aggregates real-time compliance rate, total scans, pending reviews,
       │     inspector active roster, and violation distributions across jurisdiction.
       │
       ├── GET /api/supervisor/inspections
       │     Jurisdiction-wide 18-attribute dossier of all inspections with
       │     full filtering (inspector, status, date, location, compliance).
       │
       ├── GET /api/supervisor/inspectors
       │     Performance metrics, total inspections, violation detection rates,
       │     and last login timestamps per field officer.
       │
       ├── DELETE /api/inspections/{id}/report  [SUPERVISORY ACTION]
       │     Requires { "confirm": true, "reason": "..." }
       │     Deletes PDF and DOCX disk files and database record.
       │     Inspection reverts to ANALYSIS_COMPLETE.
       │     Surviving immutable audit log recorded in audit_logs.
       │
       └── DELETE /api/inspections/{id}         [SUPERVISORY DESTRUCTIVE ACTION]
             Requires { "confirm": true, "reason": "..." }
             Performs complete atomic cascade deletion:
             evidence -> compliance_checks -> declarations -> ocr_results ->
             product_images (unlinks disk files) -> product -> report -> inspection.
             Audit trail survives with inspection_id = NULL.
```

---

## 3. Data Flow and Source-of-Truth Hierarchy

| Data Domain | Runtime Authority / Storage | Client-Side Mirror | Synchronization Mechanism |
|---|---|---|---|
| **User Identity & Roles** | PostgreSQL `users` table | AsyncStorage `auth_token`, `auth_user` | JWT Bearer token decoded on backend; fetched on login & profile refresh |
| **Inspection Metadata** | PostgreSQL `inspections` table | React Native navigation params & local state | REST JSON via `/api/inspections/{id}` |
| **Unsynced Field Drafts** | AsyncStorage `legal_metrology_offline_drafts_v1` | AsyncStorage primary | `syncService.ts` idempotent push upon network reachability |
| **Package Label Images** | Server filesystem `./uploads/{id}_{slot}.jpg` + PostgreSQL `product_images` | Camera local cache URIs | Multipart form POST per slot; local file deleted after confirmed upload |
| **OCR Raw Transcripts** | PostgreSQL `ocr_results` (immutable baseline) | React state in `ExtractedDeclarationsScreen` | Generated by `/api/inspections/{id}/ocr` |
| **Declarations** | PostgreSQL `declarations` table | React state + editable modal | Server authoritative; patches sent via `PATCH /api/declarations/{id}` |
| **Statutory Rules** | Python registry `STATUTORY_RULE_REGISTRY` + DB `rule_versions` | Frontend static labels | Version-pinned rule execution in deterministic engine |
| **Compliance Checks** | PostgreSQL `compliance_checks` table | React state in `FindingsScreen` | Created by rule engine; updated by `/adjudicate` endpoints |
| **Adjudication Decisions** | PostgreSQL `compliance_checks` & `inspector_reviews` | React state | Server authoritative; finalization blocks on pending findings |
| **Inspection Reports** | Filesystem `./generated_reports/` + PostgreSQL `reports` (SHA-256 sealed) | Downloaded PDF blob / viewer | Generated once per finalized inspection; immutable against tampering |
| **Audit Logs** | PostgreSQL `audit_logs` table (write-only append log) | Supervisor screens | Emitted on every significant state transition and deletion |
