"""
tests/test_system_qa_deep_hunt.py

Deep QA Bug Hunt & Remediation Suite for NiriKsha.
Tests boundary values, injection, malformed requests, idempotency,
duplicate submissions, image validation, unicode/Hindi text, and authorization.
"""

import io
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.models import Inspection, Product, ProductImage, Declaration, ComplianceCheck, Report

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/auth/login", json={
        "officer_id": "DOCA-INSP-842",
        "password": "admin123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# ============================================================================
# 1. AUTHENTICATION & AUTHORIZATION HARDENING
# ============================================================================

def test_auth_invalid_credentials(client):
    """Ensure invalid password returns 401, not 500."""
    resp = client.post("/api/auth/login", json={
        "officer_id": "DOCA-INSP-842",
        "password": "wrongpassword"
    })
    assert resp.status_code == 401
    assert "Invalid" in resp.text

def test_auth_nonexistent_user(client):
    """Ensure nonexistent officer returns 401, not 500."""
    resp = client.post("/api/auth/login", json={
        "officer_id": "NONEXISTENT_OFFICER_999",
        "password": "any"
    })
    assert resp.status_code == 401

def test_auth_missing_fields(client):
    """Ensure missing fields return 422 Unprocessable Entity."""
    resp = client.post("/api/auth/login", json={"officer_id": "DOCA-INSP-842"})
    assert resp.status_code == 422

def test_protected_endpoints_require_token(client):
    """Ensure protected endpoints return 401 when no token is supplied."""
    endpoints = [
        ("GET", "/api/inspections"),
        ("POST", "/api/inspections"),
        ("GET", "/api/rules"),
    ]
    for method, path in endpoints:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code in (401, 403), f"Endpoint {path} did not reject unauthenticated request: {resp.status_code}"

def test_protected_endpoints_reject_tampered_token(client):
    """Ensure tampered/malformed Bearer token returns 401."""
    tampered_headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalidpayload.invalidsig"}
    resp = client.get("/api/inspections", headers=tampered_headers)
    assert resp.status_code == 401

# ============================================================================
# 2. INPUT VALIDATION & FUZZING (STEP 1: INSPECTION CREATION)
# ============================================================================

def test_create_inspection_missing_location(client, auth_headers):
    """Ensure missing location is rejected with 422."""
    payload = {
        "category": "Packaged Food",
        "product_name": "Test Rice"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp.status_code == 422

def test_create_inspection_invalid_category(client, auth_headers):
    """Ensure non-standard category is rejected with 422."""
    payload = {
        "category": "Automotive Parts",  # Invalid category under PCR 2011 scope
        "product_name": "Brake Pad",
        "location": "Sector 18 Noida"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp.status_code == 422

def test_create_inspection_with_whitespace_product_name(client, auth_headers):
    """Ensure whitespace-only product name is rejected or cleaned."""
    payload = {
        "category": "Packaged Food",
        "product_name": "    ",
        "location": "Azadpur Mandi"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    # If accepted, check whether it stripped or if it rejected
    if resp.status_code in (200, 201):
        # If accepted, it shouldn't store pure whitespace
        pname = resp.json().get("product", {}).get("product_name", "")
        assert pname.strip() != "" or resp.status_code in (400, 422)
    else:
        assert resp.status_code in (400, 422)

def test_create_inspection_with_unicode_and_hindi_text(client, auth_headers):
    """Ensure Hindi text and special Unicode characters are stored and retrieved cleanly."""
    hindi_name = "हिमालयन पतंजलि जैविक ओट्स"
    hindi_brand = "पतंजलि"
    payload = {
        "category": "Packaged Food",
        "product_name": hindi_name,
        "brand_name": hindi_brand,
        "location": "चांदनी चौक, नई दिल्ली",
        "notes": "परीक्षण निरीक्षण नोट — ₹180.50 मूल्य"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp.status_code in (200, 201), f"Failed creating inspection with Hindi text: {resp.text}"
    insp_id = resp.json()["id"]

    # Verify retrieval
    get_resp = client.get(f"/api/inspections/{insp_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    prod_info = get_resp.json().get("product", {})
    assert prod_info.get("product_name") == hindi_name
    assert prod_info.get("brand_name") == hindi_brand

def test_create_inspection_with_oversized_text(client, auth_headers):
    """Ensure huge inputs (e.g. 50,000 chars) are handled safely without 500 crash."""
    huge_text = "A" * 50000
    payload = {
        "category": "Packaged Food",
        "product_name": huge_text,
        "location": "Warehouse 4"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    # Backend may accept it or reject with 422, but MUST NOT crash with 500
    assert resp.status_code != 500

# ============================================================================
# 3. IDEMPOTENT OFFLINE SYNC & DUPLICATE CREATION PREVENTION
# ============================================================================

def test_duplicate_inspection_submission_same_draft_id(client, auth_headers):
    """Ensure multiple submissions with the same client_draft_id create only ONE inspection."""
    draft_id = "draft-uuid-qa-test-12345"
    payload = {
        "client_draft_id": draft_id,
        "category": "Packaged Food",
        "product_name": "Idempotency Test Oatmeal",
        "location": "Oatmeal Mandi, Delhi"
    }

    # First request
    resp1 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp1.status_code in (200, 201), f"First request failed: {resp1.text}"
    id1 = resp1.json()["id"]

    # Second request (e.g. rapid double click or network retry)
    resp2 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp2.status_code in (200, 201), f"Second request failed: {resp2.text}"
    id2 = resp2.json()["id"]

    assert id1 == id2, f"Idempotency violated: got two different IDs for same draft: {id1} vs {id2}"

# ============================================================================
# 4. IMAGE UPLOAD VALIDATION & SECURITY
# ============================================================================

def test_upload_non_image_file_rejected(client, auth_headers):
    """Ensure non-image files (.exe, .py, .txt) are rejected with 400/422."""
    create_resp = client.post("/api/inspections", json={
        "category": "Packaged Food",
        "product_name": "Security File Test",
        "location": "Test Location"
    }, headers=auth_headers)
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    # Attempt uploading an executable / script disguised as image
    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00This is not a real image")
    files = {"file": ("malicious.exe", fake_exe, "application/octet-stream")}
    resp = client.post(
        f"/api/inspections/{insp_id}/images",
        params={"view_type": "front"},
        files=files,
        headers=auth_headers
    )
    assert resp.status_code in (400, 415, 422), f"Executable upload should be rejected, got: {resp.status_code}"

def test_upload_empty_zero_byte_file(client, auth_headers):
    """Ensure 0-byte file is rejected cleanly without 500 error."""
    create_resp = client.post("/api/inspections", json={
        "category": "Packaged Food",
        "product_name": "Zero Byte Test",
        "location": "Test Location"
    }, headers=auth_headers)
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    empty_file = io.BytesIO(b"")
    files = {"file": ("empty.jpg", empty_file, "image/jpeg")}
    resp = client.post(
        f"/api/inspections/{insp_id}/images",
        params={"view_type": "front"},
        files=files,
        headers=auth_headers
    )
    assert resp.status_code in (400, 422), f"0-byte file should be rejected with 400/422, got: {resp.status_code}"

def test_upload_path_traversal_filename(client, auth_headers):
    """Ensure directory traversal in filename (../../evil.jpg) is sanitized."""
    create_resp = client.post("/api/inspections", json={
        "category": "Packaged Food",
        "product_name": "Path Traversal Test",
        "location": "Test Location"
    }, headers=auth_headers)
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    # Minimal valid 1x1 JPEG bytes
    valid_jpg_bytes = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x01, 0x00, 0x48, 0x00, 0x48, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x03, 0x02, 0x02, 0x03, 0x02, 0x02, 0x03, 0x03, 0x03, 0x03, 0x04,
        0x03, 0x03, 0x04, 0x05, 0x08, 0x05, 0x05, 0x04, 0x04, 0x05, 0x0A, 0x07,
        0x07, 0x06, 0x08, 0x0C, 0x0A, 0x0C, 0x0C, 0x0B, 0x0A, 0x0B, 0x0B, 0x0D,
        0x0E, 0x12, 0x10, 0x0D, 0x0E, 0x11, 0x0E, 0x0B, 0x0B, 0x10, 0x16, 0x10,
        0x11, 0x13, 0x14, 0x15, 0x15, 0x15, 0x0C, 0x0F, 0x17, 0x18, 0x16, 0x14,
        0x18, 0x12, 0x14, 0x15, 0x14, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
        0x00, 0xBF, 0x00, 0xFF, 0xD9
    ])
    files = {"file": ("../../../../evil_overwrite.jpg", io.BytesIO(valid_jpg_bytes), "image/jpeg")}
    resp = client.post(
        f"/api/inspections/{insp_id}/images",
        params={"view_type": "front"},
        files=files,
        headers=auth_headers
    )
    if resp.status_code in (200, 201):
        file_path = resp.json()["file_path"]
        assert ".." not in file_path, f"Path traversal unescaped in saved file path: {file_path}"

# ============================================================================
# 5. FINDINGS & ADJUDICATION GATES
# ============================================================================

def test_adjudicate_nonexistent_finding(client, auth_headers):
    """Ensure adjudicating non-existent finding returns 404, not 500."""
    resp = client.patch(
        "/api/findings/nonexistent-finding-uuid-9999/adjudicate",
        json={"action": "CONFIRMED", "notes": "Test notes"},
        headers=auth_headers
    )
    assert resp.status_code == 404

def test_adjudicate_invalid_action(client, auth_headers):
    """Ensure invalid action in adjudication is rejected with 400/422."""
    create_resp = client.post("/api/inspections", json={
        "category": "Packaged Food",
        "product_name": "Finding Action Test",
        "location": "Test Location"
    }, headers=auth_headers)
    assert create_resp.status_code in (200, 201)
    insp_id = create_resp.json()["id"]

    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=auth_headers)
    assert eval_resp.status_code == 200

    find_resp = client.get(f"/api/inspections/{insp_id}/findings", headers=auth_headers)
    findings = find_resp.json()
    if findings:
        fid = findings[0]["id"]
        bad_resp = client.patch(
            f"/api/findings/{fid}/adjudicate",
            json={"action": "INVALID_ACTION_XYZ", "notes": "Test notes"},
            headers=auth_headers
        )
        assert bad_resp.status_code in (400, 422), f"Invalid action should be rejected, got: {bad_resp.status_code}"

# ============================================================================
# 6. REPORT INTEGRITY & IMMUTABILITY
# ============================================================================

def test_get_report_nonexistent_inspection(client, auth_headers):
    """Ensure requesting report for nonexistent inspection returns 404."""
    resp = client.get("/api/inspections/nonexistent-insp-id/report", headers=auth_headers)
    assert resp.status_code == 404

def test_get_pdf_nonexistent_inspection(client, auth_headers):
    """Ensure requesting PDF for nonexistent inspection returns 404."""
    resp = client.get("/api/inspections/nonexistent-insp-id/report/pdf", headers=auth_headers)
    assert resp.status_code == 404

def test_delete_report_endpoint_does_not_exist(client, auth_headers):
    """Ensure report deletion endpoint does NOT exist (official reports are immutable)."""
    resp = client.delete("/api/inspections/any-id/report", headers=auth_headers)
    assert resp.status_code in (404, 405), f"DELETE report must not exist, got: {resp.status_code}"
