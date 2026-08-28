# AI-Assisted Legal Metrology Packaged-Commodity Inspection System

**Smart India Hackathon 2026 • Problem Statement ID: 26034**  
**Ministry**: Ministry of Consumer Affairs, Food & Public Distribution  
**Department**: Department of Consumer Affairs (DoCA)  
**Category**: Software System to Check Compliance of Packaged Commodities under Legal Metrology (Packaged Commodities) Rules, 2011

---

## 1. Executive Summary & Purpose

The **AI-Assisted Legal Metrology Inspection System** is an enforcement-grade software platform built for field inspection officers under the Department of Consumer Affairs (DoCA). It streamlines packaged commodity inspections by coupling computer vision and optical character recognition (OCR) with a **deterministic statutory rule engine** mapped directly to the **Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)**.

### Core Architectural Principle: Human-in-the-Loop & Statutory Safety
- **AI / OCR Role**: Restricted exclusively to image ingestion, image quality assessment (blur, glare, resolution), optical character recognition, and structured declaration parsing.
- **Deterministic Rule Engine**: Compliance evaluations are executed against deterministic PCR 2011 statutory rules. AI never makes autonomous legal violation determinations.
- **Inspector Adjudication**: All compliance findings must be reviewed and adjudicated (Confirmed / Dismissed / Noted) by a human enforcement officer before finalization.

---

## 2. Quickstart & Local Setup

### Prerequisites
- Python 3.10+
- Modern Web Browser (Chrome, Edge, Firefox, Safari)

### Installation & Execution
```bash
# 1. Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# 2. Start FastAPI application server
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Once running, navigate to:
- **Application Portal & Landing Page**: `http://127.0.0.1:8000/`
- **Field Inspector Login**: `http://127.0.0.1:8000/stitch/code/01_login.html`
- **Interactive OpenAPI Documentation**: `http://127.0.0.1:8000/docs`

---

## 3. Demo Credentials (Pre-Seeded)

| Role | Officer ID / Username | Password | Designation | Zone |
|---|---|---|---|---|
| **Field Inspecting Officer** | `DOCA-INSP-842` | `admin123` | Senior Inspector (Legal Metrology) | Northern Zone - Delhi HQ |

*(Note: These credentials are seeded for local demonstration and evaluation purposes).*

---

## 4. End-to-End Inspection Workflow

1. **Sign In**: Authenticate using designated Officer ID and password.
2. **Dashboard**: View aggregate statistics (Total Inspections, Needs Verification, Verified Compliant, Potential Non-Compliance) and recent records.
3. **New Inspection**: Register commodity name, category (*Packaged Food* or *Household/Personal Care*), brand, location, and batch/lot number.
4. **Image Upload & Quality Assessment**: Capture or upload package images (Front, Back, Side). OpenCV evaluates blur score, brightness, and resolution.
5. **OCR & Declaration Extraction**: Non-destructive OCR extracts raw text and localizes bounding boxes for 7 statutory fields under Rule 6:
   - Commodity Name (Rule 6(1)(f))
   - Manufacturer / Packer / Importer (Rule 6(1)(a))
   - Net Quantity with metric SI units (Rule 6(1)(c))
   - Maximum Retail Price (MRP) & Tax Qualifier (Rule 6(1)(e))
   - Month & Year of Manufacture/Packing (Rule 6(1)(d))
   - Consumer Care & Grievance Redressal (Rule 6(1)(g))
   - Country of Origin (Rule 6(1)(b))
6. **Inspector Verification**: Inspecting officer verifies or corrects extracted declarations. Baseline OCR values and confidence are preserved immutably.
7. **Rule Engine Evaluation**: Deterministic statutory evaluation determines rule states (`PASS`, `POTENTIAL_NON_COMPLIANCE`, `INSUFFICIENT_EVIDENCE`, `NOT_APPLICABLE`).
8. **Photographic Evidence & Adjudication**: Officer reviews evidence overlays and adjudicates potential findings (*Confirm* or *Dismiss with statutory justification*).
9. **Inspection Finalization**: Officer finalizes the inspection, updating overall status (`VERIFIED_COMPLIANT`, `POTENTIAL_NON_COMPLIANCE`, or `NEEDS_MANUAL_VERIFICATION`).
10. **Statutory PDF Report**: ReportLab engine compiles an official inspection report PDF stored under `generated_reports/` and logged in the immutable audit trail.

---

## 5. Automated Test Suite

The test suite contains **66 automated tests** with 100% pass rate:
```bash
# Run complete test suite across all 6 phases
.\venv\Scripts\python.exe -m pytest tests/ -v -W ignore::starlette.exceptions.StarletteDeprecationWarning

# Run complete QA & Hardening audit script
.\venv\Scripts\python.exe -m tests.qa_hardening_audit
```

---

## 6. Known MVP Limitations & Statutory Disclosures

1. **Font Height Measurement (Rule 9 / Table 1)**: Excluded from MVP compliance decisions. Precise millimeter height measurement from smartphone cameras requires calibrated optical targets not present in general field capture.
2. **Dual-Unit Declarations (Rule 12)**: Excluded.
3. **Institutional Consumer Wholesale Exemptions (Rule 3)**: Excluded.
4. **Statutory Human Responsibility**: The software serves strictly as an **AI-assisted decision support system**. All enforcement actions and final legal determinations remain under the statutory authority of the human inspecting officer.
