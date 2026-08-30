# REST API Reference Documentation

> **SIH 2026 Prototype — For demonstration purposes only.**

The backend exposes a REST API built with FastAPI. All endpoints, except `/api/health` and `/api/auth/login`, require an `Authorization: Bearer <token>` header containing a valid JSON Web Token (JWT).

Base URL for local execution: `http://127.0.0.1:8000`

---

## 1. Authentication & Officer Profile

### `POST /api/auth/login`
Authenticates a field officer and issues a JWT access token.

- **Request Body**:
  ```json
  {
    "officer_id": "DOCA-INSP-842",
    "password": "admin123"
  }
  ```
- **Success Response (`200 OK`)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "officer_id": "DOCA-INSP-842",
    "full_name": "Inspector Rajesh Kumar",
    "designation": "Senior Inspector (Legal Metrology)",
    "zone": "Northern Zone - Delhi HQ"
  }
  ```
- **Error Response (`401 Unauthorized`)**:
  ```json
  {
    "detail": "Invalid Officer ID or password"
  }
  ```

### `GET /api/auth/me`
Retrieves the profile of the currently authenticated officer.

- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "c8f2b1d3-4e5a-4b6c-8d7e-9f0a1b2c3d4e",
    "officer_id": "DOCA-INSP-842",
    "full_name": "Inspector Rajesh Kumar",
    "email": "rajesh.kumar@doca.gov.in",
    "phone": "+91 98765 43210",
    "designation": "Senior Inspector (Legal Metrology)",
    "zone": "Northern Zone - Delhi HQ",
    "role": "INSPECTOR"
  }
  ```

---

## 2. Inspection Management

### `POST /api/inspections`
Creates a new inspection record in `DRAFT` status.

- **Request Body**:
  ```json
  {
    "product_name": "Premium Basmati Rice 5kg",
    "brand_name": "Agro Foods",
    "category": "Packaged Food",
    "batch_number": "AGR-2026-08B",
    "location": "Azadpur Wholesale Mandi, Delhi",
    "notes": "Routine retail compliance check"
  }
  ```
- **Success Response (`201 Created`)**:
  ```json
  {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "inspection_number": "LM-2026-00891",
    "status": "DRAFT",
    "overall_status": null,
    "location": "Azadpur Wholesale Mandi, Delhi",
    "created_at": "2026-08-30T10:30:00Z"
  }
  ```

### `GET /api/inspections/dashboard-stats`
Retrieves aggregate inspection counts and summary metrics for the inspector dashboard.

- **Success Response (`200 OK`)**:
  ```json
  {
    "total_inspections": 42,
    "needs_verification": 12,
    "verified_compliant": 24,
    "potential_non_compliance": 6,
    "recent_inspections": [ ... ]
  }
  ```

### `GET /api/inspections/{inspection_id}`
Fetches full details of an inspection including product information, uploaded images, declarations, findings, and report metadata.

---

## 3. Package Image Ingestion & Quality Check

### `POST /api/inspections/{inspection_id}/images`
Uploads a package image (multipart/form-data) and runs automated OpenCV image quality assessment.

- **Form Fields**:
  - `file`: Image binary (`image/jpeg`, `image/png`, `image/webp`)
  - `view_type`: `"front" | "back" | "panel" | "side" | "other"`
- **Success Response (`201 Created`)**:
  ```json
  {
    "id": "e1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
    "inspection_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "file_path": "uploads/inspections/.../front.jpg",
    "view_type": "front",
    "blur_score": 342.5,
    "glare_score": 0.02,
    "quality_score": 0.94,
    "quality_status": "GOOD",
    "created_at": "2026-08-30T10:32:00Z"
  }
  ```

---

## 4. OCR & Declaration Extraction

### `POST /api/inspections/{inspection_id}/ocr`
Runs the modular OCR pipeline and extracts 7 structured statutory declarations mapped to PCR 2011 Rule 6.

- **Success Response (`200 OK`)**:
  ```json
  {
    "inspection_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "raw_text": "PREMIUM BASMATI RICE\nNET QUANTITY: 5 kg\nMRP Rs. 450.00 (INCL. OF ALL TAXES)...",
    "mean_confidence": 0.92,
    "engine_used": "OpenCV-Morphological",
    "declarations": [
      {
        "id": "d1e2f3a4-b5c6-7d8e-9f0a-1b2c3d4e5f6a",
        "field_name": "commodity_name",
        "extracted_value": "PREMIUM BASMATI RICE",
        "corrected_value": null,
        "effective_value": "PREMIUM BASMATI RICE",
        "confidence": 0.95,
        "verification_status": "PENDING"
      },
      {
        "id": "d2e3f4a5-b6c7-8d9e-0f1a-2b3c4d5e6f7b",
        "field_name": "net_quantity",
        "extracted_value": "5 kg",
        "corrected_value": null,
        "effective_value": "5 kg",
        "confidence": 0.94,
        "verification_status": "PENDING"
      }
    ]
  }
  ```

### `PATCH /api/declarations/{declaration_id}`
Allows an inspector to correct an extracted declaration value. The original OCR value is preserved immutably.

- **Request Body**:
  ```json
  {
    "corrected_value": "5 kg",
    "verification_status": "CORRECTED",
    "correction_reason": "Officer corrected OCR character recognition on net quantity unit"
  }
  ```
- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "d2e3f4a5-b6c7-8d9e-0f1a-2b3c4d5e6f7b",
    "field_name": "net_quantity",
    "extracted_value": "5 kg",
    "corrected_value": "5 kg",
    "effective_value": "5 kg",
    "verification_status": "CORRECTED"
  }
  ```

---

## 5. Rule Engine & Statutory Compliance Evaluation

### `POST /api/inspections/{inspection_id}/evaluate`
Evaluates the effective declarations against the deterministic Legal Metrology (Packaged Commodities) Rules, 2011 rule set.

- **Success Response (`200 OK`)**:
  ```json
  {
    "inspection_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "rules_evaluated_count": 7,
    "findings": [
      {
        "id": "f1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
        "rule_code": "PCR_RULE_06_1_E",
        "rule_name": "Maximum Retail Price (MRP) & Tax Declaration",
        "statutory_reference": "Rule 6(1)(e), Legal Metrology (Packaged Commodities) Rules, 2011",
        "result_state": "PASS",
        "extracted_value": "MRP Rs. 450.00 (INCL. OF ALL TAXES)",
        "adjudication_action": "PENDING"
      }
    ]
  }
  ```

### `PATCH /api/findings/{finding_id}/adjudicate`
Records human-in-the-loop inspector adjudication on a specific finding.

- **Request Body**:
  ```json
  {
    "action": "CONFIRMED",
    "notes": "Verified missing consumer care email on package rear panel."
  }
  ```
- **Supported Actions**: `"CONFIRMED" | "DISMISSED" | "CORRECTED" | "REQUEST_NEW_IMAGE" | "NOT_APPLICABLE"`
- **Success Response (`200 OK`)**:
  ```json
  {
    "id": "f1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
    "rule_code": "PCR_RULE_06_1_G",
    "adjudication_action": "CONFIRMED",
    "officer_notes": "Verified missing consumer care email on package rear panel."
  }
  ```

---

## 6. Inspection Finalization & Report Generation

### `POST /api/inspections/{inspection_id}/finalize`
Finalizes the inspection lifecycle and triggers the statutory PDF report generation.

- **Request Body**:
  ```json
  {
    "officer_notes": "Inspection completed. Notice issued for missing Rule 6(1)(g) consumer care details."
  }
  ```
- **Success Response (`200 OK`)**:
  ```json
  {
    "inspection_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "status": "COMPLETED",
    "overall_status": "POTENTIAL_NON_COMPLIANCE",
    "report_id": "r1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
    "report_number": "LM_Report_LM_2026_00891_v1",
    "pdf_url": "/api/inspections/f47ac10b-58cc-4372-a567-0e02b2c3d479/report/pdf"
  }
  ```
- **Gating Error Response (`409 Conflict`)**:
  ```json
  {
    "detail": {
      "error": "UNRESOLVED_FINDINGS",
      "message": "Cannot finalize inspection. 1 findings require inspector adjudication.",
      "unresolved_findings": [ "PCR_RULE_06_1_G" ]
    }
  }
  ```

### `GET /api/inspections/{inspection_id}/report/pdf`
Streams the binary PDF inspection certificate generated by ReportLab (`application/pdf`).

---

## 7. Rules Registry & Audit Trail

### `GET /api/rules`
Lists all active statutory rules registered in the deterministic rule engine.

### `GET /api/inspections/{inspection_id}/audit-logs`
Retrieves the complete immutable audit trail of actions performed on an inspection.
