"""Middleware stack — strict order per Bootstrap P0.5 + sec 3.3 of MYEXCELLENCE.md.

Order:
  1. CorrelationMiddleware    (logs)
  2. TenantMiddleware         (extracts tenant context for /api/* if logged in)
  3. AuthMiddleware           (validates JWT for protected routes)
  4. RbacMiddleware           (per-route permissions — applied via dependencies)
  5. ThrottleMiddleware       (rate limit per IP)

CSRF is N/A: we use Bearer/cookie JWT with SameSite=Lax (no cookie-based form posts).
"""
from __future__ import annotations
import secrets
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import APP_ENV
from core.errors import ErrorCode
from core.http import get_client_ip
from core.logger import log, set_correlation_id
from core.rate_limit import hit
from core.response import fail
from core.security import decode_token
from core.db import get_db

from .context import CurrentUser, TenantContext


# Bundle H · UserScopeAssignment — helper para cargar la lista de clients
# permitidos por usuario externo. Hace lazy-migration del campo legacy
# `users.client_id` (Bundle G) → fila en `user_scope_assignments` (Bundle H).
async def _load_allowed_client_ids(db, user_doc: dict) -> list[str]:
    """Iter57 — cargar scopes para usuarios externos (obligatorio) **y para
    internos con asignación explícita** en `user_scope_assignments`.

    Comportamiento por rol:
    - `client_viewer/client_auditor` (externos): siempre carga scopes (legacy
      `users.client_id` se migra a una fila lazy en `user_scope_assignments`).
    - Internos (`agent/supervisor/coordinator`): consulta `user_scope_assignments`.
      Si hay filas → devolverá la lista (restringe lo que el usuario ve).
      Si NO hay filas → devuelve `[]` (visión completa del tenant — comportamiento
      legacy preservado para no romper tenants sin scopes configurados).
    - `root_dev/superadmin/admin`: siempre `[]` (sin restricción).
    """
    role = user_doc.get("role")
    if role in ("root_dev", "superadmin", "admin"):
        return []
    tenant_id = user_doc["tenant_id"]
    user_id = user_doc["id"]
    cursor = db.user_scope_assignments.find(
        {"tenant_id": tenant_id, "user_id": user_id, "client_id": {"$ne": None}},
        {"_id": 0, "client_id": 1},
    )
    rows = await cursor.to_list(length=200)
    client_ids = [r["client_id"] for r in rows]
    # Lazy migration desde el campo legacy users.client_id si aún no se migró.
    # Aplica para externos (que siempre tenían `client_id`) — los internos
    # no tenían `client_id` en el doc, así que no entran a este path.
    legacy_cid = user_doc.get("client_id")
    if legacy_cid and legacy_cid not in client_ids:
        from core.uuid import new_id
        from datetime import datetime, timezone
        try:
            await db.user_scope_assignments.insert_one({
                "id": new_id(),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "client_id": legacy_cid,
                "subclient_id": None,
                "project_id": None,
                "assigned_by": None,  # legacy
                "assigned_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:  # noqa: BLE001 — race con índice único: ya migrado
            pass
        client_ids.append(legacy_cid)
    return client_ids


# ---------- 1. Correlation ID ----------------------------------------------
class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        cid = request.headers.get("X-Correlation-ID") or "cid_" + secrets.token_hex(6)
        set_correlation_id(cid)
        request.state.correlation_id = cid
        started = time.time()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("unhandled_exception", extra={"context": {"path": request.url.path}})
            if APP_ENV == "production":
                # R17: never expose stack traces in prod
                response = fail(ErrorCode.INTERNAL_ERROR, "Internal error.", request_id=cid)
            else:
                raise
        response.headers["X-Correlation-ID"] = cid
        log.info(
            "request",
            extra={
                "context": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": getattr(response, "status_code", 0),
                    "duration_ms": int((time.time() - started) * 1000),
                }
            },
        )
        return response


# ---------- 2. Auth + Tenant -----------------------------------------------
PUBLIC_PATHS = {
    "/api/system/health",
    "/api/system/version",
    "/api/auth/login",
    "/api/auth/logout",
    "/docs",
    "/openapi.json",
    "/redoc",
}

PUBLIC_PREFIXES = (
    "/api/guias/ingest/webhook",  # validated by HMAC, not session
    "/api/reclamos/ingest/",       # carrier dictamen webhook (R18)
    "/api/webhooks/zenvia/",       # Zenvia inbound — validated by HMAC SHA-256
    "/api/webhooks/resend/",       # Iter55 — Resend inbound — Svix signature
    "/api/webhook-test/",          # public test echo + chaos harness
)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return True
    if not path.startswith("/api/"):
        return True  # Non-API paths are handled by the React SPA
    return False


class AuthTenantMiddleware(BaseHTTPMiddleware):
    """Combined Auth + Tenant — order preserved (tenant context is built from auth)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request.state.user = None
        request.state.tenant = None

        if _is_public(request.url.path):
            return await call_next(request)

        token = request.cookies.get("access_token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            return fail(ErrorCode.AUTH_REQUIRED, "Autenticación requerida.")

        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                return fail(ErrorCode.AUTH_REQUIRED, "Token inválido.")
        except Exception:  # noqa: BLE001
            return fail(ErrorCode.AUTH_REQUIRED, "Token inválido o expirado.")

        db = get_db()
        user = await db.users.find_one(
            {"id": payload["sub"], "status": "active"}, {"_id": 0, "password_hash": 0}
        )
        if not user:
            return fail(ErrorCode.AUTH_REQUIRED, "Usuario no encontrado o inactivo.")

        tenant = await db.tenants.find_one({"id": user["tenant_id"]}, {"_id": 0})
        if not tenant:
            return fail(ErrorCode.AUTH_REQUIRED, "Tenant no encontrado.")

        # Tenant maintenance redirect — root_dev can still operate
        if tenant["status"] == "maintenance" and user["role"] != "root_dev":
            return fail(ErrorCode.TENANT_MAINTENANCE, "Tenant en mantenimiento.")
        if tenant["status"] == "suspended":
            return fail(ErrorCode.TENANT_MAINTENANCE, "Tenant suspendido.")

        request.state.user = CurrentUser(
            id=user["id"],
            tenant_id=user["tenant_id"],
            email=user["email"],
            role=user["role"],
            name=user.get("name", ""),
            # Bundle G · G-04 — refresco en cada request (no cachear en JWT).
            # Si admin cambia client_id de un externo, la próxima request lo aplica.
            client_id=user.get("client_id"),
            # Bundle H — lista de clients permitidos. Para externos se calcula
            # desde user_scope_assignments con lazy-migration del legacy users.client_id.
            # Para internos queda vacía (visión completa del tenant).
            allowed_client_ids=await _load_allowed_client_ids(db, user),
        )
        request.state.tenant = TenantContext(
            id=tenant["id"], slug=tenant["slug"], status=tenant["status"]
        )
        return await call_next(request)


# ---------- 3. Throttle (global IP) ----------------------------------------
class ThrottleMiddleware(BaseHTTPMiddleware):
    """Coarse global throttle: 240 req/min per IP. Per-endpoint limits live in routes."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        ip = get_client_ip(request)
        allowed, retry = hit(f"global:{ip}", max_hits=240, window_seconds=60)
        if not allowed:
            response = fail(ErrorCode.RATE_LIMITED, "Demasiadas solicitudes. Intente más tarde.")
            response.headers["Retry-After"] = str(retry)
            return response
        return await call_next(request)
