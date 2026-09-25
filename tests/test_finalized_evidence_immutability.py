"""
tests/test_finalized_evidence_immutability.py

Comprehensive test suite verifying that for finalized inspections (status == COMPLETED or official report exists):
1. DELETE finalized image -> rejected with HTTP 409 Conflict.
2. POST /api/inspections/{id}/images (upload replacement/new image) -> rejected with HTTP 409 Conflict.
3. PATCH /api/declarations/{id} (modify declaration value/metadata) -> rejected with HTTP 409 Conflict.
4. Replace finalized image file / rerun OCR -> rejected with HTTP 409 Conflict.
5. Modify finalized evidence association / re-adjudicate -> rejected with HTTP 409 Conflict.
6. Normal draft image & evidence operations retain intended behavior before finalization.
"""

import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

@pytest.fixture(scope="module")
def inspector_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": settings.SEED_OFFICER_ID, "password": settings.SEED_OFFICER_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def _wait_for_ocr_completion(client: TestClient, token: str, insp_id: str, max_wait_sec: float = 60.0):
    """Waits for durable OCR processing to finish via /ocr/status endpoint."""
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        st_resp = client.get(f"/api/inspections/{insp_id}/ocr/status", headers=_auth(token))
        if st_resp.status_code == 200:
            st_data = st_resp.json()
            status = st_data.get("status")
            if status == "COMPLETED":
                return st_data
            elif status == "FAILED":
                raise AssertionError(f"Durable OCR job failed: {st_data.get('error_message')}")
        time.sleep(1.0)
    raise AssertionError(f"Timed out waiting for OCR job on inspection {insp_id} after {max_wait_sec}s")


def _create_and_finalize_inspection(client: TestClient, token: str, name_suffix: str = "1"):
    """Helper to create an inspection, upload image, run OCR, evaluate, and generate official report."""
    insp_resp = client.post(
        "/api/inspections",
        json={
            "location": f"Market {name_suffix}",
            "product_name": f"Product {name_suffix}",
            "brand_name": "Brand",
            "category": "Packaged Food",
        },
        headers=_auth(token),
    )
    assert insp_resp.status_code == 201, insp_resp.text
    insp_id = insp_resp.json()["id"]

    img_path = FIXTURES_DIR / "clear_package.jpg"
    with open(img_path, "rb") as f:
        up_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=_auth(token),
            files={"file": ("clear_package.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert up_resp.status_code == 201, up_resp.text
    img_id = up_resp.json()["id"]

    # Run OCR
    ocr_resp = client.post(f"/api/inspections/{insp_id}/ocr", headers=_auth(token))
    assert ocr_resp.status_code in (200, 202), ocr_resp.text
    if ocr_resp.status_code == 202:
        _wait_for_ocr_completion(client, token, insp_id)

    # Evaluate rules
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=_auth(token))
    assert eval_resp.status_code == 200, eval_resp.text

    # Generate Report (which finalizes / attaches official statutory report)
    rpt_resp = client.post(f"/api/inspections/{insp_id}/report", headers=_auth(token))
    assert rpt_resp.status_code in (200, 201), rpt_resp.text

    return insp_id, img_id

def test_01_delete_finalized_image_rejected(client: TestClient, inspector_token: str):
    """DELETE finalized image must be rejected with HTTP 409 Conflict."""
    insp_id, img_id = _create_and_finalize_inspection(client, inspector_token, "del_img")
    del_resp = client.delete(f"/api/images/{img_id}", headers=_auth(inspector_token))
    assert del_resp.status_code == 409, f"Expected 409 Conflict, got {del_resp.status_code}: {del_resp.text}"
    assert "evidence cannot be deleted after inspection finalization" in del_resp.json()["detail"].lower()

def test_02_post_finalized_image_rejected(client: TestClient, inspector_token: str):
    """POST image to finalized inspection must be rejected with HTTP 409 Conflict."""
    insp_id, _ = _create_and_finalize_inspection(client, inspector_token, "post_img")
    img_path = FIXTURES_DIR / "clear_package.jpg"
    with open(img_path, "rb") as f:
        up_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=_auth(inspector_token),
            files={"file": ("clear_package.jpg", f, "image/jpeg")},
            data={"view_type": "back"}
        )
    assert up_resp.status_code == 409, f"Expected 409 Conflict, got {up_resp.status_code}: {up_resp.text}"
    assert "cannot be modified, uploaded, or replaced" in up_resp.json()["detail"].lower()

def test_03_patch_finalized_declaration_rejected(client: TestClient, inspector_token: str):
    """PATCH declaration on finalized inspection must be rejected with HTTP 409 Conflict."""
    insp_id, _ = _create_and_finalize_inspection(client, inspector_token, "patch_decl")
    decl_resp = client.get(f"/api/inspections/{insp_id}/declarations", headers=_auth(inspector_token))
    assert decl_resp.status_code == 200
    decls = decl_resp.json()
    assert len(decls) > 0
    target_decl_id = decls[0]["id"]

    patch_resp = client.patch(
        f"/api/declarations/{target_decl_id}",
        headers=_auth(inspector_token),
        json={"corrected_value": "Tampered Value", "correction_reason": "Illegal edit"}
    )
    assert patch_resp.status_code == 409, f"Expected 409 Conflict, got {patch_resp.status_code}: {patch_resp.text}"
    assert "cannot be modified after inspection finalization" in patch_resp.json()["detail"].lower()

def test_04_rerun_ocr_or_evaluate_on_finalized_inspection_rejected(client: TestClient, inspector_token: str):
    """POST /ocr and POST /evaluate on finalized inspection must be rejected with HTTP 409 Conflict."""
    insp_id, _ = _create_and_finalize_inspection(client, inspector_token, "rerun_ocr")

    ocr_resp = client.post(f"/api/inspections/{insp_id}/ocr", headers=_auth(inspector_token))
    assert ocr_resp.status_code == 409, f"Expected 409 on OCR re-run, got {ocr_resp.status_code}: {ocr_resp.text}"

    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=_auth(inspector_token))
    assert eval_resp.status_code == 409, f"Expected 409 on evaluate re-run, got {eval_resp.status_code}: {eval_resp.text}"

def test_05_modify_finalized_adjudication_rejected(client: TestClient, inspector_token: str):
    """PATCH /findings/{id}/adjudicate and request-new-image on finalized inspection must be rejected with HTTP 409."""
    insp_id, _ = _create_and_finalize_inspection(client, inspector_token, "adjudicate_final")
    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers=_auth(inspector_token))
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    assert len(findings) > 0
    finding_id = findings[0]["id"]

    adj_resp = client.patch(
        f"/api/findings/{finding_id}/adjudicate",
        headers=_auth(inspector_token),
        json={"action": "CONFIRMED", "notes": "Post-finalization attempt"}
    )
    assert adj_resp.status_code == 409, f"Expected 409 on adjudication, got {adj_resp.status_code}: {adj_resp.text}"

    req_img_resp = client.post(
        f"/api/findings/{finding_id}/request-new-image",
        headers=_auth(inspector_token)
    )
    assert req_img_resp.status_code == 409, f"Expected 409 on request-new-image, got {req_img_resp.status_code}: {req_img_resp.text}"

def test_06_draft_inspection_operations_retain_intended_behavior(client: TestClient, inspector_token: str):
    """Unfinalized draft inspections retain full legitimate editing and modification capabilities."""
    insp_resp = client.post(
        "/api/inspections",
        json={
            "location": "Draft Market",
            "product_name": "Draft Biscuit",
            "brand_name": "DraftBrand",
            "category": "Packaged Food",
        },
        headers=_auth(inspector_token),
    )
    assert insp_resp.status_code == 201
    draft_id = insp_resp.json()["id"]

    # Image upload works on draft
    img_path = FIXTURES_DIR / "clear_package.jpg"
    with open(img_path, "rb") as f:
        up_resp = client.post(
            f"/api/inspections/{draft_id}/images",
            headers=_auth(inspector_token),
            files={"file": ("clear_package.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert up_resp.status_code == 201
    draft_img_id = up_resp.json()["id"]

    # OCR works on draft
    ocr_resp = client.post(f"/api/inspections/{draft_id}/ocr", headers=_auth(inspector_token))
    assert ocr_resp.status_code in (200, 202), ocr_resp.text
    if ocr_resp.status_code == 202:
        _wait_for_ocr_completion(client, inspector_token, draft_id)

    # Declaration edit works on draft
    decl_resp = client.get(f"/api/inspections/{draft_id}/declarations", headers=_auth(inspector_token))
    decls = decl_resp.json()
    assert len(decls) > 0
    target_decl_id = decls[0]["id"]
    patch_resp = client.patch(
        f"/api/declarations/{target_decl_id}",
        headers=_auth(inspector_token),
        json={"corrected_value": "Legitimate Draft Correction", "correction_reason": "Pre-finalization correction"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["effective_value"] == "Legitimate Draft Correction"

    # Image deletion works on draft
    del_resp = client.delete(f"/api/images/{draft_img_id}", headers=_auth(inspector_token))
    assert del_resp.status_code == 200
