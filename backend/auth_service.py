from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.config import settings
from backend.database import get_db
from backend.models import User
from backend.auth_utils import verify_password

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Optional[User]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
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

    user = db.query(User).filter(User.officer_id == officer_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Officer not found"
        )
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

