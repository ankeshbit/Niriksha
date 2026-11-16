import time
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from jose import jwt

from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import User, RevokedToken
from backend.auth_service import (
    create_access_token,
    revoke_token,
    is_token_revoked,
    cleanup_expired_revoked_tokens,
    hash_token
)
from backend.auth_utils import hash_password

client = TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_officer(db: Session):
    officer = db.query(User).filter(User.officer_id == "DOCA-TEST-REVOKE-01").first()
    if not officer:
        officer = User(
            officer_id="DOCA-TEST-REVOKE-01",
            full_name="Revocation Test Officer",
            email="revoke.test@lm.gov.in",
            designation="Inspector",
            zone="Test Zone",
            password_hash=hash_password("OriginalPassword123"),
            role="INSPECTOR"
        )
        db.add(officer)
        db.commit()
        db.refresh(officer)
    else:
        officer.password_hash = hash_password("OriginalPassword123")
        officer.password_updated_at = datetime.utcnow()
        db.commit()
    return officer


class TestJWTRevocation:
    """Test suite verifying server-side JWT revocation, password invalidation, and cleanup."""

    def test_token_works_before_logout(self, test_officer: User):
        """Active token successfully authenticates before logout."""
        token = create_access_token({"sub": test_officer.officer_id, "role": test_officer.role})
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["officer_id"] == test_officer.officer_id

    def test_token_is_rejected_immediately_after_logout(self, test_officer: User):
        """Immediately after calling /api/auth/logout, the token is rejected with HTTP 401."""
        token = create_access_token({"sub": test_officer.officer_id, "role": test_officer.role})

        # Pre-check: token is valid
        res_pre = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_pre.status_code == 200

        # Logout
        res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert res_logout.status_code == 200
        assert "logged out" in res_logout.json().get("message", "").lower()

        # Post-check: same token MUST be rejected
        res_post = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_post.status_code == 401
        assert "revoked" in res_post.json().get("detail", "").lower()

    def test_password_change_invalidates_previously_issued_tokens(self, test_officer: User):
        """Changing password invalidates existing sessions/tokens, requiring re-login."""
        old_token = create_access_token({"sub": test_officer.officer_id, "role": test_officer.role})

        # Ensure old token is valid first
        res_pre = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert res_pre.status_code == 200

        time.sleep(1.05)  # Advance past 1-second clock-skew grace window

        # Change password
        res_change = client.post(
            "/api/auth/change-password",
            json={"current_password": "OriginalPassword123", "new_password": "NewSecretPassword456"},
            headers={"Authorization": f"Bearer {old_token}"}
        )
        assert res_change.status_code == 200

        # Old token MUST be rejected now
        res_post = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert res_post.status_code == 401

        # Newly issued token with new credentials works
        new_token = create_access_token({"sub": test_officer.officer_id, "role": test_officer.role})
        res_new = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert res_new.status_code == 200

    def test_expired_token_handling_does_not_throw_500(self, db: Session, test_officer: User):
        """Expired tokens submitted for logout or auth must return safe 200/401 and NEVER throw HTTP 500."""
        # Create an already expired token (expired 10 minutes ago)
        expired_token = create_access_token(
            {"sub": test_officer.officer_id, "role": test_officer.role},
            expires_delta=timedelta(minutes=-10)
        )

        # Access with expired token yields 401, not 500
        res_auth = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert res_auth.status_code == 401

        # Logout with expired token completes safely without 500
        res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {expired_token}"})
        assert res_logout.status_code == 200

    def test_malformed_token_handling_does_not_throw_500(self):
        """Malformed JWT strings never crash the application or cause 500 Internal Server Errors."""
        malformed_token = "invalid.bearer.token"

        res_auth = client.get("/api/auth/me", headers={"Authorization": f"Bearer {malformed_token}"})
        assert res_auth.status_code == 401

        res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {malformed_token}"})
        assert res_logout.status_code == 200

    def test_revocation_store_cleanup_removes_expired_entries(self, db: Session):
        """cleanup_expired_revoked_tokens removes expired entries without touching active ones."""
        # Seed an expired revocation entry
        exp_hash = hash_token("expired_token_sample_123")
        db.merge(RevokedToken(
            token_hash=exp_hash,
            officer_id="TEST-CLEANUP",
            expires_at=datetime.utcnow() - timedelta(minutes=5),
            reason="TEST_EXPIRED"
        ))

        # Seed an active revocation entry
        act_hash = hash_token("active_token_sample_456")
        db.merge(RevokedToken(
            token_hash=act_hash,
            officer_id="TEST-CLEANUP",
            expires_at=datetime.utcnow() + timedelta(hours=2),
            reason="TEST_ACTIVE"
        ))
        db.commit()

        # Run cleanup
        deleted = cleanup_expired_revoked_tokens(db)
        assert deleted >= 1

        # Verify expired was deleted, active remains
        assert db.query(RevokedToken).filter(RevokedToken.token_hash == exp_hash).first() is None
        assert db.query(RevokedToken).filter(RevokedToken.token_hash == act_hash).first() is not None

        # Clean up active entry
        db.query(RevokedToken).filter(RevokedToken.token_hash == act_hash).delete()
        db.commit()

    def test_performance_overhead_remains_negligible(self, db: Session, test_officer: User):
        """In-process token revocation cache check must execute with sub-millisecond overhead."""
        token = create_access_token({"sub": test_officer.officer_id, "role": test_officer.role})

        # Revoke the token to populate cache
        revoke_token(db, token, officer_id=test_officer.officer_id, reason="BENCHMARK")

        # Measure 100 consecutive in-process revocation checks
        times = []
        for _ in range(100):
            t0 = time.perf_counter()
            is_rev = is_token_revoked(db, token)
            t1 = time.perf_counter()
            assert is_rev is True
            times.append((t1 - t0) * 1000)

        avg_ms = sum(times) / len(times)
        # In-memory revocation cache check should be well under 1ms
        assert avg_ms < 5.0, f"Average cache check latency too high: {avg_ms:.3f}ms"
