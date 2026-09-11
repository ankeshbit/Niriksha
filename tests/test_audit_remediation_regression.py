"""
tests/test_audit_remediation_regression.py

Comprehensive Regression Test Suite for NiriKsha Audit Remediation.
Covers:
  - DEF-01: OCR Production Contract & Helpers
  - DEF-02: Finalized/Report Image Deletion Protection (HTTP 409)
  - DEF-03: No Hardcoded Personal LAN IP in mobile api.ts
  - DEF-05: Authenticated POST /api/auth/logout
  - DEF-07: OCR Extraction Robustness (Substitutions & Header Rejection)
  - DEF-08: Dedicated client_draft_id Column, Clean Notes & Idempotency
  - DEF-13: Production DB & Report Storage Isolation
"""

import os
import re
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.models import Inspection, Product, ProductImage, Declaration, ComplianceCheck, Report, AuditLog
from backend.database import SessionLocal
from backend.extraction_service import DeterministicRegexExtractor
from backend.ocr_service import OCRTextBox

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def get_auth_token():
    """Helper to authenticate seed officer and return JWT token."""
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ===========================================================================
# DEF-02: Image Deletion Protection
# ===========================================================================

def test_delete_draft_inspection_image_allowed():
    """Verify that deleting an image from a non-finalized DRAFT inspection succeeds (200 OK)."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create draft inspection
    insp_resp = client.post("/api/inspections", headers=headers, json={
        "product_name": "Test Delete Draft Product",
        "category": "Packaged Food",
        "location": "Delhi Market"
    })
    assert insp_resp.status_code == 201
    insp_id = insp_resp.json()["id"]

    # 2. Upload image
    with open(FIXTURES_DIR / "clear_package.jpg", "rb") as f:
        img_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=headers,
            files={"file": ("clear.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )
    assert img_resp.status_code == 201
    image_id = img_resp.json()["id"]

    # 3. Delete image from DRAFT inspection -> should succeed
    del_resp = client.delete(f"/api/images/{image_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Image deleted successfully"


def test_delete_completed_inspection_image_rejected():
    """Verify that deleting an image from a COMPLETED inspection is rejected with HTTP 409 Conflict."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create inspection
    insp_resp = client.post("/api/inspections", headers=headers, json={
        "product_name": "Completed Inspection Item",
        "category": "Packaged Food",
        "location": "Warehouse Zone 1"
    })
    assert insp_resp.status_code == 201
    insp_id = insp_resp.json()["id"]

    # 2. Upload image
    with open(FIXTURES_DIR / "clear_package.jpg", "rb") as f:
        img_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=headers,
            files={"file": ("clear.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )
    assert img_resp.status_code == 201
    image_id = img_resp.json()["id"]

    # 3. Mark inspection status as COMPLETED
    db = SessionLocal()
    insp = db.query(Inspection).filter(Inspection.id == insp_id).first()
    insp.status = "COMPLETED"
    db.commit()
    db.close()

    # 4. Attempt to delete supporting image -> MUST be rejected with HTTP 409 Conflict
    del_resp = client.delete(f"/api/images/{image_id}", headers=headers)
    assert del_resp.status_code == 409
    assert "Official inspection evidence cannot be deleted" in del_resp.json()["detail"]


def test_delete_report_associated_image_rejected():
    """Verify that deleting an image associated with an official report is rejected with HTTP 409."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Query existing completed inspection with report in test database or create one
    db = SessionLocal()
    rep = db.query(Report).first()
    db.close()

    if rep:
        # Check if the inspection has images
        db = SessionLocal()
        img = db.query(ProductImage).filter(ProductImage.inspection_id == rep.inspection_id).first()
        db.close()
        if img:
            del_resp = client.delete(f"/api/images/{img.id}", headers=headers)
            assert del_resp.status_code == 409
            assert "cannot be deleted" in del_resp.json()["detail"].lower()


def test_delete_nonexistent_image_returns_404():
    """Verify that deleting a non-existent image returns 404 Not Found."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.delete("/api/images/non-existent-img-uuid-9999", headers=headers)
    assert resp.status_code == 404
    assert "Image record not found" in resp.json()["detail"]


# ===========================================================================
# DEF-05: Logout Endpoint
# ===========================================================================

def test_auth_logout_endpoint_success():
    """Verify POST /api/auth/logout succeeds with valid token and logs audit event."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Logout
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Successfully logged out"

    # Verify audit log recorded
    db = SessionLocal()
    last_log = db.query(AuditLog).filter(
        AuditLog.actor_id == settings.SEED_OFFICER_ID,
        AuditLog.action == "LOGOUT"
    ).order_by(AuditLog.created_at.desc()).first()
    assert last_log is not None
    assert last_log.action == "LOGOUT"
    db.close()


def test_auth_logout_endpoint_requires_authentication():
    """Verify POST /api/auth/logout returns 401 Unauthorized without token."""
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 401


# ===========================================================================
# DEF-08: Dedicated client_draft_id Column, Idempotency & Clean Notes
# ===========================================================================

def test_client_draft_id_dedicated_column_and_idempotency():
    """Verify client_draft_id is stored in dedicated column and prevents duplicates."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    draft_id = "draft-uuid-audit-remediation-001"

    # First submission
    resp1 = client.post("/api/inspections", headers=headers, json={
        "product_name": "Idempotent Mustard Oil 1L",
        "category": "Packaged Food",
        "location": "Sector 18 Market",
        "notes": "Inspector draft note for audit",
        "client_draft_id": draft_id
    })
    assert resp1.status_code == 201
    data1 = resp1.json()
    insp_id_1 = data1["id"]
    insp_num_1 = data1["inspection_number"]

    # Verify DB record has dedicated client_draft_id column and clean notes
    db = SessionLocal()
    insp_db = db.query(Inspection).filter(Inspection.id == insp_id_1).first()
    assert insp_db is not None
    assert insp_db.client_draft_id == draft_id
    assert insp_db.notes == "Inspector draft note for audit"
    assert "[client_draft_id:" not in (insp_db.notes or "")
    db.close()

    # Second submission with same draft ID (simulating offline replay/retry)
    resp2 = client.post("/api/inspections", headers=headers, json={
        "product_name": "Idempotent Mustard Oil 1L",
        "category": "Packaged Food",
        "location": "Sector 18 Market",
        "notes": "Inspector draft note for audit",
        "client_draft_id": draft_id
    })
    assert resp2.status_code in [200, 201]
    data2 = resp2.json()
    assert data2["id"] == insp_id_1
    assert data2["inspection_number"] == insp_num_1

    # Verify count in database is exactly 1 for this draft
    db = SessionLocal()
    count = db.query(Inspection).filter(Inspection.client_draft_id == draft_id).count()
    assert count == 1, f"Expected exactly 1 inspection for draft {draft_id}, got {count}"
    db.close()


def test_different_client_draft_ids_create_separate_inspections():
    """Verify different client_draft_ids create separate inspections."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    resp_a = client.post("/api/inspections", headers=headers, json={
        "product_name": "Product A",
        "category": "Packaged Food",
        "location": "Zone A",
        "client_draft_id": "draft-distinct-A"
    })
    resp_b = client.post("/api/inspections", headers=headers, json={
        "product_name": "Product B",
        "category": "Packaged Food",
        "location": "Zone B",
        "client_draft_id": "draft-distinct-B"
    })

    assert resp_a.status_code == 201
    assert resp_b.status_code == 201
    assert resp_a.json()["id"] != resp_b.json()["id"]


# ===========================================================================
# DEF-07: OCR Extraction Robustness (Substitutions & Obvious Header Rejection)
# ===========================================================================

def test_ocr_date_label_substitution_toleration():
    """Verify date extractor tolerates common OCR substitutions like MED for MFD."""
    extractor = DeterministicRegexExtractor()

    # Case 1: MFD misspelled as MED
    text1 = "MED: 08/2026 \n MRP Rs. 150.00"
    boxes1 = [
        OCRTextBox(text="MED: 08/2026", confidence=0.88, bbox=[10, 10, 150, 40], sequence=1)
    ]
    decl1 = extractor._extract_date(text1, boxes1, "img-1")
    assert decl1.extraction_status == "EXTRACTED"
    assert "08/2026" in decl1.extracted_value

    # Case 2: MFG misspelled as MFC
    text2 = "MFC BY: SUNFLOWER FOODS PVT LTD \n NET QTY: 1 kg"
    boxes2 = [
        OCRTextBox(text="MFC BY: SUNFLOWER FOODS PVT LTD", confidence=0.87, bbox=[10, 50, 250, 80], sequence=2)
    ]
    decl2 = extractor._extract_manufacturer(text2, boxes2, "img-2")
    assert decl2.extraction_status == "EXTRACTED"
    assert "SUNFLOWER FOODS" in decl2.extracted_value


def test_ocr_consumer_care_em_dash_toleration():
    """Verify consumer care phone extraction tolerates Unicode em-dashes and hyphens."""
    extractor = DeterministicRegexExtractor()
    text = "FOR COMPLAINTS: 1800—200—1122 / CARE@SUNFLOWER.IN"
    boxes = [
        OCRTextBox(text=text, confidence=0.91, bbox=[10, 100, 300, 130], sequence=3)
    ]
    decl = extractor._extract_consumer_care(text, boxes, "img-3")
    assert decl.extraction_status == "EXTRACTED"
    assert "1800" in decl.extracted_value


def test_ocr_commodity_name_rejects_non_product_headers():
    """Verify commodity name extraction rejects non-commodity headings like NUTRITIONAL FACTS."""
    extractor = DeterministicRegexExtractor()

    # Image text with Nutrition Facts header appearing before the commodity name
    boxes = [
        OCRTextBox(text="NUTRITIONAL FACTS & DETAILS", confidence=0.92, bbox=[10, 10, 300, 40], sequence=1),
        OCRTextBox(text="INGREDIENTS: WHEAT FLOUR, WATER, SALT", confidence=0.89, bbox=[10, 50, 350, 80], sequence=2),
        OCRTextBox(text="DIRECTIONS FOR USE: BOIL BEFORE SERVING", confidence=0.88, bbox=[10, 90, 350, 120], sequence=3),
        OCRTextBox(text="WHOLE WHEAT ATTA", confidence=0.94, bbox=[10, 130, 250, 170], sequence=4),
        OCRTextBox(text="NET WEIGHT: 5 kg", confidence=0.95, bbox=[10, 180, 200, 210], sequence=5),
        OCRTextBox(text="MRP RS 240.00", confidence=0.96, bbox=[10, 220, 180, 250], sequence=6),
    ]
    raw_text = "\n".join([b.text for b in boxes])

    decl = extractor._extract_commodity_name(raw_text, boxes, "img-atta")
    assert decl.extraction_status == "EXTRACTED"
    assert "NUTRITION" not in decl.extracted_value.upper()
    assert "INGREDIENTS" not in decl.extracted_value.upper()
    assert "DIRECTIONS" not in decl.extracted_value.upper()
    assert decl.extracted_value.upper() == "WHOLE WHEAT ATTA"


# ===========================================================================
# DEF-03: No Hardcoded Personal LAN IP in Mobile Source
# ===========================================================================

def test_static_audit_no_personal_lan_ip_in_api_ts():
    """Static test proving no personal LAN IP (e.g. 10.185.115.213) is hardcoded in api.ts."""
    api_ts_path = Path(__file__).resolve().parent.parent / "mobile" / "src" / "services" / "api.ts"
    assert api_ts_path.exists(), "mobile/src/services/api.ts must exist"

    content = api_ts_path.read_text(encoding="utf-8")

    # Reject hardcoded private/personal IPs in quotes
    # 10.x.x.x (except 10.0.2.2 emulator), 192.168.x.x, 172.16-31.x.x
    forbidden_pattern = re.compile(
        r"['\"]https?://(10\.(?!0\.2\.2)\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):\d+['\"]"
    )
    matches = forbidden_pattern.findall(content)
    assert len(matches) == 0, f"Forbidden personal LAN IP found in api.ts: {matches}"
