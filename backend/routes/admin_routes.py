"""
Admin routes: seed data, cleanup, upload history.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel

from dependencies import db, get_current_user, require_role, hash_password

router = APIRouter(tags=["Admin"])


# ==================== UPLOAD HISTORY ====================

@router.get("/upload-history")
async def get_upload_history(user: dict = Depends(get_current_user)):
    history = await db.upload_history.find({}, {"_id": 0}).sort("uploaded_at", -1).to_list(100)
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    for h in history:
        h["client_name"] = clients.get(h.get("client_id"), "")
        h["provider_name"] = providers.get(h.get("provider_id"), "")
    return history


@router.post("/upload-history")
async def create_upload_history(data: dict, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    history_entry = {
        "id": str(uuid.uuid4()),
        "date": data.get("date"),
        "client_id": data.get("client_id"),
        "provider_id": data.get("provider_id"),
        "package_count": data.get("package_count", 0),
        "journey_id": data.get("journey_id"),
        "journey_status": data.get("journey_status", "scheduled"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": user["id"],
    }
    await db.upload_history.insert_one(history_entry)
    return history_entry


# ==================== SEED DATA ====================

@router.post("/seed")
async def seed_database():
    existing_users = await db.users.count_documents({})
    if existing_users > 0:
        return {"message": "Base de datos ya tiene datos"}

    clients = [
        {"id": str(uuid.uuid4()), "name": "Cubbo", "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "Grupo Nadro", "created_at": datetime.now(timezone.utc).isoformat()},
    ]
    await db.clients.insert_many(clients)

    providers = [
        {
            "id": str(uuid.uuid4()),
            "name": "Chamedé Logistics",
            "contact_name": "Chamedé",
            "contact_phone": "+52 55 0000 0001",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Octavio Transport",
            "contact_name": "Octavio",
            "contact_phone": "+52 55 0000 0002",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    await db.providers.insert_many(providers)

    password_hash = hash_password("LastMile2026")
    users = [
        {"id": str(uuid.uuid4()), "email": "agente@me.mx", "name": "Agente ME", "role": "agent", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "yael@me.mx", "name": "Yael Coordinador", "role": "coordinator", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "karina@me.mx", "name": "Karina Ejecutivo", "role": "executive", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "dev@me.mx", "name": "Dev Admin", "role": "developer", "password": password_hash, "created_at": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "email": "proveedor@me.mx", "name": "Proveedor Chamedé", "role": "proveedor", "password": password_hash, "assigned_providers": [providers[0]["id"]], "created_at": datetime.now(timezone.utc).isoformat()},
    ]
    await db.users.insert_many(users)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    journey1_id = str(uuid.uuid4())
    journey1 = {
        "id": journey1_id, "date": today, "client_id": clients[0]["id"], "provider_id": providers[0]["id"],
        "status": "in_progress", "packages_total": 25, "packages_delivered": 15, "packages_failed": 2, "packages_retry": 3,
        "start_data": {
            "departure_time": f"{today}T08:30:00", "odometer_start": 45230, "fuel_level": "Lleno",
            "vehicle_condition": "Bueno", "packages_loaded": 25, "started_at": datetime.now(timezone.utc).isoformat(),
        },
        "close_data": None, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.journeys.insert_one(journey1)

    journey2_id = str(uuid.uuid4())
    journey2 = {
        "id": journey2_id, "date": yesterday, "client_id": clients[1]["id"], "provider_id": providers[1]["id"],
        "status": "closed", "packages_total": 30, "packages_delivered": 27, "packages_failed": 2, "packages_retry": 1,
        "start_data": {
            "departure_time": f"{yesterday}T09:00:00", "odometer_start": 44800, "fuel_level": "3/4",
            "vehicle_condition": "Bueno", "packages_loaded": 30, "started_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
        "close_data": {
            "closed_at": f"{yesterday}T18:30:00", "odometer_end": 44950,
            "packages_delivered": 27, "packages_failed": 2, "packages_to_retry": 1,
            "km_traveled": 150, "delivery_rate": 90.0,
        },
        "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    await db.journeys.insert_one(journey2)

    for i in range(25):
        pkg = {
            "id": str(uuid.uuid4()), "journey_id": journey1_id,
            "tracking_number": f"TRK{1000+i}", "recipient_name": f"Cliente {i+1}",
            "address": f"Calle {i+1} #100, Col. Centro",
            "zone": "Zona Norte" if i < 12 else "Zona Sur",
            "delivery_window": "09:00-12:00" if i < 12 else "12:00-15:00",
            "status": "delivered" if i < 15 else ("failed" if i < 17 else "pending"),
            "is_retry": i >= 22,
        }
        await db.packages.insert_one(pkg)

    for i in range(30):
        pkg = {
            "id": str(uuid.uuid4()), "journey_id": journey2_id,
            "tracking_number": f"TRK{2000+i}", "recipient_name": f"Cliente {i+1}",
            "address": f"Av Principal {i*10}, Col. Industrial",
            "zone": "Zona Industrial", "delivery_window": "10:00-14:00",
            "status": "delivered" if i < 27 else ("failed" if i < 29 else "retry"),
            "is_retry": False,
        }
        await db.packages.insert_one(pkg)

    incidents = [
        {
            "id": str(uuid.uuid4()), "journey_id": journey1_id, "occurred_at": f"{today}T10:30:00",
            "incident_type": "Destinatario ausente", "description": "Cliente no se encontraba en domicilio",
            "severity": "Bajo", "tracking_number": "TRK1015", "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()), "journey_id": journey1_id, "occurred_at": f"{today}T12:15:00",
            "incident_type": "Tiempo excesivo por entrega", "description": "Tráfico intenso en zona centro",
            "severity": "Medio", "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()), "journey_id": journey2_id, "occurred_at": f"{yesterday}T14:00:00",
            "incident_type": "Llanta ponchada", "description": "Se reventó llanta trasera derecha",
            "severity": "Alto", "action_taken": "Se cambió por llanta de refacción",
            "status": "resolved", "resolved_at": f"{yesterday}T15:30:00",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        },
    ]
    await db.incidents.insert_many(incidents)

    return {
        "message": "Base de datos inicializada exitosamente",
        "data": {"clients": len(clients), "providers": len(providers), "users": len(users), "journeys": 2, "packages": 55, "incidents": len(incidents)},
    }


async def _chunked_delete(collection, query: dict, chunk_size: int = 500) -> int:
    """Delete documents in chunks to avoid MongoDB timeouts on large datasets.
    Relies on the query matching 'id' (UUID). Works for any {'field': {'$in': [...]}}
    query by processing in ID batches when applicable."""
    # Optimization: for simple {} or small-match queries, single delete is faster.
    # For $in queries with many IDs, chunk them.
    if "$in" in str(query):
        # Extract the $in list and chunk
        key = next(iter(query))
        ids = query[key].get("$in", [])
        if len(ids) <= chunk_size:
            result = await collection.delete_many(query)
            return result.deleted_count or 0
        total = 0
        for i in range(0, len(ids), chunk_size):
            batch_q = {key: {"$in": ids[i:i + chunk_size]}}
            result = await collection.delete_many(batch_q)
            total += result.deleted_count or 0
        return total
    result = await collection.delete_many(query)
    return result.deleted_count or 0


# ==================== CLEANUP ====================

class CleanupRequest(BaseModel):
    date_from: Optional[str] = None  # YYYY-MM-DD (inclusive)
    date_to: Optional[str] = None    # YYYY-MM-DD (inclusive)
    dry_run: bool = False


def _build_journey_date_query(date_from: Optional[str], date_to: Optional[str]) -> dict:
    """Build a MongoDB query on the journey.date string field using YYYY-MM-DD bounds.
    journey.date may be in formats like '2026-03-24 16:47:36.697000' or '2026-03-24'.
    Comparing lexicographically on prefix works since the format is sortable."""
    if not date_from and not date_to:
        return {}
    cond = {}
    if date_from:
        cond["$gte"] = date_from
    if date_to:
        # Include whole day: add sentinel that's > any timestamp of that day
        cond["$lt"] = date_to + "\uffff"
    return {"date": cond}


@router.get("/cleanup/routes-packages/preview")
async def cleanup_preview(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Conteo de qué se eliminaría con los filtros dados. No borra nada."""
    jquery = _build_journey_date_query(date_from, date_to)
    journey_count = await db.journeys.count_documents(jquery)
    if journey_count == 0:
        return {
            "journeys": 0, "packages": 0, "incidents": 0,
            "ai_evaluation_jobs": 0, "route_edits": 0, "training_samples": 0,
            "date_from": date_from, "date_to": date_to,
        }
    journey_ids = [j["id"] async for j in db.journeys.find(jquery, {"_id": 0, "id": 1})]
    pkg_count = await db.packages.count_documents({"journey_id": {"$in": journey_ids}})
    inc_count = await db.incidents.count_documents({"journey_id": {"$in": journey_ids}})
    aij_count = await db.ai_evaluation_jobs.count_documents({"route_id": {"$in": journey_ids}})
    redit_count = await db.route_edits.count_documents({"journey_id": {"$in": journey_ids}})
    tsamp_count = await db.training_samples.count_documents({"journey_id": {"$in": journey_ids}})
    return {
        "journeys": journey_count,
        "packages": pkg_count,
        "incidents": inc_count,
        "ai_evaluation_jobs": aij_count,
        "route_edits": redit_count,
        "training_samples": tsamp_count,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.post("/cleanup/routes-packages")
async def cleanup_routes_packages(
    data: CleanupRequest = CleanupRequest(),
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Elimina rutas, paquetes, incidencias y jobs IA relacionados.
    Sin date_from/date_to borra TODO (comportamiento legacy). Con rango borra solo
    journeys cuya fecha de operación caiga en [date_from, date_to].

    Bug fix 2026-05-21: las incidencias eliminadas se copian a `incidents_archive`
    y se registra audit_log obligatorio con conteos y rango de fechas.
    """
    jquery = _build_journey_date_query(data.date_from, data.date_to)

    # Fetch target journey IDs
    journey_ids = [j["id"] async for j in db.journeys.find(jquery, {"_id": 0, "id": 1})]

    if data.dry_run:
        pkg_count = await db.packages.count_documents({"journey_id": {"$in": journey_ids}}) if journey_ids else 0
        inc_count = await db.incidents.count_documents({"journey_id": {"$in": journey_ids}}) if journey_ids else 0
        return {
            "message": "Dry run — sin cambios",
            "would_delete": {
                "journeys": len(journey_ids),
                "packages": pkg_count,
                "incidents": inc_count,
            },
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    archive_meta_base = {
        "deleted_at": now_iso,
        "deleted_by_id": user["id"],
        "deleted_by_email": user.get("email"),
        "deleted_by_name": user.get("name"),
        "deletion_source": "admin_cleanup_bulk",
        "date_from": data.date_from,
        "date_to": data.date_to,
    }

    # Legacy path: no filter → delete all
    if not data.date_from and not data.date_to:
        # Cancelar todos los jobs activos primero
        cancel_all = await db.ai_evaluation_jobs.update_many(
            {"status": {"$in": ["En_Cola", "Evaluando"]}},
            {"$set": {
                "status": "Error",
                "fecha_termino": now_iso,
                "error_detail": "Cancelado por limpieza total de rutas/pedidos.",
            }},
        )
        # Archive ALL incidents before nuking the collection
        all_inc = await db.incidents.find({}, {"_id": 0}).to_list(100000)
        if all_inc:
            archive_docs = [{**inc, "_archive_meta": archive_meta_base} for inc in all_inc]
            await db.incidents_archive.insert_many(archive_docs)
        j_del_count = await _chunked_delete(db.journeys, {})
        p_del_count = await _chunked_delete(db.packages, {})
        i_del_count = await _chunked_delete(db.incidents, {})
        aij_del_count = await _chunked_delete(db.ai_evaluation_jobs, {})
        redit_del_count = await _chunked_delete(db.route_edits, {})
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "action": "cleanup_all",
            "user_id": user["id"],
            "user_email": user.get("email"),
            "details": {
                "journeys_deleted": j_del_count,
                "packages_deleted": p_del_count,
                "incidents_deleted": i_del_count,
                "incidents_archived": len(all_inc),
                "ai_eval_jobs_cancelled": cancel_all.modified_count or 0,
            },
            "timestamp": now_iso,
        })
        return {
            "message": "Datos limpiados (todo)",
            "deleted": {
                "journeys": j_del_count,
                "packages": p_del_count,
                "incidents": i_del_count,
                "incidents_archived": len(all_inc),
                "ai_evaluation_jobs": aij_del_count,
                "route_edits": redit_del_count,
            },
            "cancelled_active_jobs": cancel_all.modified_count or 0,
        }

    if not journey_ids:
        return {
            "message": "No hay rutas en el rango seleccionado",
            "deleted": {"journeys": 0, "packages": 0, "incidents": 0, "ai_evaluation_jobs": 0, "route_edits": 0},
        }

    # Cancelar jobs activos de esas rutas ANTES de eliminar, para detener el worker
    # en el próximo batch y evitar gasto IA adicional.
    cancel_result = await db.ai_evaluation_jobs.update_many(
        {"route_id": {"$in": journey_ids}, "status": {"$in": ["En_Cola", "Evaluando"]}},
        {"$set": {
            "status": "Error",
            "fecha_termino": now_iso,
            "error_detail": "Cancelado por limpieza de rutas/pedidos.",
        }},
    )

    # Archive incidents from these journeys before deleting
    inc_to_archive = await db.incidents.find({"journey_id": {"$in": journey_ids}}, {"_id": 0}).to_list(50000)
    if inc_to_archive:
        archive_docs = [{**inc, "_archive_meta": {**archive_meta_base, "journey_ids_count": len(journey_ids)}} for inc in inc_to_archive]
        await db.incidents_archive.insert_many(archive_docs)

    j_del_count = await _chunked_delete(db.journeys, jquery)
    p_del_count = await _chunked_delete(db.packages, {"journey_id": {"$in": journey_ids}})
    i_del_count = await _chunked_delete(db.incidents, {"journey_id": {"$in": journey_ids}})
    aij_del_count = await _chunked_delete(db.ai_evaluation_jobs, {"route_id": {"$in": journey_ids}})
    redit_del_count = await _chunked_delete(db.route_edits, {"journey_id": {"$in": journey_ids}})

    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "cleanup_by_date",
        "user_id": user["id"],
        "user_email": user.get("email"),
        "details": {
            "date_from": data.date_from,
            "date_to": data.date_to,
            "journeys_deleted": j_del_count,
            "packages_deleted": p_del_count,
            "incidents_deleted": i_del_count,
            "incidents_archived": len(inc_to_archive),
            "ai_eval_jobs_cancelled": cancel_result.modified_count or 0,
        },
        "timestamp": now_iso,
    })

    return {
        "message": f"Datos limpiados del rango {data.date_from or '…'} → {data.date_to or '…'}",
        "date_from": data.date_from,
        "date_to": data.date_to,
        "deleted": {
            "journeys": j_del_count,
            "packages": p_del_count,
            "incidents": i_del_count,
            "incidents_archived": len(inc_to_archive),
            "ai_evaluation_jobs": aij_del_count,
            "route_edits": redit_del_count,
        },
        "cancelled_active_jobs": cancel_result.modified_count or 0,
    }



# ==================== INCIDENTS FORENSICS ====================
class ForensicsRequest(BaseModel):
    tracking_numbers: list[str] = []
    journey_id: Optional[str] = None
    routal_route_id: Optional[str] = None
    hours_back: int = 48  # buscar audit_logs de últimas N horas


@router.post("/incidents/forensics")
async def incidents_forensics(
    data: ForensicsRequest,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Endpoint forense para investigar incidencias eliminadas o desaparecidas.

    Recibe una lista de tracking_numbers (o un journey_id / routal_route_id) y
    devuelve, para cada tracking, un reporte con:
    - Estado actual del package (existe? journey_id, status, last update)
    - Estado actual de la journey
    - Incidencias activas para ese tracking
    - Incidencias archivadas (incidents_archive) con metadata de quién/cuándo borró
    - Audit logs relevantes (incident_deleted, journey_deleted, cleanup_*) en la ventana

    Diseñado para encontrar la causa raíz de incidencias "desaparecidas".
    """
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=data.hours_back)).isoformat()

    # Resolve journey_ids in scope (if route filter given)
    scope_journey_ids = None
    if data.journey_id:
        scope_journey_ids = [data.journey_id]
    elif data.routal_route_id:
        scope_journey_ids = [
            j["id"] async for j in db.journeys.find(
                {"routal_route_id": data.routal_route_id}, {"_id": 0, "id": 1}
            )
        ]

    report = {"tracking_reports": [], "scope_journey_ids": scope_journey_ids, "hours_back": data.hours_back}

    trackings = list(set(data.tracking_numbers or []))
    for tn in trackings:
        pkg = await db.packages.find_one({"tracking_number": tn}, {"_id": 0})
        active_incs = await db.incidents.find({"tracking_number": tn}, {"_id": 0}).to_list(20)
        archived_incs = await db.incidents_archive.find({"tracking_number": tn}, {"_id": 0}).to_list(50)

        journey_info = None
        if pkg and pkg.get("journey_id"):
            journey_info = await db.journeys.find_one(
                {"id": pkg["journey_id"]},
                {"_id": 0, "id": 1, "date": 1, "status": 1, "routal_route_id": 1, "routal_plan_id": 1, "driver_name": 1},
            )

        # Audit logs by tracking_number, by journey_id, or any global cleanup
        or_clauses = [{"tracking_number": tn}]
        if pkg and pkg.get("journey_id"):
            or_clauses.append({"journey_id": pkg["journey_id"]})
        or_clauses.append({"action": {"$in": ["cleanup_all", "cleanup_by_date"]}})
        audit_query = {
            "$and": [
                {"timestamp": {"$gte": cutoff_iso}},
                {"$or": or_clauses},
            ]
        }
        related_logs = await db.audit_logs.find(audit_query, {"_id": 0}).sort("timestamp", -1).to_list(30)

        report["tracking_reports"].append({
            "tracking_number": tn,
            "package_exists": pkg is not None,
            "package_status": pkg.get("status") if pkg else None,
            "package_journey_id": pkg.get("journey_id") if pkg else None,
            "journey": journey_info,
            "active_incidents": [
                {"id": i["id"], "type": i.get("incident_type"), "status": i.get("status"), "occurred_at": i.get("occurred_at")}
                for i in active_incs
            ],
            "archived_incidents": [
                {
                    "id": i["id"],
                    "type": i.get("incident_type"),
                    "originally_journey_id": i.get("journey_id"),
                    "deleted_at": (i.get("_archive_meta") or {}).get("deleted_at"),
                    "deleted_by_email": (i.get("_archive_meta") or {}).get("deleted_by_email"),
                    "deletion_source": (i.get("_archive_meta") or {}).get("deletion_source"),
                    "deletion_reason": (i.get("_archive_meta") or {}).get("deletion_reason"),
                }
                for i in archived_incs
            ],
            "audit_logs_recent": [
                {
                    "action": log.get("action"),
                    "user_email": log.get("user_email"),
                    "timestamp": log.get("timestamp"),
                    "details": log.get("details"),
                }
                for log in related_logs[:10]
            ],
        })

    # Global destructive events in the window (regardless of tracking)
    global_events = await db.audit_logs.find(
        {"timestamp": {"$gte": cutoff_iso}, "action": {"$in": ["cleanup_all", "cleanup_by_date", "journey_deleted", "incident_deleted"]}},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(100)
    report["recent_destructive_events"] = [
        {
            "action": e.get("action"),
            "user_email": e.get("user_email"),
            "timestamp": e.get("timestamp"),
            "tracking_number": e.get("tracking_number"),
            "journey_id": e.get("journey_id"),
            "details": e.get("details"),
        }
        for e in global_events
    ]

    return report
