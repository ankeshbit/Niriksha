import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.rule_engine import rule_engine, get_all_rules, get_rule_by_code, RuleResultState

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def get_auth_token():
    """Helper to authenticate and return a valid JWT token."""
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert response.status_code == 200
    return response.json()["access_token"]

def create_inspection_with_ocr(token: str, fixture_name: str = "clear_package.jpg", product_name: str = "Premium Basmati Rice 5kg"):
    """Helper to create inspection, upload image, and run OCR."""
    insp_resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": product_name,
            "category": "Packaged Food",
            "location": "Central Delhi Test Lab",
            "brand_name": "Agro Pure"
        }
    )
    assert insp_resp.status_code == 201
    insp_id = insp_resp.json()["id"]

    # Upload image
    with open(FIXTURES_DIR / fixture_name, "rb") as f:
        img_resp = client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (fixture_name, f, "image/jpeg")},
            data={"view_type": "front"}
        )
    assert img_resp.status_code == 201

    # Run OCR & extraction
    ocr_resp = client.post(
        f"/api/inspections/{insp_id}/ocr",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert ocr_resp.status_code == 200

    return insp_id

# 1. Rule Registry Loads & Metadata is Valid
def test_rule_registry_loading_and_metadata():
    rules = get_all_rules()
    assert len(rules) >= 8
    
    mrp_rule = get_rule_by_code("PCR_RULE_06_1_E")
    assert mrp_rule is not None
    assert "Rule 6(1)(e)" in mrp_rule.statutory_reference
    assert mrp_rule.required_fields == ["mrp"]

# 2. Deterministic Rule Engine Execution for Complete Package (PASS)
def test_deterministic_rule_engine_complete_package_pass():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "clear_package.jpg")

    response = client.post(
        f"/api/inspections/{insp_id}/evaluate",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["inspection_id"] == insp_id
    assert data["total_rules_evaluated"] >= 8
    assert data["passed_count"] >= 6
    assert data["overall_status"] == "NO_POTENTIAL_VIOLATIONS"
    assert len(data["findings"]) >= 8

# 3. Rule Evaluation for Incomplete Package (POTENTIAL_NON_COMPLIANCE)
def test_rule_evaluation_missing_declarations():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "missing_declarations_package.jpg")

    response = client.post(
        f"/api/inspections/{insp_id}/evaluate",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["potential_non_compliance_count"] >= 1
    assert data["overall_status"] == "POTENTIAL_NON_COMPLIANCE"

    findings_map = {f["rule_code"]: f for f in data["findings"]}
    # Missing Net Quantity & Consumer Care in this fixture
    assert findings_map["PCR_RULE_06_1_C"]["result_state"] == "POTENTIAL_NON_COMPLIANCE"
    assert findings_map["PCR_RULE_06_1_G"]["result_state"] == "POTENTIAL_NON_COMPLIANCE"

# 4. Insufficient Evidence Handling for Blurry / Poor Image
def test_insufficient_evidence_handling():
    token = get_auth_token()
    insp_resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "Sample Blurry Item",
            "category": "Packaged Food",
            "location": "Warehouse Zone 3"
        }
    )
    insp_id = insp_resp.json()["id"]

    # Upload blurry image
    with open(FIXTURES_DIR / "blurry_package.jpg", "rb") as f:
        client.post(
            f"/api/inspections/{insp_id}/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("blurry_package.jpg", f, "image/jpeg")},
            data={"view_type": "front"}
        )

    # Run OCR (extracts unverified/empty text due to blur)
    client.post(f"/api/inspections/{insp_id}/ocr", headers={"Authorization": f"Bearer {token}"})

    # Evaluate rules
    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    assert data["insufficient_evidence_count"] >= 1 or data["overall_status"] == "NEEDS_MANUAL_VERIFICATION"

# 5. Non-Applicable Rule Handling (NOT_APPLICABLE)
def test_not_applicable_rule_evaluation():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "clear_package.jpg")

    # Mark country of origin as not applicable (domestic item)
    coo_decl = client.get(
        f"/api/inspections/{insp_id}/declarations/country_of_origin",
        headers={"Authorization": f"Bearer {token}"}
    ).json()

    client.patch(
        f"/api/declarations/{coo_decl['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_applicable": False, "verification_status": "VERIFIED"}
    )

    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    assert eval_resp.status_code == 200
    findings_map = {f["rule_code"]: f for f in eval_resp.json()["findings"]}
    assert findings_map["PCR_RULE_06_1_B"]["result_state"] == "NOT_APPLICABLE"

# 6. Data Integrity: Original OCR Value Preserved vs Inspector Correction
def test_data_integrity_original_ocr_preserved_separately():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "clear_package.jpg")

    mrp_decl = client.get(
        f"/api/inspections/{insp_id}/declarations/mrp",
        headers={"Authorization": f"Bearer {token}"}
    ).json()

    orig_extracted = mrp_decl["extracted_value"]
    decl_id = mrp_decl["id"]

    # Inspector verifies and corrects value
    corrected_val = "Rs. 500.00 (INCL. OF ALL TAXES)"
    patch_resp = client.patch(
        f"/api/declarations/{decl_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "corrected_value": corrected_val,
            "verification_status": "CORRECTED",
            "correction_reason": "Price revised in retail store"
        }
    )
    assert patch_resp.status_code == 200
    updated_decl = patch_resp.json()

    # Verify original extracted value is NOT destroyed
    assert updated_decl["extracted_value"] == orig_extracted
    assert updated_decl["corrected_value"] == corrected_val
    assert updated_decl["effective_value"] == corrected_val
    assert updated_decl["verified_by"] == settings.SEED_OFFICER_ID
    assert updated_decl["verified_at"] is not None

# 7. Rule Engine Evaluates Effective Value (Corrected by Officer)
def test_rule_engine_uses_effective_corrected_value():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "missing_declarations_package.jpg")

    net_qty_decl = client.get(
        f"/api/inspections/{insp_id}/declarations/net_quantity",
        headers={"Authorization": f"Bearer {token}"}
    ).json()
    decl_id = net_qty_decl["id"]

    # Officer manually verifies and adds 1 kg
    client.patch(
        f"/api/declarations/{decl_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "corrected_value": "1 kg",
            "verification_status": "CORRECTED",
            "correction_reason": "Verified on back panel"
        }
    )

    # Re-evaluate rules
    eval_resp = client.post(
        f"/api/inspections/{insp_id}/evaluate",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert eval_resp.status_code == 200
    findings_map = {f["rule_code"]: f for f in eval_resp.json()["findings"]}
    
    # Net quantity rule should now PASS using effective value
    assert findings_map["PCR_RULE_06_1_C"]["result_state"] == "PASS"
    assert findings_map["PCR_RULE_06_1_C"]["extracted_value"] == "1 kg"

# 8. Idempotency: Multiple Evaluations Do Not Duplicate Findings
def test_idempotent_rule_evaluations():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "clear_package.jpg")

    # First evaluation
    client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    findings_1 = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"}).json()

    # Second evaluation
    client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    findings_2 = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"}).json()

    assert len(findings_1) == len(findings_2)

# 9. Finding Attached to Traceable Evidence
def test_finding_evidence_traceability():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "clear_package.jpg")
    client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})

    findings = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"}).json()
    mrp_finding = next(f for f in findings if f["rule_code"] == "PCR_RULE_06_1_E")
    
    assert len(mrp_finding["evidence_items"]) >= 1
    ev = mrp_finding["evidence_items"][0]
    assert ev["image_id"] is not None
    assert ev["highlight_text"] is not None

# 10. Inspector Adjudication: Confirm Finding
def test_inspector_adjudication_confirm():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "missing_declarations_package.jpg")
    client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})

    findings = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"}).json()
    non_comp_finding = next(f for f in findings if f["result_state"] == "POTENTIAL_NON_COMPLIANCE")
    finding_id = non_comp_finding["id"]

    # Adjudicate as CONFIRMED
    adj_resp = client.patch(
        f"/api/findings/{finding_id}/adjudicate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "CONFIRMED",
            "notes": "Verified violation on retail shelf during inspection."
        }
    )
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    assert data["adjudication_status"] == "CONFIRMED"
    assert data["adjudication_notes"] == "Verified violation on retail shelf during inspection."
    assert data["adjudicated_by"] == settings.SEED_OFFICER_ID
    assert data["adjudicated_at"] is not None

# 11. Inspector Adjudication: Dismiss Finding
def test_inspector_adjudication_dismiss():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "missing_declarations_package.jpg")
    client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})

    findings = client.get(f"/api/inspections/{insp_id}/findings", headers={"Authorization": f"Bearer {token}"}).json()
    non_comp_finding = next(f for f in findings if f["result_state"] == "POTENTIAL_NON_COMPLIANCE")
    finding_id = non_comp_finding["id"]

    # Adjudicate as DISMISSED
    adj_resp = client.patch(
        f"/api/findings/{finding_id}/adjudicate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "DISMISSED",
            "notes": "Commodity is an exempted package category under Rule 26."
        }
    )
    assert adj_resp.status_code == 200
    data = adj_resp.json()
    assert data["adjudication_status"] == "DISMISSED"

# 12. Audit Trail Logging for Enforcement Actions
def test_immutable_audit_trail_logging():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "clear_package.jpg")
    client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})

    # Retrieve audit logs
    audit_resp = client.get(
        f"/api/inspections/{insp_id}/audit-logs",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) >= 2
    actions = [l["action"] for l in logs]
    assert "RULE_EVALUATION_EXECUTED" in actions
    assert "OCR_AND_EXTRACTION_COMPLETED" in actions

# 13. Realistic Fixture: Imported Commodity Scenario
def test_imported_commodity_evaluation():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "imported_product_package.jpg", product_name="Extra Virgin Olive Oil 1L")

    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    assert data["passed_count"] >= 6
    findings_map = {f["rule_code"]: f for f in data["findings"]}
    # Country of Origin should pass for imported product
    assert findings_map["PCR_RULE_06_1_B"]["result_state"] == "PASS"
    assert "Spain" in findings_map["PCR_RULE_06_1_B"]["extracted_value"]

# 14. Realistic Fixture: Multi-Panel Secondary Label Scenario
def test_multipanel_package_evaluation():
    token = get_auth_token()
    insp_id = create_inspection_with_ocr(token, "multi_panel_back.jpg", product_name="Green Mills Wheat Flour 1000g")

    eval_resp = client.post(f"/api/inspections/{insp_id}/evaluate", headers={"Authorization": f"Bearer {token}"})
    assert eval_resp.status_code == 200
    findings_map = {f["rule_code"]: f for f in eval_resp.json()["findings"]}
    assert findings_map["PCR_RULE_06_1_C"]["result_state"] == "PASS"
    assert "1000 g" in findings_map["PCR_RULE_06_1_C"]["extracted_value"]

# 15. Security: Unauthenticated & Unauthorized Protections
def test_unauthenticated_and_unauthorized_rule_endpoints():
    resp_eval = client.post("/api/inspections/some-id/evaluate")
    assert resp_eval.status_code == 401

    resp_find = client.get("/api/inspections/some-id/findings")
    assert resp_find.status_code == 401

    resp_adj = client.patch("/api/findings/some-id/adjudicate", json={"action": "CONFIRMED"})
    assert resp_adj.status_code == 401
