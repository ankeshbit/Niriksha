"""
tests/test_location_feature.py
Backend contract tests for the Location field used by NewInspectionScreen
(both manual entry and GPS-detected reverse-geocoded addresses).
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)


def _token():
    r = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD,
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth():
    return {"Authorization": f"Bearer {_token()}"}


def _create(location, product="Location Test Product", brand="TestBrand"):
    return client.post("/api/inspections", json={
        "product_name": product,
        "brand_name": brand,
        "category": "Packaged Food",
        "location": location,
    }, headers=_auth())


# ── 1. Manual location entry ───────────────────────────────────────────────────

def test_manual_location_accepted():
    """Manually typed location is stored and returned verbatim."""
    loc = "Sector 4 Market, New Delhi"
    r = _create(loc)
    assert r.status_code == 201, r.text
    assert r.json()["location"] == loc


def test_manual_location_special_chars():
    """Location with commas, slashes, and brackets is preserved."""
    loc = "Shop No. 12/B, Block-C (Ground Floor), Azadpur Mandi"
    r = _create(loc, product="Mango Pickle Jar")
    assert r.status_code == 201
    assert r.json()["location"] == loc


def test_manual_location_unicode():
    """Unicode/Devanagari location string is stored correctly."""
    loc = "अज़ादपुर थोक मंडी, दिल्ली"
    r = _create(loc, product="Basmati Rice 5kg")
    assert r.status_code == 201
    assert r.json()["location"] == loc


def test_manual_location_long_string():
    """A long location string (>150 chars) is stored without truncation."""
    loc = "Wholesale Market, Building A, " + "X" * 120
    r = _create(loc, product="Long Location Test")
    assert r.status_code == 201
    assert r.json()["location"] == loc


# ── 2. Auto-detected / reverse-geocoded address ────────────────────────────────

def test_reverse_geocoded_address_accepted():
    """A realistic reverse-geocoded address is accepted like a manual one."""
    loc = "Azadpur Sabzi Mandi, Azadpur, Delhi"
    r = _create(loc, product="Tomato Ketchup 500g")
    assert r.status_code == 201
    assert r.json()["location"] == loc


def test_gps_coordinates_as_fallback_string():
    """If client sends coords as text (geocoder offline), backend accepts it."""
    loc = "28.7041 N, 77.1025 E"
    r = _create(loc, product="Salt 1kg Pack")
    assert r.status_code == 201
    assert r.json()["location"] == loc


def test_multiple_inspections_different_auto_locations():
    """Two inspections with distinct auto-detected locations are independent."""
    loc1 = "Nehru Place, South Delhi"
    loc2 = "Lajpat Nagar Market, New Delhi"
    r1 = _create(loc1, product="Biscuit Pack A")
    r2 = _create(loc2, product="Biscuit Pack B")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["location"] == loc1
    assert r2.json()["location"] == loc2


# ── 3. Validation ──────────────────────────────────────────────────────────────

def test_empty_location_rejected():
    """Empty location string must return 422."""
    r = client.post("/api/inspections", json={
        "product_name": "Test", "brand_name": "Brand",
        "category": "Packaged Food", "location": "",
    }, headers=_auth())
    assert r.status_code in (400, 422), r.text


def test_missing_location_rejected():
    """Omitting location must return 422."""
    r = client.post("/api/inspections", json={
        "product_name": "Test", "brand_name": "Brand", "category": "Packaged Food",
    }, headers=_auth())
    assert r.status_code in (400, 422), r.text


def test_whitespace_only_location_rejected():
    """Whitespace-only location string must return 422."""
    r = client.post("/api/inspections", json={
        "product_name": "Test", "brand_name": "Brand",
        "category": "Packaged Food", "location": "   ",
    }, headers=_auth())
    assert r.status_code in (400, 422), r.text


# ── 4. Submission flow unchanged ───────────────────────────────────────────────

def test_inspection_number_generated():
    """Inspection number is auto-generated regardless of location source."""
    r = _create("Chandni Chowk, Delhi", product="Mustard Oil 1L")
    assert r.status_code == 201
    assert r.json()["inspection_number"].startswith("LM-")


def test_unauthenticated_request_rejected():
    """Creating inspection without a token is rejected (401)."""
    r = client.post("/api/inspections", json={
        "product_name": "Test", "brand_name": "Brand",
        "category": "Packaged Food", "location": "Connaught Place",
    })
    assert r.status_code == 401, r.text


def test_get_inspection_returns_correct_location():
    """GET /api/inspections/{id} returns the exact stored location."""
    loc = "Karol Bagh Market, Delhi"
    cr = _create(loc, product="Wheat Flour 10kg")
    assert cr.status_code == 201
    insp_id = cr.json()["id"]
    gr = client.get(f"/api/inspections/{insp_id}", headers=_auth())
    assert gr.status_code == 200
    assert gr.json()["location"] == loc


def test_offline_draft_with_location_idempotent():
    """An offline draft synced with client_draft_id is idempotent."""
    draft_id = str(uuid.uuid4())
    loc = "Okhla Industrial Area, Phase II, Delhi"
    payload = {
        "product_name": "Refined Sugar 1kg", "brand_name": "SugarBrand",
        "category": "Packaged Food", "location": loc,
        "client_draft_id": draft_id,
    }
    r1 = client.post("/api/inspections", json=payload, headers=_auth())
    assert r1.status_code == 201
    r2 = client.post("/api/inspections", json=payload, headers=_auth())
    assert r2.status_code in (200, 201)
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["location"] == loc


def test_location_button_does_not_affect_other_fields():
    """Sending a location string does not corrupt other inspection fields."""
    loc = "Sarojini Nagar Market, New Delhi"
    product = "Paneer Cubes 200g"
    brand = "FreshDairy"
    r = client.post("/api/inspections", json={
        "product_name": product, "brand_name": brand,
        "category": "Packaged Food", "location": loc,
        "batch_number": "BATCH-2026-001",
    }, headers=_auth())
    assert r.status_code == 201
    data = r.json()
    assert data["location"] == loc
    assert data["product"]["product_name"] == product
    assert data["product"]["brand_name"] == brand
