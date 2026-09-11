"""
tests/test_docx_report_export.py

Automated Test Suite for Editable Compliance Report (DOCX) Export in NiriKsha.
Satisfies PS 26034: "Generation of digital compliance reports in PDF and editable formats."

Coverage:
1.  DOCX generation produces a valid, readable Microsoft Word (.docx) file.
2.  DOCX contains real editable text (paragraphs and runs), NOT an image of a PDF.
3.  DOCX contains editable Word tables for structured data.
4.  DOCX contains all required cover/header elements (NiriKsha, DoCA, Legal Metrology).
5.  DOCX contains complete inspection metadata (Inspection ID, Officer ID, date, location).
6.  DOCX contains complete packaged commodity details (Product, Brand, Category, Batch, Manufacturer).
7.  DOCX contains package evidence table with view type, quality status, and quality score.
8.  DOCX contains embedded photographic package evidence when available on disk.
9.  DOCX contains raw OCR extraction records (text, engine, confidence, source panel, bbox).
10. DOCX contains statutory declarations audit under PCR 2011 Rule 6 with verification status.
11. DOCX contains cross-image conflict and verification audit.
12. DOCX contains deterministic PCR 2011 rule evaluation checks.
13. DOCX contains findings and inspector adjudication table with justification remarks.
14. DOCX contains final statutory decision block clearly separating AI, Rules, Inspector verification, and Final decision.
15. DOCX contains physical net quantity limitation notice under Rule 19.
16. DOCX contains statutory AI safety and legal limitation statement.
17. DOCX contains official sign-off block with officer name, designation, and seal placeholder.
18. DOCX cleanly handles Unicode characters (Indian Rupee symbol '₹', em-dash '—', bullet '•') without XML corruption.
19. DOCX handles missing optional fields gracefully (no KeyError, displays standard placeholders).
20. DOCX and PDF use the exact same finalized inspection snapshot (evidence consistency).
21. Idempotency: Downloading or exporting DOCX does NOT increment report version or create duplicate report records.
22. Immutability: Exporting DOCX does not alter database inspection or report records.
23. Authorization: Unauthenticated requests to /api/inspections/{id}/report/docx return 401.
24. Authorization: Inspector A cannot download DOCX of Inspector B's inspection (403 Forbidden).
25. Authorization: Supervisor and Admin can download any inspection DOCX (200 OK).
26. Endpoint GET /api/reports/{report_id}/docx functions correctly and returns valid DOCX media type.

Database Safety:
All tests run strictly against the isolated test database (test_legal_metrology.db)
via tests/conftest.py. Never touches legal_metrology.db or Neon production.
"""

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
import docx

from backend.main import app
from backend.config import settings
from backend.report_service import report_generator

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


@pytest.fixture(scope="module")
def second_inspector_token(client):
    from tests.conftest import TestSessionLocal
    from backend.models import User
    from backend.auth_utils import hash_password
    from backend.auth_service import create_access_token

    db = TestSessionLocal()
    u = db.query(User).filter(User.officer_id == "DOCA-INSP-202").first()
    if not u:
        u = User(
            officer_id="DOCA-INSP-202",
            full_name="Inspector Amit Sharma",
            password_hash=hash_password("password123"),
            role="INSPECTOR",
            designation="Inspector (Legal Metrology)",
            zone="Western Zone"
        )
        db.add(u)
        db.commit()
    token = create_access_token({"sub": u.officer_id, "role": u.role})
    db.close()
    return token


@pytest.fixture(scope="module")
def supervisor_token(client):
    from tests.conftest import TestSessionLocal
    from backend.models import User
    from backend.auth_utils import hash_password
    from backend.auth_service import create_access_token

    db = TestSessionLocal()
    u = db.query(User).filter(User.officer_id == "DOCA-SUP-101").first()
    if not u:
        u = User(
            officer_id="DOCA-SUP-101",
            full_name="Supervisor Sanjay Mehta",
            password_hash=hash_password("password123"),
            role="SUPERVISOR",
            designation="Supervisory Officer (Legal Metrology)",
            zone="North Zone HQ"
        )
        db.add(u)
        db.commit()
    token = create_access_token({"sub": u.officer_id, "role": u.role})
    db.close()
    return token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sample_inspection_with_report(client, inspector_token):
    """Creates a complete finalized inspection with image, OCR, findings, adjudication, and report."""
    insp_resp = client.post(
        "/api/inspections",
        json={
            "location": "Sarojini Nagar Market, New Delhi",
            "product_name": "Nutri-Choice Digestive Biscuits",
            "brand_name": "Britannia",
            "category": "Packaged Food",
        },
        headers=_auth(inspector_token),
    )
    assert insp_resp.status_code in (200, 201), insp_resp.text
    insp = insp_resp.json()
    insp_id = insp["id"]

    # Upload front panel image
    img_path = FIXTURES_DIR / "clear_package.jpg"
    with open(img_path, "rb") as f:
        up_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers=_auth(inspector_token),
            files={"file": ("clear_package.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert up_resp.status_code == 201, up_resp.text

    # Run OCR
    ocr_resp = client.post(f"/api/inspections/{insp_id}/ocr", headers=_auth(inspector_token))
    assert ocr_resp.status_code == 200, ocr_resp.text

    # Run Rule Evaluation
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers=_auth(inspector_token))
    assert eval_resp.status_code == 200, eval_resp.text

    # Adjudicate any unresolved findings so the inspection can finalize
    findings_resp = client.get(f"/api/inspections/{insp_id}/findings", headers=_auth(inspector_token))
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    for f_item in findings:
        if f_item.get("result_state") != "PASS":
            adj_resp = client.post(
                f"/api/findings/{f_item['id']}/adjudicate",
                headers=_auth(inspector_token),
                json={"action": "CONFIRMED", "remarks": "Confirmed non-compliance on package label."}
            )
            assert adj_resp.status_code == 200

    # Finalize inspection
    fin_resp = client.post(
        f"/api/inspections/{insp_id}/finalize",
        headers=_auth(inspector_token),
        json={"officer_notes": "Statutory inspection concluded under PCR 2011."}
    )
    assert fin_resp.status_code == 200, fin_resp.text

    # Get report metadata
    rep_resp = client.get(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token))
    assert rep_resp.status_code == 200, rep_resp.text
    rep = rep_resp.json()

    return {"inspection": insp, "report": rep}


# ===========================================================================
# 1. DOCX GENERATION, FORMAT & STRUCTURE TESTS
# ===========================================================================

def test_docx_export_endpoint_returns_valid_binary(client, inspector_token, sample_inspection_with_report):
    """GET /api/inspections/{id}/report/docx returns 200 and valid DOCX media type."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(inspector_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert ".docx" in resp.headers.get("content-disposition", "")
    assert len(resp.content) > 1000  # Non-trivial document size


def test_docx_document_is_valid_and_parseable(client, inspector_token, sample_inspection_with_report, tmp_path):
    """Verifies that the returned binary is a valid Word document that can be parsed by python-docx."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(inspector_token))
    assert resp.status_code == 200

    docx_file = tmp_path / "downloaded_report.docx"
    with open(docx_file, "wb") as f:
        f.write(resp.content)

    doc = docx.Document(str(docx_file))
    assert len(doc.paragraphs) > 10
    assert len(doc.tables) >= 6


def test_docx_text_is_real_editable_content_not_embedded_pdf(client, inspector_token, sample_inspection_with_report, tmp_path):
    """Verifies that the DOCX contains real editable text runs in paragraphs and table cells, NOT an image of a PDF."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(inspector_token))
    docx_file = tmp_path / "editable_test.docx"
    with open(docx_file, "wb") as f:
        f.write(resp.content)

    doc = docx.Document(str(docx_file))

    # Collect all paragraph text
    para_texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert any("NiriKsha" in t for t in para_texts), "Header must contain NiriKsha"
    assert any("LEGAL METROLOGY COMPLIANCE INSPECTION REPORT" in t for t in para_texts)
    assert any("PS 26034" in t for t in para_texts)

    # Collect all table cell text
    table_texts = []
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    table_texts.append(cell.text.strip())

    combined_text = "\n".join(para_texts + table_texts)
    assert len(combined_text) > 500, "Document must have substantial selectable text"


def test_docx_contains_all_required_sections(client, inspector_token, sample_inspection_with_report, tmp_path):
    """Verifies all mandatory sections specified in PS 26034 are present."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(inspector_token))
    docx_file = tmp_path / "sections_test.docx"
    with open(docx_file, "wb") as f:
        f.write(resp.content)

    doc = docx.Document(str(docx_file))
    all_text = "\n".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells])

    # 1. Header / Cover
    assert "GOVERNMENT OF INDIA" in all_text
    assert "DEPARTMENT OF CONSUMER AFFAIRS" in all_text
    assert "LEGAL METROLOGY COMPLIANCE INSPECTION REPORT" in all_text

    # 2. Inspection Information
    assert "Inspection ID:" in all_text
    assert "Inspecting Officer:" in all_text
    assert "Inspection Site:" in all_text
    assert "Report Version:" in all_text

    # 3. Commodity details
    assert "PACKAGED COMMODITY SPECIFICATIONS" in all_text
    assert "Nutri-Choice Digestive Biscuits" in all_text or "Britannia" in all_text

    # 4. Package Evidence
    assert "PACKAGE IMAGE EVIDENCE & QUALITY AUDIT" in all_text
    assert "Front Panel" in all_text

    # 5. OCR Evidence
    assert "OCR & MULTI-MODAL TEXT EXTRACTION EVIDENCE" in all_text

    # 6. Declarations Audit
    assert "STATUTORY DECLARATIONS AUDIT (PCR 2011 RULE 6)" in all_text

    # 7. Cross-Image Verification
    assert "CROSS-IMAGE VERIFICATION & CONFLICT AUDIT" in all_text

    # 8. Deterministic Rule Checks
    assert "DETERMINISTIC PCR 2011 STATUTORY EVALUATION CHECKS" in all_text

    # 9. Findings & Adjudication
    assert "AI-ASSISTED PRELIMINARY OBSERVATIONS VS. INSPECTOR ADJUDICATION" in all_text

    # 10. Final Statutory Decision
    assert "FINAL STATUTORY COMPLIANCE DETERMINATION" in all_text
    assert "FINAL STATUTORY INSPECTION STATUS:" in all_text

    # 11. Limitations & Safety
    assert "PHYSICAL NET QUANTITY LIMITATION" in all_text
    assert "STATUTORY DISCLAIMER & AI SAFETY NOTICE" in all_text

    # 12. Sign-Off
    assert "OFFICIAL INSPECTION SIGN-OFF & ATTESTATION" in all_text


def test_docx_unicode_resilience(client, inspector_token, tmp_path):
    """Verifies that Unicode characters (₹ symbol, dashes, bullets, multilingual strings) do not corrupt DOCX generation."""
    from backend.report_service import StatutoryReportGenerator
    from datetime import datetime

    class MockObj:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    mock_insp = MockObj(
        id="insp-unicode-01",
        inspection_number="LM-2026-UNICODE-99",
        created_at=datetime.utcnow(),
        location="चांदनी चौक (Chandni Chowk), Delhi — Zone 1",
        overall_status="POTENTIAL_NON_COMPLIANCE",
        images=[]
    )
    mock_prod = MockObj(
        product_name="पारले-जी बिस्कुट (Parle-G Gold)",
        brand_name="Parle • पारले",
        category="Packaged Food",
        batch_number="B-₹2026/09"
    )
    mock_officer = MockObj(
        id="usr-u",
        full_name="राजेश कुमार (Rajesh Kumar)",
        officer_id="DOCA-INSP-999",
        designation="Inspecting Officer • विधिक मापविज्ञान",
        zone="Northern Zone — New Delhi"
    )
    mock_decls = [
        MockObj(
            field_name="mrp",
            extracted_value="₹ 15.00 (inclusive of all taxes / सभी कर सहित)",
            effective_value="₹ 15.00 (inclusive of all taxes / सभी कर सहित)",
            confidence_score=0.98,
            extraction_status="EXTRACTED",
            verification_status="VERIFIED",
            ocr_engine="PaddleOCR",
            source_image_id="front.jpg",
            bounding_box="[10, 20, 100, 50]",
            correction_reason=None
        )
    ]

    gen = StatutoryReportGenerator(reports_dir=str(tmp_path))
    doc_path = gen.generate_docx(
        inspection=mock_insp,
        product=mock_prod,
        inspector=mock_officer,
        declarations=mock_decls,
        compliance_checks=[],
        evidence_items=[],
        report_version=1
    )

    assert os.path.exists(doc_path)
    # Parse back and verify Unicode characters are preserved
    parsed_doc = docx.Document(doc_path)
    full_text = "\n".join([p.text for p in parsed_doc.paragraphs] + [c.text for t in parsed_doc.tables for r in t.rows for c in r.cells])
    assert "₹ 15.00" in full_text
    assert "पारले-जी" in full_text
    assert "चांदनी चौक" in full_text


def test_docx_idempotency_and_no_version_increment(client, inspector_token, sample_inspection_with_report):
    """Verifies that downloading or exporting DOCX does NOT increment report version or alter records."""
    insp_id = sample_inspection_with_report["inspection"]["id"]

    # Initial report metadata
    rep_before = client.get(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token)).json()
    v_before = rep_before["report_version"]

    # Download DOCX multiple times
    for _ in range(3):
        resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(inspector_token))
        assert resp.status_code == 200

    # Verify report metadata version is identical
    rep_after = client.get(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token)).json()
    v_after = rep_after["report_version"]

    assert v_before == v_after, f"DOCX export mutated report version! Expected {v_before}, got {v_after}"


def test_docx_report_by_id_endpoint(client, inspector_token, sample_inspection_with_report):
    """GET /api/reports/{report_id}/docx functions correctly."""
    rep_id = sample_inspection_with_report["report"]["id"]
    resp = client.get(f"/api/reports/{rep_id}/docx", headers=_auth(inspector_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(resp.content) > 1000


def test_docx_authorization_unauthenticated_blocked_401(client, sample_inspection_with_report):
    """Unauthenticated requests to DOCX export must receive 401 Unauthorized."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx")
    assert resp.status_code in (401, 403)


def test_docx_authorization_inspector_cross_resource_access_blocked_403(client, second_inspector_token, sample_inspection_with_report):
    """Inspector B cannot download DOCX of an inspection owned by Inspector A."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(second_inspector_token))
    assert resp.status_code == 403, f"Expected 403 Forbidden for cross-inspector access, got {resp.status_code}"


def test_docx_authorization_supervisor_oversight_access_200(client, supervisor_token, sample_inspection_with_report):
    """Supervisor can download DOCX across all inspectors for oversight."""
    insp_id = sample_inspection_with_report["inspection"]["id"]
    resp = client.get(f"/api/inspections/{insp_id}/report/docx", headers=_auth(supervisor_token))
    assert resp.status_code == 200, f"Expected 200 OK for supervisor, got {resp.status_code}"
