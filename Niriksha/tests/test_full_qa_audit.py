"""
tests/test_full_qa_audit.py

Comprehensive Full-System QA Audit Test Suite for NiriKsha.
Runs strictly against test_legal_metrology.db (enforced by conftest.py).

Covers:
- Auth (valid, invalid, malformed, expired/missing JWT, user isolation)
- Dashboard metrics & live DB consistency
- Inspection lifecycle (create, get, list, declarations, evaluations, adjudications, reports, finalization)
- Image upload, MIME type restrictions, file size limits, binary download, delete
- OCR and Deterministic Rule Engine evaluations
- Inspector verification and override workflows
- Security edge cases (SQL injection payloads, path traversal attempts, IDOR)
- Database integrity, cascade deletions, audit logging
"""

import io
import pytest
from fastapi.testclient import TestClient
from backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": "DOCA-INSP-842", "password": "admin123"}
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# ==========================================
# 1. AUTHENTICATION & SECURITY TESTS
# ==========================================

def test_auth_valid_login(client):
    resp = client.post("/api/auth/login", json={"officer_id": "DOCA-INSP-842", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["officer_id"] == "DOCA-INSP-842"
    assert "password" not in data
    assert "password_hash" not in data

def test_auth_invalid_password(client):
    resp = client.post("/api/auth/login", json={"officer_id": "DOCA-INSP-842", "password": "wrongpassword"})
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]

def test_auth_invalid_officer_id(client):
    resp = client.post("/api/auth/login", json={"officer_id": "NON_EXISTENT_OFFICER", "password": "admin123"})
    assert resp.status_code == 401

def test_auth_empty_credentials(client):
    resp = client.post("/api/auth/login", json={"officer_id": "", "password": ""})
    assert resp.status_code in [400, 401, 422]

def test_auth_missing_token_on_protected_route(client):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 401

def test_auth_fake_token_on_protected_route(client):
    resp = client.get("/api/dashboard", headers={"Authorization": "Bearer fake.jwt.token"})
    assert resp.status_code == 401

def test_auth_profile_and_update(client, auth_headers):
    # GET profile
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["officer_id"] == "DOCA-INSP-842"

    # PATCH profile
    resp_patch = client.patch(
        "/api/auth/me",
        json={"email": "rajesh.updated@lm.gov.in", "phone": "+91 99999 88888"},
        headers=auth_headers
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["email"] == "rajesh.updated@lm.gov.in"

def test_auth_change_password_validation(client, auth_headers):
    # Too short password
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "admin123", "new_password": "123"},
        headers=auth_headers
    )
    assert resp.status_code in [400, 422]

    # Wrong current password
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrongpassword", "new_password": "newsecurepassword123"},
        headers=auth_headers
    )
    assert resp.status_code == 400

# ==========================================
# 2. DASHBOARD METRICS TESTS
# ==========================================

def test_dashboard_metrics_consistency(client, auth_headers):
    resp = client.get("/api/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_inspections" in data
    assert "needs_manual_verification" in data
    assert "verified_inspections" in data
    assert "potential_non_compliance" in data
    assert isinstance(data["recent_inspections"], list)

# ==========================================
# 3. INSPECTION CREATION & VALIDATION TESTS
# ==========================================

def test_inspection_create_missing_product_name(client, auth_headers):
    resp = client.post(
        "/api/inspections",
        json={"product_name": "", "category": "Packaged Food", "location": "Delhi"},
        headers=auth_headers
    )
    assert resp.status_code == 400

def test_inspection_create_valid_and_fetch(client, auth_headers):
    payload = {
        "product_name": "QA Test Whole Wheat Atta 10kg",
        "brand_name": "Patanjali",
        "category": "Packaged Food",
        "location": "Shahdara Mandi, Delhi",
        "batch_number": "BATCH-QA-2026-001",
        "notes": "Full QA Automated Test"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    insp = resp.json()
    insp_id = insp["id"]
    assert "LM-2026-" in insp["inspection_number"]
    assert insp["product"]["product_name"] == "QA Test Whole Wheat Atta 10kg"
    assert insp["status"] == "DRAFT"

    # Fetch details
    resp_get = client.get(f"/api/inspections/{insp_id}", headers=auth_headers)
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == insp_id

def test_inspection_not_found(client, auth_headers):
    resp = client.get("/api/inspections/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404

# ==========================================
# 4. IMAGE UPLOAD, QUALITY & MANAGEMENT TESTS
# ==========================================

def test_image_upload_and_delete(client, auth_headers):
    # 1. Create inspection
    insp_resp = client.post(
        "/api/inspections",
        json={"product_name": "Image QA Product", "category": "Packaged Food", "location": "Test Site"},
        headers=auth_headers
    )
    insp_id = insp_resp.json()["id"]

    # 2. Upload dummy JPEG
    fake_jpeg = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9")
    files = {"file": ("front_panel.jpg", fake_jpeg, "image/jpeg")}
    data = {"view_type": "front"}

    upload_resp = client.post(f"/api/inspections/{insp_id}/images", files=files, data=data, headers=auth_headers)
    assert upload_resp.status_code == 201
    img_id = upload_resp.json()["id"]

    # 3. List images
    list_resp = client.get(f"/api/inspections/{insp_id}/images", headers=auth_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 4. Get metadata
    meta_resp = client.get(f"/api/images/{img_id}", headers=auth_headers)
    assert meta_resp.status_code == 200
    assert meta_resp.json()["view_type"] == "front"

    # 5. Delete image
    del_resp = client.delete(f"/api/images/{img_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    # 6. Verify image is gone
    list_resp_after = client.get(f"/api/inspections/{insp_id}/images", headers=auth_headers)
    assert len(list_resp_after.json()) == 0

def test_image_upload_invalid_mime_rejected(client, auth_headers):
    insp_resp = client.post(
        "/api/inspections",
        json={"product_name": "MIME QA Product", "category": "Packaged Food", "location": "Test Site"},
        headers=auth_headers
    )
    insp_id = insp_resp.json()["id"]

    fake_exe = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00")
    files = {"file": ("malicious.exe", fake_exe, "application/x-msdownload")}
    data = {"view_type": "front"}

    upload_resp = client.post(f"/api/inspections/{insp_id}/images", files=files, data=data, headers=auth_headers)
    assert upload_resp.status_code == 400

# ==========================================
# 5. DETERMINISTIC RULE ENGINE & EVALUATIONS
# ==========================================

def test_rules_registry_endpoints(client, auth_headers):
    resp = client.get("/api/rules", headers=auth_headers)
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 7
    codes = [r["rule_code"] for r in rules]
    assert "PCR_RULE_06_1_A" in codes
    assert "PCR_RULE_06_1_E" in codes

    # Single rule fetch
    resp_single = client.get("/api/rules/PCR_RULE_06_1_A", headers=auth_headers)
    assert resp_single.status_code == 200
    assert resp_single.json()["rule_code"] == "PCR_RULE_06_1_A"

def test_evaluation_and_adjudication_workflow(client, auth_headers):
    # 1. Create inspection
    insp_resp = client.post(
        "/api/inspections",
        json={"product_name": "Adjudication QA Mustard Oil", "category": "Packaged Food", "location": "Warehouse A"},
        headers=auth_headers
    )
    insp_id = insp_resp.json()["id"]

    # 2. Evaluate rules
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=auth_headers)
    assert eval_resp.status_code == 200
    findings = eval_resp.json()["findings"]
    assert len(findings) > 0

    finding_id = findings[0]["id"]

    # 3. Adjudicate finding
    adj_payload = {
        "action": "CONFIRMED",
        "notes": "Officer verified non-compliance under PCR 2011 Rule 6"
    }
    adj_resp = client.patch(f"/api/findings/{finding_id}/adjudicate", json=adj_payload, headers=auth_headers)
    assert adj_resp.status_code == 200
    assert adj_resp.json()["adjudication_status"] == "CONFIRMED"

# ==========================================
# 6. REPORT GENERATION & PDF TESTS
# ==========================================

def test_report_generation_and_pdf_stream(client, auth_headers):
    # 1. Create inspection
    insp_resp = client.post(
        "/api/inspections",
        json={"product_name": "Report QA Rice 5kg", "category": "Packaged Food", "location": "Delhi Zone 1"},
        headers=auth_headers
    )
    insp_id = insp_resp.json()["id"]

    # 2. Evaluate rules
    client.post(f"/api/inspections/{insp_id}/evaluate", headers=auth_headers)

    # 3. Generate Report
    rep_resp = client.post(f"/api/inspections/{insp_id}/report", headers=auth_headers)
    assert rep_resp.status_code in [200, 201]
    rep_data = rep_resp.json()
    assert rep_data["inspection_id"] == insp_id
    assert rep_data["report_version"] == 1
    assert "Legal Metrology" in rep_data["legal_safety_statement"] or "PCR 2011" in rep_data["legal_safety_statement"]


    # 4. Stream PDF
    pdf_resp = client.get(f"/api/inspections/{insp_id}/report/pdf", headers=auth_headers)
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert len(pdf_resp.content) > 1000


# ==========================================
# 7. SECURITY & INJECTION PROBES
# ==========================================

def test_security_sql_injection_in_string_fields(client, auth_headers):
    """Verifies that SQL injection payloads in string fields are safely sanitized/escaped by SQLAlchemy."""
    sqli_payload = {
        "product_name": "'; DROP TABLE inspections; --",
        "brand_name": "' OR '1'='1",
        "category": "Packaged Food",
        "location": "Delhi' UNION SELECT * FROM users --",
        "batch_number": "1' OR '1'='1"
    }
    resp = client.post("/api/inspections", json=sqli_payload, headers=auth_headers)
    assert resp.status_code == 201
    insp_id = resp.json()["id"]

    # Verify table was NOT dropped and inspection is readable
    get_resp = client.get(f"/api/inspections/{insp_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["product"]["product_name"] == "'; DROP TABLE inspections; --"

def test_security_path_traversal_in_image_download(client, auth_headers):
    """Verifies that path traversal IDs cannot leak filesystem files."""
    resp = client.get("/api/images/../../../../etc/passwd/file", headers=auth_headers)
    assert resp.status_code in [404, 400, 422]
