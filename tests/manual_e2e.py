from fastapi.testclient import TestClient
from pathlib import Path
from backend.main import app

client = TestClient(app)

# 1. Login
login_res = client.post('/api/auth/login', json={'officer_id': 'DOCA-INSP-842', 'password': 'admin123'})
assert login_res.status_code == 200
token = login_res.json()['access_token']
print('[1/9] Officer authenticated successfully.')

# 2. Create Inspection
insp_res = client.post(
    '/api/inspections',
    headers={'Authorization': f'Bearer {token}'},
    json={
        'product_name': 'Himalayan Organic Basmati Rice 5kg',
        'category': 'Packaged Food',
        'location': 'New Delhi Wholesale Market Sector 12',
        'batch_number': 'HM-BR-2026-99',
        'brand_name': 'Himalayan Agro'
    }
)
assert insp_res.status_code == 201
insp_id = insp_res.json()['id']
insp_num = insp_res.json()['inspection_number']
print(f'[2/9] Created Inspection {insp_num} (ID: {insp_id})')

# 3. Upload Package Image
img_path = Path('tests/fixtures/clear_package.jpg')
with open(img_path, 'rb') as f:
    up_res = client.post(
        f'/api/inspections/{insp_id}/images',
        headers={'Authorization': f'Bearer {token}'},
        files={'file': ('clear_package.jpg', f, 'image/jpeg')},
        data={'view_type': 'front'}
    )
assert up_res.status_code == 201
up_json = up_res.json()
print(f"[3/9] Uploaded Package Image (Quality: {up_json['quality_status']}, Score: {up_json['quality_score']:.2f})")

# 4. Run OCR & Extraction
ocr_res = client.post(f'/api/inspections/{insp_id}/ocr', headers={'Authorization': f'Bearer {token}'})
assert ocr_res.status_code == 200
decls = ocr_res.json()['declarations']
print(f'[4/9] OCR completed. Extracted {len(decls)} statutory declarations.')

# 5. Officer Verification
mrp_decl = next(d for d in decls if d['field_name'] == 'mrp')
patch_res = client.patch(
    f"/api/declarations/{mrp_decl['id']}",
    headers={'Authorization': f'Bearer {token}'},
    json={'corrected_value': 'Rs. 450.00 (Incl. of all taxes)', 'verification_status': 'CORRECTED', 'correction_reason': 'Verified on MRP panel'}
)
assert patch_res.status_code == 200
print('[5/9] Officer verified MRP declaration.')

# 6. Evaluate Deterministic Rules
eval_res = client.post(f'/api/inspections/{insp_id}/evaluate', headers={'Authorization': f'Bearer {token}'})
assert eval_res.status_code == 200
findings = eval_res.json()['findings']
print(f'[6/9] Evaluated {len(findings)} statutory rules under PCR 2011.')

# 7. Adjudicate Findings
for f in findings:
    if f['result_state'] == 'POTENTIAL_NON_COMPLIANCE':
        client.patch(
            f"/api/findings/{f['id']}/adjudicate",
            headers={'Authorization': f'Bearer {token}'},
            json={'action': 'CONFIRMED', 'notes': 'Confirmed on physical verification.'}
        )
print('[7/9] Adjudication completed by Inspecting Officer.')

# 8. Finalize Inspection
fin_res = client.post(
    f'/api/inspections/{insp_id}/finalize',
    headers={'Authorization': f'Bearer {token}'},
    json={'officer_notes': 'All PCR 2011 statutory checks verified by Inspector.'}
)
assert fin_res.status_code == 200
fin_data = fin_res.json()
print(f"[8/9] Inspection Finalized. Overall Status: {fin_data['overall_status']}")

# 9. Download & Verify Generated PDF
pdf_res = client.get(f'/api/inspections/{insp_id}/report/pdf', headers={'Authorization': f'Bearer {token}'})
assert pdf_res.status_code == 200
assert pdf_res.headers['content-type'] == 'application/pdf'
assert len(pdf_res.content) > 2000
print(f'[9/9] Statutory PDF Inspection Report generated and streamed successfully ({len(pdf_res.content)} bytes).')
print('=== END-TO-END PIPELINE VALIDATION SUCCEEDED 100% ===')
