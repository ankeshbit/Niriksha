# Automated Testing & Verification Guide

> **SIH 2026 Prototype — For demonstration purposes only.**

The system includes an automated test suite implemented in **Pytest** covering all backend layers, rule evaluations, report generators, and full mobile end-to-end workflows. In addition, the mobile application includes static type checking via **TypeScript**.

---

## 1. Test Suite Summary

- **Total Automated Tests**: **77 tests**
- **Test Status**: **77 / 77 Passed (100%)**
- **TypeScript Type Check**: **0 Errors (`tsc --noEmit`)**
- **Validation Scope**: Authentication, Inspection Lifecycle, OpenCV Image Quality Assessment, Modular OCR & Field Extraction, Deterministic Rule Engine, Human Adjudication (all 5 actions), HTTP 409 Finalization Gate, ReportLab PDF Binary Generation, and Immutable Audit Trail.

---

## 2. Test Catalog & Matrix

| Test Module | Tests | Focus Area & Verified Behaviors |
|---|---|---|
| `tests/test_foundation.py` | 6 | Health check endpoint, seed inspector authentication, invalid password rejection, profile retrieval, rules registry endpoint, static UI screens availability. |
| `tests/test_phase2.py` | 9 | JWT authentication lifecycle, protected route access control, inspection creation validation, retrieval by ID, recent inspections sorting, dashboard summary metrics. |
| `tests/test_phase3.py` | 10 | Authenticated image upload, unauthenticated rejection, MIME type validation, corrupted image handling, image sequencing, OpenCV blur detection, low-resolution detection, darkness detection, image deletion. |
| `tests/test_phase4.py` | 10 | OCR service initialization, direct image OCR processing, raw bounding box persistence, Rule 6 structured field extraction (7 declarations), missing field handling, inspector declaration patch correction, data immutability. |
| `tests/test_phase5.py` | 13 | Rule registry metadata, deterministic rule engine execution (compliant package), missing declarations evaluation, insufficient evidence handling, not applicable rule evaluation, effective value resolution, idempotency, finding-to-evidence traceability, confirmation & dismissal adjudication, imported commodity evaluation, multi-panel package evaluation. |
| `tests/test_phase6.py` | 13 | Inspector finding view, confirm with notes, dismiss with statutory reason, unauthorized adjudication rejection, overall status transitions (`NO_POTENTIAL_VIOLATIONS`, `POTENTIAL_NON_COMPLIANCE`, `NEEDS_MANUAL_VERIFICATION`), ReportLab PDF creation, PDF binary stream, report versioning increment, audit trail event logging, reports archive list, imported & missing declaration PDF scenarios. |
| `tests/test_final_corrections.py` | 8 | HTTP 409 conflict gate blocking finalization with unresolved findings, resolution of all findings unblocking finalization, `NOT_APPLICABLE` adjudication action, `CORRECTED` adjudication action, final status guarantees, rule versioning in API response, `REQUEST_NEW_IMAGE` action maintaining `NEEDS_MORE_EVIDENCE`, rejection of invalid adjudication actions. |
| `tests/test_e2e_mobile_workflow.py` | 3 | Complete mobile inspection flow simulating all mobile API interactions, full execution across all 5 inspector adjudication actions, and clean compliant flow. |

---

## 3. Running Backend Tests

### 3.1 Run Complete Test Suite

Execute all 77 automated tests using Pytest:

**On Windows (PowerShell):**
```powershell
$env:DATABASE_URL="sqlite:///./legal_metrology.db"
.\venv\Scripts\python.exe -m pytest tests/ -v -W ignore::starlette.exceptions.StarletteDeprecationWarning
```

**On macOS / Linux:**
```bash
export DATABASE_URL="sqlite:///./legal_metrology.db"
python -m pytest tests/ -v -W ignore::starlette.exceptions.StarletteDeprecationWarning
```

### 3.2 Run Specific Test Suites

```bash
# Run End-to-End Mobile Workflow tests
python -m pytest tests/test_e2e_mobile_workflow.py -v

# Run Statutory Rule Engine tests
python -m pytest tests/test_phase5.py -v

# Run Adjudication & 409 Gate tests
python -m pytest tests/test_final_corrections.py -v
```

---

## 4. Comprehensive QA & Hardening Script

The repository includes a dedicated end-to-end audit runner that executes a complete 10-step inspection scenario:

```bash
# Windows PowerShell
$env:DATABASE_URL="sqlite:///./legal_metrology.db"
.\venv\Scripts\python.exe -m tests.qa_hardening_audit

# macOS / Linux
export DATABASE_URL="sqlite:///./legal_metrology.db"
python -m tests.qa_hardening_audit
```

**Audit Checks Executed**:
1. Authenticates field inspecting officer (`DOCA-INSP-842`).
2. Creates an inspection record.
3. Uploads realistic package image & verifies OpenCV quality score.
4. Executes OCR and parses 7 statutory declarations.
5. Applies inspector correction and verifies baseline OCR value preservation.
6. Evaluates deterministic rule engine against effective declaration values.
7. Records human-in-the-loop adjudication decisions.
8. Finalizes inspection through the verification gate.
9. Compiles and validates ReportLab statutory PDF output.
10. Validates the immutable lifecycle audit trail.

---

## 5. Mobile TypeScript Verification

To ensure type safety across all React Native components and screens:

```bash
cd mobile
npm run ts:check
```

Expected result: Clean exit with zero diagnostic errors (`tsc --noEmit`).
