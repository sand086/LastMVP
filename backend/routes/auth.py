"""Auth routes — /api/auth/login, /logout, /me, /redirect-target.

Per MYEXCELLENCE.md sec 8 + auth playbook.
"""
from __future__ import annotations
from fastapi import APIRouter, Request

from core.config import APP_ENV, SESSION_LIFETIME_SECONDS
from core.errors import ErrorCode
from core.http import get_client_ip
from core.logger import log
from core.rate_limit import hit, reset
from core.response import fail, ok
from core.security import create_access_token, verify_password
from core.config import LOGIN_MAX_ATTEMPTS, LOGIN_LOCKOUT_SECONDS
from middleware.rbac import default_landing_for, require_authenticated
from repositories.users import UserRepository
from repositories.tenants import TenantRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return fail(ErrorCode.VALIDATION_FAILED, "Body JSON inválido.")

    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password:
        return fail(ErrorCode.VALIDATION_FAILED, "Email y password son obligatorios.",
                    field="email" if not email else "password")

    ip = get_client_ip(request)
    identifier = f"{ip}:{email}"

    # Brute-force check (R09 — anti brute-force)
    allowed, retry = hit(identifier, max_hits=LOGIN_MAX_ATTEMPTS, window_seconds=LOGIN_LOCKOUT_SECONDS)
    if not allowed:
        resp = fail(ErrorCode.RATE_LIMITED, "Demasiados intentos. Intente más tarde.")
        resp.headers["Retry-After"] = str(retry)
        return resp

    users = UserRepository()
    user = await users.by_email(email)
    if not user or user.get("status") != "active":
        # Sec 8 - do not reveal that user exists or is inactive
        log.warning("login_failed", extra={"context": {"email": email, "reason": "no_user_or_inactive"}})
        return fail(ErrorCode.AUTH_REQUIRED, "Credenciales inválidas.")

    if not verify_password(password, user["password_hash"]):
        log.warning("login_failed", extra={"context": {"email": email, "reason": "bad_password"}})
        return fail(ErrorCode.AUTH_REQUIRED, "Credenciales inválidas.")

    # Tenant maintenance check (root_dev bypasses)
    tenants = TenantRepository()
    tenant = await tenants.col.find_one({"id": user["tenant_id"]}, {"_id": 0})
    if not tenant:
        return fail(ErrorCode.AUTH_REQUIRED, "Tenant no encontrado.")
    if tenant["status"] == "suspended":
        return fail(ErrorCode.TENANT_MAINTENANCE, "Tenant suspendido.")

    reset(identifier)
    await users.touch_login(user["id"])

    token = create_access_token(
        user_id=user["id"], tenant_id=user["tenant_id"],
        role=user["role"], email=user["email"],
        client_id=user.get("client_id"),
    )
    secure_cookie = APP_ENV == "production"

    response = ok({
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user.get("name", ""),
            "role": user["role"],
            "tenant_id": user["tenant_id"],
            # Bundle G · G-01 — exponer client_id al frontend para
            # decisiones de routing/UI (no es secreto, ya está en el JWT).
            "client_id": user.get("client_id"),
        },
        "access_token": token,  # also returned in body for non-cookie clients
        "redirect_to": (
            "/maintenance" if tenant["status"] == "maintenance" and user["role"] != "root_dev"
            else default_landing_for(user["role"])
        ),
    })
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=SESSION_LIFETIME_SECONDS,
        path="/",
    )
    return response


@router.post("/logout")
async def logout():
    response = ok({"message": "Sesión cerrada."})
    response.delete_cookie("access_token", path="/")
    return response


@router.get("/me")
async def me(request: Request):
    user = await require_authenticated(request)
    return ok({
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "client_id": user.client_id,  # Bundle G · G-01
        "default_landing": default_landing_for(user.role),
    })


@router.get("/redirect-target")
async def redirect_target(request: Request):
    """Used by the frontend RBAC fallback page (/default) to pick where to land."""
    user = await require_authenticated(request)
    return ok({"redirect_to": default_landing_for(user.role)})
