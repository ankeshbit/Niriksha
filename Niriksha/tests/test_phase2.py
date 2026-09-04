import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)

def get_auth_token():
    """Helper to authenticate and return a valid JWT token."""
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert response.status_code == 200
    return response.json()["access_token"]

# 1. Successful Login
def test_successful_login():
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["officer_id"] == settings.SEED_OFFICER_ID

# 2. Failed Login
def test_failed_login():
    response = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": "wrong_password_123"
    })
    assert response.status_code == 401
    assert "Invalid Officer ID or password" in response.json()["detail"]

    # Test non-existent officer
    response_no_user = client.post("/api/auth/login", json={
        "officer_id": "UNKNOWN_OFFICER",
        "password": "password"
    })
    assert response_no_user.status_code == 401

# 3. Protected Endpoint Without Authentication
def test_protected_endpoints_without_auth():
    # /api/auth/me
    resp_me = client.get("/api/auth/me")
    assert resp_me.status_code == 401

    # /api/dashboard
    resp_dash = client.get("/api/dashboard")
    assert resp_dash.status_code == 401

    # /api/inspections
    resp_insp = client.get("/api/inspections")
    assert resp_insp.status_code == 401

    # POST /api/inspections
    resp_post = client.post("/api/inspections", json={
        "product_name": "Test",
        "category": "Packaged Food",
        "location": "Delhi"
    })
    assert resp_post.status_code == 401

# 4. Current-User Retrieval
def test_current_user_profile():
    token = get_auth_token()
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["officer_id"] == settings.SEED_OFFICER_ID
    assert data["full_name"] == settings.SEED_OFFICER_NAME
    assert data["designation"] == settings.SEED_OFFICER_DESIGNATION
    assert data["zone"] == settings.SEED_OFFICER_ZONE
    assert data["role"] == "INSPECTOR"

# 5. Successful Inspection Creation
def test_successful_inspection_creation():
    token = get_auth_token()
    payload = {
        "product_name": "Organic Whole Wheat Flour",
        "brand_name": "Prakriti Harvest",
        "category": "Packaged Food",
        "location": "Central Delhi Retail Market",
        "batch_number": "BATCH-2026-AUG-01",
        "notes": "Routine market surveillance inspection"
    }

    response = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json=payload
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "inspection_number" in data
    assert data["inspection_number"].startswith("LM-2026-")
    assert data["status"] == "DRAFT"
    assert data["location"] == "Central Delhi Retail Market"
    assert data["product"]["product_name"] == "Organic Whole Wheat Flour"
    assert data["product"]["brand_name"] == "Prakriti Harvest"
    assert data["product"]["category"] == "Packaged Food"

# 6. Invalid Inspection Creation
def test_invalid_inspection_creation_missing_fields():
    token = get_auth_token()
    
    # Missing product_name
    response = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "",
            "category": "Packaged Food",
            "location": "Delhi"
        }
    )
    assert response.status_code == 400
    assert "Product name is required" in response.json()["detail"]

    # Missing location
    response_loc = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "Sunflower Oil",
            "category": "Packaged Food",
            "location": ""
        }
    )
    assert response_loc.status_code == 400

# 7. Inspection Retrieval
def test_get_inspection_by_id():
    token = get_auth_token()
    # 1. Create
    create_resp = client.post(
        "/api/inspections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_name": "Mustard Oil 1L",
            "brand_name": "Kisan Shuddh",
            "category": "Packaged Food",
            "location": "Rohini Sector 7"
        }
    )
    assert create_resp.status_code == 201
    insp_id = create_resp.json()["id"]

    # 2. Retrieve
    get_resp = client.get(
        f"/api/inspections/{insp_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == insp_id
    assert data["product"]["product_name"] == "Mustard Oil 1L"

# 8. Recent Inspection Retrieval
def test_get_recent_inspections():
    token = get_auth_token()
    response = client.get(
        "/api/inspections/recent",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert "inspection_number" in items[0]
    assert "product_name" in items[0]

# 9. Authenticated Dashboard Data
def test_dashboard_stats_and_recents():
    token = get_auth_token()
    response = client.get(
        "/api/dashboard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_inspections" in data
    assert "needs_manual_verification" in data
    assert "verified_inspections" in data
    assert "potential_non_compliance" in data
    assert "recent_inspections" in data
    assert data["total_inspections"] >= 1
    assert isinstance(data["recent_inspections"], list)
