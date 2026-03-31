"""
System observability routes for LastMile OS.
Health, Logs, Errors, Integrity, Performance, Config.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone, timedelta
from typing import Optional
import os
import time
import io
import csv
from pathlib import Path
import logging

from dependencies import db, get_current_user

logger = logging.getLogger(__name__)

SERVER_START_TIME = time.time()

router = APIRouter(prefix="/system", tags=["System"])


def _check_system_role(user):
    if user["role"] not in ("coordinator", "developer"):
        raise HTTPException(status_code=403, detail="Acceso denegado")


# ==================== HEALTH DASHBOARD ====================

@router.get("/health")
async def system_health(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    now = datetime.now(timezone.utc)

    api_status = "ok"

    mongo_status = "disconnected"
    mongo_latency_ms = 0
    try:
        start = time.time()
        await db.command("ping")
        mongo_latency_ms = round((time.time() - start) * 1000, 2)
        mongo_status = "connected"
    except Exception:
        pass

    yesterday = (now - timedelta(hours=24)).isoformat()
    errors_4xx = await db.request_metrics.count_documents({
        "status_code": {"$gte": 400, "$lt": 500},
        "timestamp": {"$gte": yesterday}
    })
    errors_5xx = await db.request_metrics.count_documents({
        "status_code": {"$gte": 500},
        "timestamp": {"$gte": yesterday}
    })

    recent_metrics = await db.request_metrics.find(
        {}, {"duration_ms": 1, "_id": 0}
    ).sort("timestamp", -1).limit(100).to_list(100)
    avg_latency = round(
        sum(m.get("duration_ms", 0) for m in recent_metrics) / max(len(recent_metrics), 1), 2
    )

    upload_dir = Path(__file__).parent.parent / "uploads"
    upload_size_mb = 0
    if upload_dir.exists():
        total = sum(f.stat().st_size for f in upload_dir.rglob("*") if f.is_file())
        upload_size_mb = round(total / (1024 * 1024), 2)

    error_events = await db.request_metrics.find(
        {"status_code": {"$gte": 400}},
        {"_id": 0, "timestamp": 1, "path": 1, "status_code": 1, "method": 1, "client_ip": 1}
    ).sort("timestamp", -1).limit(10).to_list(10)

    uptime_seconds = int(time.time() - SERVER_START_TIME)
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60

    return {
        "api_status": api_status,
        "mongo_status": mongo_status,
        "mongo_latency_ms": mongo_latency_ms,
        "avg_latency_ms": avg_latency,
        "errors_4xx_24h": errors_4xx,
        "errors_5xx_24h": errors_5xx,
        "upload_size_mb": upload_size_mb,
        "uptime": f"{hours}h {minutes}m",
        "uptime_seconds": uptime_seconds,
        "recent_errors": error_events,
        "timestamp": now.isoformat(),
    }

# ==================== PERFORMANCE METRICS ====================

@router.get("/performance")
async def system_performance(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    now = datetime.now(timezone.utc)
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    pipeline_hourly = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$group": {"_id": "$hour", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    hourly_raw = await db.request_metrics.aggregate(pipeline_hourly).to_list(24)
    requests_per_hour = {str(h["_id"]): h["count"] for h in hourly_raw}

    pipeline_slow = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}}},
        {"$group": {
            "_id": {"method": "$method", "path": "$path"},
            "avg_ms": {"$avg": "$duration_ms"},
            "max_ms": {"$max": "$duration_ms"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"avg_ms": -1}},
        {"$limit": 10}
    ]
    slowest = await db.request_metrics.aggregate(pipeline_slow).to_list(10)
    slowest_endpoints = [{
        "method": s["_id"]["method"],
        "path": s["_id"]["path"],
        "avg_ms": round(s["avg_ms"], 2),
        "max_ms": round(s["max_ms"], 2),
        "count": s["count"],
    } for s in slowest]

    pipeline_users = [
        {"$match": {"timestamp": {"$gte": seven_days_ago}, "user_id": {"$ne": ""}}},
        {"$group": {"_id": "$user_id", "actions": {"$sum": 1}}},
        {"$sort": {"actions": -1}},
        {"$limit": 10}
    ]
    active_users_raw = await db.audit_logs.aggregate(pipeline_users).to_list(10)
    user_ids = [u["_id"] for u in active_users_raw]
    users_map = {}
    if user_ids:
        ul = await db.users.find({"id": {"$in": user_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
        users_map = {u["id"]: u["name"] for u in ul}
    active_users = [{"user_id": u["_id"], "name": users_map.get(u["_id"], u["_id"]), "actions": u["actions"]} for u in active_users_raw]

    layout_uploads = await db.audit_logs.count_documents(
        {"action": "layout_uploaded", "timestamp": {"$gte": seven_days_ago}}
    )

    upload_dir = Path(__file__).parent.parent / "uploads"
    file_sizes = []
    if upload_dir.exists():
        for f in upload_dir.rglob("*"):
            if f.is_file() and f.suffix in (".csv", ".xlsx"):
                file_sizes.append(f.stat().st_size / 1024)
    avg_file_size_kb = round(sum(file_sizes) / max(len(file_sizes), 1), 2)

    return {
        "requests_per_hour": requests_per_hour,
        "slowest_endpoints": slowest_endpoints,
        "active_users": active_users,
        "avg_layout_file_size_kb": avg_file_size_kb,
        "total_layouts_7d": layout_uploads,
    }

# ==================== LOG VIEWER ====================

@router.get("/logs")
async def get_audit_logs(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    errors_only: bool = False,
    page: int = 1,
    page_size: int = 30,
    user: dict = Depends(get_current_user)
):
    _check_system_role(user)
    query = {}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to
    if user_id:
        query["user_id"] = user_id
    if action:
        query["action"] = action
    if errors_only:
        query["status"] = "error"

    total = await db.audit_logs.count_documents(query)
    skip = (page - 1) * page_size
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(page_size).to_list(page_size)

    uid_set = list(set(log.get("user_id", "") for log in logs if log.get("user_id")))
    users_map = {}
    if uid_set:
        ul = await db.users.find({"id": {"$in": uid_set}}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
        users_map = {u["id"]: u["name"] for u in ul}
    for log in logs:
        log["user_name"] = users_map.get(log.get("user_id", ""), log.get("user_id", ""))

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max((total + page_size - 1) // page_size, 1),
    }

@router.get("/logs/actions")
async def get_log_action_types(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    actions = await db.audit_logs.distinct("action")
    return {"actions": sorted(actions)}

@router.get("/logs/export")
async def export_audit_logs(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    _check_system_role(user)
    query = {}
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to
    if user_id:
        query["user_id"] = user_id
    if action:
        query["action"] = action

    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(10000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Usuario", "Rol", "Accion", "Entidad", "ID Entidad", "IP", "Status"])
    for log in logs:
        writer.writerow([log.get("timestamp",""), log.get("user_id",""), log.get("user_role",""),
                         log.get("action",""), log.get("entity_type",""), log.get("entity_id",""),
                         log.get("ip",""), log.get("status","")])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"}
    )

# ==================== ERROR TRACKER ====================

@router.get("/errors")
async def get_system_errors(
    error_type: Optional[str] = None,
    reviewed: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    _check_system_role(user)
    query = {}
    if error_type:
        query["error_type"] = error_type
    if reviewed is not None and reviewed != "":
        query["reviewed"] = reviewed.lower() == "true"
    errors = await db.system_errors.find(query, {"_id": 0}).sort("last_seen", -1).to_list(200)
    return {"errors": errors}

@router.get("/errors/count")
async def get_unreviewed_error_count(user: dict = Depends(get_current_user)):
    if user["role"] not in ("coordinator", "developer"):
        return {"count": 0}
    count = await db.system_errors.count_documents({"reviewed": False})
    return {"count": count}

@router.post("/errors/{error_id}/review")
async def review_error(error_id: str, user: dict = Depends(get_current_user)):
    _check_system_role(user)
    result = await db.system_errors.update_one(
        {"id": error_id},
        {"$set": {"reviewed": True, "reviewed_by": user["id"], "reviewed_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Error no encontrado")
    return {"message": "Error marcado como revisado"}

@router.post("/errors/review-all")
async def review_all_errors(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    result = await db.system_errors.update_many(
        {"reviewed": False},
        {"$set": {"reviewed": True, "reviewed_by": user["id"], "reviewed_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": f"{result.modified_count} errores marcados como revisados"}

# ==================== DATA INTEGRITY CHECKER ====================

@router.post("/integrity/run")
async def run_integrity_checks(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    import uuid as _uuid
    issues = []
    now = datetime.now(timezone.utc)

    bad_starts = await db.journeys.find(
        {"start_data": None, "status": {"$ne": "scheduled"}},
        {"_id": 0, "id": 1, "date": 1, "status": 1, "driver_name": 1}
    ).to_list(100)
    for j in bad_starts:
        issues.append({
            "type": "Ruta sin inicio", "severity": "Alta", "entity_type": "journey", "entity_id": j["id"],
            "description": f"Ruta del {j.get('date','')} ({j.get('driver_name','')}) status '{j['status']}' sin datos de inicio",
            "suggested_action": "Revisar y corregir status de la ruta",
        })

    bad_closes = await db.journeys.find(
        {"close_data": None, "status": "closed"},
        {"_id": 0, "id": 1, "date": 1, "driver_name": 1}
    ).to_list(100)
    for j in bad_closes:
        issues.append({
            "type": "Ruta cerrada sin cierre", "severity": "Alta", "entity_type": "journey", "entity_id": j["id"],
            "description": f"Ruta del {j.get('date','')} ({j.get('driver_name','')}) cerrada sin datos de cierre",
            "suggested_action": "Verificar integridad o reabrir ruta",
        })

    zero_delivered = await db.journeys.find(
        {"packages_delivered": 0, "status": {"$in": ["in_progress", "closed"]}},
        {"_id": 0, "id": 1, "date": 1}
    ).to_list(100)
    for j in zero_delivered:
        dc = await db.packages.count_documents({"journey_id": j["id"], "status": "delivered"})
        if dc > 0:
            issues.append({
                "type": "Conteo inconsistente", "severity": "Media", "entity_type": "journey", "entity_id": j["id"],
                "description": f"Ruta muestra 0 entregados pero tiene {dc} paquetes delivered",
                "suggested_action": "Recalcular contadores de paquetes",
            })

    closed_ids = [j["id"] for j in await db.journeys.find({"status": "closed"}, {"_id": 0, "id": 1}).to_list(500)]
    if closed_ids:
        open_incs = await db.incidents.find(
            {"journey_id": {"$in": closed_ids}, "status": "open"},
            {"_id": 0, "id": 1, "journey_id": 1, "incident_type": 1}
        ).to_list(100)
        for inc in open_incs:
            issues.append({
                "type": "Incidencia abierta en ruta cerrada", "severity": "Media",
                "entity_type": "incident", "entity_id": inc["id"],
                "description": f"Incidencia '{inc.get('incident_type','')}' abierta en ruta cerrada",
                "suggested_action": "Resolver o cerrar la incidencia",
            })

    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    all_users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(100)
    for u in all_users:
        recent = await db.audit_logs.find_one({"user_id": u["id"], "timestamp": {"$gte": thirty_days_ago}}, {"_id": 0})
        if not recent:
            issues.append({
                "type": "Usuario inactivo", "severity": "Baja", "entity_type": "user", "entity_id": u["id"],
                "description": f"'{u.get('name','')}' ({u.get('email','')}) sin actividad en 30+ dias",
                "suggested_action": "Verificar si el usuario sigue activo",
            })

    result = {
        "id": str(_uuid.uuid4()),
        "timestamp": now.isoformat(),
        "run_by": user["id"],
        "total_issues": len(issues),
        "issues_by_severity": {
            "Alta": len([i for i in issues if i["severity"] == "Alta"]),
            "Media": len([i for i in issues if i["severity"] == "Media"]),
            "Baja": len([i for i in issues if i["severity"] == "Baja"]),
        },
        "issues": issues,
    }
    await db.integrity_results.delete_many({})
    await db.integrity_results.insert_one({**result})
    result.pop("_id", None)
    return result

@router.get("/integrity/results")
async def get_integrity_results(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    result = await db.integrity_results.find_one({}, {"_id": 0})
    if not result:
        return {"message": "No se ha ejecutado ninguna validacion", "issues": [], "total_issues": 0}
    return result

@router.get("/integrity/export")
async def export_integrity_report(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    result = await db.integrity_results.find_one({}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="No hay resultados")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tipo", "Severidad", "Entidad", "ID", "Descripcion", "Accion sugerida"])
    for issue in result.get("issues", []):
        writer.writerow([issue.get("type",""), issue.get("severity",""), issue.get("entity_type",""),
                         issue.get("entity_id",""), issue.get("description",""), issue.get("suggested_action","")])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=integrity_report.csv"}
    )

# ==================== ENVIRONMENT CONFIG ====================

@router.get("/config")
async def get_system_config(user: dict = Depends(get_current_user)):
    _check_system_role(user)
    import fastapi
    mongo_url = os.environ.get("MONGO_URL", "")
    try:
        from urllib.parse import urlparse
        parsed = urlparse(mongo_url)
        mongo_host = f"{parsed.hostname}:{parsed.port}" if parsed.port else str(parsed.hostname)
    except Exception:
        mongo_host = "unknown"

    server_file = Path(__file__).parent.parent / "server.py"
    last_deploy = ""
    if server_file.exists():
        last_deploy = datetime.fromtimestamp(server_file.stat().st_mtime, tz=timezone.utc).isoformat()

    try:
        db_stats = await db.command("dbstats")
        db_size_mb = round(db_stats.get("dataSize", 0) / (1024 * 1024), 2)
        collections_count = db_stats.get("collections", 0)
    except Exception:
        db_size_mb = 0
        collections_count = 0

    uptime_seconds = int(time.time() - SERVER_START_TIME)
    return {
        "backend_version": f"FastAPI {fastapi.__version__}",
        "python_version": __import__("sys").version.split()[0],
        "mongo_host": mongo_host,
        "db_name": os.environ.get("DB_NAME", ""),
        "db_size_mb": db_size_mb,
        "collections_count": collections_count,
        "jwt_expiry_hours": 24,
        "cors_origins": os.environ.get("CORS_ORIGINS", "*"),
        "last_deploy": last_deploy,
        "uptime_seconds": uptime_seconds,
        "uptime": f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m",
    }

# ==================== SYNC SCHEDULE (Adaptive Scheduler) ====================

@router.get("/sync-schedule")
async def get_sync_schedule(user: dict = Depends(get_current_user)):
    """Show sync status of active journeys with adaptive scheduling info."""
    _check_system_role(user)
    from kosmo_sync import _get_sync_interval_minutes, _is_within_active_window, _get_cdmx_now

    active_journeys = await db.journeys.find(
        {"status": {"$in": ["scheduled", "in_progress"]}},
        {"_id": 0, "id": 1, "date": 1, "status": 1, "last_sync_at": 1, "next_sync_at": 1,
         "client_name": 1, "provider_name": 1, "driver_name": 1, "cosmo_route_id": 1},
    ).sort("date", -1).to_list(200)

    cdmx_now = _get_cdmx_now()
    schedule = []
    for j in active_journeys:
        interval = _get_sync_interval_minutes(j.get("date", ""))
        schedule.append({
            "journey_id": j["id"],
            "cosmo_route_id": j.get("cosmo_route_id"),
            "date": j.get("date"),
            "status": j.get("status"),
            "driver_name": j.get("driver_name"),
            "sync_interval_min": interval,
            "last_sync_at": j.get("last_sync_at"),
            "next_sync_at": j.get("next_sync_at"),
        })

    return {
        "active_window": _is_within_active_window(),
        "cdmx_time": cdmx_now.strftime("%Y-%m-%d %H:%M:%S"),
        "active_journeys_count": len(schedule),
        "schedule": schedule,
    }
