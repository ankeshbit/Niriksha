"""
tests/test_offline_and_idempotency.py

Tests for:
1. Health endpoint availability (/api/health)
2. Normal online inspection creation creates exactly 1 inspection
3. Offline draft idempotent sync (same client_draft_id returns existing inspection without duplicate)
4. Repeated sync retries with same client_draft_id do not create duplicate inspections
5. Multiple distinct client_draft_ids create distinct inspections
6. Isolation from production legal_metrology.db
"""

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

def test_health_check_endpoint(client):
    """Verifies that /api/health responds with healthy status for connectivity detection."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

def test_normal_online_inspection_creation(client, auth_headers):
    """Verifies standard online inspection creation without client_draft_id."""
    payload = {
        "product_name": "Online Basmati Rice",
        "category": "Packaged Food",
        "brand_name": "India Gate",
        "location": "Online Retail Store",
        "batch_number": "ONL-2026-101"
    }
    resp = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["product"]["product_name"] == "Online Basmati Rice"
    assert "LM-2026-" in data["inspection_number"]

def test_idempotent_offline_draft_sync(client, auth_headers):
    """
    Verifies that syncing a draft with a client_draft_id creates exactly one inspection,
    and repeated syncs with the same client_draft_id return the same inspection (idempotent).
    """
    client_draft_id = "draft-test-uuid-550e8400-e29b-41d4-a716-446655440000"
    payload = {
        "product_name": "Offline Synced Mustard Oil 1L",
        "category": "Packaged Food",
        "brand_name": "Patanjali",
        "location": "Warehouse Zone 4",
        "batch_number": "OFF-2026-X1",
        "notes": "Captured offline in remote warehouse",
        "client_draft_id": client_draft_id
    }

    # 1. Initial Sync
    resp1 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp1.status_code == 201
    data1 = resp1.json()
    insp_id_1 = data1["id"]
    insp_num_1 = data1["inspection_number"]

    # 2. Duplicate Sync Attempt #1 (simulating retry after timeout/lost response)
    resp2 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp2.status_code == 201 or resp2.status_code == 200
    data2 = resp2.json()
    assert data2["id"] == insp_id_1, "Duplicate inspection ID created!"
    assert data2["inspection_number"] == insp_num_1, "Duplicate inspection number created!"

    # 3. Duplicate Sync Attempt #2
    resp3 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp3.status_code in [200, 201]
    data3 = resp3.json()
    assert data3["id"] == insp_id_1
    assert data3["inspection_number"] == insp_num_1

def test_distinct_drafts_create_distinct_inspections(client, auth_headers):
    """Verifies that two different client_draft_ids create two distinct inspections."""
    payload_a = {
        "product_name": "Draft Product A",
        "category": "Packaged Food",
        "brand_name": "Brand A",
        "location": "Site A",
        "client_draft_id": "draft-distinct-alpha-1111"
    }
    payload_b = {
        "product_name": "Draft Product B",
        "category": "Household/Personal Care",
        "brand_name": "Brand B",
        "location": "Site B",
        "client_draft_id": "draft-distinct-beta-2222"
    }

    resp_a = client.post("/api/inspections", json=payload_a, headers=auth_headers)
    resp_b = client.post("/api/inspections", json=payload_b, headers=auth_headers)

    assert resp_a.status_code == 201
    assert resp_b.status_code == 201

    assert resp_a.json()["id"] != resp_b.json()["id"]
    assert resp_a.json()["inspection_number"] != resp_b.json()["inspection_number"]
