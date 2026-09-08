# NiriKsha Current Project Functionality Audit

## 1. Audit Scope

This audit is a strict, independent functionality and reliability evaluation of the **CURRENT NiriKsha codebase** as it exists in the repository today.

> [!IMPORTANT]
> **Audit Baseline Invariant**: This audit evaluates the existing implementation **exclusively against the ORIGINAL project requirements / PRD** (Smart India Hackathon 2026 Problem Statement 26034 for the Department of Consumer Affairs, DoCA). It explicitly **DOES NOT** evaluate against the newly updated PRD, nor does it evaluate future features such as e-commerce web crawlers, nationwide cloud databases, barcode scanning systems, or microservice architectures.

**Strict Audit Rules Observed:**
- **Zero code changes**: No source files, configurations, database records, or tests were modified or patched during this audit.
- **Brutal honesty**: Features are evaluated on whether they actually work reliably under real operational conditions, not merely whether code files or function signatures exist.
- **Classification criteria**: Every finding is categorized by severity (`P0` through `P4`) and status (`WORKING`, `PARTIALLY WORKING`, `BROKEN`, `MISSING`, `INCORRECT`, `UNRELIABLE`, `DATA LEAKAGE`, `SECURITY ISSUE`, `PERFORMANCE ISSUE`, `UI/UX ISSUE`, `PRD MISMATCH`, or `NOT VERIFIED`).

---

## 2. Original Requirements Used

The audit baseline was established by identifying the original project requirements document in the repository:

- **Baseline Document**: `docs/prd/Legal_Metrology_MVP_PRD.docx` (and its verbatim text extraction [extracted_prd.txt](file:///c:/Users/ankes/OneDrive/Desktop/SIH/docs/prd/extracted_prd.txt)).
- **Title**: *AI-Assisted Legal Metrology Packaged-Commodity Inspection System — Simplified Product Requirements Document (MVP)*.
- **Hackathon & Challenge Context**: Smart India Hackathon (SIH) 2026 • Problem Statement ID: 26034.
- **Authority / Client**: Ministry of Consumer Affairs, Food & Public Distribution — Department of Consumer Affairs (DoCA).
- **Core Stated Vision (Section 1 & 2)**: An AI-assisted decision-support tool helping enforcement officers inspect packaged commodities against the Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011).
- **Core Principle**: AI detects and assists; deterministic statutory rules evaluate; photographic evidence supports; human inspectors make all final legal decisions.

---

## 3. Current System Architecture

The current implemented codebase comprises:

1. **Client Layer (Mobile & Web)**:
   - **Framework**: React Native 0.74.5 with Expo SDK ~51.0.28 and TypeScript 5.3.3.
   - **Target Platforms**: Android APK standalone build, iOS support, and React Native for Web (`react-native-web` 0.19.13).
   - **Navigation**: React Navigation Native Stack v6 (`@react-navigation/native-stack`).
   - **Screens (13 screens)**: Login, Dashboard, New Inspection, Capture Images, Analyzing, Extracted Declarations, Findings, Evidence Review, Review & Submit, Report Preview, Reports List Archive, Profile, and Offline Drafts.
   - **On-Device Image Quality Module**: Kotlin-based native bridge `ImageQualityModule.kt` implementing OpenCV-equivalent integer Laplacian variance convolution ($kernel = [0, 1, 0; 1, -4, 1; 0, 1, 0]$) with pure TypeScript fallback for Web.

2. **Backend REST API Layer**:
   - **Framework**: Python 3.10 + FastAPI + Uvicorn.
   - **Database**: SQLite database (`legal_metrology.db`) via SQLAlchemy ORM, with optional Supabase PostgreSQL compatibility switch via environment variable `DATABASE_URL`.
   - **Authentication**: JWT token-based authentication (HS256) with role-based access control (`INSPECTOR`, `ADMIN`).

3. **Core Services**:
   - **Image Quality Assessment**: OpenCV Laplacian variance blur detection, luminance percentile glare estimation, and resolution gating.
   - **Modular OCR**: Coordinator `ModularOCRService` wrapping `TesseractOCREngine` (Pytesseract with auto-discovery of binary paths) and OpenCV morphological bounding box segmentation `MorphologicalOpenCVOCREngine`.
   - **Declaration Extraction**: `DeterministicRegexExtractor` extracting 7 statutory declarations (Rule 6(1)) plus Country of Origin, with fallback LLM hook.
   - **Statutory Rule Engine**: `DeterministicRuleEngine` evaluating 7 Category A Legal rules and 2 Category B Data Quality rules without non-deterministic AI variance.
   - **Human Adjudication Gate**: 5 officer actions (`CONFIRM`, `DISMISS`, `CORRECT`, `NEEDS_MORE_EVIDENCE`, `NOT_APPLICABLE`), with HTTP 409 gating blocking report compilation on unresolved findings.
   - **Report Generator**: ReportLab statutory PDF compilation incorporating product metadata, declarations table, image quality audit, adjudication decisions, and statutory disclaimers.

4. **Storage & Offline Infrastructure**:
   - Local disk directories `uploads/inspections/` and `generated_reports/`.
   - Client-side offline draft management via `draftStorage.ts` (SecureStore on mobile, localStorage on Web).
   - Reactive and proactive network synchronization via `networkService.ts` and `syncService.ts`.

---

## 4. Executive Summary

| Category | Status | Summary Evaluation |
|---|---|---|
| **Core Workflow (Happy Path)** | **WORKING** | End-to-end pipeline (Login → New Inspection → Capture → Image Quality → OCR → Extraction → Rules → Adjudication → Finalize → PDF Report) functions correctly when input data conforms to expected patterns. |
| **Statutory Rule Engine** | **WORKING** | All 7 Category A Legal rules and 2 Category B Data Quality rules evaluate deterministically without AI hallucinations. |
| **Unresolved Findings Gate** | **WORKING** | Backend reliably blocks report generation with HTTP 409 Conflict if potential violations remain unadjudicated. |
| **Report Immutability** | **WORKING** | Reports cannot be deleted via API; no DELETE endpoints exist for reports or inspections. |
| **Automated Test Suite** | **BROKEN (Collection)** | Running `pytest -v` out-of-the-box fails during collection because `tests/test_ocr_production.py` imports functions removed during recent refactoring (`find_tesseract_binary`). When ignored, 231 of 232 tests pass. |
| **Mobile Automated Tests** | **BROKEN** | `npm test` fails with `Missing script: "test"`. Unit tests in `mobile/src/screens/__tests__/` cannot be executed via npm. |
| **Finalized Image Deletion** | **SECURITY / DATA INTEGRITY RISK** | `DELETE /api/images/{image_id}` allows deleting photographic evidence even after an inspection is finalized with a legal report. |
| **Android Network Brittleness** | **UNRELIABLE** | Android API host hardcodes developer LAN IP `10.185.115.213:8000`, which fails if the network changes or when tested on standard Android Emulators (`10.0.2.2`). |
| **UI Polling Overhead** | **PERFORMANCE RISK** | Active dashboard and report archive screens poll the backend every 3–4 seconds with unthrottled multiple API requests. |
| **Web Location Fallback** | **UI/UX DEFECT** | "Use Current Location" on Web detects GPS coordinates but alerts the user to type manually without populating the field. |
| **Database Cleanliness** | **DATA LEAKAGE** | `legal_metrology.db` contains leftover test inspections (`hvhv`, `sdfsd`, `dscdscd`), and `generated_reports/` contains hundreds of test PDFs. |

---

## 5. Complete Defect List

| ID | Severity | Category | Feature | Status | Problem | Expected | Actual | Evidence | Reproduction |
|---|---|---|---|---|---|---|---|---|---|
| **DEF-01** | **P1** | Automated Testing | Test Suite Execution | **BROKEN** | `pytest -v` crashes on collection with `ImportError` in `test_ocr_production.py`. | Entire test suite collects and runs clean out-of-the-box. | Collection terminates immediately with exit code 1; no tests execute unless explicitly ignored. | [test_ocr_production.py:10](file:///c:/Users/ankes/OneDrive/Desktop/SIH/tests/test_ocr_production.py#L10) | Run `.\venv\Scripts\pytest -v` from project root. |
| **DEF-02** | **P1** | Security / Data Integrity | Image Management | **BROKEN** | `DELETE /api/images/{image_id}` lacks check for inspection status; allows deleting photographic evidence from finalized inspections. | Deleting images of finalized inspections with generated reports must be blocked with HTTP 400 or 409. | Image record and file on disk are deleted; leaves official report referencing non-existent image evidence. | [main.py:821-853](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L821-L853) | Finalize an inspection, then issue `DELETE /api/images/{image_id}` with valid officer token. |
| **DEF-03** | **P1** | Mobile / Build | API Connectivity | **UNRELIABLE** | Android defaults to static hardcoded LAN IP `http://10.185.115.213:8000`. | Dynamic IP discovery, emulator loopback detection (`10.0.2.2`), or runtime configuration modal. | Android APK fails to connect if PC IP changes or when launched in standard emulator. | [api.ts:5, 35](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/services/api.ts#L5) | Run APK on an emulator or Wi-Fi network with different subnet. |
| **DEF-04** | **P2** | Mobile Testing | Test Infrastructure | **MISSING** | `npm test` fails with `npm error Missing script: "test"`. | Configured test runner (Jest) executing screen tests in `mobile/src/screens/__tests__/`. | 4 test files exist in `mobile/src/screens/__tests__/` but cannot be executed by npm scripts. | [package.json:5-11](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/package.json#L5-L11) | Run `npm --prefix mobile test`. |
| **DEF-05** | **P2** | Authentication | Session Management | **MISSING** | `POST /api/auth/logout` endpoint does not exist (returns 404). | Dedicated server-side logout route handling token invalidation or audit logging. | Logout is strictly client-side token deletion; server has no knowledge of logout. | [audit_auth.py:53](file:///C:/Users/ankes/.gemini/antigravity-ide/brain/2aaa087d-277a-4d15-968d-c6f49794b6ae/scratch/audit_auth.py) | Issue `POST /api/auth/logout` with Bearer token. |
| **DEF-06** | **P2** | Performance / Mobile | Real-time Synchronization | **PERFORMANCE ISSUE** | Aggressive continuous interval polling (every 3s on Dashboard, every 4s on ReportsList). | Focused refresh, WebSocket, long polling, or throttled periodic sync (e.g. 30–60s). | Constant background network requests drain battery and saturate server on multi-device deployments. | [DashboardScreen.tsx:145](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/DashboardScreen.tsx#L145), [ReportsListScreen.tsx:96](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ReportsListScreen.tsx#L96) | Open Dashboard on mobile while monitoring backend access logs. |
| **DEF-07** | **P2** | OCR / Extraction | Date & Name Extraction | **PARTIALLY WORKING** | OCR character substitutions (e.g., "MED" for "MFD") or package titles ("NUTRITIONAL FACTS") cause false `NOT_FOUND` or wrong commodity name. | Fault-tolerant fuzzy matching for standard acronyms ("MFD", "PKD", "MED") and layout-aware commodity name filtering. | Common packaging font variations fail regex extraction, forcing unnecessary manual corrections. | [extraction_service.py:165](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/extraction_service.py#L165) | Run OCR extraction on `imported_product_package.jpg` containing "MED / IMPORT DATE: 04/2026". |
| **DEF-08** | **P2** | Database Design | Schema Normalization | **INCORRECT** | `client_draft_id` is stored embedded inside user-facing `notes` text column instead of a dedicated indexed column. | Dedicated `client_draft_id` column with unique index on `inspections` table. | String manipulation `[client_draft_id:...]` pollutes inspection notes and relies on substring queries. | [main.py:516, 544](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L516) | Inspect `notes` column in `inspections` table. |
| **DEF-09** | **P2** | Security | Configuration | **SECURITY ISSUE** | Hardcoded development `SECRET_KEY` in `.env`. | Enforced secret generation or startup rejection if default secret is detected in production. | Insecure secret allows forging HS256 JWT tokens if deployed with `.env` defaults. | [.env:10](file:///c:/Users/ankes/OneDrive/Desktop/SIH/.env#L10) | View `SECRET_KEY` in `.env`. |
| **DEF-10** | **P3** | UI / Navigation | Web Location | **UI/UX ISSUE** | "Use Current Location" on Web acquires coordinates but alerts user to type manually, leaving input blank. | Populate location field with readable address or formatted lat/long coordinates. | Field remains blank; user must manually re-type location despite granting browser permission. | [NewInspectionScreen.tsx:219-225](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/NewInspectionScreen.tsx#L219-L225) | Click "Use Current Location" in Web app. |
| **DEF-11** | **P3** | UI / Report Preview | Data Binding | **INCORRECT** | `ReportPreviewScreen.tsx` references `report?.report_number`, which does not exist in backend schema. | Correct field reference matching backend schema (`report?.inspection_number` or `report?.report_version`). | Evaluates to `undefined`, silently falling back to `inspectionNumber` or `'LM-2026'`. | [ReportPreviewScreen.tsx:58](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ReportPreviewScreen.tsx#L58) | Inspect filename generated in `handleSharePdf`. |
| **DEF-12** | **P3** | Architecture / Stitch | Static Web Portal | **PARTIALLY WORKING** | Static `/stitch` routes return 404 because `stitch_screens/code/` directory is missing from repository. | Stitch HTML screens served or code cleaned up if superseded by React Native Web. | Test `test_all_13_stitch_screens_exist_and_render` is skipped; static portal routes are dead. | [test_foundation.py:84](file:///c:/Users/ankes/OneDrive/Desktop/SIH/tests/test_foundation.py#L84), [main.py:113](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L113) | Navigate to `http://localhost:8000/stitch/code/01_login.html`. |
| **DEF-13** | **P3** | Database / Filesystem | Test Hygiene | **DATA LEAKAGE** | Hundreds of automated test PDFs left in `generated_reports/`, and dummy rows (`hvhv`, `sdfsd`) in `legal_metrology.db`. | Dedicated temporary test directory for test artifacts; clean demo database. | Production `generated_reports/` directory contains 200+ test files; `legal_metrology.db` contains test clutter. | [inspect_db.py output](file:///C:/Users/ankes/.gemini/antigravity-ide/brain/2aaa087d-277a-4d15-968d-c6f49794b6ae/scratch/inspect_db.py) | List `generated_reports/` directory contents. |
| **DEF-14** | **P4** | Code Quality | Models Definition | **COSMETIC** | Duplicate return statement in `Report.download_url` property in `backend/models.py`. | Single clean return statement. | Redundant unreachable return statement on line 266. | [models.py:265-266](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/models.py#L265-L266) | Inspect lines 264-266 of `backend/models.py`. |

---

## 6. Backend Problems

1. **Unprotected Image Deletion on Finalized Records (`DELETE /api/images/{image_id}`)**:
   - In [main.py:821-853](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L821-L853), the handler checks only if the user owns the image or is an admin.
   - It **does not check** `img.inspection.status == "COMPLETED"`.
   - An officer can delete uploaded label imagery after finalization, leaving an official inspection certificate referencing deleted evidence files.

2. **Absence of Server-Side Logout Endpoint**:
   - The FastAPI router has no route for `POST /api/auth/logout`.
   - Any client calling this endpoint receives HTTP 404 Not Found. While JWT tokens are inherently stateless, standard security architectures provide a blacklist or at minimum an audit log event marking session termination.

3. **Sub-optimal Client Draft ID Indexing in Database**:
   - `client_draft_id` is embedded into the `notes` column as `[client_draft_id:<UUID>]`.
   - In `_fetch_existing_draft()`, the query runs a `LIKE %...%` query across freeform notes:
     ```python
     db.query(Inspection).filter(
         Inspection.inspector_id == user_id,
         Inspection.notes.contains(draft_marker)
     ).first()
     ```
   - This prevents indexing and risks false collisions if an officer types that exact marker string in manual notes.

4. **Static Stitch Directory Missing**:
   - Lines 113–115 in `main.py` attempt to mount `BASE_DIR / "stitch_screens"`. Because this directory does not exist in the repository, any request to `/stitch/...` fails.

---

## 7. Mobile Problems

1. **Hardcoded IP Address in Production Configuration**:
   - In [mobile/src/services/api.ts:5](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/services/api.ts#L5), `PC_LAN_API_HOST` is hardcoded to `'http://10.185.115.213:8000'`.
   - Line 35 defaults `Platform.OS === 'android'` to this hardcoded IP.
   - When deploying to an Android physical device on another network, or on an Android emulator (which routes to host via `10.0.2.2`), network calls fail immediately unless `EXPO_PUBLIC_API_URL` was baked in at build time.

2. **Battery & Network Drain via Unthrottled Polling**:
   - In `DashboardScreen.tsx` ([line 145](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/DashboardScreen.tsx#L145)), `useFocusEffect` registers a `setInterval` firing `loadData(true)` every **3000 milliseconds**. Each iteration fires 3 asynchronous API calls (`getProfile`, `getDashboard`, `listInspections(limit=100)`).
   - In `ReportsListScreen.tsx` ([line 96](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ReportsListScreen.tsx#L96)), `setInterval` fires `loadReports(true)` every **4000 milliseconds**.
   - This results in ~80 requests per minute when simply looking at the dashboard.

3. **Web Location Reverse Geocoding Omission**:
   - In `NewInspectionScreen.tsx` ([lines 202-239](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/NewInspectionScreen.tsx#L202-L239)), on Web, the code obtains coordinates via `navigator.geolocation`, then comments:
     `Reverse geocoding: skipped on Web (Geocoding API removed in SDK 49)`
     and alerts "Current location detected. Please enter the location manually."
   - The user must manually type the location despite giving permission.

4. **Schema Field Mismatch in Report Preview**:
   - In `ReportPreviewScreen.tsx` ([line 58](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ReportPreviewScreen.tsx#L58)), the PDF sharing filename uses `report?.report_number`. The backend schema returns `report_version` and `inspection_number`, but no `report_number`.

---

## 8. OCR / AI Problems

1. **Rigid Regex Matching Sensitive to Single-Character OCR Misrecognitions**:
   - Live testing against `tests/fixtures/imported_product_package.jpg` revealed:
     Tesseract extracted: `'MED / IMPORT DATE: 04/2026'` (interpreting `MFD` as `MED`).
   - The regex in `extraction_service.py`:
     ```python
     r'(?:mfd|pkg|packed|mfg|manufactured|date)\s*[:\.]?\s*(\d{1,2}[\/\-\.]\d{2,4})'
     ```
     does not recognize `MED`. Consequently, date extraction yielded `NOT_FOUND` on a label where the date was clearly printed.

2. **Header Pollution in Commodity Name Extraction**:
   - On packaging where nutritional facts or marketing slogans appear above the commodity title, the regex heuristic extracts the first bold uppercase block:
     On `scripts/real_images/real_package_back.jpg`, it extracted `'NUTRITIONAL FACTS & DETAILS'` as the `commodity_name`.

3. **Em-Dash Failure in Telephone Extraction**:
   - Indian toll-free phone numbers printed with typographical dashes (e.g. `1800—200—1122`) fail the phone regex `r'(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4})'`.
   - In our live audit test on `real_package_back.jpg`, the phone was missed and only the email `@sunshine.in` was captured.

4. **Absence of Multilingual / Hindi OCR**:
   - While the original PRD mentioned Hindi as an optional/secondary language, the current Tesseract configuration runs exclusively with English trained data (`eng.traineddata` in `backend/tessdata`). Hindi text on packaged commodities cannot be read by the current OCR engine.

---

## 9. Image Processing Problems

1. **Blur Detection Algorithm Execution**:
   - **Verification**: VERIFIED WORKING.
   - The Laplacian variance blur detection algorithm accurately calculates sharpness:
     - Clear fixture (`clear_package.jpg`): Mean confidence 0.94, sharpness > 250 (Status: `GOOD`).
     - Blurry fixture (`blurry_package.jpg`): 0 text boxes, sharpness < 50 (Status: `POOR` / Warning).
   - On Android, the native module `ImageQualityModule.kt` matches the OpenCV algorithm.

2. **Resolution Downscaling Invariant**:
   - The system strictly downscales only when width > 800px and never upscales small images, preserving sharpness ratios.

---

## 10. Rule Engine Problems

1. **Statutory Coverage**:
   - The rule engine correctly codifies 7 Category A Legal rules under PCR 2011 Rule 6(1) and 2 Category B Data Quality rules.
   - Rule versioning (`version_number = 1`) and statutory citations are strictly preserved.

2. **Missing Rule Engine Capabilities from Original PRD**:
   - In original PRD Section 12 (FR-18), an administrative interface to toggle/disable individual rules was specified (`P2`).
   - While rules can be retrieved via `GET /api/rules`, there is no API endpoint or UI allowing supervisors to enable, disable, or adjust thresholds for statutory rules at runtime.

---

## 11. Findings / Review Problems

1. **Adjudication Actions**:
   - Supported actions: `CONFIRM`, `DISMISS`, `CORRECT`, `NEEDS_MORE_EVIDENCE`, `NOT_APPLICABLE`.
   - All 5 actions execute deterministically on the backend and persist to `InspectorReview` and `AuditLog`.

2. **Re-evaluation on New Image Request**:
   - Original PRD acceptance criterion 612 specifies: "Requesting a new image causes the finding to be re-evaluated."
   - In the current implementation, `POST /api/findings/{finding_id}/request-new-image` sets `adjudication_status = "NEEDS_MORE_EVIDENCE"`. It retains the finding in an unresolved state, but does not automatically invalidate or re-trigger the OCR pipeline when a replacement image is uploaded. The inspector must manually re-trigger the analysis.

---

## 12. Report Problems

1. **Verification of Dynamic Content vs Hardcoded Values**:
   - Audited [report_service.py](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/report_service.py): All displayed fields (commodity name, brand, inspector name, zone, location, declarations, findings, decisions) bind dynamically to database entities.
   - No hardcoded demo values ("Premium Basmati Rice", "Agro Foods", "LM-2026-00001") are hardcoded into PDF output.

2. **Fallback Strings in PDF Generator**:
   - In `report_service.py` lines 147–150:
     ```python
     officer_name = getattr(inspector, "full_name", "Inspector Rajesh Kumar")
     officer_id = getattr(inspector, "officer_id", "DOCA-INSP-842")
     ```
     If an inspector record has a `None` attribute, it falls back to demo strings instead of generic placeholders like `"Unknown Officer"`.

---

## 13. Offline / Sync Problems

1. **Draft Creation & Persistence**:
   - Creating a draft while offline saves to client storage without premature network calls.
   - Reconnection automatically triggers background synchronization via `syncService.ts`.

2. **Sync Recovery Under Network Interruption**:
   - If image upload fails midway through a sync, `syncService.ts` rolls back status to `READY_FOR_SYNC`, preserves local image files, and caches `syncedInspectionId` so subsequent retries do not create duplicate inspections.

3. **SecureStore Size Invariant**:
   - Image URIs are stored as file paths (`file://...`), preventing SecureStore storage quota overflow.

---

## 14. Authentication Problems

1. **Token Invalidation on Password Change**:
   - When an officer changes their password via `POST /api/auth/change-password`, previously issued JWT tokens remain valid until expiration (1440 minutes / 24 hours), because tokens are stateless and no token revocation list is maintained.

---

## 15. Database Problems

1. **Production Database Contamination**:
   - In `legal_metrology.db`, inspections `LM-2026-00002`, `LM-2026-00003`, and `LM-2026-00004` contain test data (`hvhv`, `sdfsd`, `dscdscd`, `hjbhb`, `dsf`, `dgdg`) created during development.
   - In accordance with audit instructions, this data was NOT deleted or cleaned.

2. **Foreign Key Integrity**:
   - `PRAGMA foreign_key_check` executed with **0 errors**.
   - Orphaned record check confirmed **0 orphaned records** across products, images, checks, evidence, and reports.

---

## 16. UI / Navigation Problems

1. **Back Navigation After Finalization**:
   - Once an inspection is finalized and the user is redirected to `ReportPreviewScreen`, pressing the Android hardware back button can return to `ReviewAndSubmitScreen`, where pressing Finalize again returns fast-path idempotency, but may confuse field officers expecting to return to the Dashboard.

2. **Missing Empty State Retry on Reports Archive**:
   - The uncommitted modification in `ReportsListScreen.tsx` adds an error state and retry button, but the committed repository version did not provide a dedicated retry trigger when report fetching failed.

---

## 17. Security Problems

1. **Default JWT Secret Key**:
   - `SECRET_KEY` in `.env` is set to a public development string. In production, this allows forging authentication tokens.

2. **CORS Regex Permissiveness**:
   - In `backend/main.py`:
     ```python
     app.add_middleware(CORSMiddleware, allow_origin_regex=r"^https?://.*$", ...)
     ```
     This allows any origin on the web to make authenticated requests to the API if credentials are provided.

---

## 18. Build / Android Problems

1. **Android NDK & SDK Path Configuration**:
   - The project includes local SDK and JDK directories (`android-sdk`, `jdk-17`).
   - The pre-built APK `niriksha-debug.apk` (169 MB) exists and verifies that the Android build pipeline compiles.
   - However, the built APK incorporates the hardcoded IP address `10.185.115.213:8000`, making it non-functional when tested on networks with different addressing.

---

## 19. Hardcoded / Mock / Demo Data Problems

| Location | String / Value | Classification | Production Impact |
|---|---|---|---|
| `backend/seed_demo_inspection.py` | `LM-2026-00001`, `Azadpur Wholesale Mandi` | **SAFE (Standalone Script)** | Only runs when manually invoked as a standalone script. |
| `backend/report_service.py:147` | `Inspector Rajesh Kumar`, `DOCA-INSP-842` | **RISK (Fallback String)** | Leaks demo name if `inspector.full_name` is null. |
| `mobile/src/screens/NewInspectionScreen.tsx:590` | `e.g. Premium Basmati Rice`, `e.g. Agro Foods` | **SAFE (UI Placeholder)** | Standard input placeholder text (`placeholder="..."`). |
| `mobile/src/screens/ReportPreviewScreen.tsx:58` | `LM-2026` | **SAFE (Filename Fallback)** | Fallback filename if metadata is null. |
| `legal_metrology.db` | `LM-2026-00001` (`Himalayan Organic Oats`) | **SAFE (Seeded Demo Inspection)** | Single baseline reference record. |

---

## 20. Automated Test Results

### Pytest Backend Test Suite

```
Command: .\venv\Scripts\pytest -v --ignore=tests/test_ocr_production.py
Result: 231 PASSED, 1 SKIPPED, 0 FAILED (466.87s / 7m 46s)
```

- **Collection Error in `tests/test_ocr_production.py`**:
  `ImportError: cannot import name 'find_tesseract_binary' from 'backend.ocr_service'`.
- **Skipped Test**:
  `tests/test_foundation.py::test_all_13_stitch_screens_exist_and_render` (Skipped because `stitch_screens` folder is omitted from repo).
- **Passed Test Modules (231 tests)**:
  - `test_adversarial_regression.py`: 12 passed
  - `test_complete_post_image_workflow.py`: 31 passed
  - `test_e2e_mobile_workflow.py`: 3 passed
  - `test_final_corrections.py`: 8 passed
  - `test_foundation.py`: 4 passed (1 skipped)
  - `test_full_qa_audit.py`: 10 passed
  - `test_last_login.py`: 7 passed
  - `test_location_feature.py`: 13 passed
  - `test_offline_and_idempotency.py`: 6 passed
  - `test_offline_image_quality.py`: 20 passed
  - `test_pdf_unicode_resilience.py`: 3 passed
  - `test_phase2.py`: 7 passed
  - `test_phase3.py`: 6 passed
  - `test_phase4.py`: 8 passed
  - `test_phase5.py`: 11 passed
  - `test_phase6.py`: 16 passed
  - `test_report_immutability.py`: 21 passed
  - `test_system_qa_deep_hunt.py`: 45 passed

### Mobile Frontend TypeScript Check

```
Command: npm --prefix mobile run ts:check
Result: 0 ERRORS (tsc --noEmit passed cleanly)
```

### Mobile Frontend Unit Tests

```
Command: npm --prefix mobile test
Result: FAILED — Missing script: "test"
```

---

## 21. Features That Are Implemented but Not Actually Working

1. **Out-of-the-Box Automated Testing**: Running `pytest` without parameters immediately crashes before executing any tests due to the unhandled `ImportError` in `tests/test_ocr_production.py`.
2. **Static HTML Inspection Portal (`/stitch`)**: Backend mounts `/stitch` to `BASE_DIR / "stitch_screens"`, but the directory is missing, returning 404 for all stitch pages.
3. **Web Location Detection**: Tapping "Use Current Location" on Web detects GPS coordinates, but leaves the location text input blank with an alert instructing the user to type manually.
4. **Standalone APK on Variable Networks**: The pre-built Android APK cannot communicate with the backend on standard local subnets or emulators due to hardcoded LAN IP `10.185.115.213`.

---

## 22. Features That Are Partially Working

1. **OCR Declaration Extraction**: Works on high-contrast, perfectly printed labels matching exact acronyms, but fails when single-character OCR substitutions occur (e.g. `MED` for `MFD`) or when nutritional panel headers precede commodity titles.
2. **Server-Side Logout**: Handled exclusively on client by clearing SecureStore; the backend does not implement `/api/auth/logout`.
3. **Re-imaging Workflow**: Requesting a new image flags the finding as `NEEDS_MORE_EVIDENCE`, but does not automatically re-evaluate the finding upon image replacement without manual re-triggering.

---

## 23. Features That Are Missing From the ORIGINAL Requirements

1. **Admin Rule Configuration API & UI (FR-18, P2)**: The original PRD specified admin controls to enable, disable, and configure individual statutory rules at runtime. Currently, rules are statically defined in Python dictionaries and cannot be enabled/disabled via API.
2. **Full Multilingual Packaging Support**: The original PRD noted Hindi language packaging support. The current OCR pipeline is configured exclusively with English language models.
3. **Dedicated Client Draft ID Database Column**: Idempotency is supported, but implemented via substring search in the freeform `notes` column rather than a dedicated schema column.

---

## 24. Features That Cannot Be Physically Verified

In accordance with strict verification instructions:

- **PHYSICAL ANDROID VERIFIED**: **CANNOT BE PERFORMED**. No physical Android device was connected via ADB (`adb devices` returned 0 devices).
- **EMULATOR VERIFIED**: **CANNOT BE PERFORMED**. No Android emulator instance was running.
- **BUILD VERIFIED**: **YES**. `niriksha-debug.apk` is compiled (169 MB) and TypeScript compilation passed with zero errors (`tsc --noEmit`).
- **WEB VERIFIED**: **YES**. Verified via browser emulation and component analysis.
- **SOURCE CODE VERIFIED**: **YES**. Every module, model, route, service, and algorithm was directly inspected and audited.

---

## 25. Recommended Fix Priority

### P0 (Immediate Blockers)
*None. Core business logic and report gating function without critical data corruption.*

### P1 (Major Operational & Testing Issues)
1. **Fix `tests/test_ocr_production.py` imports**: Update test imports to align with `TesseractOCREngine` and `ModularOCRService` to restore one-command `pytest` test suite execution.
2. **Protect Finalized Inspection Images**: Add `if img.inspection.status == "COMPLETED": raise HTTPException(400)` to `delete_inspection_image` in [main.py:821](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L821).
3. **Dynamic Host Configuration for Android**: Replace static IP `10.185.115.213:8000` with dynamic host resolution or an in-app server settings modal.

### P2 (Moderate Robustness & Performance)
4. **Install Jest & Add `test` Script in `mobile/package.json`**: Enable running the 4 existing mobile unit tests.
5. **Throttle Mobile Polling**: Reduce interval polling on Dashboard and ReportsList from 3–4 seconds to 30–60 seconds, or replace with pull-to-refresh.
6. **Fuzzy OCR Date Acronym Matching**: Expand date regex to accept `MED`, `MFG`, `PKD`, `M/D`.
7. **Implement `POST /api/auth/logout`**: Provide an explicit server-side logout route with audit logging.
8. **Add Dedicated `client_draft_id` Column**: Migrate `client_draft_id` from freeform `notes` text into a dedicated indexed column on `inspections`.

### P3 (Minor UX & Hygiene)
9. **Web Geolocation Auto-Fill**: Auto-fill GPS coordinates into the location input on Web when reverse geocoding is unavailable.
10. **Clean Up Leftover Test Reports**: Ensure test fixtures save PDFs to a temporary scratch directory instead of `generated_reports/`.
11. **Align `ReportResponse` Schema**: Expose `report_number` or update mobile `ReportPreviewScreen.tsx` to use `inspection_number`.

### P4 (Cosmetic)
12. **Remove Duplicate Return Statement**: Remove duplicate `return` line in `backend/models.py:266`.

---

## 26. Final Status

# **NEEDS MINOR FIXES**

### Justification:
The core NiriKsha inspection system **is architecturally sound, adheres faithfully to the original DoCA SIH 2026 PRD principles**, and enforces all key statutory invariants (deterministic rule execution, human-in-the-loop adjudication, unresolved finding gating via HTTP 409, and report immutability). 

However, it **cannot be classified as a RELEASE CANDIDATE** due to:
1. An out-of-the-box broken automated test suite collection (`test_ocr_production.py`).
2. A missing guard allowing image deletion on finalized inspections.
3. A hardcoded LAN IP in the mobile network service that breaks Android out-of-the-box connectivity on standard subnets.
4. Aggressive 3-second UI polling that degrades mobile performance.

Addressing these specific items will immediately elevate the project to **RELEASE CANDIDATE** status.
