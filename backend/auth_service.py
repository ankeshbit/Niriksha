import hashlib
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend.config import settings
from backend.database import get_db
from backend.models import User, RevokedToken
from backend.auth_utils import verify_password

logger = logging.getLogger("backend.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Lightweight in-process cache for fast revocation checks (<0.1ms overhead)
# Maps token_hash -> expiry_timestamp
_revocation_cache: Dict[str, float] = {}


def hash_token(token: str) -> str:
    """Computes a SHA-256 hash of a JWT token string."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a signed JWT access token containing standard subject,
    expiration (exp), issued-at (iat), and unique token ID (jti) claims.
    """
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": now.timestamp(),
        "jti": str(uuid.uuid4())
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def is_token_revoked(db: Session, token: str) -> bool:
    """
    Checks if a JWT token has been explicitly revoked on the server side.
    Fast path: in-memory cache lookup.
    Authoritative path: PostgreSQL revoked_tokens table lookup.
    """
    if not token or not isinstance(token, str):
        return True

    token_h = hash_token(token)
    now_ts = datetime.utcnow().timestamp()

    # Fast cache check
    cached_exp = _revocation_cache.get(token_h)
    if cached_exp is not None:
        if cached_exp > now_ts:
            return True
        else:
            _revocation_cache.pop(token_h, None)

    # Database authoritative check
    entry = db.query(RevokedToken).filter(RevokedToken.token_hash == token_h).first()
    if entry:
        entry_exp = entry.expires_at.timestamp() if entry.expires_at else (now_ts + 3600)
        if entry_exp > now_ts:
            _revocation_cache[token_h] = entry_exp
            return True
        else:
            # Expired revocation entry
            return False

    return False


def revoke_token(
    db: Session,
    token: str,
    officer_id: Optional[str] = None,
    reason: str = "LOGOUT"
) -> bool:
    """
    Authoritatively revokes a JWT token on the server side by persisting its hash
    to the PostgreSQL revoked_tokens store and updating the fast in-memory cache.
    """
    if not token or not isinstance(token, str):
        return False

    token_h = hash_token(token)
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    resolved_officer_id = officer_id or "UNKNOWN"

    # Safely extract exp and sub from unverified token payload if possible
    try:
        unverified_payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_signature": False, "verify_exp": False}
        )
        if not officer_id and unverified_payload.get("sub"):
            resolved_officer_id = str(unverified_payload["sub"])
        if unverified_payload.get("exp"):
            exp_val = unverified_payload["exp"]
            if isinstance(exp_val, (int, float)):
                expires_at = datetime.utcfromtimestamp(exp_val)
    except Exception:
        pass

    # Update in-memory fast cache
    _revocation_cache[token_h] = expires_at.timestamp()

    # Persist to database
    try:
        revoked_entry = RevokedToken(
            token_hash=token_h,
            officer_id=resolved_officer_id,
            expires_at=expires_at,
            revoked_at=now,
            reason=reason
        )
        db.merge(revoked_entry)
        db.commit()
        logger.info(f"[TOKEN_REVOKED] Token for {resolved_officer_id} revoked ({reason}).")
        return True
    except IntegrityError:
        db.rollback()
        return True
    except Exception as exc:
        db.rollback()
        logger.error(f"[TOKEN_REVOCATION_ERR] Could not persist token revocation: {exc}")
        return False


def cleanup_expired_revoked_tokens(db: Session) -> int:
    """Removes expired entries from revoked_tokens table to keep storage minimal."""
    try:
        now = datetime.utcnow()
        deleted = db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete(synchronize_session=False)
        db.commit()
        # Clean local cache as well
        now_ts = now.timestamp()
        expired_keys = [k for k, exp in _revocation_cache.items() if exp < now_ts]
        for k in expired_keys:
            _revocation_cache.pop(k, None)
        return deleted
    except Exception as exc:
        db.rollback()
        logger.warning(f"[REVOCATION_CLEANUP_WARN] {exc}")
        return 0


def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Optional[User]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 1. Server-side Revocation Check (Token Blacklist)
    if is_token_revoked(db, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 2. Cryptographic signature and claim verification
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        officer_id: str = payload.get("sub")
        if officer_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": "Bearer"}
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 3. User Existence and Active Status
    user = db.query(User).filter(User.officer_id == officer_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Officer not found",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 4. Password Rotation Invalidation (User-level Token Family Invalidation)
    token_iat = payload.get("iat")
    if user.password_updated_at and token_iat is not None:
        try:
            pwd_updated_ts = user.password_updated_at.timestamp()
            # Allow 1-second clock skew margin
            if float(token_iat) < (pwd_updated_ts - 1.0):
                # Automatically blacklist this stale token
                revoke_token(db, token, officer_id=user.officer_id, reason="PASSWORD_ROTATED")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session invalidated due to password change. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"}
                )
        except (ValueError, TypeError):
            pass

    return user


class RoleChecker:
    """FastAPI dependency to enforce role-based access control."""
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = {r.upper() for r in allowed_roles}

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_role = (current_user.role or "INSPECTOR").upper()
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: required role in {sorted(list(self.allowed_roles))}, your role is '{user_role}'"
            )
        return current_user


def require_roles(*roles: str):
    """Factory helper for role checking dependency."""
    return RoleChecker(list(roles))


# Standard Role Dependencies for PS 26034
require_inspector = RoleChecker(["INSPECTOR", "ADMIN"])
require_supervisor_or_admin = RoleChecker(["SUPERVISOR", "ADMIN"])
require_supervisor = RoleChecker(["SUPERVISOR", "ADMIN"])
require_admin = RoleChecker(["ADMIN"])
