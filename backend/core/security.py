"""Authentication primitives — bcrypt + JWT.

Aligned with auth playbook + MYEXCELLENCE.md sec 8.1:
- password_hash with bcrypt cost 12 (R05)
- JWT in httpOnly cookies, 8h lifetime (sec 8.1)
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt

from .config import BCRYPT_COST, SESSION_LIFETIME_SECONDS

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        # Fail closed — refuse to issue tokens without a configured secret in non-dev
        from .config import APP_ENV
        if APP_ENV == "production":
            raise RuntimeError("JWT_SECRET is required in production")
        return "dev-only-insecure-secret-replace-me"
    return secret


def create_access_token(*, user_id: str, tenant_id: str, role: str, email: str,
                         client_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "role": role,
        # Bundle G · G-01 — para externals, anclar al client_id en el token.
        # Sólo informativo: la fuente de verdad es BD (refresco en cada req).
        "client_id": client_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=SESSION_LIFETIME_SECONDS)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
