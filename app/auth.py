from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import secrets
import hmac
from fastapi import Cookie, Depends, HTTPException, status, Request
from jose import JWTError, jwt

from app.auth_db import User, get_user_by_id
from app.config import get_settings

AUTH_COOKIE_NAME = "atm_rul_token"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user: User) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expiration_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": expires_at,
    }
    
    # Use RS256 with private key if available, otherwise fallback to HS256
    if settings.jwt_private_key_path and Path(settings.jwt_private_key_path).exists():
        try:
            private_key = Path(settings.jwt_private_key_path).read_text()
            return jwt.encode(payload, private_key, algorithm="RS256")
        except Exception:
            # Fall back to HS256 if private key is invalid
            pass
    
    # Fallback to HS256 for development
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def get_current_user(atm_rul_token: str | None = Cookie(default=None)) -> User:
    if not atm_rul_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    settings = get_settings()
    try:
        # Try RS256 first, then fall back to HS256
        public_key_path = Path(settings.jwt_public_key_path) if settings.jwt_public_key_path else None
        if settings.jwt_algorithm == "RS256" and public_key_path and public_key_path.exists():
            public_key = Path(settings.jwt_public_key_path).read_text()
            payload = jwt.decode(atm_rul_token, public_key, algorithms=["RS256"])
        else:
            payload = jwt.decode(atm_rul_token, settings.jwt_secret_key, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token") from exc

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


def get_current_user_optional(token: str | None = Cookie(default=None, alias="atm_rul_token")) -> Optional[User]:
    """Get current user if authenticated, otherwise return None (for optional auth pages)."""
    if not token:
        return None
    try:
        settings = get_settings()
        # Try RS256 first, then fallback to HS256
        public_key_path = Path(settings.jwt_public_key_path) if settings.jwt_public_key_path else None
        if settings.jwt_algorithm == "RS256" and Path(settings.jwt_public_key_path).exists():
            public_key = Path(settings.jwt_public_key_path).read_text()
            payload = jwt.decode(token, public_key, algorithms=["RS256"])
        else:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None

    return get_user_by_id(user_id)



