import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent

def test_health_endpoint():
    """Verify system health endpoint and database connectivity."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["environment"] == "development"

def test_seed_officer_login_success():
    """Verify seed officer can authenticate with credentials."""
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["officer_id"] == settings.SEED_OFFICER_ID
    assert data["full_name"] == settings.SEED_OFFICER_NAME

def test_officer_login_invalid_password():
    """Verify invalid password returns 401 Unauthorized."""
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": "wrong_password"
    })
    assert response.status_code == 401
    assert "Invalid Officer ID or password" in response.json()["detail"]

def test_get_current_user_profile():
    """Verify authenticated profile retrieval with JWT."""
    # 1. Login
    login_resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    token = login_resp.json()["access_token"]

    # 2. Get profile
    profile_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert profile_resp.status_code == 200
    profile_data = profile_resp.json()
    assert profile_data["officer_id"] == settings.SEED_OFFICER_ID
    assert profile_data["designation"] == settings.SEED_OFFICER_DESIGNATION

def test_rules_registry_endpoint():
    """Verify registered statutory rules are exposed."""
    response = client.get("/api/rules")
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) >= 8
    rule_codes = [r["rule_code"] for r in rules]
    assert "PCR_RULE_06_1_E" in rule_codes
    assert "PCR_RULE_06_1_C" in rule_codes
    assert "PCR_RULE_06_1_A" in rule_codes

def test_all_13_stitch_screens_exist_and_render():
    """Verify that all 13 Stitch screens exist on disk and serve HTTP 200 via static mount if present."""
    stitch_dir = BASE_DIR / "stitch_screens" / "code"
    if not stitch_dir.exists():
        pytest.skip("stitch_screens not present in repository")

    screens = [
        "01_login.html",
        "02_dashboard.html",
        "03_extracted_declarations.html",
        "04_new_inspection_step1.html",
        "05_findings.html",
        "06_evidence_review.html",
        "07_inspection_report_preview.html",
        "08_reports_list.html",
        "09_capture_images_warning.html",
        "10_profile.html",
        "11_draft_saved_offline.html",
        "12_analyzing.html",
        "13_step3_review_and_submit.html"
    ]

    for screen_file in screens:
        file_path = stitch_dir / screen_file
        assert file_path.exists(), f"Stitch screen file missing: {screen_file}"
        assert file_path.stat().st_size > 1000, f"Stitch screen file empty or corrupted: {screen_file}"
        
        # Test HTTP availability through FastAPI mount
        resp = client.get(f"/stitch/code/{screen_file}")
        assert resp.status_code == 200, f"Stitch screen not served: {screen_file}"
        assert "<!DOCTYPE html>" in resp.text

