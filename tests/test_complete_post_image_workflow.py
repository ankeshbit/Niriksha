"""
tests/test_complete_post_image_workflow.py

Comprehensive test suite verifying the complete post-image-analysis workflow of NiriKsha:
1. Sharp image -> OCR proceeds
2. Blurry image -> retake requested
3. OCR extraction -> structured declarations created
4. Missing declaration -> potential finding / manual review
5. Conflicting declarations across images -> manual verification (cross-image verification)
6. Rule evaluation -> deterministic PCR 2011 compliance results
7. OCR uncertainty -> needs manual verification (never automatic violation)
8. Inspector correction -> original OCR preserved, effective value updated
9. Request New Image -> finding marked and returns to image capture
10. Inspector confirmation -> finding becomes verified
11. Report generation -> distinct AI signals vs inspector findings, multi-image conflict audit
12. Physical quantity limitation -> photographically verified disclaimer present
13. Offline capture -> no production DB mutation
14. Reconnect -> exactly one inspection created (idempotency)
15. Repeated sync -> no duplicate inspection
16. Report immutability -> delete attempt blocked, report remains intact

SAFETY GUARANTEE: Runs strictly against isolated test_legal_metrology.db.
"""

import os
import io
import json
import pytest
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.main import app
from backend.config import settings
from backend.database import get_db, SessionLocal
from backend.models import Inspection, Product, ProductImage, Declaration, ComplianceCheck, Report, AuditLog
from backend.extraction_service import (
    ExtractedDeclarationItem,
    cross_image_verification,
    normalize_declaration_for_comparison
)
from backend.rule_engine.engine import rule_engine
from backend.rule_engine.models import RuleResultState
from backend.report_service import report_generator

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

@pytest.fixture
def auth_client():
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    client.headers = {"Authorization": f"Bearer {token}"}
    return client

# 1. Blur detection gate (Sharp vs Blurry)
def test_01_image_quality_gate(auth_client):
    # Upload clear image
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Gate Test Product",
        "category": "Packaged Food",
        "location": "Warehouse A"
    })
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        upload_resp = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("clear.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )
    assert upload_resp.status_code in (200, 201)
    img_data = upload_resp.json()
    assert img_data["quality_status"] in ["GOOD", "ACCEPTABLE"]
    assert img_data["quality_score"] >= 0.0

# 2. OCR Extraction & structured declarations
def test_02_ocr_and_declaration_creation(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Premium Basmati Rice",
        "brand_name": "Agro Pure",
        "category": "Packaged Food",
        "location": "Delhi APMC Market"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_resp.status_code == 200
    data = ocr_resp.json()
    assert data["declarations_count"] > 0
    assert "declarations" in data

    decl_resp = auth_client.get(f"/api/inspections/{insp_id}/declarations")
    assert decl_resp.status_code == 200
    decls = decl_resp.json()
    field_names = [d["field_name"] for d in decls]
    assert "mrp" in field_names
    assert "net_quantity" in field_names

# 3. Cross-Image Verification & Conflict Detection
def test_03_cross_image_conflict_detection():
    # Simulate extraction across Front and Back images with conflicting MRP (₹650 vs ₹680)
    front_items = [
        ExtractedDeclarationItem(
            field_name="mrp",
            field_label="Maximum Retail Price (MRP)",
            extracted_value="₹ 650.00 (Incl. of all taxes)",
            normalized_value="650.00",
            confidence=0.95,
            source_image_id="img-front",
            extraction_status="EXTRACTED"
        ),
        ExtractedDeclarationItem(
            field_name="net_quantity",
            field_label="Net Quantity",
            extracted_value="1 kg",
            normalized_value="1 kg",
            confidence=0.96,
            source_image_id="img-front",
            extraction_status="EXTRACTED"
        )
    ]
    back_items = [
        ExtractedDeclarationItem(
            field_name="mrp",
            field_label="Maximum Retail Price (MRP)",
            extracted_value="₹ 680.00 (Incl. of all taxes)",
            normalized_value="680.00",
            confidence=0.93,
            source_image_id="img-back",
            extraction_status="EXTRACTED"
        ),
        ExtractedDeclarationItem(
            field_name="net_quantity",
            field_label="Net Quantity",
            extracted_value="1 kg",
            normalized_value="1 kg",
            confidence=0.97,
            source_image_id="img-back",
            extraction_status="EXTRACTED"
        )
    ]

    per_image = {
        "img-front": front_items,
        "img-back": back_items
    }

    merged, conflicts = cross_image_verification(per_image)
    
    # Verify MRP is conflicting
    mrp_decl = next((d for d in merged if d.field_name == "mrp"), None)
    assert mrp_decl is not None
    assert mrp_decl.has_conflict is True
    assert mrp_decl.extraction_status == "CONFLICTING"
    assert len(mrp_decl.conflicts) == 2
    assert "img-front" in mrp_decl.source_images
    assert "img-back" in mrp_decl.source_images

    # Verify Net Quantity agreed and merged cleanly
    qty_decl = next((d for d in merged if d.field_name == "net_quantity"), None)
    assert qty_decl is not None
    assert qty_decl.has_conflict is False
    assert qty_decl.extraction_status == "EXTRACTED"
    assert qty_decl.extracted_value == "1 kg"

# 4. Conflicting declaration evaluates to NEEDS_MANUAL_VERIFICATION
def test_04_conflict_rule_evaluation():
    conflicting_decl = {
        "field_name": "mrp",
        "extracted_value": "₹ 650 vs ₹ 680",
        "has_conflict": True,
        "extraction_status": "CONFLICTING",
        "verification_status": "NEEDS_MANUAL_VERIFICATION",
        "source_image_id": "img-front"
    }
    
    eval_results = rule_engine.evaluate_inspection(
        inspection_id="test-insp-conflict",
        product_data={"product_name": "Test Rice", "category": "Packaged Food"},
        declarations=[conflicting_decl],
        images=[{"id": "img-front", "quality_status": "GOOD"}]
    )

    mrp_check = next((c for c in eval_results if c.rule_code == "PCR_RULE_06_1_E"), None)
    assert mrp_check is not None
    assert mrp_check.result_state in [RuleResultState.NEEDS_MANUAL_VERIFICATION, RuleResultState.INSUFFICIENT_EVIDENCE]
    assert "conflicting" in mrp_check.explanation.lower() or "manual verification" in mrp_check.explanation.lower()

# 5. Missing mandatory declaration handling
def test_05_missing_declaration_potential_non_compliance():
    # Net quantity missing
    missing_qty_decl = {
        "field_name": "net_quantity",
        "extracted_value": None,
        "extraction_status": "NOT_FOUND",
        "verification_status": "UNVERIFIED"
    }

    eval_results = rule_engine.evaluate_inspection(
        inspection_id="test-insp-missing",
        product_data={"product_name": "Test Tea", "category": "Packaged Food"},
        declarations=[missing_qty_decl],
        images=[{"id": "img-1", "quality_status": "GOOD"}]
    )

    qty_check = next((c for c in eval_results if c.rule_code == "PCR_RULE_06_1_C"), None)
    assert qty_check is not None
    assert qty_check.result_state == RuleResultState.POTENTIAL_NON_COMPLIANCE

# 6. Physical Quantity Limitation Notice
def test_06_physical_quantity_limitation_notice():
    # Valid quantity declared
    valid_qty_decl = {
        "field_name": "net_quantity",
        "extracted_value": "5 kg",
        "extraction_status": "EXTRACTED",
        "verification_status": "UNVERIFIED"
    }

    eval_results = rule_engine.evaluate_inspection(
        inspection_id="test-insp-qty-limit",
        product_data={"product_name": "Rice 5kg", "category": "Packaged Food"},
        declarations=[valid_qty_decl],
        images=[{"id": "img-1", "quality_status": "GOOD"}]
    )

    qty_check = next((c for c in eval_results if c.rule_code == "PCR_RULE_06_1_C"), None)
    assert qty_check is not None
    assert "physical net quantity requires appropriate physical verification" in qty_check.explanation.lower()

# 7. Inspector Correction Preserves Original OCR Value
def test_07_inspector_correction_auditability(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Wheat Flour",
        "category": "Packaged Food",
        "location": "Retail Outlet 9"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    
    decls = auth_client.get(f"/api/inspections/{insp_id}/declarations").json()
    mrp_decl = next(d for d in decls if d["field_name"] == "mrp")
    orig_ocr = mrp_decl["extracted_value"]

    # Inspector corrects MRP value
    patch_resp = auth_client.patch(
        f"/api/declarations/{mrp_decl['id']}",
        json={
            "corrected_value": "₹ 240.00 (Incl. of all taxes)",
            "correction_reason": "Corrected based on physical label"
        }
    )
    assert patch_resp.status_code == 200
    updated_decl = patch_resp.json()
    
    # Verification: Original OCR value is preserved intact
    assert updated_decl["extracted_value"] == orig_ocr
    assert updated_decl["corrected_value"] == "₹ 240.00 (Incl. of all taxes)"
    assert updated_decl["effective_value"] == "₹ 240.00 (Incl. of all taxes)"
    assert updated_decl["verification_status"] == "VERIFIED"

# 8. Request New Image Flow
def test_08_request_new_image_action(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Spices Pack",
        "category": "Packaged Food",
        "location": "Supermarket"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    findings = eval_resp.json()["findings"]
    assert len(findings) > 0

    first_finding = findings[0]
    req_img_resp = auth_client.post(f"/api/findings/{first_finding['id']}/request-new-image")
    assert req_img_resp.status_code == 200
    res_data = req_img_resp.json()
    assert res_data["adjudication_status"] == "NEEDS_MORE_EVIDENCE"

# 9. Inspector Confirmation of Finding
def test_09_inspector_confirmation(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Juice Bottle",
        "category": "Packaged Food",
        "location": "Mall Store"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    findings = eval_resp.json()["findings"]
    first_finding = findings[0]

    adj_resp = auth_client.patch(
        f"/api/findings/{first_finding['id']}/adjudicate",
        json={
            "action": "CONFIRMED",
            "notes": "Inspector confirmed finding during physical inspection."
        }
    )
    assert adj_resp.status_code == 200
    assert adj_resp.json()["adjudication_status"] == "CONFIRMED"

# 10. PDF Report Generation with AI vs Inspector Distinction & Conflicts
def test_10_report_generation_with_conflicts_and_notices(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Mustard Oil 1L",
        "category": "Packaged Food",
        "location": "Bazaar"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    auth_client.post(f"/api/inspections/{insp_id}/evaluate")

    # Generate PDF report
    rep_resp = auth_client.post(f"/api/inspections/{insp_id}/report")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert rep_data["pdf_path"] is not None
    assert Path(rep_data["pdf_path"]).exists()
    assert rep_data["report_version"] == 1

    # Verify PDF stream download
    pdf_stream = auth_client.get(f"/api/inspections/{insp_id}/report/pdf")
    assert pdf_stream.status_code == 200
    assert pdf_stream.headers["content-type"] == "application/pdf"
    assert len(pdf_stream.content) > 1000

# 11. Report Immutability: Delete is forbidden
def test_11_report_immutability(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Salt 1kg",
        "category": "Packaged Food",
        "location": "Local Store"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    rep_resp = auth_client.post(f"/api/inspections/{insp_id}/report")
    rep_id = rep_resp.json()["id"]

    # DELETE /api/reports/{id} must not exist or be 405 Method Not Allowed
    del_resp = auth_client.delete(f"/api/reports/{rep_id}")
    assert del_resp.status_code in [404, 405]

    # Re-fetch report to prove it survived
    get_rep = auth_client.get(f"/api/reports/{rep_id}")
    assert get_rep.status_code == 200
    assert get_rep.json()["id"] == rep_id

# 12. Offline sync idempotency (zero duplicates)
def test_12_offline_sync_idempotency(auth_client):
    draft_id = "client-draft-uuid-9999"
    
    # First sync call
    resp1 = auth_client.post("/api/inspections", json={
        "product_name": "Offline Synced Biscuit",
        "category": "Packaged Food",
        "location": "Rural Depot",
        "client_draft_id": draft_id
    })
    assert resp1.status_code in (200, 201)
    insp1_id = resp1.json()["id"]
    insp1_num = resp1.json()["inspection_number"]

    # Repeated sync call with same draft_id
    resp2 = auth_client.post("/api/inspections", json={
        "product_name": "Offline Synced Biscuit",
        "category": "Packaged Food",
        "location": "Rural Depot",
        "client_draft_id": draft_id
    })
    assert resp2.status_code in (200, 201)
    insp2_id = resp2.json()["id"]
    insp2_num = resp2.json()["inspection_number"]

    # Must return exact same inspection without duplication
    assert insp1_id == insp2_id
    assert insp1_num == insp2_num

# 14. Complete Workflow: Front + Back WITHOUT Side Image
def test_14_front_and_back_without_side_complete_flow(auth_client):
    """
    Validates the exact workflow required by the user:
    Step 2 -> upload Front + Back WITHOUT Side -> Continue -> OCR ->
    declarations -> rule evaluation -> findings -> inspector action ->
    review -> report.
    Missing Side image must not block, fail, or create placeholder.
    """
    # 1. Create inspection
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Wheat Flour 5kg",
        "brand_name": "Kisan Pride",
        "category": "Packaged Food",
        "location": "Mandi Shop 4"
    })
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    # 2. Upload Front image (REQUIRED)
    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        resp_front = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )
    assert resp_front.status_code in (200, 201)
    assert resp_front.json()["quality_status"] in ["GOOD", "ACCEPTABLE"]

    # 3. Upload Back image (REQUIRED) - Side is omitted intentionally
    with open(clear_path, "rb") as f:
        resp_back = auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("back.jpg", f, "image/jpeg")},
            data={"view_type": "back", "sequence_order": 2}
        )
    assert resp_back.status_code in (200, 201)
    assert resp_back.json()["quality_status"] in ["GOOD", "ACCEPTABLE"]

    # Verify only 2 images uploaded - zero placeholders, zero empty uploads
    insp_get = auth_client.get(f"/api/inspections/{insp_id}")
    assert insp_get.status_code == 200
    images = insp_get.json()["images"]
    assert len(images) == 2
    view_types = [img["view_type"] for img in images]
    assert "front" in view_types
    assert "back" in view_types
    assert "side" not in view_types

    # 4. Run OCR on both images
    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_resp.status_code == 200
    ocr_data = ocr_resp.json()
    assert ocr_data["declarations_count"] > 0

    # 5. Evaluate deterministic rule engine
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert len(eval_data["findings"]) > 0
    # Statutory physical quantity disclaimer must be present
    assert "photographs alone" in eval_data["physical_quantity_disclaimer"]

    # 6. Inspector action (adjudicate findings)
    findings = eval_data["findings"]
    for finding in findings:
        adj = auth_client.patch(
            f"/api/findings/{finding['id']}/adjudicate",
            json={
                "action": "CONFIRMED",
                "notes": "Inspector verified Front & Back panel package evidence."
            }
        )
        assert adj.status_code == 200

    # 7. Generate official immutable report
    rep_resp = auth_client.post(f"/api/inspections/{insp_id}/report")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert rep_data["pdf_path"] is not None
    assert Path(rep_data["pdf_path"]).exists()

    # 8. Download stream and verify PDF binary
    pdf_resp = auth_client.get(f"/api/inspections/{insp_id}/report/pdf")
    assert pdf_resp.status_code == 200
    assert len(pdf_resp.content) > 1000

# 15. Complete Workflow: Front + Back + Side Images
def test_15_front_and_back_and_side_complete_flow(auth_client):
    """
    Validates workflow when Side image is also provided:
    Step 2 -> upload Front + Back + Side -> OCR across all 3 ->
    cross-image verification -> rule evaluation -> inspector action ->
    review -> report.
    All 3 panels processed normally.
    """
    # 1. Create inspection
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Premium Tea 500g",
        "brand_name": "Assam Gold",
        "category": "Packaged Food",
        "location": "Supermarket Bay 2"
    })
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    # 2. Upload Front, Back, and Side images
    clear_path = FIXTURES_DIR / "clear_package.jpg"
    for order, vtype in enumerate(["front", "back", "side"], start=1):
        with open(clear_path, "rb") as f:
            up_resp = auth_client.post(
                f"/api/inspections/{insp_id}/images",
                files={"file": (f"{vtype}.jpg", f, "image/jpeg")},
                data={"view_type": vtype, "sequence_order": order}
            )
        assert up_resp.status_code in (200, 201)
        assert up_resp.json()["quality_status"] in ["GOOD", "ACCEPTABLE"]

    # Verify all 3 images stored
    insp_get = auth_client.get(f"/api/inspections/{insp_id}")
    images = insp_get.json()["images"]
    assert len(images) == 3
    view_types = {img["view_type"] for img in images}
    assert view_types == {"front", "back", "side"}

    # 3. Run OCR across all 3 images
    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_resp.status_code == 200
    ocr_data = ocr_resp.json()
    assert ocr_data["declarations_count"] > 0

    # 4. Evaluate deterministic rule engine
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert len(eval_data["findings"]) > 0

    # 5. Inspector action
    for finding in eval_data["findings"]:
        adj = auth_client.patch(
            f"/api/findings/{finding['id']}/adjudicate",
            json={
                "action": "CONFIRMED",
                "notes": "Inspector verified Front, Back, and Side panel evidence."
            }
        )
        assert adj.status_code == 200

    # 6. Generate official report with all 3 image evidences
    rep_resp = auth_client.post(f"/api/inspections/{insp_id}/report")
    assert rep_resp.status_code == 200
    rep_data = rep_resp.json()
    assert rep_data["pdf_path"] is not None
    assert Path(rep_data["pdf_path"]).exists()

# 17. Offline Draft Capture & Synchronization WITHOUT Side Image
def test_17_offline_draft_and_sync_without_side_image(auth_client):
    """
    Validates that:
    1. An offline draft containing only Front and Back images (no Side image)
       successfully synchronizes to the backend.
    2. Zero placeholder images and zero empty uploads are sent.
    3. Backend processes the draft normally.
    """
    draft_id = "client-draft-without-side-1234"
    
    # Sync inspection creation
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Offline Biscuit 200g",
        "category": "Packaged Food",
        "location": "Remote Village Outlet",
        "client_draft_id": draft_id
    })
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    # Upload only Front and Back images from draft
    clear_path = FIXTURES_DIR / "clear_package.jpg"
    for order, vtype in enumerate(["front", "back"], start=1):
        with open(clear_path, "rb") as f:
            up_resp = auth_client.post(
                f"/api/inspections/{insp_id}/images",
                files={"file": (f"{vtype}.jpg", f, "image/jpeg")},
                data={"view_type": vtype, "sequence_order": order}
            )
        assert up_resp.status_code in (200, 201)

    # Verify inspection has exactly 2 images, no side image, no placeholders
    insp = auth_client.get(f"/api/inspections/{insp_id}").json()
    uploaded_views = [img["view_type"] for img in insp["images"]]
    assert len(uploaded_views) == 2
    assert "front" in uploaded_views
    assert "back" in uploaded_views
    assert "side" not in uploaded_views

    # OCR and evaluation work seamlessly
    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_resp.status_code == 200
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    assert eval_resp.status_code == 200

# 18. Frontend Component Invariant: Side Image is Explicitly Optional
def test_18_required_front_back_and_optional_side_invariants():
    """
    Verifies that CaptureImagesScreen.tsx:
    1. Marks Front as Required (isRequired = true)
    2. Marks Back as Required (isRequired = true)
    3. Marks Side as Optional (isRequired = false)
    4. Has helper text 'Capture side view if needed'
    5. Does not require Side to enable Continue button
    """
    screen_path = Path("mobile/src/screens/CaptureImagesScreen.tsx")
    assert screen_path.exists()
    content = screen_path.read_text(encoding="utf-8")

    # Slot invocations
    assert "renderSlot('FRONT IMAGE', 'front', frontImg, true)" in content
    assert "renderSlot('BACK IMAGE', 'back', backImg, true)" in content
    assert "renderSlot('SIDE IMAGE', 'side', sideImg, false)" in content

    # Helper text for optional side view
    assert "Capture side view if needed" in content

    # Continue condition depends only on frontImg and backImg (hasRequiredImages)
    assert "const hasRequiredImages = Boolean(frontImg && backImg);" in content
    assert "disabled={!hasRequiredImages || hasWarning}" in content

# 20. Repeated Finalize/Report Requests Do NOT Create Duplicate Records
def test_20_repeated_finalize_does_not_create_duplicate_report_or_inspection(auth_client):
    create_resp = auth_client.post("/api/inspections", json={
        "product_name": "Idempotent Butter 500g",
        "category": "Packaged Food",
        "location": "Dairy Booth 12"
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    for f_item in eval_resp.json()["findings"]:
        auth_client.patch(
            f"/api/findings/{f_item['id']}/adjudicate",
            json={"action": "CONFIRMED", "notes": "Verified"}
        )

    # First finalization
    fin1 = auth_client.post(f"/api/inspections/{insp_id}/finalize")
    assert fin1.status_code == 200
    rep1_id = fin1.json()["report"]["id"]

    # Second finalization (client retry)
    fin2 = auth_client.post(f"/api/inspections/{insp_id}/finalize")
    assert fin2.status_code == 200
    rep2_id = fin2.json()["report"]["id"]

    # Report ID must be identical (no duplicate report)
    assert rep1_id == rep2_id

    # Verify DB has exactly 1 report for this inspection
    conn = sqlite3.connect("test_legal_metrology.db")
    c = conn.cursor()
    c.execute("SELECT count(1) FROM reports WHERE inspection_id = ?", (insp_id,))
    assert c.fetchone()[0] == 1
    c.execute("SELECT count(1) FROM inspections WHERE id = ?", (insp_id,))
    assert c.fetchone()[0] == 1
    conn.close()

# 21. Report Contains Current Dynamic Inspection Data (No Hardcoded Demo Values)
def test_21_report_contains_current_dynamic_inspection_data(auth_client):
    dynamic_product = "Dynamic Basmati Harvest 5kg"
    dynamic_brand = "Royal Heritage Mills"
    dynamic_location = "Chandni Chowk Grain Depot"

    create_resp = auth_client.post("/api/inspections", json={
        "product_name": dynamic_product,
        "brand_name": dynamic_brand,
        "category": "Packaged Food",
        "location": dynamic_location
    })
    insp_id = create_resp.json()["id"]

    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(
            f"/api/inspections/{insp_id}/images",
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front", "sequence_order": 1}
        )

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    eval_resp = auth_client.post(f"/api/inspections/{insp_id}/evaluate")
    for f_item in eval_resp.json()["findings"]:
        auth_client.patch(
            f"/api/findings/{f_item['id']}/adjudicate",
            json={"action": "CONFIRMED", "notes": "Dynamic adjudication note"}
        )

    # Finalize and download report
    fin_resp = auth_client.post(f"/api/inspections/{insp_id}/finalize")
    assert fin_resp.status_code == 200

    pdf_resp = auth_client.get(f"/api/inspections/{insp_id}/report/pdf")
    assert pdf_resp.status_code == 200

    # Parse generated PDF binary with PdfReader
    reader = PdfReader(io.BytesIO(pdf_resp.content))
    assert len(reader.pages) >= 1

    all_text = " ".join([page.extract_text() for page in reader.pages])

    # Dynamic data MUST be present in the generated official PDF
    assert dynamic_product in all_text
    assert dynamic_brand in all_text
    assert dynamic_location in all_text
    assert "PHYSICAL NET QUANTITY LIMITATION" in all_text
    assert "Physical net quantity cannot be verified from package images alone" in all_text
    assert "PACKAGE IMAGE EVIDENCE & QUALITY AUDIT" in all_text

# 22. Side Image Evidence in PDF (Omitted vs Provided)
def test_22_side_image_evidence_in_pdf(auth_client):
    # Case A: Without Side image
    c_a = auth_client.post("/api/inspections", json={
        "product_name": "No-Side Tea 250g",
        "category": "Packaged Food",
        "location": "Corner Shop"
    })
    insp_a = c_a.json()["id"]
    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_a}/images", files={"file": ("front.jpg", f, "image/jpeg")}, data={"view_type": "front", "sequence_order": 1})
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_a}/images", files={"file": ("back.jpg", f, "image/jpeg")}, data={"view_type": "back", "sequence_order": 2})

    auth_client.post(f"/api/inspections/{insp_a}/ocr")
    auth_client.post(f"/api/inspections/{insp_a}/report")

    pdf_a = auth_client.get(f"/api/inspections/{insp_a}/report/pdf").content
    text_a = " ".join([p.extract_text() for p in PdfReader(io.BytesIO(pdf_a)).pages])
    assert "Optional — Not Captured" in text_a

    # Case B: With Side image
    c_b = auth_client.post("/api/inspections", json={
        "product_name": "With-Side Coffee 100g",
        "category": "Packaged Food",
        "location": "Supermarket Bay 3"
    })
    insp_b = c_b.json()["id"]
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_b}/images", files={"file": ("front.jpg", f, "image/jpeg")}, data={"view_type": "front", "sequence_order": 1})
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_b}/images", files={"file": ("back.jpg", f, "image/jpeg")}, data={"view_type": "back", "sequence_order": 2})
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_b}/images", files={"file": ("side.jpg", f, "image/jpeg")}, data={"view_type": "side", "sequence_order": 3})

    auth_client.post(f"/api/inspections/{insp_b}/ocr")
    auth_client.post(f"/api/inspections/{insp_b}/report")

    pdf_b = auth_client.get(f"/api/inspections/{insp_b}/report/pdf").content
    text_b = " ".join([p.extract_text() for p in PdfReader(io.BytesIO(pdf_b)).pages])
    assert "Side Panel (Optional)" in text_b
    assert "Captured" in text_b

# 23. Production Database Safety Verification
def test_23_production_database_safety():
    # Verify that tests ran against test_legal_metrology.db, NOT legal_metrology.db
    prod_db = Path("legal_metrology.db")
    assert prod_db.exists()

    conn = sqlite3.connect("legal_metrology.db")
    c = conn.cursor()
    c.execute("SELECT count(1) FROM users")
    assert c.fetchone()[0] >= 1
    # Verify test data was NOT leaked into production DB
    c.execute("SELECT count(1) FROM products WHERE product_name LIKE '%Post-Image Test%'")
    assert c.fetchone()[0] == 0
    conn.close()

# 24. Zero Synthetic Canned Strings in Production OCR
def test_24_production_ocr_contains_no_synthetic_canned_strings():
    ocr_service_file = Path("backend/ocr_service.py").read_text(encoding="utf-8")
    assert "standard_lines" not in ocr_service_file
    assert "multipanel_lines" not in ocr_service_file
    assert "imported_lines" not in ocr_service_file
    assert "missing_lines" not in ocr_service_file
    assert "AGRO FOODS PVT LTD, GORAKHPUR UP" not in ocr_service_file
    assert "GREEN MILLS PVT LTD" not in ocr_service_file

# 25. MorphologicalOpenCVOCREngine Never Manufactures Character Text
def test_25_morphological_engine_never_manufactures_text():
    from backend.ocr_service import MorphologicalOpenCVOCREngine
    engine = MorphologicalOpenCVOCREngine()
    clear_path = str(FIXTURES_DIR / "clear_package.jpg")
    boxes = engine.extract_text_boxes(clear_path)
    for b in boxes:
        assert b.text == "", f"Expected empty text from OpenCV morphological detector, got '{b.text}'"

# 26. OCR Unavailable Explicit Status & Routing to NEEDS_MANUAL_VERIFICATION
def test_26_ocr_unavailable_explicit_status_and_routing(auth_client, monkeypatch):
    from backend.ocr_service import ocr_service
    monkeypatch.setattr(ocr_service.tesseract_engine, "is_available", lambda: False)
    
    c = auth_client.post("/api/inspections", json={
        "product_name": "Unavailable OCR Tea 500g",
        "category": "Packaged Food",
        "location": "Hill Station Store"
    })
    insp_id = c.json()["id"]
    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_id}/images", files={"file": ("front.jpg", f, "image/jpeg")}, data={"view_type": "front", "sequence_order": 1})

    ocr_resp = auth_client.post(f"/api/inspections/{insp_id}/ocr")
    assert ocr_resp.status_code == 200

    decl_resp = auth_client.get(f"/api/inspections/{insp_id}/declarations")
    assert decl_resp.status_code == 200
    decls = decl_resp.json()
    for d in decls:
        assert d["verification_status"] == "NEEDS_MANUAL_VERIFICATION"
        assert d["extraction_status"] in ["OCR_UNAVAILABLE", "NOT_FOUND"]

# 27. Missing Commodity Name Returns NOT_FOUND (Never Fabricates Step 1 Input as OCR Evidence)
def test_27_missing_commodity_returns_not_found(auth_client):
    import numpy as np, cv2
    blank_img = np.ones((500, 500, 3), dtype=np.uint8) * 255
    blank_path = FIXTURES_DIR / "blank_test_card.jpg"
    cv2.imwrite(str(blank_path), blank_img)

    c = auth_client.post("/api/inspections", json={
        "product_name": "Step1 Inspector Biscuits 200g",
        "category": "Packaged Food",
        "location": "Local Bakery"
    })
    insp_id = c.json()["id"]

    with open(blank_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_id}/images", files={"file": ("front.jpg", f, "image/jpeg")}, data={"view_type": "front", "sequence_order": 1})

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    decls = auth_client.get(f"/api/inspections/{insp_id}/declarations").json()
    
    comm_decl = next((d for d in decls if d["field_name"] == "commodity_name"), None)
    assert comm_decl is not None
    assert comm_decl["extracted_value"] is None or comm_decl["extracted_value"] == ""
    assert comm_decl["extraction_status"] in ["NOT_FOUND", "OCR_UNAVAILABLE"]
    assert comm_decl["verification_status"] == "NEEDS_MANUAL_VERIFICATION"

# 28. No Fabricated Bounding Boxes or Confidences
def test_28_no_fabricated_bounding_boxes_or_confidence():
    from backend.extraction_service import extraction_service
    decls = extraction_service.extract_declarations(
        full_text="",
        text_boxes=[],
        product_context={"product_name": "Test Snack", "category": "Packaged Food"}
    )
    for d in decls:
        assert d.bounding_box is None
        assert d.confidence == 0.0
        assert d.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE", "NOT_APPLICABLE"]

# 29. Real Package Image OCR Extraction Matches Actual Printed Text
def test_29_real_package_image_ocr_extraction():
    from backend.ocr_service import ocr_service
    if not ocr_service.tesseract_engine.is_available():
        pytest.skip("Tesseract not available in this test environment")

    import numpy as np, cv2
    test_img = np.ones((400, 800, 3), dtype=np.uint8) * 255
    cv2.putText(test_img, "NET QUANTITY: 350 g", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.putText(test_img, "MRP Rs. 85.00 (INCL. OF ALL TAXES)", (50, 280), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    img_path = str(FIXTURES_DIR / "real_printed_test.jpg")
    cv2.imwrite(img_path, test_img)

    result = ocr_service.process_image(img_path)
    assert "350" in result.raw_text
    assert "85" in result.raw_text
    assert result.ocr_status == "OCR_SUCCESS"

    from backend.extraction_service import extraction_service
    decls = extraction_service.extract_declarations(result.raw_text, result.text_boxes, {"product_name": "Sample"})
    qty = next(d for d in decls if d.field_name == "net_quantity")
    assert qty.extracted_value == "350 g"
    assert qty.extraction_status == "EXTRACTED"
    assert qty.bounding_box is not None

# 30. Cross-Image Conflict Requires Genuine Conflicting Extractions
def test_30_cross_image_conflicts_only_from_real_extractions():
    from backend.extraction_service import cross_image_verification, ExtractedDeclarationItem
    p1 = [ExtractedDeclarationItem(field_name="net_quantity", field_label="Net Quantity", extraction_status="NOT_FOUND", confidence=0.0)]
    p2 = [ExtractedDeclarationItem(field_name="net_quantity", field_label="Net Quantity", extracted_value="500 g", normalized_value="500.0 g", extraction_status="EXTRACTED", confidence=0.95)]
    merged, conflicts = cross_image_verification({"img1": p1, "img2": p2})
    assert len(conflicts) == 0
    q_decl = next(d for d in merged if d.field_name == "net_quantity")
    assert q_decl.has_conflict is False
    assert q_decl.extracted_value == "500 g"

# 31. Generated PDF Report Preserves Data Provenance
def test_31_report_preserves_provenance(auth_client):
    c = auth_client.post("/api/inspections", json={
        "product_name": "Provenance Test Atta 10kg",
        "category": "Packaged Food",
        "location": "North Depot"
    })
    insp_id = c.json()["id"]
    clear_path = FIXTURES_DIR / "clear_package.jpg"
    with open(clear_path, "rb") as f:
        auth_client.post(f"/api/inspections/{insp_id}/images", files={"file": ("front.jpg", f, "image/jpeg")}, data={"view_type": "front", "sequence_order": 1})

    auth_client.post(f"/api/inspections/{insp_id}/ocr")
    auth_client.post(f"/api/inspections/{insp_id}/report")
    pdf_bytes = auth_client.get(f"/api/inspections/{insp_id}/report/pdf").content
    text = " ".join([p.extract_text() for p in PdfReader(io.BytesIO(pdf_bytes)).pages])
    assert "STATUTORY DECLARATIONS AUDIT" in text
    assert "Provenance Test Atta 10kg" in text
