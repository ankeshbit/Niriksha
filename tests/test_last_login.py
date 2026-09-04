"""
tests/test_last_login.py
Verifies that the backend records and exposes the real previous_login_at and last_login_at:
A. First successful login:
   previous_login_at = null
   last_login_at gets populated.
B. Second successful login:
   previous_login_at equals the first login timestamp.
   last_login_at becomes the second login timestamp.
C. Third successful login:
   previous_login_at equals the second login timestamp.
   last_login_at becomes the third login timestamp.
D. Failed login:
   last_login_at remains unchanged.
E. /api/auth/me returns previous_login_at and last_login_at.
F. Fresh user with null last_login_at handled gracefully.
"""
import time
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings
from backend.models import User
import backend.database as db_module

client = TestClient(app)


def test_first_second_third_login_sequence():
    """Verify sequence of first, second, and third logins correctly captures previous_login_at."""
    test_officer_id = "DOCA-SEQ-TESTER-001"
    test_password = "securePassword123"

    # Create fresh test user with no login history in test database
    db = db_module.SessionLocal()
    try:
        from backend.auth_utils import hash_password
        existing = db.query(User).filter(User.officer_id == test_officer_id).first()
        if existing:
            db.delete(existing)
            db.commit()

        user = User(
            officer_id=test_officer_id,
            full_name="Sequence Tester",
            designation="Inspector",
            zone="Test Zone",
            password_hash=hash_password(test_password),
            role="INSPECTOR",
            last_login_at=None,
            previous_login_at=None
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    # --- A. FIRST LOGIN ---
    r1 = client.post("/api/auth/login", json={
        "officer_id": test_officer_id,
        "password": test_password
    })
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["previous_login_at"] is None, "First login must have previous_login_at = None"
    assert data1["last_login_at"] is not None, "First login must populate last_login_at"
    first_login_time = data1["last_login_at"]

    # Verify /api/auth/me on first login
    r_me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data1['access_token']}"})
    assert r_me1.status_code == 200
    assert r_me1.json()["previous_login_at"] is None
    assert r_me1.json()["last_login_at"] == first_login_time

    time.sleep(0.05)

    # --- B. SECOND LOGIN ---
    r2 = client.post("/api/auth/login", json={
        "officer_id": test_officer_id,
        "password": test_password
    })
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["previous_login_at"] == first_login_time, (
        f"Second login previous_login_at ({data2['previous_login_at']}) must equal first login time ({first_login_time})"
    )
    assert data2["last_login_at"] is not None
    assert data2["last_login_at"] != first_login_time
    second_login_time = data2["last_login_at"]

    # Verify /api/auth/me on second login
    r_me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data2['access_token']}"})
    assert r_me2.status_code == 200
    assert r_me2.json()["previous_login_at"] == first_login_time
    assert r_me2.json()["last_login_at"] == second_login_time

    time.sleep(0.05)

    # --- C. THIRD LOGIN ---
    r3 = client.post("/api/auth/login", json={
        "officer_id": test_officer_id,
        "password": test_password
    })
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["previous_login_at"] == second_login_time, (
        f"Third login previous_login_at ({data3['previous_login_at']}) must equal second login time ({second_login_time})"
    )
    assert data3["last_login_at"] is not None
    third_login_time = data3["last_login_at"]

    # Verify /api/auth/me on third login
    r_me3 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data3['access_token']}"})
    assert r_me3.status_code == 200
    assert r_me3.json()["previous_login_at"] == second_login_time
    assert r_me3.json()["last_login_at"] == third_login_time


def test_failed_login_does_not_update_timestamps():
    """Verify failed login attempt does NOT modify last_login_at or previous_login_at."""
    # 1. Login successfully to establish baseline
    r1 = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert r1.status_code == 200
    baseline_data = r1.json()
    baseline_last = baseline_data["last_login_at"]
    baseline_prev = baseline_data.get("previous_login_at")

    time.sleep(0.05)

    # 2. Attempt failed login
    r_fail = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": "wrong_password_attempt"
    })
    assert r_fail.status_code == 401

    # 3. Check DB to ensure timestamps are completely untouched
    db = db_module.SessionLocal()
    try:
        officer = db.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
        assert officer is not None
        assert officer.last_login_at.isoformat().startswith(baseline_last[:19])
        if baseline_prev:
            assert officer.previous_login_at.isoformat().startswith(baseline_prev[:19])
    finally:
        db.close()


def test_null_last_login_handled_gracefully():
    """Verify a user who has never logged in returns null for both timestamps."""
    test_officer_id = "DOCA-NEVER-LOGGED-002"
    db = db_module.SessionLocal()
    try:
        from backend.auth_utils import hash_password
        existing = db.query(User).filter(User.officer_id == test_officer_id).first()
        if not existing:
            new_user = User(
                officer_id=test_officer_id,
                full_name="Never Logged Officer",
                designation="Inspector",
                zone="Testing Zone",
                password_hash=hash_password("password123"),
                role="INSPECTOR",
                last_login_at=None,
                previous_login_at=None
            )
            db.add(new_user)
            db.commit()
        else:
            existing.last_login_at = None
            existing.previous_login_at = None
            db.commit()
    finally:
        db.close()

    from backend.auth_service import create_access_token
    token = create_access_token(data={"sub": test_officer_id, "role": "INSPECTOR"})
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["last_login_at"] is None
    assert me["previous_login_at"] is None
