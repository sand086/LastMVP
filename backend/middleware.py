"""
Non-blocking audit logging and error tracking middleware for LastMile OS.
Captures request metrics, audit events, and errors asynchronously.
"""
import asyncio
import time
import traceback
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import uuid
import logging

logger = logging.getLogger(__name__)

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


def _match_action(method: str, path: str) -> str:
    """Match a request to an audit action."""
    # Exact matches
    key = (method, path)
    if key in ACTION_MAP:
        return ACTION_MAP[key]
    
    # Pattern matches
    if method == "POST" and "/journeys/" in path:
        if path.endswith("/start"):
            return "route_started"
        if path.endswith("/close"):
            return "route_closed"
        if "/incidents" in path:
            return "incident_created"
    if method == "PUT" and "/incidents/" in path:
        if "/resolve" in path:
            return "incident_resolved"
        return "incident_updated"
    if method == "DELETE" and "/users/" in path:
        return "user_deleted"
    if method == "PUT" and "/users/" in path:
        if "/assignments" in path:
            return "user_modified"
        if "/password" in path:
            return "user_modified"
        return "user_modified"
    if method == "POST" and "/upload/" in path:
        return "layout_uploaded"
    
    return ""


def _extract_entity(path: str) -> tuple:
    """Extract entity type and ID from path."""
    parts = path.strip("/").split("/")
    # /api/journeys/{id}/start -> journeys, id
    # /api/incidents/{id} -> incidents, id
    # /api/users/{id} -> users, id
    entity_type = ""
    entity_id = ""
    
    if "journeys" in parts:
        idx = parts.index("journeys")
        entity_type = "journey"
        if idx + 1 < len(parts) and parts[idx + 1] not in ("from-cosmo",):
            entity_id = parts[idx + 1]
    elif "incidents" in parts:
        idx = parts.index("incidents")
        entity_type = "incident"
        if idx + 1 < len(parts):
            entity_id = parts[idx + 1]
    elif "users" in parts:
        idx = parts.index("users")
        entity_type = "user"
        if idx + 1 < len(parts):
            entity_id = parts[idx + 1]
    elif "upload" in parts:
        entity_type = "layout"
    elif "reports" in parts:
        entity_type = "report"
    
    return entity_type, entity_id


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
        skip_paths = ["/api/health", "/uploads/", "/static/", "/favicon.ico"]
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
            
            # Always store request metric
            metric = {
                "id": str(uuid.uuid4()),
                "timestamp": now.isoformat(),
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "hour": now.hour,
                "date": now.strftime("%Y-%m-%d"),
            }
            await db.request_metrics.insert_one(metric)
            
            # Track errors (4xx and 5xx)
            if status_code >= 400:
                error_key = f"{method}:{path}:{status_code}"
                existing = await db.system_errors.find_one(
                    {"error_key": error_key, "reviewed": False}, {"_id": 0}
                )
                
                if existing:
                    await db.system_errors.update_one(
                        {"id": existing["id"]},
                        {
                            "$inc": {"occurrence_count": 1},
                            "$set": {
                                "last_seen": now.isoformat(),
                                "last_detail": error_detail or "",
                                "last_ip": client_ip,
                            }
                        }
                    )
                else:
                    error_type = "api_error"
                    if "/upload/" in path:
                        error_type = "parsing_error"
                    elif status_code == 422:
                        error_type = "validation_error"
                    
                    await db.system_errors.insert_one({
                        "id": str(uuid.uuid4()),
                        "error_key": error_key,
                        "error_type": error_type,
                        "method": method,
                        "endpoint": path,
                        "status_code": status_code,
                        "detail": error_detail or "",
                        "last_detail": error_detail or "",
                        "last_ip": client_ip,
                        "occurrence_count": 1,
                        "first_seen": now.isoformat(),
                        "last_seen": now.isoformat(),
                        "reviewed": False,
                        "reviewed_by": None,
                        "reviewed_at": None,
                    })
            
            # Audit logging for critical actions
            action = _match_action(method, path)
            if action and status_code < 400:
                entity_type, entity_id = _extract_entity(path)
                
                audit_entry = {
                    "id": str(uuid.uuid4()),
                    "timestamp": now.isoformat(),
                    "user_id": user_id,
                    "user_role": user_role,
                    "action": action,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "ip": client_ip,
                    "status": "success" if status_code < 400 else "error",
                    "status_code": status_code,
                    "details": "",
                    "date": now.strftime("%Y-%m-%d"),
                }
                await db.audit_logs.insert_one(audit_entry)
        
        except Exception as e:
            logger.error(f"Middleware logging error: {e}")


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
