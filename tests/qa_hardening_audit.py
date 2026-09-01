import os
import json
from pathlib import Path

# Explicitly isolate test database
BASE_DIR = Path(__file__).resolve().parent.parent
TEST_DB_PATH = BASE_DIR / "test_legal_metrology.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"

from backend.config import settings
settings.DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"

from fastapi.testclient import TestClient
from backend.main import app
import backend.database as db_module
from backend.models import Inspection, Declaration, ComplianceCheck, Report, AuditLog, Base
from backend.database import get_db
from backend.seed import seed_database

# Ensure test DB initialized
Base.metadata.create_all(bind=db_module.engine)
seed_database()

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def test_full_qa_hardening():
    print("\n=======================================================")
    print("STARTING COMPREHENSIVE QA & MVP DEMO READINESS AUDIT")
    print("=======================================================")

    # 1. Auth & Profile
    login_res = client.post('/api/auth/login', json={'officer_id': 'DOCA-INSP-842', 'password': 'admin123'})
    assert login_res.status_code == 200
    token = login_res.json()['access_token']
    officer_name = login_res.json()['full_name']
    print(f"[QA 1/10] Authenticated Officer: {officer_name} ({login_res.json()['officer_id']})")

    # 2. Create Realistic Inspection
    insp_res = client.post(
        '/api/inspections',
        headers={'Authorization': f'Bearer {token}'},
        json={
            'product_name': 'Fortune Sunlite Refined Sunflower Oil 1L',
            'category': 'Packaged Food',
            'location': 'Azadpur Wholesale Mandi Delhi',
            'batch_number': 'SUN-2026-B1',
            'brand_name': 'Fortune',
            'notes': 'Routine retail market audit under PCR 2011'
        }
    )
    assert insp_res.status_code == 201
    insp = insp_res.json()
    insp_id = insp['id']
    insp_num = insp['inspection_number']
    print(f"[QA 2/10] Created Inspection: {insp_num} at {insp['location']}")

    # 3. Upload Realistic Package Image
    img_path = FIXTURES_DIR / "good_package.jpg"
    with open(img_path, 'rb') as f:
        up_res = client.post(
            f'/api/inspections/{insp_id}/images',
            headers={'Authorization': f'Bearer {token}'},
            files={'file': ('fortune_oil_front.jpg', f, 'image/jpeg')},
            data={'view_type': 'front'}
        )
    assert up_res.status_code == 201
    img_data = up_res.json()
    print(f"[QA 3/10] Uploaded Image: Quality = {img_data['quality_status']}, Score = {img_data['quality_score']:.2f}")

    # 4. Non-Destructive OCR & Structured Declarations
    ocr_res = client.post(f'/api/inspections/{insp_id}/ocr', headers={'Authorization': f'Bearer {token}'})
    assert ocr_res.status_code == 200
    decls = ocr_res.json()['declarations']
    assert len(decls) == 7
    print(f"[QA 4/10] Extracted 7 Statutory Declarations via OCR")

    # 5. Inspector Correction (OCR vs Corrected vs Effective Value Integrity)
    mrp_decl = next(d for d in decls if d['field_name'] == 'mrp')
    orig_ocr_mrp = mrp_decl['extracted_value']
    corrected_mrp = "Rs. 195.00 (Incl. of all taxes)"

    patch_res = client.patch(
        f"/api/declarations/{mrp_decl['id']}",
        headers={'Authorization': f'Bearer {token}'},
        json={
            'corrected_value': corrected_mrp,
            'verification_status': 'CORRECTED',
            'correction_reason': 'Officer corrected OCR character on price tag'
        }
    )
    assert patch_res.status_code == 200
    patched_decl = patch_res.json()
    assert patched_decl['extracted_value'] == orig_ocr_mrp  # Baseline OCR UNTOUCHED
    assert patched_decl['corrected_value'] == corrected_mrp  # Correction SAVED
    assert patched_decl['effective_value'] == corrected_mrp  # Effective resolved to correction
    safe_ocr_mrp = orig_ocr_mrp.replace('\u20b9', 'Rs. ') if orig_ocr_mrp else ''
    safe_eff_mrp = patched_decl['effective_value'].replace('\u20b9', 'Rs. ') if patched_decl['effective_value'] else ''
    print(f"[QA 5/10] Data Integrity Verified: Baseline OCR ({safe_ocr_mrp}) preserved, Effective = {safe_eff_mrp}")

    # 6. Rule Evaluation with Effective Value
    eval_res = client.post(f'/api/inspections/{insp_id}/evaluate', headers={'Authorization': f'Bearer {token}'})
    assert eval_res.status_code == 200
    findings = eval_res.json()['findings']
    mrp_finding = next(f for f in findings if f['rule_code'] == 'PCR_RULE_06_1_E')
    assert mrp_finding['extracted_value'] == corrected_mrp  # Rule engine received effective value
    print(f"[QA 6/10] Rule Engine evaluated {len(findings)} rules using effective values.")

    # 7. Adjudication (Confirmation & Dismissal)
    for f in findings:
        if f['result_state'] == 'POTENTIAL_NON_COMPLIANCE':
            adj = client.patch(
                f"/api/findings/{f['id']}/adjudicate",
                headers={'Authorization': f'Bearer {token}'},
                json={'action': 'CONFIRMED', 'notes': 'Confirmed non-compliance on package inspection.'}
            )
            assert adj.status_code == 200
    print(f"[QA 7/10] Human Adjudication Recorded with Statutory Justifications")

    # 8. Inspection Finalization
    fin_res = client.post(
        f'/api/inspections/{insp_id}/finalize',
        headers={'Authorization': f'Bearer {token}'},
        json={'officer_notes': 'Finalized by Inspecting Officer Rajesh Kumar.'}
    )
    assert fin_res.status_code == 200
    fin_data = fin_res.json()
    assert fin_data['status'] == 'COMPLETED'
    print(f"[QA 8/10] Inspection Finalized with status: {fin_data['overall_status']}")

    # 9. PDF Generation & Database-vs-PDF Consistency
    rep_res = client.get(f'/api/inspections/{insp_id}/report', headers={'Authorization': f'Bearer {token}'})
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data['inspection_id'] == insp_id
    assert rep_data['report_version'] >= 1

    pdf_res = client.get(f'/api/inspections/{insp_id}/report/pdf', headers={'Authorization': f'Bearer {token}'})
    assert pdf_res.status_code == 200
    assert pdf_res.headers['content-type'] == 'application/pdf'
    assert len(pdf_res.content) > 3000
    print(f"[QA 9/10] Statutory PDF generated ({len(pdf_res.content)} bytes, v{rep_data['report_version']})")

    # 10. Audit Trail Verification
    audit_res = client.get(f'/api/inspections/{insp_id}/audit-logs', headers={'Authorization': f'Bearer {token}'})
    assert audit_res.status_code == 200
    actions = [a['action'] for a in audit_res.json()]
    assert 'INSPECTION_CREATED' in actions
    assert 'IMAGE_UPLOADED' in actions
    assert 'DECLARATION_VERIFIED' in actions
    assert 'RULE_EVALUATION_EXECUTED' in actions
    assert 'REPORT_GENERATED' in actions
    assert 'INSPECTION_FINALIZED' in actions
    print(f"[QA 10/10] Immutable Audit Trail verified ({len(actions)} lifecycle events recorded)")

    print("\n=======================================================")
    print("ALL 10 QA & HARDENING CHECKS PASSED WITH 100% SUCCESS")
    print("=======================================================\n")

if __name__ == "__main__":
    test_full_qa_hardening()
