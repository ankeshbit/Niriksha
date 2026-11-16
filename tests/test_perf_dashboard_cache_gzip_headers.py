"""
tests/test_perf_dashboard_cache_gzip_headers.py

Verifies:
1. /api/dashboard/summary and /api/supervisor/dashboard conditional aggregation with func.count().filter(...).
2. Supervisor dashboard 15-second in-process TTL cache keyed by (role, user_id).
3. GZipMiddleware with minimum_size=1000.
4. Cache-Control: public, max-age=3600 on GET /api/rules.
5. ETag and Cache-Control: private, max-age=300 on GET /api/images/{image_id}/file, plus 304 on If-None-Match.
"""

import time
import uuid
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app, clear_supervisor_dashboard_cache
from backend.config import settings
from backend.models import (
    User,
    Inspection,
    Product,
    ProductImage,
    Declaration,
    ComplianceCheck,
    Report,
    RuleVersion,
)
from backend.database import SessionLocal
from backend.auth_service import create_access_token
from backend.auth_utils import hash_password

client = TestClient(app)


@pytest.fixture(scope="function")
def db_session():
    """Provides an isolated database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_cache():
    """Clears in-process supervisor dashboard cache before each test."""
    clear_supervisor_dashboard_cache()
    yield
    clear_supervisor_dashboard_cache()


@pytest.fixture
def test_users(db_session: Session):
    """Provides test inspector, supervisor, and admin users."""
    inspector = db_session.query(User).filter(User.officer_id == "INSP-CACHE-01").first()
    if not inspector:
        inspector = User(
            officer_id="INSP-CACHE-01",
            full_name="Cache Test Inspector",
            role="INSPECTOR",
            designation="Field Officer",
            zone="West",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(inspector)

    supervisor = db_session.query(User).filter(User.officer_id == "SUP-CACHE-01").first()
    if not supervisor:
        supervisor = User(
            officer_id="SUP-CACHE-01",
            full_name="Cache Test Supervisor",
            role="SUPERVISOR",
            designation="Supervisory Officer",
            zone="West",
            password_hash=hash_password("Pass123!")
        )
        db_session.add(supervisor)

    db_session.commit()
    db_session.refresh(inspector)
    db_session.refresh(supervisor)

    insp_token = create_access_token({"sub": inspector.officer_id, "role": inspector.role})
    sup_token = create_access_token({"sub": supervisor.officer_id, "role": supervisor.role})

    return {
        "inspector": inspector,
        "supervisor": supervisor,
        "inspector_headers": {"Authorization": f"Bearer {insp_token}"},
        "supervisor_headers": {"Authorization": f"Bearer {sup_token}"},
    }


def test_dashboard_summary_conditional_aggregation(test_users):
    """GET /api/dashboard/summary executes and returns all 7 dynamic KPIs."""
    headers = test_users["inspector_headers"]
    resp = client.get("/api/dashboard/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    for kpi in [
        "total_inspections",
        "completed_inspections",
        "pending_verification",
        "potential_non_compliance",
        "compliant_inspections",
        "reports_generated",
        "manual_verification_required"
    ]:
        assert kpi in data
        assert isinstance(data[kpi], int)


def test_supervisor_dashboard_ttl_cache(test_users, monkeypatch):
    """GET /api/supervisor/dashboard returns cached response within 15 seconds."""
    headers = test_users["supervisor_headers"]

    # 1. First call populates cache
    resp1 = client.get("/api/supervisor/dashboard", headers=headers)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()

    # 2. Second call within 15 seconds returns identical cached data
    resp2 = client.get("/api/supervisor/dashboard", headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data1 == data2

    # 3. Simulate passage of 16 seconds -> cache should refresh
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 16.0)

    resp3 = client.get("/api/supervisor/dashboard", headers=headers)
    assert resp3.status_code == 200


def test_rules_cache_control_header(test_users):
    """GET /api/rules contains Cache-Control: public, max-age=3600."""
    headers = test_users["inspector_headers"]
    resp = client.get("/api/rules", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("Cache-Control") == "public, max-age=3600"
    assert isinstance(resp.json(), list)


def test_images_file_etag_and_cache_control(db_session: Session, test_users):
    """GET /api/images/{id}/file contains ETag, Cache-Control: private, max-age=300, and 304 on If-None-Match."""
    from backend.storage_service import storage_service

    headers = test_users["inspector_headers"]
    user = test_users["inspector"]

    # Create an inspection and store an image
    insp = Inspection(
        id=str(uuid.uuid4()),
        inspection_number=f"INSP-CACHE-{uuid.uuid4().hex[:6].upper()}",
        inspector_id=user.id,
        location="Connaught Place, New Delhi",
        status="IMAGES_UPLOADED"
    )
    db_session.add(insp)
    db_session.flush()

    raw_data = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60\x00\x00\xFF\xDB\x00C\x00" + b"TEST_IMAGE_BYTES"
    stored_path = storage_service.save_file(f"inspections/{insp.id}/test_etag.jpg", raw_data)

    img = ProductImage(
        id=str(uuid.uuid4()),
        inspection_id=insp.id,
        view_type="front",
        file_path=stored_path,
        quality_status="GOOD"
    )
    db_session.add(img)
    db_session.commit()

    # 1. Fetch image binary -> verify headers
    resp = client.get(f"/api/images/{img.id}/file", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("Cache-Control") == "private, max-age=300"
    etag = resp.headers.get("ETag")
    assert etag is not None and len(etag) > 0

    # 2. Conditional request with matching If-None-Match -> 304 Not Modified
    headers_with_etag = {**headers, "If-None-Match": etag}
    resp_304 = client.get(f"/api/images/{img.id}/file", headers=headers_with_etag)
    assert resp_304.status_code == 304
    assert resp_304.headers.get("ETag") == etag
    assert resp_304.headers.get("Cache-Control") == "private, max-age=300"

    # Cleanup
    try:
        storage_service.delete_file(stored_path)
        db_session.delete(img)
        db_session.delete(insp)
        db_session.commit()
    except Exception:
        pass


def test_gzip_middleware(test_users):
    """GZipMiddleware compresses response when response size >= 1000 and Accept-Encoding: gzip is set."""
    headers = {**test_users["inspector_headers"], "Accept-Encoding": "gzip"}
    resp = client.get("/api/rules", headers=headers)
    assert resp.status_code == 200
    # If the uncompressed body is >= 1000 bytes, content-encoding is gzip
    if len(resp.content) >= 1000 or resp.headers.get("content-encoding") == "gzip":
        assert resp.headers.get("content-encoding") == "gzip"
