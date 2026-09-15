# NiriKsha — Complete REST API Catalog & Reference

**Base URL (Localhost):** `http://127.0.0.1:8000`  
**Base URL (Android Emulator):** `http://10.0.2.2:8000`  
**Authentication Standard:** OAuth2 Bearer JWT Token (`Authorization: Bearer <token>`)  
**Header Requirements:** `Content-Type: application/json` (or `multipart/form-data` for file uploads)  

---

## 1. System Health & Authentication

### GET `/api/health`
- **Auth:** None (Public)
- **Role:** Any
- **Purpose:** Server and database liveness and readiness probe.
- **Request Parameters:** None
- **Request Body:** None
- **Response (200 OK):**
  ```json
  {
    "status": "healthy",
    "timestamp": "2026-09-15T18:54:05.123456Z",
    "version": "1.0.0",
    "environment": "development",
    "database": "connected",
    "database_backend": "PostgreSQL",
    "database_driver": "postgresql+psycopg",
    "database_host": "Neon",
    "is_neon": true,
    "is_sqlite": false,
    "ocr_engine": "paddleocr"
  }
  ```
- **Database Effect:** Executes `SELECT 1` ping against active engine.
- **Errors:** 503 if database connection fails.

---

### POST `/api/auth/login`
- **Auth:** None (Public)
- **Role:** Any
- **Purpose:** Authenticate officer and issue 24-hour signed JWT bearer token.
- **Request Body:**
  ```json
  {
    "officer_id": "DOCA-INSP-842",
    "password": "admin123"
  }
  ```
- **Response (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": "c1f7a24e-4b68-4f81-8cb4-2c6e949c8112",
      "officer_id": "DOCA-INSP-842",
      "full_name": "Inspector Rajesh Kumar",
      "email": "rajesh.kumar@lm.gov.in",
      "phone": "+91 98765 43210",
      "designation": "Senior Inspector (Legal Metrology)",
      "zone": "Northern Zone - Delhi HQ",
      "role": "INSPECTOR",
      "last_login_at": "2026-09-15T18:00:00Z",
      "previous_login_at": "2026-09-14T09:30:00Z"
    }
  }
  ```
- **Database Effect:** Updates `users.previous_login_at = users.last_login_at` and sets `users.last_login_at = utcnow()`.
- **Errors:** 401 if invalid credentials or officer not found; 422 if request malformed.

---

### GET `/api/auth/me`
- **Auth:** Bearer Token
- **Role:** Any authenticated user
- **Purpose:** Retrieve profile and permissions of currently authenticated officer.
- **Response (200 OK):** `UserProfileResponse` object.
- **Errors:** 401 if token missing or invalid.

---

### PATCH `/api/auth/me`
- **Auth:** Bearer Token
- **Role:** Any authenticated user
- **Purpose:** Update editable profile fields (full_name, email, phone, designation, zone).
- **Request Body:** `UpdateProfileRequest` (optional fields).
- **Response (200 OK):** Updated `UserProfileResponse`.
- **Database Effect:** Updates `users` row.

---

### POST `/api/auth/change-password`
- **Auth:** Bearer Token
- **Role:** Any authenticated user
- **Purpose:** Change officer password.
- **Request Body:**
  ```json
  {
    "current_password": "...",
    "new_password": "..."
  }
  ```
- **Response (200 OK):** `{"message": "Password updated successfully"}`
- **Database Effect:** Hashes new password and updates `users.password_hash` and `users.password_updated_at`.

---

### POST `/api/auth/logout`
- **Auth:** Bearer Token
- **Role:** Any authenticated user
- **Purpose:** Formal audit logout endpoint.
- **Response (200 OK):** `{"message": "Logged out successfully"}`
- **Database Effect:** Records `LOGOUT` in `audit_logs`.

---

## 2. Field Inspector Dashboard & Metrics

### GET `/api/dashboard/summary`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `SUPERVISOR`, `ADMIN`
- **Purpose:** Enforcement KPIs and count cards for dashboard.
- **Response (200 OK):**
  ```json
  {
    "inspections_today": 4,
    "pending_reviews": 2,
    "potential_violations": 5,
    "completed_inspections": 12,
    "compliance_rate_percent": 75.0,
    "total_inspections": 16
  }
  ```
- **Database Effect:** Scoped aggregation query against `inspections` and `compliance_checks`. (Inspectors see only their assigned records; Supervisors see jurisdiction-wide).

---

### GET `/api/dashboard/inspections`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `SUPERVISOR`, `ADMIN`
- **Query Params:**
  - `status`: Filter by status (`DRAFT`, `ANALYZING`, `NEEDS_REVIEW`, `COMPLETED`)
  - `date`: ISO date `YYYY-MM-DD`
  - `limit`: Default 20, max 100
  - `offset`: Default 0
- **Response (200 OK):** Paginated list of `DashboardInspectionListItem`.

---

### GET `/api/dashboard/pending-actions`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `SUPERVISOR`, `ADMIN`
- **Purpose:** Actionable feed of items awaiting inspector adjudication or image upload.
- **Response (200 OK):** List of `PendingActionItem`.

---

### GET `/api/dashboard/analytics`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `SUPERVISOR`, `ADMIN`
- **Purpose:** Violation trends breakdown by rule code, severity, and commodity category.

---

### GET `/api/dashboard/enforcement`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `SUPERVISOR`, `ADMIN`
- **Purpose:** Chronological timeline of recent compliance audits and officer actions.

---

## 3. Search & Surveillance Repository

### GET `/api/repository/inspections` (Aliases: `/api/inspections/search`, `/api/inspections/history`)
- **Auth:** Bearer Token
- **Role:** `INSPECTOR` (scoped), `SUPERVISOR`, `ADMIN` (global)
- **Query Params:** `query`, `status`, `start_date`, `end_date`, `category`, `finding_type`, `limit`, `offset`.
- **Purpose:** Full-text multi-criteria search across inspection numbers, products, locations, and brands.
- **Response (200 OK):** `RepositoryInspectionsResponse`.

---

### GET `/api/repository/products` (Alias: `/api/products/search`)
- **Auth:** Bearer Token
- **Query Params:** `query`, `category`, `limit`, `offset`.
- **Purpose:** Search catalog of unique products surveyed across enforcement operations.
- **Response (200 OK):** `RepositoryProductsResponse`.

---

### GET `/api/repository/products/{product_key}/inspections` (Alias: `/api/products/{product_key}/history`)
- **Auth:** Bearer Token
- **Purpose:** Historical inspection surveillance trail for a specific product key over time.

---

### GET `/api/repository/reports`
- **Auth:** Bearer Token
- **Query Params:** `query`, `start_date`, `end_date`, `limit`, `offset`.
- **Purpose:** Repository of sealed statutory inspection reports.

---

## 4. Inspection Lifecycle & Management

### POST `/api/inspections`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Initialize new compliance inspection with atomic sequence number allocation and offline draft idempotency.
- **Request Body:**
  ```json
  {
    "product_name": "Organic Almond Milk 1L",
    "brand_name": "PureNut",
    "category": "Packaged Food",
    "location": "Retail Outlet 42, Connaught Place, New Delhi",
    "batch_number": "BATCH-2026-A1",
    "notes": "Surveillance audit under PCR 2011",
    "client_draft_id": "draft-9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "inspection_type": "PHYSICAL"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "id": "e4b9c1d2-...",
    "inspection_number": "LM-2026-00042",
    "status": "DRAFT",
    "product_name": "Organic Almond Milk 1L",
    "client_draft_id": "draft-9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "created_at": "2026-09-15T18:54:05Z"
  }
  ```
- **Idempotency Guarantee:** If `client_draft_id` already exists, returns HTTP 200 with existing inspection without creating a duplicate.
- **Database Effect:** Inserts `inspections` and `products` row, atomically increments `inspection_number_counters`.

---

### GET `/api/inspections/{inspection_id}`
- **Auth:** Bearer Token
- **Purpose:** Fetch complete inspection dossier including product, images, declarations, compliance checks, and report metadata.
- **Response (200 OK):** `InspectionDetailResponse`.
- **Errors:** 404 if not found; 403 if inspector attempts access to another officer's record.

---

### POST `/api/inspections/{inspection_id}/images`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Upload package panel photograph with real-time blur and glare quality assessment.
- **Form Data:**
  - `file`: Binary image (JPEG / PNG)
  - `view_type`: Slot string (`front`, `back`, `side`, `panel`, `other`)
- **Response (201 Created):**
  ```json
  {
    "id": "img-uuid-...",
    "inspection_id": "e4b9c1d2-...",
    "original_filename": "front_panel.jpg",
    "file_path": "uploads/e4b9c1d2_front.jpg",
    "view_type": "front",
    "blur_score": 245.8,
    "quality_status": "GOOD",
    "quality_score": 0.94
  }
  ```
- **Immutability Invariant (DEF-02):** Rejects upload with HTTP 409 Conflict if inspection is `COMPLETED` or already has a generated report.
- **Database Effect:** Inserts `product_images` row, saves file to disk; transitions `status` from `DRAFT` to `IMAGES_UPLOADED`.

---

### DELETE `/api/images/{image_id}`
- **Auth:** Bearer Token
- **Purpose:** Delete uploaded image and unlink file from disk.
- **Immutability Invariant:** Rejects with 409 Conflict if inspection finalized or report generated.

---

### DELETE `/api/inspections/{inspection_id}/images/slot/{view_type}`
- **Auth:** Bearer Token
- **Purpose:** Replace/delete image in a specific panel slot (`front`, `back`, `side`).

---

### POST `/api/quality-check`
- **Auth:** Bearer Token
- **Purpose:** On-demand standalone package image quality assessment powered by BlurDetection2 without requiring inspection ID.
- **Form Data:** `file` (Image binary)
- **Response (200 OK):** `QualityCheckResponse` with Laplacian blur score, contrast, and quality decision.

---

## 5. OCR, PP-Structure Layout & Declarations

### POST `/api/inspections/{inspection_id}/ocr`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Run multi-panel OCR, PP-Structure layout segmentation, statutory declaration extraction, and cross-image merging.
- **Response (200 OK):** `RunOCRResponse` with all extracted fields, bounding boxes, confidence scores, detected conflicts, and barcodes.
- **Concurrency & Idempotency:** Guarded by active event lock per inspection. Re-calling an already extracted inspection reuses existing declarations without re-triggering expensive inference.
- **Database Effect:** Inserts `ocr_results`, inserts/updates 8 `declarations`, transitions status to `ANALYSIS_COMPLETE`.

---

### GET `/api/inspections/{inspection_id}/declarations`
- **Auth:** Bearer Token
- **Purpose:** Fetch all structured declaration records for the inspection.
- **Response (200 OK):** Array of `DeclarationResponse` objects.

---

### GET `/api/inspections/{inspection_id}/declaration-validation`
- **Auth:** Bearer Token
- **Purpose:** Retrieve unified 8-dimensional compliance matrix:
  `| Declaration | Present | Correct | Readable | Placement | Font Size | Format | Status |`
- **Response (200 OK):** `DeclarationValidationMatrixResponse`.

---

### GET `/api/inspections/{inspection_id}/compliance-summary`
- **Auth:** Bearer Token
- **Purpose:** Canonical breakdown of passed checks, confirmed violations, pending adjudications, and overall compliance status.

---

### PATCH `/api/declarations/{declaration_id}`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Officer verification and manual correction of OCR-extracted value.
- **Request Body:**
  ```json
  {
    "corrected_value": "Net Wt. 500 g",
    "verification_status": "CORRECTED",
    "correction_reason": "Corrected misread numeral '50O g' to '500 g'"
  }
  ```
- **Database Effect:** Updates `declarations.corrected_value`, records officer ID and timestamp, emits `DECLARATION_VERIFIED` audit log.

---

## 6. Statutory Compliance Evaluation & Adjudication

### POST `/api/inspections/{inspection_id}/evaluate`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Run deterministic rule engine against verified effective declaration values.
- **Response (200 OK):** Array of evaluated `ComplianceCheck` findings.
- **Database Effect:** Inserts/updates `compliance_checks`, links `evidence` crops; sets `adjudication_status = 'PENDING'` for non-pass findings.

---

### GET `/api/inspections/{inspection_id}/findings`
- **Auth:** Bearer Token
- **Query Params:** `filter`: `'all'` | `'pending_adjudication'`
- **Purpose:** List compliance findings with photographic evidence and statutory citations.
- **Response (200 OK):** Array of `FindingResponse` objects.

---

### POST `/api/findings/{finding_id}/adjudicate` (Aliases: `PATCH .../adjudicate`, `POST /api/compliance-checks/{id}/adjudicate`)
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Human-in-the-loop statutory decision on a preliminary finding.
- **Request Body:**
  ```json
  {
    "action": "CONFIRMED",
    "notes": "Verified package missing mandatory MRP tax qualifier."
  }
  ```
  *(Supported actions: `CONFIRMED`, `DISMISSED`, `CORRECTED`, `NOT_APPLICABLE`, `NEEDS_MORE_EVIDENCE`)*
- **Database Effect:** Updates `compliance_checks.adjudication_status`, notes, and timestamp; inserts row into `inspector_reviews`; records immutable `audit_logs`.

---

### GET `/api/findings/{finding_id}/evidence`
- **Auth:** Bearer Token
- **Purpose:** Retrieve photographic evidence crops and bounding-box coordinates for a finding.

---

### POST `/api/findings/{finding_id}/request-new-image`
- **Auth:** Bearer Token
- **Purpose:** Mark finding as `NEEDS_MORE_EVIDENCE` requesting field officer to re-photograph packaging panel.

---

### POST `/api/inspections/{inspection_id}/finalize`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Purpose:** Execute statutory finalization gate, compute legal overall status, and lock evidence.
- **Request Body:** Optional `{ "notes": "..." }`
- **Response (200 OK):** `FinalizeInspectionResponse`
- **Pre-Condition Gate:** HTTP 400 Bad Request if any finding remains with `adjudication_status == 'PENDING'`.
- **Database Effect:** Sets `inspections.status = 'COMPLETED'`, computes `overall_status`, writes `finalized_at`.

---

## 7. Statutory Inspection Reports

### POST `/api/inspections/{inspection_id}/report`
- **Auth:** Bearer Token
- **Role:** `INSPECTOR`, `ADMIN`
- **Query Params:** `force_regenerate`: boolean (default false)
- **Purpose:** Generate formal statutory ReportLab A4 PDF and DOCX reports with SHA-256 integrity hash.
- **Response (200 OK):** `ReportResponse` with download URLs and cryptographic hash.
- **Idempotency Guard (AUDIT-REP-01):** Returns existing report if already generated and file exists on disk, preventing version inflation.

---

### GET `/api/inspections/{inspection_id}/report/pdf`
- **Auth:** Bearer Token
- **Purpose:** Stream binary PDF file with `Content-Disposition: inline; filename=...`.

---

### GET `/api/inspections/{inspection_id}/report/docx`
- **Auth:** Bearer Token
- **Purpose:** Download editable Word DOCX statutory report.

---

## 8. E-Commerce & Online Marketplace Surveillance (PS 26034)

### POST `/api/inspections/{inspection_id}/listing`
- **Auth:** Bearer Token
- **Purpose:** Save e-commerce listing attributes for comparison against physical package OCR.

---

### POST `/api/inspections/{inspection_id}/listing/compare`
- **Auth:** Bearer Token
- **Purpose:** Run automated field-by-field discrepancy analysis between online listing and package OCR.
- **Rule Enforcement:** Flags potential violations under Rule 18(2A) (Overcharging: Online Price > Package MRP) and Rule 6(10) (Mandatory E-commerce Display).

---

### POST `/api/inspections/{inspection_id}/listing/comparisons/{comparison_id}/adjudicate`
- **Auth:** Bearer Token
- **Purpose:** Inspector adjudication on e-commerce discrepancy findings.

---

## 9. Supervisory Oversight & Administration

### GET `/api/supervisor/dashboard`
- **Auth:** Bearer Token
- **Role:** `SUPERVISOR`, `ADMIN` (HTTP 403 Forbidden for `INSPECTOR`)
- **Purpose:** Supervisory oversight dashboard metrics across entire jurisdiction.

---

### GET `/api/supervisor/inspectors`
- **Auth:** Bearer Token
- **Role:** `SUPERVISOR`, `ADMIN`
- **Purpose:** Inspector roster with activity metrics, inspection counts, and last login timestamps.

---

### GET `/api/supervisor/inspections`
- **Auth:** Bearer Token
- **Role:** `SUPERVISOR`, `ADMIN`
- **Query Params:** `limit`, `offset`, `status`, `inspector_id`, `search`, `start_date`, `end_date`, `compliance_status`.
- **Purpose:** Paginated 18-attribute complete dossier of all inspections in jurisdiction.

---

### DELETE `/api/inspections/{inspection_id}/report`
- **Auth:** Bearer Token
- **Role:** `SUPERVISOR`, `ADMIN` (Strictly forbidden for `INSPECTOR`)
- **Request Body:**
  ```json
  {
    "confirm": true,
    "reason": "Administrative correction required before re-issuance"
  }
  ```
- **Database & Disk Effect:** Unlinks PDF and DOCX files from disk, deletes `reports` row, reverts inspection status to `ANALYSIS_COMPLETE`. Writes permanent audit log.

---

### DELETE `/api/inspections/{inspection_id}`
- **Auth:** Bearer Token
- **Role:** `SUPERVISOR`, `ADMIN` (Strictly forbidden for `INSPECTOR`)
- **Request Body:**
  ```json
  {
    "confirm": true,
    "reason": "Defective inspection record created in error during system calibration"
  }
  ```
- **Cascade Deletion:** Unlinks all image files from disk; atomically deletes evidence, compliance_checks, declarations, ocr_results, product_images, product, report, and inspection.
- **Audit Survival:** The associated `audit_logs` records survive with `inspection_id` set to `NULL` for permanent legal accountability.
