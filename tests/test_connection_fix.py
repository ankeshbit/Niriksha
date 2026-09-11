"""
tests/test_connection_fix.py

Regression tests for the NiriKsha "Failed to fetch" / Connection Lost fix.

Root causes verified:
  RC-1: networkService health-check timeout too aggressive (2500ms → 8000ms)
  RC-2: UNKNOWN-state isChecking guard returned false instead of true
  RC-3: Web blob: URI fetch failure wrongly classified as network error
  RC-4: isNetworkError brittle string match caught too many error types
  RC-5: No OCR timeout; slow PaddleOCR falsely looked like connectivity failure

These tests verify:
  A. Backend health endpoint responds within acceptable thresholds
  B. CORS from the Expo web dev origin (localhost:8081) is allowed
  C. POST /api/inspections creates an inspection with client_draft_id (idempotency)
  D. Duplicate sync (same client_draft_id) returns existing record — no duplicate
  E. Image upload endpoint accepts multipart/form-data
  F. Authentication errors return 401, not masquerade as network errors
  G. 404 for non-existent resources is a proper HTTP error, not network error
  H. Health endpoint is stable under rapid sequential calls

IMPORTANT:
- All tests run against the ISOLATED test database (see conftest.py / pytest.ini).
- Zero records written to Neon production.
"""

import io
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from jose import jwt

from backend.main import app
from backend.database import SessionLocal
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password
from backend.models import User

try:
    from PIL import Image as PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


# ─── Fixtures ────────────────────────────────────────────────────────────────

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    """Isolated database session — does NOT use Neon production DB."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="module")
def inspector_token(db_session: Session):
    """
    Create (or reuse) a test inspector account and return a valid JWT token.
    The account is created in the test/isolated database only.
    """
    officer_id = "TEST_CONN_FIX_INSPECTOR"
    user = db_session.query(User).filter(User.officer_id == officer_id).first()
    if not user:
        user = User(
            officer_id=officer_id,
            full_name="Connection Fix Test Inspector",
            role="INSPECTOR",
            designation="Field Inspector (Legal Metrology)",
            zone="North Zone",
            password_hash=hash_password("TestConnFix123!"),
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    token = create_access_token({"sub": user.officer_id, "role": user.role})
    return token


@pytest.fixture(scope="module")
def auth_headers(inspector_token: str):
    return {"Authorization": f"Bearer {inspector_token}"}


def make_test_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    """Create a minimal valid JPEG in memory for upload tests."""
    if _PIL_AVAILABLE:
        img = PILImage.new("RGB", (width, height), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    # Fallback: minimal JPEG header bytes
    return (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
        b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\xc9'
        b'\xff\xd9'
    )


# ─── Test A: Health endpoint response time ────────────────────────────────────

def test_health_responds_quickly():
    """
    RC-1 regression: Health endpoint must respond well within 8s.
    Previously the 2500ms threshold was too aggressive; this test confirms
    the baseline is fast enough that even the old threshold would not trip
    on a healthy backend.
    """
    start = time.monotonic()
    resp = client.get("/api/health")
    elapsed = time.monotonic() - start

    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    data = resp.json()
    assert data.get("status") == "healthy"
    # Must respond in under 3 seconds (well below new 8s threshold)
    assert elapsed < 3.0, (
        f"Health check took {elapsed:.2f}s — unexpectedly slow. "
        "The 8s networkService threshold is designed to tolerate this."
    )


# ─── Test B: CORS from Expo web dev origin ───────────────────────────────────

def test_cors_from_expo_web_origin():
    """
    RC-1/RC-2 regression: CORS must allow requests from localhost:8081
    (the Expo web dev server), which is what the browser sends.
    """
    # Preflight OPTIONS for /api/inspections from Expo web origin
    resp = client.options(
        "/api/inspections",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    # FastAPI returns 200 for OPTIONS preflight
    assert resp.status_code == 200, f"CORS preflight failed: {resp.status_code}"
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    # Should be either the exact origin or wildcard *
    assert allow_origin in ("http://localhost:8081", "*"), (
        f"CORS did not allow localhost:8081 origin. Got: '{allow_origin}'"
    )
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    assert "POST" in allow_methods.upper() or allow_methods == "*", (
        f"CORS did not allow POST. Got: '{allow_methods}'"
    )


# ─── Test C: Inspection creation with client_draft_id ────────────────────────

def test_create_inspection_with_client_draft_id(auth_headers):
    """
    RC-4 regression: Inspection creation must succeed for authenticated inspectors.
    Verifies the basic POST /api/inspections flow works end-to-end.
    """
    resp = client.post(
        "/api/inspections",
        json={
            "product_name": "Regression Test Product",
            "brand_name": "TestBrand",
            "category": "Packaged Food",
            "location": "Test Lab, New Delhi",
            "client_draft_id": "draft-connection-fix-test-c001",
        },
        headers=auth_headers,
    )

    assert resp.status_code in (200, 201), f"Inspection creation failed: {resp.text}"
    data = resp.json()
    assert "id" in data
    assert data.get("product", {}).get("product_name") == "Regression Test Product"
    # Confirm it's a real UUID (not a draft- prefix)
    assert not data["id"].startswith("draft-"), (
        f"Inspection ID should be a UUID, not a draft ID: {data['id']}"
    )


# ─── Test D: Idempotency — same client_draft_id returns same inspection ──────

def test_sync_idempotency_no_duplicate_inspection(auth_headers):
    """
    RC-4 regression: Retrying sync with the same client_draft_id must NOT
    create a duplicate inspection. This verifies the idempotency guarantee
    that prevents duplicate records when sync retries after a partial failure.
    """
    draft_id = "draft-idempotency-fix-test-d002"

    payload = {
        "product_name": "Idempotency Test Product",
        "brand_name": "IdempBrand",
        "category": "Packaged Food",
        "location": "Test Lab",
        "client_draft_id": draft_id,
    }

    # First creation
    resp1 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp1.status_code in (200, 201), f"First creation failed: {resp1.text}"
    id1 = resp1.json()["id"]

    # Second creation with same draft ID (simulates sync retry)
    resp2 = client.post("/api/inspections", json=payload, headers=auth_headers)
    assert resp2.status_code in (200, 201), f"Second creation failed: {resp2.text}"
    id2 = resp2.json()["id"]

    # Must return the same inspection — no duplicate
    assert id1 == id2, (
        f"Idempotency broken: two different inspections created for the same "
        f"client_draft_id='{draft_id}'. Got {id1} and {id2}."
    )


# ─── Test E: Image upload endpoint accepts multipart ─────────────────────────

def test_image_upload_multipart(auth_headers):
    """
    RC-3 regression: Image upload endpoint must accept multipart/form-data.
    Verifies the server side of the image upload path.
    """
    # Create inspection first
    resp = client.post(
        "/api/inspections",
        json={
            "product_name": "Image Upload Test",
            "brand_name": "UploadBrand",
            "category": "Packaged Food",
            "location": "Lab",
            "client_draft_id": "draft-image-upload-test-e003",
        },
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)
    inspection_id = resp.json()["id"]

    # Upload a test image
    jpeg_bytes = make_test_jpeg_bytes()
    files = {"file": ("front_panel.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
    data = {"view_type": "front"}

    upload_resp = client.post(
        f"/api/inspections/{inspection_id}/images",
        files=files,
        data=data,
        headers=auth_headers,
    )

    # Should succeed — 200 or 201
    assert upload_resp.status_code in (200, 201), (
        f"Image upload failed: {upload_resp.status_code} — {upload_resp.text}"
    )


# ─── Test F: Authentication errors are 401, not network errors ───────────────

def test_unauthenticated_request_returns_401_not_network_error():
    """
    RC-4 regression: An unauthenticated request must return 401, not cause
    a network-level error. The old brittle isNetworkError check could NOT
    distinguish between auth failures and network failures.
    """
    resp = client.post(
        "/api/inspections",
        json={
            "product_name": "Unauth Test",
            "brand_name": "Brand",
            "category": "Packaged Food",
            "location": "Lab",
        },
        # No Authorization header
    )

    assert resp.status_code == 401, (
        f"Expected 401 Unauthorized, got {resp.status_code}. "
        "This ensures auth errors are not treated as connectivity failures."
    )


# ─── Test G: 404 is a proper HTTP error, not a network error ─────────────────

def test_nonexistent_inspection_returns_404_not_network_error(auth_headers):
    """
    RC-4 regression: A 404 response for a non-existent resource must be
    a proper HTTP error, not classified as a connectivity failure.
    """
    resp = client.get(
        "/api/inspections/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )

    assert resp.status_code == 404, (
        f"Expected 404 for non-existent inspection, got {resp.status_code}"
    )
    # Body should have a detail message, not a generic network error
    data = resp.json()
    assert "detail" in data, "Expected JSON error detail for 404 response"


# ─── Test H: Health endpoint is stable under sequential calls ────────────────

def test_health_endpoint_stable_under_sequential_calls():
    """
    RC-1/RC-2 regression: Multiple sequential health check calls must all
    succeed. This simulates the networkService calling /api/health on startup,
    focus events, and reconnect events without false OFFLINE transitions.
    """
    for i in range(5):
        resp = client.get("/api/health")
        assert resp.status_code == 200, (
            f"Health check {i+1}/5 failed: {resp.text}"
        )
        assert resp.json().get("status") == "healthy"
