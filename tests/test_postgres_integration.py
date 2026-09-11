"""
tests/test_postgres_integration.py

Dedicated PostgreSQL Integration Test Suite.
Validates critical NiriKsha backend workflows:
- Authentication & JWT issuance
- Inspection creation & client_draft_id idempotency
- Image upload & quality scoring
- OCR extraction & provenance tracking
- Rule engine compliance checks
- Inspector finding adjudication & remarks
- Inspection finalization & statutory report generation
- Finalized evidence immutability (HTTP 409 Conflict)
- Explicit logout & immutable audit logging

Executes against the active test engine or a dedicated disposable PostgreSQL database
configured via TEST_DATABASE_URL / POSTGRES_TEST_DATABASE_URL.
"""

import os
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.models import Inspection, ProductImage, Declaration, ComplianceCheck, Report, AuditLog
from backend.database import SessionLocal

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


def test_integration_workflow_complete():
    """
    End-to-End integration test covering the complete statutory lifecycle:
    Auth -> Draft ID -> Upload -> OCR -> Rules -> Adjudicate -> Finalize -> PDF Stream -> Immutable -> Logout
    """
    # 1. Authentication
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Inspection Creation with client_draft_id idempotency
    draft_id = f"client-draft-pg-{uuid.uuid4().hex[:8]}"
    payload = {
        "product_name": "Postgres Integration Oats",
        "category": "Packaged Food",
        "brand_name": "Himalayan Harvest",
        "batch_number": "BATCH-PG-99",
        "location": "Staging Warehouse Zone B",
        "client_draft_id": draft_id
    }
    
    # First creation -> 201 Created
    create_resp1 = client.post("/api/inspections", headers=headers, json=payload)
    assert create_resp1.status_code == 201, f"Create failed: {create_resp1.text}"
    insp_data = create_resp1.json()
    insp_id = insp_data["id"]
    insp_num = insp_data["inspection_number"]
    assert insp_data.get("client_draft_id") == draft_id

    # Second creation with identical client_draft_id -> idempotent (returns existing, no duplicate)
    create_resp2 = client.post("/api/inspections", headers=headers, json=payload)
    assert create_resp2.status_code in [200, 201], f"Duplicate creation must return 200/201: {create_resp2.text}"
    assert create_resp2.json()["id"] == insp_id
    assert create_resp2.json()["inspection_number"] == insp_num

    # 3. Image Upload & Quality Scoring
    sample_image = FIXTURES_DIR / "clear_package.jpg"
    with open(sample_image, "rb") as f:
        img_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=headers,
            files={"file": ("front.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert img_resp.status_code == 201, f"Image upload failed: {img_resp.text}"
    img_data = img_resp.json()
    img_id = img_data["id"]
    assert "quality_score" in img_data
    assert img_data["quality_status"] in ("ACCEPTABLE", "GOOD", "POOR", "REJECTED")

    # 4. OCR Extraction & Declaration Extraction
    ocr_resp = client.post(f"/api/inspections/{insp_id}/ocr", headers=headers)
    assert ocr_resp.status_code == 200, f"OCR failed: {ocr_resp.text}"
    ocr_data = ocr_resp.json()
    assert "declarations" in ocr_data
    assert "ocr_results" in ocr_data

    # 5. Rule Engine Evaluation
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=headers)
    assert eval_resp.status_code == 200, f"Rule evaluation failed: {eval_resp.text}"
    eval_data = eval_resp.json()
    findings = eval_data.get("findings", [])
    assert len(findings) > 0, "Expected statutory compliance check findings"

    # 6. Inspector Adjudication for non-PASS findings
    for finding in findings:
        if finding["result_state"] != "PASS":
            adj_resp = client.patch(
                f"/api/findings/{finding['id']}/adjudicate",
                headers=headers,
                json={
                    "action": "CONFIRMED",
                    "notes": "PostgreSQL integration test confirmed finding."
                }
            )
            assert adj_resp.status_code == 200, f"Adjudication failed: {adj_resp.text}"

    # 7. Inspection Finalization & Statutory Report Generation
    fin_resp = client.post(f"/api/inspections/{insp_id}/finalize", headers=headers)
    assert fin_resp.status_code == 200, f"Finalize failed: {fin_resp.text}"
    fin_data = fin_resp.json()
    assert fin_data["status"] == "COMPLETED"
    assert fin_data["report"] is not None

    # Stream official report PDF
    pdf_resp = client.get(f"/api/inspections/{insp_id}/report/pdf", headers=headers)
    assert pdf_resp.status_code == 200, f"PDF stream failed: {pdf_resp.text}"
    assert pdf_resp.headers.get("content-type") == "application/pdf"
    assert len(pdf_resp.content) > 0

    # 8. Finalized Evidence Immutability (DEF-01 / DEF-02 / DEF-13)
    with open(sample_image, "rb") as f:
        post_fin_upload = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=headers,
            files={"file": ("extra.jpg", f, "image/jpeg")},
            data={"view_type": "back"}
        )
    assert post_fin_upload.status_code == 409, (
        f"Expected 409 Conflict when uploading to finalized inspection, got {post_fin_upload.status_code}"
    )

    post_fin_delete = client.delete(f"/api/images/{img_id}", headers=headers)
    assert post_fin_delete.status_code == 409, (
        f"Expected 409 Conflict when deleting image from finalized inspection, got {post_fin_delete.status_code}"
    )

    # 9. Explicit Logout (DEF-05)
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200, f"Logout failed: {logout_resp.text}"
    assert "logged out" in logout_resp.json().get("message", "").lower()

    # 10. Audit Logging Verification
    audit_resp = client.get(f"/api/inspections/{insp_id}/audit-logs", headers=headers)
    assert audit_resp.status_code == 200, f"Audit logs failed: {audit_resp.text}"
    audit_logs = audit_resp.json()
    assert len(audit_logs) >= 3, "Expected multiple immutable audit log entries"
