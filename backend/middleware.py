"""
Non-blocking audit logging and error tracking middleware for LastMile OS.
Captures request metrics, audit events, and errors asynchronously.
"""
import asyncio
import time
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import uuid
import logging

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' https://api.openai.com https://*.emergentagent.com wss://*.emergentagent.com"
        )
        # Default no-store for /api/* (sensitive data) — but skip for static/immutable
        # asset endpoints that benefit from long browser caching (e.g. Routal image
        # proxy serves URL-by-id assets that never change).
        path = request.url.path
        is_immutable_asset = (
            path.startswith("/api/integrations/routal/image/")
            or path.startswith("/api/integrations/routal/signature/")
        )
        if is_immutable_asset:
            # Force long browser cache; immutable per (report_id, image_id)
            response.headers["Cache-Control"] = "private, max-age=2592000, immutable"
            if "Pragma" in response.headers:
                del response.headers["Pragma"]
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
        return response

# Action mapping: endpoint pattern -> action name
ACTION_MAP = {
    ("POST", "/api/auth/login"): "login_attempt",
    ("POST", "/api/journeys/from-cosmo"): "layout_uploaded",
    ("POST", "/api/journeys"): "route_created",
    ("POST", "/api/incidents"): "incident_created",
    ("PUT", "/api/incidents"): "incident_updated",
    ("POST", "/api/users"): "user_created",
    ("PUT", "/api/users"): "user_modified",
    ("DELETE", "/api/users"): "user_deleted",
    ("GET", "/api/reports/export"): "export_generated",
    ("POST", "/api/reports/generate"): "export_generated",
    ("POST", "/api/reports/generate-excel"): "export_generated",
}


_PATTERN_RULES = [
    # (method, path_contains, path_endswith, action)
    ("POST", "/journeys/", "/start", "route_started"),
    ("POST", "/journeys/", "/close", "route_closed"),
    ("POST", "/journeys/", "/incidents", "incident_created"),
    ("PUT", "/incidents/", "/resolve", "incident_resolved"),
    ("PUT", "/incidents/", None, "incident_updated"),
    ("DELETE", "/users/", None, "user_deleted"),
    ("PUT", "/users/", None, "user_modified"),
    ("POST", "/upload/", None, "layout_uploaded"),
]


def _match_action(method: str, path: str) -> str:
    """Match a request to an audit action using lookup table then pattern rules."""
    key = (method, path)
    if key in ACTION_MAP:
        return ACTION_MAP[key]

    for rule_method, contains, endswith, action in _PATTERN_RULES:
        if method != rule_method or contains not in path:
            continue
        if endswith is None or path.endswith(endswith):
            return action

    return ""


_ENTITY_KEYWORDS = ["journeys", "incidents", "users", "upload", "reports"]
_ENTITY_TYPE_MAP = {
    "journeys": "journey",
    "incidents": "incident",
    "users": "user",
    "upload": "layout",
    "reports": "report",
}
_NO_ID_KEYWORDS = {"upload", "reports"}
_SKIP_ID_VALUES = {"from-cosmo"}


def _extract_entity(path: str) -> tuple:
    """Extract entity type and ID from path using lookup tables."""
    parts = path.strip("/").split("/")

    for keyword in _ENTITY_KEYWORDS:
        if keyword not in parts:
            continue
        entity_type = _ENTITY_TYPE_MAP[keyword]
        if keyword in _NO_ID_KEYWORDS:
            return entity_type, ""
        idx = parts.index(keyword)
        entity_id = ""
        if idx + 1 < len(parts) and parts[idx + 1] not in _SKIP_ID_VALUES:
            entity_id = parts[idx + 1]
        return entity_type, entity_id

    return "", ""


class AuditMiddleware(BaseHTTPMiddleware):
    """Async middleware for audit logging, error tracking, and performance metrics."""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        request_id = str(uuid.uuid4())[:8]
        
        # Extract user info from auth header (best effort)
        user_id = ""
        user_role = ""
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        method = request.method
        path = request.url.path
        
        # Skip static files and health checks for logging
        # Note: bare "/health" is included for k8s/monitor probes that don't use the
        # /api prefix — backend ingress still routes them here and they would
        # otherwise spam system_errors with 404s.
        skip_paths = ["/api/health", "/health", "/uploads/", "/static/", "/favicon.ico"]
        should_log = not any(path.startswith(sp) for sp in skip_paths)
        
        response = None
        error_detail = None
        
        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)
            status_code = response.status_code
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            status_code = 500
            error_detail = str(exc)
            raise
        finally:
            if should_log and hasattr(request, 'app'):
                try:
                    db = request.app.state.db
                    
                    # Non-blocking: fire and forget
                    asyncio.create_task(
                        self._log_request(
                            db, method, path, status_code, duration_ms,
                            client_ip, user_id, user_role, request_id, error_detail
                        )
                    )
                except Exception:
                    pass
        
        return response
    
    async def _log_request(self, db, method, path, status_code, duration_ms,
                           client_ip, user_id, user_role, request_id, error_detail):
        """Log request metrics and errors asynchronously."""
        try:
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            date_str = now.strftime("%Y-%m-%d")

            # Always store request metric
            await db.request_metrics.insert_one({
                "id": str(uuid.uuid4()),
                "timestamp": now_iso,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "hour": now.hour,
                "date": date_str,
            })

            if status_code >= 400:
                await self._track_error(db, method, path, status_code, client_ip, error_detail, now_iso)

            if status_code < 400:
                await self._track_audit(db, method, path, user_id, user_role, client_ip, status_code, now_iso, date_str)

        except Exception as e:
            logger.error(f"Middleware logging error: {e}")

    async def _track_error(self, db, method, path, status_code, client_ip, error_detail, now_iso):
        """Track 4xx/5xx errors in system_errors collection.
        Skip 'expected' errors (session expired, entity not found after delete, empty-result 404s)
        para no contaminar el Error Tracker con falsos positivos."""
        # 401 en endpoints con auth: expira sesión = flujo normal, no es error
        if status_code == 401:
            return

        # 429 (rate limit): respuesta defensiva esperada, NO es un bug del código.
        # Tracking these floods system_errors when bots/scripts hit limits.
        if status_code == 429:
            return

        # 404 en patrones de business-logic esperado
        if status_code == 404:
            expected_404_prefixes = (
                "/api/journeys/",          # ruta eliminada / URL tipeada
                "/api/packages/",          # paquete eliminado
                "/api/clients/",           # cliente eliminado
                "/api/providers/",         # proveedor eliminado
                "/api/users/",             # usuario eliminado
                "/api/lumi/active-context",# ruta del LumiChat ya borrada
                "/api/lumi/tools/journey-lookup",
                "/api/ai-evaluation/jobs/",# job inexistente
                "/api/architecture/snapshots/",
                "/api/admin/export-liquidacion",  # período sin datos
                "/api/admin/routes-report",       # idem
                "/api/reports/export",             # idem
                "/api/integrations/routal/image/", # imágenes Routal expiradas/borradas
                "/api/integrations/routal/signature/", # firmas Routal expiradas/borradas
            )
            if any(path.startswith(p) for p in expected_404_prefixes):
                return

        error_key = f"{method}:{path}:{status_code}"
        existing = await db.system_errors.find_one(
            {"error_key": error_key, "reviewed": False}, {"_id": 0}
        )

        if existing:
            await db.system_errors.update_one(
                {"id": existing["id"]},
                {"$inc": {"occurrence_count": 1}, "$set": {
                    "last_seen": now_iso, "last_detail": error_detail or "", "last_ip": client_ip,
                }}
            )
        else:
            error_type = "parsing_error" if "/upload/" in path else (
                "validation_error" if status_code == 422 else "api_error"
            )
            await db.system_errors.insert_one({
                "id": str(uuid.uuid4()), "error_key": error_key,
                "error_type": error_type, "method": method, "endpoint": path,
                "status_code": status_code, "detail": error_detail or "",
                "last_detail": error_detail or "", "last_ip": client_ip,
                "occurrence_count": 1, "first_seen": now_iso, "last_seen": now_iso,
                "reviewed": False, "reviewed_by": None, "reviewed_at": None,
            })

    async def _track_audit(self, db, method, path, user_id, user_role, client_ip, status_code, now_iso, date_str):
        """Log audit trail for critical actions."""
        action = _match_action(method, path)
        if not action:
            return
        entity_type, entity_id = _extract_entity(path)
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()), "timestamp": now_iso,
            "user_id": user_id, "user_role": user_role, "action": action,
            "entity_type": entity_type, "entity_id": entity_id,
            "ip": client_ip, "status": "success",
            "status_code": status_code, "details": "", "date": date_str,
        })


async def log_audit_event(db, user_id: str, user_role: str, action: str,
                          entity_type: str = "", entity_id: str = "",
                          ip: str = "", details: str = "", status: str = "success"):
    """Explicitly log an audit event from endpoint code."""
    try:
        now = datetime.now(timezone.utc)
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "timestamp": now.isoformat(),
            "user_id": user_id,
            "user_role": user_role,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "ip": ip,
            "status": status,
            "status_code": 200 if status == "success" else 400,
            "details": details,
            "date": now.strftime("%Y-%m-%d"),
        })
    except Exception as e:
        logger.error(f"Audit log error: {e}")


async def log_system_error(db, error_type: str, endpoint: str, method: str,
                           detail: str, status_code: int = 500, ip: str = ""):
    """Explicitly log a system error."""
    try:
        now = datetime.now(timezone.utc)
        error_key = f"{method}:{endpoint}:{status_code}:{error_type}"
        
        existing = await db.system_errors.find_one(
            {"error_key": error_key, "reviewed": False}, {"_id": 0}
        )
        
        if existing:
            await db.system_errors.update_one(
                {"id": existing["id"]},
                {
                    "$inc": {"occurrence_count": 1},
                    "$set": {"last_seen": now.isoformat(), "last_detail": detail}
                }
            )
        else:
            await db.system_errors.insert_one({
                "id": str(uuid.uuid4()),
                "error_key": error_key,
                "error_type": error_type,
                "method": method,
                "endpoint": endpoint,
                "status_code": status_code,
                "detail": detail,
                "last_detail": detail,
                "last_ip": ip,
                "occurrence_count": 1,
                "first_seen": now.isoformat(),
                "last_seen": now.isoformat(),
                "reviewed": False,
                "reviewed_by": None,
                "reviewed_at": None,
            })
    except Exception as e:
        logger.error(f"System error log error: {e}")
