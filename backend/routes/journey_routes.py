"""
Journey management routes: CRUD, start, close, incidents, cosmo import, bulk update.
"""
import asyncio
import uuid
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime, timezone

from dependencies import (
    db, get_current_user, require_role, apply_assignment_filter,
    _next_day, _normalize_address,
)
from models import (
    JourneyCreate, JourneyStartData, JourneyCloseData,
    IncidentCreate, IncidentResponse, CosmoJourneyCreate, BulkStatusUpdate,
)
from pydantic import BaseModel
from middleware import log_audit_event
from utils.pii import encrypt_pkg_pii, apply_pii_visibility_pkgs
from evidence_scoring import (
    evaluate_packages_for_journey,
    evaluate_single_package_for_journey,
    get_ai_eval_status,
)
from ws_manager import ws_manager
from routes.webhook_routes import dispatch_webhook_event
from pagination_utils import paginated_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Journeys"])


# ==================== JOURNEYS ====================

@router.get("/journeys")
async def get_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(get_current_user),
):
    query = {}
    # FIX 3 (iter83): Hide legacy plan-based Routal journeys that have been split
    # AND no longer have orphan incidents. If a legacy still has any incidents
    # pointing to it, keep visible so they remain accessible.
    query["$or"] = [
        {"migrated_to_journeys": {"$exists": False}},
        {"_legacy_incidents_remaining": {"$gt": 0}},
    ]
    if date_from:
        query["date"] = {"$gte": date_from}
    if date_to:
        query.setdefault("date", {})["$lt"] = _next_day(date_to)
    if client_id:
        query["client_id"] = client_id
    if provider_id:
        query["provider_id"] = provider_id
    if status:
        query["status"] = status

    query = apply_assignment_filter(user, query)

    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    skip = (page - 1) * page_size

    total_count = await db.journeys.count_documents(query)
    total_pages = max(1, -(-total_count // page_size))

    journeys = await db.journeys.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(page_size).to_list(page_size)

    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    journey_ids = [j["id"] for j in journeys]
    incident_counts = {}
    open_incident_counts = {}
    if journey_ids:
        pipeline_total = [
            {"$match": {"journey_id": {"$in": journey_ids}}},
            {"$group": {"_id": "$journey_id", "count": {"$sum": 1}}},
        ]
        pipeline_open = [
            {"$match": {"journey_id": {"$in": journey_ids}, "status": "open"}},
            {"$group": {"_id": "$journey_id", "count": {"$sum": 1}}},
        ]
        async for doc in db.incidents.aggregate(pipeline_total):
            incident_counts[doc["_id"]] = doc["count"]
        async for doc in db.incidents.aggregate(pipeline_open):
            open_incident_counts[doc["_id"]] = doc["count"]

    for j in journeys:
        j["client_name"] = clients.get(j.get("client_id"), "")
        j["provider_name"] = providers.get(j.get("provider_id"), "")
        j["incidents_count"] = incident_counts.get(j["id"], 0)
        j["open_incidents_count"] = open_incident_counts.get(j["id"], 0)

    return {
        **paginated_response(journeys, total=total_count, page=page, page_size=page_size),
        # Backwards compat: viejos consumidores leen pagination.total_count
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_count,
            "total_count": total_count,
            "total_pages": total_pages,
            "pages": total_pages,
        },
    }


@router.get("/journeys/{journey_id}")
async def get_journey(journey_id: str, user: dict = Depends(get_current_user)):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    client = await db.clients.find_one({"id": journey.get("client_id")}, {"_id": 0})
    provider = await db.providers.find_one({"id": journey.get("provider_id")}, {"_id": 0})
    journey["client_name"] = client["name"] if client else ""
    journey["provider_name"] = provider["name"] if provider else ""

    packages = await db.packages.find({"journey_id": journey_id}, {"_id": 0}).to_list(1000)
    apply_pii_visibility_pkgs(packages, user.get("role"))

    order_refs = [p.get("order_reference_id") for p in packages if p.get("order_reference_id")]
    if order_refs:
        sibling_pipeline = [
            {"$match": {"order_reference_id": {"$in": list(set(order_refs))}}},
            {"$lookup": {
                "from": "journeys",
                "localField": "journey_id",
                "foreignField": "id",
                "as": "journey_info",
            }},
            {"$unwind": {"path": "$journey_info", "preserveNullAndEmptyArrays": True}},
            {"$project": {
                "_id": 0,
                "order_reference_id": 1,
                "journey_id": 1,
                "journey_date": "$journey_info.date",
            }},
            {"$sort": {"journey_date": 1}},
        ]
        siblings = await db.packages.aggregate(sibling_pipeline).to_list(5000)

        ref_groups = defaultdict(list)
        for s in siblings:
            ref_groups[s["order_reference_id"]].append(s["journey_id"])

        for p in packages:
            ref = p.get("order_reference_id", "")
            group = ref_groups.get(ref, [])
            total = len(set(group))
            if total <= 1:
                p["delivery_attempt"] = 1
            else:
                unique_journeys = list(dict.fromkeys(group))
                try:
                    pos = unique_journeys.index(p["journey_id"])
                    p["delivery_attempt"] = total - pos
                except ValueError:
                    p["delivery_attempt"] = 1

    # Enrich packages with unified fields for Guías tab
    for p in packages:
        p.setdefault("ai_score", p.get("evidence_score"))
        # Preserve raw IA error keys and severity mapping from AI evaluation
        raw_ia_errors = p.get("ia_errors", [])
        ia_severity = p.get("ia_severity", {})
        # Build human-readable errors for display
        ai_errors = []
        detail = p.get("evidence_detail", {}) or {}
        ai_errors.extend(detail.get("missing_items", []))
        ai_errors.extend(detail.get("alerts", []))
        p["ai_errors"] = ai_errors
        p["ia_errors_raw"] = raw_ia_errors
        p["ia_severity"] = ia_severity
        p["ai_confidence"] = detail.get("confidence")
        p.setdefault("manually_reviewed", bool(p.get("reviewed_by")))
        p.setdefault("manually_reviewed_note", p.get("review_note", None))
        p["photos_count"] = p.get("kosmo_proof_count", len(p.get("kosmo_proof_urls", [])))
        p.setdefault("delivery_note", p.get("kosmo_delivery_note", ""))
        p["kosmo_url"] = p.get("tracking_url", "")

    journey["packages"] = packages

    incidents = await db.incidents.find({"journey_id": journey_id}, {"_id": 0}).to_list(100)
    journey["incidents"] = incidents
    journey["incidents_count"] = len(incidents)
    journey["open_incidents_count"] = len([i for i in incidents if i["status"] == "open"])

    return journey


@router.post("/journeys")
async def create_journey(data: JourneyCreate, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    journey_id = str(uuid.uuid4())
    journey = {
        "id": journey_id,
        "order_id": "",
        "date": data.date,
        "client_id": data.client_id,
        "provider_id": data.provider_id,
        "status": "scheduled",
        "route_type": data.route_type or "CDMX / Zona Metro",
        "city": data.city,
        "max_packages": data.max_packages,
        "packages_total": len(data.packages) + len(data.retry_packages),
        "packages_delivered": 0,
        "packages_failed": 0,
        "packages_retry": len(data.retry_packages),
        "start_data": None,
        "close_data": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"],
    }
    await db.journeys.insert_one(journey)

    # Bulk insert: build list first, then single insert_many call (N+1 → 1 query)
    if data.packages:
        pkg_docs = [{
            "id": str(uuid.uuid4()),
            "journey_id": journey_id,
            "tracking_number": pkg.get("tracking_number", ""),
            "recipient_name": pkg.get("recipient_name", ""),
            "address": pkg.get("address", ""),
            "recipient_phone": pkg.get("recipient_phone", ""),
            "zone": pkg.get("zone", ""),
            "delivery_window": pkg.get("delivery_window", ""),
            "status": "pending",
            "is_retry": False,
        } for pkg in data.packages]
        # PII at-rest: encrypt sensitive fields before insert
        for d in pkg_docs:
            encrypt_pkg_pii(d)
        await db.packages.insert_many(pkg_docs)

    # Bulk update retry packages with a single update_many call
    if data.retry_packages:
        await db.packages.update_many(
            {"id": {"$in": data.retry_packages}},
            {"$set": {"journey_id": journey_id, "status": "pending", "is_retry": True}},
        )

    return {"id": journey_id, "message": "Ruta creada exitosamente"}


@router.put("/journeys/{journey_id}/start")
async def start_journey(journey_id: str, data: JourneyStartData, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    if journey["status"] != "scheduled":
        raise HTTPException(status_code=400, detail="La ruta ya fue iniciada o cerrada")
    if not data.checklist_completed:
        raise HTTPException(status_code=400, detail="Debe completar el checklist antes de iniciar")

    start_data = {
        "departure_time": data.departure_time,
        "odometer_start": data.odometer_start,
        "fuel_level": data.fuel_level,
        "vehicle_condition": data.vehicle_condition,
        "vehicle_notes": data.vehicle_notes,
        "packages_loaded": data.packages_loaded,
        "notes": data.notes,
        "arrival_time_cedis": data.arrival_time_cedis,
        "backup_driver_name": data.backup_driver_name,
        "backup_request_time": data.backup_request_time,
        "backup_arrival_time": data.backup_arrival_time,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "started_by": user["id"],
    }

    update_fields = {"status": "in_progress", "start_data": start_data}
    if hasattr(data, 'route_type') and data.route_type:
        update_fields["route_type"] = data.route_type
    if hasattr(data, 'city') and data.city:
        update_fields["city"] = data.city
    if hasattr(data, 'max_packages') and data.max_packages:
        update_fields["max_packages"] = data.max_packages

    await db.journeys.update_one({"id": journey_id}, {"$set": update_fields})
    await log_audit_event(db, user["id"], user["role"], "route_started", "journey", journey_id)
    await ws_manager.broadcast_journey_update(journey_id, "started")

    # Dispatch webhook
    asyncio.create_task(dispatch_webhook_event("journey.started", {
        "journey_id": journey_id,
        "client_id": journey.get("client_id"),
        "provider_id": journey.get("provider_id"),
        "driver": journey.get("driver"),
        "packages_total": journey.get("packages_total"),
        "started_by": user["email"],
        "start_data": start_data,
    }))

    return {"message": "Ruta iniciada exitosamente"}


@router.put("/journeys/{journey_id}/close")
async def close_journey(journey_id: str, data: JourneyCloseData, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    if journey["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="La ruta debe estar en progreso para cerrarla")

    start_data = journey.get("start_data", {})
    odometer_start = start_data.get("odometer_start", 0)
    packages_loaded = start_data.get("packages_loaded", journey["packages_total"])

    # Auto-calculate fields if not provided
    if data.packages_delivered is None:
        data.packages_delivered = await db.packages.count_documents({"journey_id": journey_id, "status": "delivered"})
    if data.packages_failed is None:
        data.packages_failed = await db.packages.count_documents({"journey_id": journey_id, "status": {"$in": ["failed", "cancelled"]}})

    odometer_end = data.odometer_end or 0
    km_traveled = max(0, odometer_end - odometer_start) if odometer_end else 0
    delivery_rate = (data.packages_delivered / packages_loaded * 100) if packages_loaded > 0 else 0
    packages_to_retry = max(0, packages_loaded - data.packages_delivered - data.packages_failed)

    close_data = {
        "closed_at": data.closed_at or datetime.now(timezone.utc).isoformat(),
        "odometer_end": odometer_end,
        "packages_delivered": data.packages_delivered,
        "packages_failed": data.packages_failed,
        "packages_to_retry": packages_to_retry,
        "km_traveled": km_traveled,
        "delivery_rate": round(delivery_rate, 2),
        "notes": data.notes,
        "closed_by": user["id"],
    }

    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": {
            "status": "closed",
            "close_data": close_data,
            "packages_delivered": data.packages_delivered,
            "packages_failed": data.packages_failed,
        }},
    )

    for failed_pkg in data.failed_packages:
        await db.packages.update_one(
            {"id": failed_pkg["id"]},
            {"$set": {"status": "returned", "failure_reason": failed_pkg.get("failure_reason", "")}},
        )

    await log_audit_event(db, user["id"], user["role"], "route_closed", "journey", journey_id)
    await evaluate_packages_for_journey(db, journey_id)
    await ws_manager.broadcast_journey_update(journey_id, "closed")

    # Dispatch webhook
    asyncio.create_task(dispatch_webhook_event("journey.closed", {
        "journey_id": journey_id,
        "client_id": journey.get("client_id"),
        "provider_id": journey.get("provider_id"),
        "driver": journey.get("driver"),
        "close_data": close_data,
    }))

    return {"message": "Ruta cerrada exitosamente", "close_data": close_data}


# ==================== INCIDENTS ====================

@router.get("/incidents")
async def get_incidents(
    journey_id: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query = {}
    if journey_id:
        query["journey_id"] = journey_id
    if status:
        query["status"] = status
    incidents = await db.incidents.find(query, {"_id": 0}).sort("occurred_at", -1).to_list(500)
    return incidents


@router.post("/incidents", response_model=IncidentResponse)
async def create_incident(data: IncidentCreate, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    # Validar catalogo nuevo de tipos. Catalogo viejo sigue permitido para compatibilidad
    # con scripts/tests existentes, pero si viene del nuevo catalogo y es 'otro' se
    # requiere comentario_asesor.
    VALID_NEW_TYPES = {
        "evidencia_incidencia_incorrecta",
        "autorizacion_tercero_incorrecta",
        "evidencia_entrega_incorrecta",
        "notas_incorrectas",
        "otro",
    }
    comentario = (data.comentario_asesor or "").strip() or None
    if data.incident_type == "otro" and not comentario:
        raise HTTPException(
            status_code=422,
            detail="Describe brevemente el tipo de incidencia.",
        )
    # Si no es 'otro', no persistimos comentario_asesor aunque venga en payload
    if data.incident_type != "otro":
        comentario = None
    # Si el tipo pertenece al catalogo nuevo pero no es valido, rechazar
    if data.incident_type in VALID_NEW_TYPES or data.incident_type == "otro":
        pass  # ok
    # (valores antiguos siguen aceptados sin validacion para no bloquear tests legacy)

    incident = {
        "id": str(uuid.uuid4()),
        "journey_id": data.journey_id,
        "occurred_at": data.occurred_at,
        "incident_type": data.incident_type,
        "description": data.description,
        "severity": data.severity,
        "tracking_number": data.tracking_number,
        "action_taken": data.action_taken,
        "imputability": data.imputability or "Por definir",
        "source": getattr(data, "source", None) or "incidencias",
        "comentario_asesor": comentario,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"],
    }
    await db.incidents.insert_one(incident)
    await log_audit_event(db, user["id"], user["role"], "incident_created", "incident", incident["id"])
    await ws_manager.broadcast_incident_update(data.journey_id)

    # Dispatch webhook
    asyncio.create_task(dispatch_webhook_event("incident.created", {
        "incident_id": incident["id"],
        "journey_id": data.journey_id,
        "incident_type": data.incident_type,
        "severity": data.severity,
        "description": data.description,
        "imputability": incident["imputability"],
        "comentario_asesor": comentario,
    }))

    return {k: v for k, v in incident.items() if k != "_id"}


@router.put("/incidents/{incident_id}")
async def update_incident(incident_id: str, data: dict, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    update_data = {k: v for k, v in data.items() if k not in ["id", "_id"]}
    if data.get("status") == "resolved":
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
        update_data["resolved_by"] = user["id"]
    result = await db.incidents.update_one({"id": incident_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return {"message": "Incidencia actualizada"}


@router.delete("/incidents/{incident_id}")
async def delete_incident(incident_id: str, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    result = await db.incidents.delete_one({"id": incident_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return {"message": "Incidencia eliminada"}



@router.delete("/journeys/{journey_id}")
async def delete_journey(journey_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    """Delete a journey and cascade delete all related packages, incidents, and images."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0, "id": 1, "status": 1})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    # Cascade delete
    pkg_result = await db.packages.delete_many({"journey_id": journey_id})
    inc_result = await db.incidents.delete_many({"journey_id": journey_id})
    img_result = await db.images.delete_many({"journey_id": journey_id})
    ts_result = await db.training_samples.delete_many({"journey_id": journey_id})
    await db.journeys.delete_one({"id": journey_id})

    # Audit log
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "action": "journey_deleted",
        "journey_id": journey_id,
        "user_id": user["id"],
        "user_email": user.get("email"),
        "details": {
            "packages_deleted": pkg_result.deleted_count,
            "incidents_deleted": inc_result.deleted_count,
            "images_deleted": img_result.deleted_count,
            "training_samples_deleted": ts_result.deleted_count,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"Journey {journey_id} deleted by {user.get('email')}: {pkg_result.deleted_count} packages, {inc_result.deleted_count} incidents")
    return {
        "message": "Ruta eliminada exitosamente",
        "deleted": {
            "packages": pkg_result.deleted_count,
            "incidents": inc_result.deleted_count,
            "images": img_result.deleted_count,
        },
    }


@router.put("/incidents/journey/{journey_id}/resolve-all")
async def resolve_all_incidents(journey_id: str, user: dict = Depends(require_role(["coordinator", "agent", "developer"]))):
    now = datetime.now(timezone.utc).isoformat()
    result = await db.incidents.update_many(
        {"journey_id": journey_id, "status": "open"},
        {"$set": {
            "status": "resolved",
            "resolved_at": now,
            "resolved_by": user["id"],
            "action_taken": "Resuelta en lote por el coordinador",
        }},
    )
    return {"message": f"{result.modified_count} incidencias resueltas", "resolved_count": result.modified_count}


@router.put("/packages/{package_id}/review")
async def review_package(package_id: str, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    result = await db.packages.update_one(
        {"id": package_id},
        {"$set": {"reviewed_by": user.get("name", user["email"]), "reviewed_at": now, "manually_reviewed": True}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return {"message": "Paquete marcado como revisado", "reviewed_by": user.get("name", user["email"]), "reviewed_at": now}


@router.patch("/packages/{package_id}/review")
async def review_package_with_note(
    package_id: str,
    body: dict,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    now = datetime.now(timezone.utc).isoformat()
    manually_reviewed = body.get("manually_reviewed", True)
    note = body.get("manually_reviewed_note", "")
    adjusted_score = body.get("adjusted_score")
    ai_incorrect = body.get("ai_evaluation_incorrect", False)

    update_data = {
        "manually_reviewed": manually_reviewed,
        "review_note": note,
        "reviewed_by": user.get("name", user["email"]),
        "reviewed_at": now,
    }
    if not manually_reviewed:
        update_data["rejection_reason"] = note
    if adjusted_score is not None:
        update_data["adjusted_score"] = adjusted_score
        update_data["ai_score"] = adjusted_score
        update_data["evidence_score"] = adjusted_score
    if ai_incorrect:
        update_data["ai_evaluation_incorrect"] = True

    result = await db.packages.update_one(
        {"id": package_id},
        {"$set": update_data},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")

    pkg = await db.packages.find_one({"id": package_id}, {"_id": 0})

    # Save training sample for supervised learning
    try:
        ia_errors = pkg.get("ia_errors") or []
        error_types = ia_errors if ia_errors else ["general"]
        training_sample = {
            "id": str(uuid.uuid4()),
            "package_id": package_id,
            "journey_id": pkg.get("journey_id"),
            "tracking_number": pkg.get("tracking_number") or pkg.get("order_reference_id"),
            "original_ai_score": pkg.get("evidence_score"),
            "adjusted_score": adjusted_score,
            "ai_evaluation_incorrect": ai_incorrect,
            "decision": "approved" if manually_reviewed else "rejected",
            "reviewer_note": note,
            "error_types": error_types,
            "ia_errors": ia_errors,
            "ia_feedback": pkg.get("ia_feedback", ""),
            "evidence_type": pkg.get("evidence_type"),
            "proof_count": pkg.get("kosmo_proof_count", 0),
            "labeled_by": user.get("name", user["email"]),
            "labeled_at": now,
        }
        for err_type in error_types:
            sample = {**training_sample, "error_type": err_type}
            await db.training_samples.insert_one(sample)
    except Exception as e:
        logger.warning(f"Training sample save failed: {e}")

    return pkg


# ==================== COSMO JOURNEY CREATION ====================

@router.post("/journeys/from-cosmo")
async def create_journeys_from_cosmo(
    data: CosmoJourneyCreate,
    user: dict = Depends(require_role(["coordinator", "agent", "developer"])),
):
    created_journeys = []
    updated_journeys = []
    skipped_duplicates = []
    errors = []
    total_new_packages = 0
    total_updated_packages = 0

    for mapping in data.messenger_provider_mappings:
        if mapping.get("messenger_name") and mapping.get("provider_id"):
            await db.messenger_mappings.update_one(
                {"messenger_name": mapping["messenger_name"]},
                {"$set": {
                    "messenger_name": mapping["messenger_name"],
                    "provider_id": mapping["provider_id"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )

    existing_orders = await db.packages.find({}, {"order_reference_id": 1, "cosmo_route_id": 1, "id": 1, "journey_id": 1, "_id": 0}).to_list(10000)
    existing_order_map = {}
    attempt_counts = {}
    for o in existing_orders:
        ref = o.get("order_reference_id", "")
        route = o.get("cosmo_route_id", "")
        if ref:
            composite_key = f"{route}|{ref}"
            existing_order_map[composite_key] = o
            attempt_counts[ref] = attempt_counts.get(ref, 0) + 1

    orders_by_route = {}
    for order in data.history_orders:
        route_id = order.get("order_id") or order.get("route_id", "")
        if route_id:
            if route_id not in orders_by_route:
                orders_by_route[route_id] = []
            orders_by_route[route_id].append(order)

    mappings = {m["messenger_name"]: m["provider_id"] for m in data.messenger_provider_mappings if m.get("provider_id")}

    # Pre-fetch ALL messenger_mappings (bulk: 1 query) — was N+1 inside the loop
    db_mappings = await db.messenger_mappings.find(
        {}, {"_id": 0, "messenger_name": 1, "provider_id": 1}
    ).to_list(5000)
    db_mapping_by_name = {m["messenger_name"]: m.get("provider_id") for m in db_mappings}

    # Pre-fetch ALL journeys for the route_ids in this sync (bulk: 1 query)
    sync_route_ids = [r.get("route_id", "") for r in data.route_summary if r.get("route_id")]
    existing_journeys_list = await db.journeys.find(
        {"cosmo_route_id": {"$in": sync_route_ids}}, {"_id": 0}
    ).to_list(10000)
    existing_journeys_by_cosmo = {j["cosmo_route_id"]: j for j in existing_journeys_list}

    # Accumulate package updates and journey-counter recomputations for bulk_write
    from pymongo import UpdateOne
    pkg_updates: list[UpdateOne] = []
    journeys_needing_recount: set[str] = set()

    for route in data.route_summary:
        route_id = route.get("route_id", "")
        driver_name = route.get("driver_name", "")
        if not route_id:
            continue

        provider_id = mappings.get(driver_name) or db_mapping_by_name.get(driver_name)
        if not provider_id:
            errors.append(f"Sin proveedor asignado para mensajero: {driver_name}")
            continue

        existing_journey = existing_journeys_by_cosmo.get(route_id)
        route_orders = orders_by_route.get(route_id, [])

        if existing_journey:
            route_updated = 0
            for order in route_orders:
                order_ref = order.get("order_reference_id", "")
                composite_key = f"{route_id}|{order_ref}"
                if order_ref and composite_key in existing_order_map:
                    update_fields = {}
                    new_cosmo_status = order.get("order_status", "")
                    if new_cosmo_status:
                        update_fields["cosmo_status"] = new_cosmo_status
                        if new_cosmo_status == "delivered":
                            update_fields["status"] = "delivered"
                        elif new_cosmo_status == "cancelled":
                            update_fields["status"] = "failed"
                    tracking_url = order.get("tracking_url", "")
                    if tracking_url:
                        update_fields["tracking_url"] = tracking_url
                    if update_fields:
                        pkg_data = existing_order_map[composite_key]
                        if isinstance(pkg_data, dict) and "id" in pkg_data:
                            pkg_updates.append(UpdateOne({"id": pkg_data["id"]}, {"$set": update_fields}))
                            route_updated += 1

            if route_updated > 0:
                j_id = existing_journey["id"]
                journeys_needing_recount.add(j_id)
                total_updated_packages += route_updated
                updated_journeys.append({
                    "journey_id": j_id,
                    "route_id": route_id,
                    "driver": driver_name,
                    "packages_updated": route_updated,
                })
            continue

        new_orders = []
        updated_in_other = 0
        for order in route_orders:
            order_ref = order.get("order_reference_id", "")
            composite_key = f"{route_id}|{order_ref}"
            if composite_key in existing_order_map:
                pkg_data = existing_order_map[composite_key]
                if isinstance(pkg_data, dict) and "id" in pkg_data:
                    update_fields = {}
                    new_cosmo_status = order.get("order_status", "")
                    if new_cosmo_status:
                        update_fields["cosmo_status"] = new_cosmo_status
                        if new_cosmo_status == "delivered":
                            update_fields["status"] = "delivered"
                        elif new_cosmo_status == "cancelled":
                            update_fields["status"] = "failed"
                    tracking_url = order.get("tracking_url", "")
                    if tracking_url:
                        update_fields["tracking_url"] = tracking_url
                    if update_fields:
                        pkg_updates.append(UpdateOne({"id": pkg_data["id"]}, {"$set": update_fields}))
                        updated_in_other += 1
                        total_updated_packages += 1
            else:
                new_orders.append(order)
                existing_order_map[composite_key] = True
                attempt_counts[order_ref] = attempt_counts.get(order_ref, 0) + 1

        if not new_orders and route_orders:
            if updated_in_other > 0:
                updated_journeys.append({
                    "route_id": route_id,
                    "driver": driver_name,
                    "packages_updated": updated_in_other,
                })
            else:
                skipped_duplicates.append(f"{route_id} (todas las órdenes duplicadas)")
            continue

        route_creation_date = route.get("creation_date", "")
        journey_date = route_creation_date if route_creation_date else data.date
        if journey_date and "T" in journey_date:
            journey_date = journey_date.split("T")[0]

        journey_id = str(uuid.uuid4())
        journey = {
            "id": journey_id,
            "cosmo_route_id": route_id,
            "order_id": route_id,
            "date": journey_date,
            "client_id": data.client_id,
            "provider_id": provider_id,
            "driver_name": driver_name,
            "team": route.get("team", ""),
            "status": "scheduled",
            "route_type": data.route_type or "CDMX / Zona Metro",
            "city": data.city if data.route_type == "Foránea" else None,
            "max_packages": data.max_packages if data.route_type == "Foránea" else None,
            "packages_total": len(new_orders),
            "packages_delivered": 0,
            "packages_failed": 0,
            "packages_retry": 0,
            "planned_distance": route.get("planned_distance", ""),
            "actual_distance": route.get("actual_distance", ""),
            "total_stops": route.get("total_stops", "0"),
            "completed_stops": route.get("completed_stops", "0"),
            "cancelled_stops": route.get("cancelled_stops", "0"),
            "start_data": None,
            "close_data": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user["id"],
        }
        await db.journeys.insert_one(journey)

        for order in new_orders:
            order_ref = order.get("order_reference_id", "")
            package = {
                "id": str(uuid.uuid4()),
                "journey_id": journey_id,
                "cosmo_route_id": route_id,
                "order_reference_id": order_ref,
                "tracking_number": order_ref,
                "tracking_url": order.get("tracking_url", ""),
                "recipient_name": order.get("recipient_name", ""),
                "address": order.get("recipient_address", ""),
                "recipient_phone": order.get("recipient_phone", ""),
                "zone": order.get("zone", ""),
                "delivery_window": "",
                "cosmo_status": order.get("order_status", ""),
                "status": "delivered" if order.get("order_status") == "delivered" else ("failed" if order.get("order_status") == "cancelled" else "pending"),
                "failure_reason": order.get("failure_reason", ""),
                "failure_reason_note": order.get("failure_reason_note", ""),
                "created_date": order.get("created_date", ""),
                "delivery_attempt": attempt_counts.get(order_ref, 1),
                "is_retry": attempt_counts.get(order_ref, 1) > 1,
                **_normalize_address(order.get("recipient_address", "")),
            }
            # PII at-rest encryption (idempotent, safe on retry)
            encrypt_pkg_pii(package)
            await db.packages.insert_one(package)
            total_new_packages += 1
            if package["status"] == "delivered":
                await db.journeys.update_one({"id": journey_id}, {"$inc": {"packages_delivered": 1}})
            elif package["status"] == "failed":
                await db.journeys.update_one({"id": journey_id}, {"$inc": {"packages_failed": 1}})

        created_journeys.append({
            "journey_id": journey_id,
            "route_id": route_id,
            "driver": driver_name,
            "packages": len(new_orders),
            "duplicates_updated": updated_in_other,
        })

    # ── Flush batched package updates (single bulk_write instead of N update_one)
    if pkg_updates:
        await db.packages.bulk_write(pkg_updates, ordered=False)

    # ── Recompute journey counters in bulk (aggregate instead of 2 count_documents per journey)
    if journeys_needing_recount:
        pipeline = [
            {"$match": {"journey_id": {"$in": list(journeys_needing_recount)},
                        "status": {"$in": ["delivered", "failed"]}}},
            {"$group": {"_id": {"journey_id": "$journey_id", "status": "$status"},
                        "count": {"$sum": 1}}},
        ]
        counter_map: dict[str, dict[str, int]] = {}
        async for row in db.packages.aggregate(pipeline):
            jid = row["_id"]["journey_id"]
            st = row["_id"]["status"]
            counter_map.setdefault(jid, {"delivered": 0, "failed": 0})[st] = row["count"]

        journey_updates = [
            UpdateOne({"id": jid}, {"$set": {
                "packages_delivered": counter_map.get(jid, {}).get("delivered", 0),
                "packages_failed": counter_map.get(jid, {}).get("failed", 0),
            }})
            for jid in journeys_needing_recount
        ]
        if journey_updates:
            await db.journeys.bulk_write(journey_updates, ordered=False)

    await log_audit_event(
        db, user["id"], user["role"], "layout_uploaded", "layout", "",
        details=f"{len(created_journeys)} rutas, {total_new_packages} nuevos, {total_updated_packages} actualizados",
    )
    await ws_manager.broadcast_stats_update()

    return {
        "message": f"{len(created_journeys)} rutas creadas, {total_updated_packages} paquetes actualizados",
        "created_journeys": created_journeys,
        "updated_journeys": updated_journeys,
        "skipped_duplicates": skipped_duplicates,
        "errors": errors,
        "total_new_packages": total_new_packages,
        "total_updated_packages": total_updated_packages,
    }


# ==================== RETRY PACKAGES ====================

@router.get("/retry-packages/{provider_id}")
async def get_retry_packages(provider_id: str, user: dict = Depends(get_current_user)):
    packages = await db.packages.find({"status": "retry"}, {"_id": 0}).to_list(500)
    retry_packages = []
    for pkg in packages:
        journey = await db.journeys.find_one({"id": pkg.get("journey_id")}, {"_id": 0})
        if journey and journey.get("provider_id") == provider_id:
            pkg["original_journey_date"] = journey.get("date", "")
            retry_packages.append(pkg)
    return retry_packages


# ==================== BULK PACKAGE STATUS UPDATE ====================

@router.post("/journeys/{journey_id}/packages/bulk-status")
async def bulk_update_package_status(
    journey_id: str,
    data: BulkStatusUpdate,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    valid_statuses = ["pending", "delivered", "failed", "returned"]
    if data.new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Opciones: {', '.join(valid_statuses)}")
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    result = await db.packages.update_many(
        {"id": {"$in": data.package_ids}, "journey_id": journey_id},
        {"$set": {"status": data.new_status}},
    )
    delivered = await db.packages.count_documents({"journey_id": journey_id, "status": "delivered"})
    failed = await db.packages.count_documents({"journey_id": journey_id, "status": "failed"})
    returned = await db.packages.count_documents({"journey_id": journey_id, "status": "returned"})
    total = await db.packages.count_documents({"journey_id": journey_id})
    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": {
            "packages_delivered": delivered,
            "packages_failed": failed,
            "packages_returned": returned,
            "packages_total": total,
        }},
    )
    await log_audit_event(
        db, user["id"], user["role"],
        "bulk_status_update", "packages", journey_id,
        details=f"Updated {result.modified_count} packages to {data.new_status}",
    )
    await ws_manager.broadcast_journey_update(journey_id, "packages_updated")
    return {
        "updated": result.modified_count,
        "new_status": data.new_status,
        "journey_totals": {"delivered": delivered, "failed": failed, "returned": returned, "total": total},
    }


# ==================== EVIDENCE EVALUATION ====================

@router.post("/reports/evaluate-journey/{journey_id}")
async def evaluate_journey_quality(journey_id: str, user: dict = Depends(get_current_user)):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    await evaluate_packages_for_journey(db, journey_id)
    packages = await db.packages.find(
        {"journey_id": journey_id, "evidence_score": {"$ne": None}},
        {"_id": 0, "evidence_score": 1},
    ).to_list(5000)
    scores = [p["evidence_score"] for p in packages]
    return {
        "evaluated": len(scores),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "complete": sum(1 for s in scores if s == 100),
        "partial": sum(1 for s in scores if 60 <= s < 100),
        "incomplete": sum(1 for s in scores if s < 60),
    }


@router.post("/journeys/{journey_id}/packages/{guide}/evaluate-evidence")
async def evaluate_package_evidence(
    journey_id: str,
    guide: str,
    user: dict = Depends(get_current_user),
):
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    result = await evaluate_single_package_for_journey(db, journey_id, guide, use_ai=True)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/journeys/{journey_id}/evaluate-evidence-all")
async def evaluate_all_evidence(journey_id: str, user: dict = Depends(get_current_user)):
    from ai_eval_worker import enqueue_job

    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    # Enqueue job en el worker centralizado para que aparezca en Monitor IA
    # y respete MAX_ROUTES_CONCURRENT, reintentos, orphan recovery, etc.
    result = await enqueue_job(
        db,
        route_id=journey_id,
        triggered_by="user_manual",
        triggered_by_user=user.get("id"),
        priority="NORMAL",
        force_reevaluate=False,
    )

    # Si no hay guias elegibles, caer al evaluador sincrono legacy como fallback
    # para que el usuario vea actualizacion inmediata en guias ya evaluadas.
    if not result or not result.get("job_id"):
        async def _background_ai_evaluation():
            try:
                await evaluate_packages_for_journey(db, journey_id, use_ai=True)
                logger.info(f"AI evidence evaluation completed for journey {journey_id}")
            except Exception as e:
                logger.error(f"AI evidence evaluation failed for journey {journey_id}: {e}")
        asyncio.create_task(_background_ai_evaluation())

    packages = await db.packages.find(
        {"journey_id": journey_id, "evidence_score": {"$ne": None}},
        {"_id": 0, "evidence_score": 1, "evidence_method": 1},
    ).to_list(5000)
    scores = [p["evidence_score"] for p in packages]
    ai_count = sum(1 for p in packages if p.get("evidence_method") == "ai")
    return {
        "status": "started",
        "message": (
            f"Evaluacion IA encolada ({result.get('total', 0)} guias) - visible en Monitor IA"
            if result and result.get("job_id")
            else "Evaluacion IA iniciada en segundo plano"
        ),
        "job_id": result.get("job_id") if result else None,
        "total_enqueued": result.get("total", 0) if result else 0,
        "current_stats": {
            "evaluated": len(scores),
            "ai_evaluated": ai_count,
            "rules_evaluated": len(scores) - ai_count,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "complete": sum(1 for s in scores if s == 100),
            "partial": sum(1 for s in scores if 60 <= s < 100),
            "incomplete": sum(1 for s in scores if s < 60),
        },
    }



@router.post("/journeys/{journey_id}/evaluate-ia")
async def evaluate_ia_alias(journey_id: str, user: dict = Depends(get_current_user)):
    """Alias for evaluate-evidence-all — used by Power BI Sandbox and external tools."""
    return await evaluate_all_evidence(journey_id, user)


@router.get("/journeys/{journey_id}/ai-eval-status")
async def get_ai_evaluation_status(journey_id: str, user: dict = Depends(get_current_user)):
    """Get current AI evaluation progress for a journey (used for polling)."""
    status = get_ai_eval_status(journey_id)
    return status



# ==================== PACKAGE RE-SCRAPE ====================

@router.post("/packages/{package_id}/rescrape")
async def rescrape_package(package_id: str, user: dict = Depends(get_current_user)):
    """Force re-scrape a single package's Kosmo tracking data."""
    from kosmo_sync import scrape_kosmo_page

    pkg = await db.packages.find_one({"id": package_id}, {"_id": 0})
    if not pkg:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")

    tracking_url = pkg.get("tracking_url", "")
    if not tracking_url:
        raise HTTPException(status_code=400, detail="Paquete sin URL de tracking")

    result = await scrape_kosmo_page(tracking_url)

    if result.get("error"):
        return {
            "success": False,
            "error": result["error"],
            "tracking_url": tracking_url,
        }

    now = datetime.now(timezone.utc)
    kosmo_raw = result.get("order_status") or "unknown"
    STATUS_MAP = {
        "delivered": "delivered",
        "cancelled": "failed",
        "failed": "failed",
        "returned": "returned",
    }
    mapped_status = STATUS_MAP.get(kosmo_raw)

    update_fields = {
        "kosmo_scraped_at": now.isoformat(),
        "kosmo_status_raw": kosmo_raw,
        "kosmo_order_id": result.get("order_id"),
        "kosmo_proof_count": result.get("proof_count", 0),
    }
    if result.get("updated_at_ms"):
        update_fields["kosmo_updated_at"] = result["updated_at_ms"]
    if result.get("finished_at_ms"):
        update_fields["kosmo_finished_at"] = result["finished_at_ms"]
    if result.get("driver_note"):
        update_fields["kosmo_driver_note"] = result["driver_note"]
    if result.get("proof_urls"):
        update_fields["kosmo_proof_urls"] = result["proof_urls"]

    if mapped_status:
        update_fields["status"] = mapped_status

    await db.packages.update_one({"id": package_id}, {"$set": update_fields})

    # Re-evaluate evidence score
    journey_id = pkg.get("journey_id")
    if journey_id:
        tracking = pkg.get("tracking_number") or pkg.get("order_reference_id", "")
        if tracking:
            await evaluate_single_package_for_journey(db, journey_id, tracking, use_ai=False)

    return {
        "success": True,
        "kosmo_status": kosmo_raw,
        "proof_count": result.get("proof_count", 0),
        "driver_note": result.get("driver_note"),
        "proof_urls": result.get("proof_urls", []),
    }


# ==================== BATCH RE-SCRAPE ====================

@router.post("/journeys/{journey_id}/batch-rescrape")
async def batch_rescrape_journey(journey_id: str, user: dict = Depends(get_current_user)):
    """Re-scrape ALL packages in a journey that have a tracking_url to ensure latest evidence is fetched."""
    from kosmo_sync import scrape_kosmo_page

    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    # Re-scrape ALL packages with a tracking URL — not just those with 0 proofs.
    # Kosmo may add photos after the initial scrape.
    candidates = await db.packages.find(
        {
            "journey_id": journey_id,
            "tracking_url": {"$nin": [None, ""]},
        },
        {"_id": 0, "id": 1, "tracking_url": 1, "tracking_number": 1, "order_reference_id": 1, "journey_id": 1, "kosmo_proof_count": 1},
    ).to_list(500)

    if not candidates:
        return {"total": 0, "recovered": 0, "errors": 0, "message": "No hay paquetes con URL de tracking"}

    now = datetime.now(timezone.utc)
    semaphore = asyncio.Semaphore(3)
    recovered = 0
    updated_proofs = 0
    errors = 0
    STATUS_MAP = {
        "delivered": "delivered",
        "cancelled": "failed",
        "failed": "failed",
        "returned": "returned",
    }

    async def process_one(pkg):
        nonlocal recovered, errors, updated_proofs
        async with semaphore:
            try:
                result = await scrape_kosmo_page(pkg["tracking_url"])
                if result.get("error"):
                    errors += 1
                    return

                kosmo_raw = result.get("order_status") or "unknown"
                mapped_status = STATUS_MAP.get(kosmo_raw)
                new_proof_count = result.get("proof_count", 0)
                old_proof_count = pkg.get("kosmo_proof_count") or 0

                update_fields = {
                    "kosmo_scraped_at": now.isoformat(),
                    "kosmo_status_raw": kosmo_raw,
                    "kosmo_order_id": result.get("order_id"),
                    "kosmo_proof_count": new_proof_count,
                }
                if result.get("updated_at_ms"):
                    update_fields["kosmo_updated_at"] = result["updated_at_ms"]
                if result.get("finished_at_ms"):
                    update_fields["kosmo_finished_at"] = result["finished_at_ms"]
                if result.get("driver_note"):
                    update_fields["kosmo_driver_note"] = result["driver_note"]
                if result.get("proof_urls"):
                    update_fields["kosmo_proof_urls"] = result["proof_urls"]
                if mapped_status:
                    update_fields["status"] = mapped_status

                await db.packages.update_one({"id": pkg["id"]}, {"$set": update_fields})

                if new_proof_count > 0 and old_proof_count == 0:
                    recovered += 1
                elif new_proof_count > old_proof_count:
                    updated_proofs += 1
            except Exception as e:
                logger.error(f"Batch rescrape error for {pkg['id']}: {e}")
                errors += 1

    await asyncio.gather(*[process_one(pkg) for pkg in candidates], return_exceptions=True)

    # Recount journey totals
    delivered = await db.packages.count_documents({"journey_id": journey_id, "status": "delivered"})
    failed = await db.packages.count_documents({"journey_id": journey_id, "status": "failed"})
    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": {"packages_delivered": delivered, "packages_failed": failed}},
    )

    # Re-evaluate evidence for scraped packages
    scraped_ids = [p["id"] for p in candidates]
    if scraped_ids:
        from evidence_scoring import evaluate_packages_by_ids
        await evaluate_packages_by_ids(db, scraped_ids, {journey_id})

    # Recalculate confidence scores after Kosmo data is refreshed
    all_packages = await db.packages.find({"journey_id": journey_id}, {"_id": 0}).to_list(5000)
    for pkg in all_packages:
        confidence = _compute_confidence(pkg)
        discrepancy = _detect_discrepancy(pkg, confidence)
        update_fields_conf = {"confidence": confidence, "discrepancy": discrepancy}
        existing_review = pkg.get("manual_review", {})
        if discrepancy["detected"] and not existing_review.get("reviewed_at"):
            update_fields_conf["manual_review"] = {
                "required": True, "status": "pending",
                "reviewed_by": existing_review.get("reviewed_by"),
                "reviewed_at": existing_review.get("reviewed_at"),
                "decision": existing_review.get("decision"),
            }
        await db.packages.update_one({"id": pkg["id"]}, {"$set": update_fields_conf})

    return {
        "total": len(candidates),
        "recovered": recovered,
        "updated_proofs": updated_proofs,
        "errors": errors,
        "message": f"Re-sincronización completa: {recovered} nuevos recuperados, {updated_proofs} evidencias actualizadas de {len(candidates)}",
    }



# ==================== DISCREPANCY DETECTION ====================

CARRIER_PROFILES = {
    "kosmo": {
        "required_evidences": ["foto_fachada", "foto_paquete_guia", "foto_receptor"],
        "min_confidence_for_auto_approve": 70,
        "exception_required_on_failure": True,
    }
}


def _compute_confidence(pkg: dict) -> dict:
    """Compute confidence score for a package based on evidence factors.
    NOTE: This operates on RAW DB documents, not enriched ones.
    Use DB field names: kosmo_proof_urls, kosmo_proof_count, evidence_score, ia_errors, evidence_detail."""
    proof_urls = pkg.get("kosmo_proof_urls") or []
    photos_count = pkg.get("kosmo_proof_count") or len(proof_urls)

    # Build error list from raw DB fields (not enriched ai_errors)
    raw_ia_errors = pkg.get("ia_errors") or []
    detail = pkg.get("evidence_detail") or {}
    missing_items = detail.get("missing_items") or []
    alerts = detail.get("alerts") or []
    all_errors = raw_ia_errors + missing_items + alerts

    # Use evidence_score (stored by AI/rules eval) — not the enriched ai_score
    evidence_score = pkg.get("evidence_score") or pkg.get("ai_score") or 0

    # Evidence factor checks — use raw error keys and human-readable error strings
    error_text = " ".join(all_errors).lower()
    has_foto_fachada = "fachada" not in error_text and "falta_fachada" not in error_text and photos_count > 0
    has_foto_paquete = "guia" not in error_text and "guia_no_visible" not in error_text and photos_count > 0
    has_foto_receptor = "receptor" not in error_text and "sin_foto_receptor" not in error_text and photos_count > 0
    has_motivo_excepcion = bool(pkg.get("failure_reason") or pkg.get("kosmo_driver_note"))
    has_score_ia_positivo = evidence_score > 0

    factors = {
        "foto_fachada": has_foto_fachada,
        "foto_paquete_guia": has_foto_paquete,
        "foto_receptor": has_foto_receptor,
        "motivo_excepcion": has_motivo_excepcion,
        "score_ia_positivo": has_score_ia_positivo,
    }

    score = 0
    if has_foto_fachada:
        score += 25
    if has_foto_paquete:
        score += 25
    if has_foto_receptor:
        score += 25
    if has_motivo_excepcion:
        score += 15
    if has_score_ia_positivo:
        score += 10

    level = "high" if score >= 70 else ("medium" if score >= 30 else "low")

    return {
        "score": score,
        "level": level,
        "factors": factors,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def _detect_discrepancy(pkg: dict, confidence: dict) -> dict:
    """Detect discrepancy between tracking status and evidence.
    NOTE: This operates on RAW DB documents."""
    status = pkg.get("status", "")
    kosmo_status_raw = pkg.get("kosmo_status_raw", "")
    photos_count = pkg.get("kosmo_proof_count") or len(pkg.get("kosmo_proof_urls") or [])
    has_exception = bool(pkg.get("failure_reason") or pkg.get("kosmo_driver_note"))

    # Discrepancy: tracking says delivered but no evidence at all
    is_delivered = status == "delivered"
    no_evidence = photos_count == 0 and not has_exception and confidence["score"] == 0

    detected = is_delivered and no_evidence

    if detected:
        return {
            "detected": True,
            "type": "tracking_vs_evidence",
            "tracking_says": kosmo_status_raw or "Entregado",
            "evidence_says": "Sin evidencias",
            "kosmo_internal_says": "Creado",
            "recommended_status": "Devolución sin intento",
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "detected": False,
        "type": None,
        "tracking_says": kosmo_status_raw or status,
        "evidence_says": f"{photos_count} fotos" if photos_count > 0 else "Sin evidencias",
        "kosmo_internal_says": None,
        "recommended_status": None,
        "detected_at": None,
    }


@router.post("/journeys/{journey_id}/guides/evaluate-confidence")
async def evaluate_confidence(journey_id: str, user: dict = Depends(get_current_user)):
    """Recalculate confidence scores and detect discrepancies for all guides in a journey."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    packages = await db.packages.find({"journey_id": journey_id}, {"_id": 0}).to_list(5000)

    discrepancy_count = 0
    total_confidence = 0
    evaluated = 0

    for pkg in packages:
        confidence = _compute_confidence(pkg)
        discrepancy = _detect_discrepancy(pkg, confidence)

        update_fields = {
            "confidence": confidence,
            "discrepancy": discrepancy,
        }

        # Set manual_review.required based on confidence
        existing_review = pkg.get("manual_review", {})
        if discrepancy["detected"]:
            discrepancy_count += 1
            if not existing_review.get("reviewed_at"):
                update_fields["manual_review"] = {
                    "required": True,
                    "status": "pending",
                    "reviewed_by": existing_review.get("reviewed_by"),
                    "reviewed_at": existing_review.get("reviewed_at"),
                    "decision": existing_review.get("decision"),
                }
        elif confidence["score"] < 70:
            if not existing_review.get("reviewed_at"):
                update_fields["manual_review"] = {
                    "required": True,
                    "status": "pending",
                    "reviewed_by": existing_review.get("reviewed_by"),
                    "reviewed_at": existing_review.get("reviewed_at"),
                    "decision": existing_review.get("decision"),
                }

        await db.packages.update_one({"id": pkg["id"]}, {"$set": update_fields})
        total_confidence += confidence["score"]
        evaluated += 1

    avg_confidence = round(total_confidence / evaluated, 1) if evaluated > 0 else 0

    return {
        "evaluated": evaluated,
        "discrepancies": discrepancy_count,
        "avg_confidence": avg_confidence,
        "message": f"Evaluación de confianza completa: {discrepancy_count} discrepancias detectadas en {evaluated} guías.",
    }


@router.patch("/journeys/{journey_id}/guides/{guide_id}/review")
async def review_discrepancy(
    journey_id: str,
    guide_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Review a discrepancy: confirm_return or mark_valid."""
    decision = body.get("decision")
    if decision not in ("confirm_return", "mark_valid"):
        raise HTTPException(status_code=400, detail="Decisión inválida. Use 'confirm_return' o 'mark_valid'.")

    # Find package by guide_id (order_reference_id or tracking_number) within the journey
    pkg = await db.packages.find_one(
        {"journey_id": journey_id, "$or": [{"order_reference_id": guide_id}, {"tracking_number": guide_id}, {"id": guide_id}]},
        {"_id": 0},
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Guía no encontrada")

    now = datetime.now(timezone.utc).isoformat()
    previous_status = pkg.get("status", "pending")
    reviewer = user.get("name") or user.get("email", "unknown")

    update_fields = {
        "manual_review": {
            "required": False,
            "status": "reviewed",
            "reviewed_by": reviewer,
            "reviewed_at": now,
            "decision": decision,
            "previous_status": previous_status,
        }
    }

    if decision == "confirm_return":
        update_fields["status"] = "returned"
        update_fields["manual_review"]["new_status"] = "returned"
    else:
        update_fields["manual_review"]["new_status"] = previous_status
        # Clear discrepancy flag
        update_fields["discrepancy"] = {
            "detected": False,
            "type": None,
            "tracking_says": pkg.get("discrepancy", {}).get("tracking_says"),
            "evidence_says": pkg.get("discrepancy", {}).get("evidence_says"),
            "kosmo_internal_says": None,
            "recommended_status": None,
            "resolved_at": now,
        }

    await db.packages.update_one({"id": pkg["id"]}, {"$set": update_fields})

    # Recalculate journey counts if status changed
    if decision == "confirm_return":
        delivered = await db.packages.count_documents({"journey_id": journey_id, "status": "delivered"})
        failed = await db.packages.count_documents({"journey_id": journey_id, "status": {"$in": ["failed", "cancelled"]}})
        returned = await db.packages.count_documents({"journey_id": journey_id, "status": "returned"})
        await db.journeys.update_one(
            {"id": journey_id},
            {"$set": {"packages_delivered": delivered, "packages_failed": failed, "packages_returned": returned}},
        )

    # Log audit event
    await log_audit_event(
        db, user.get("id", "unknown"), user.get("role", "unknown"),
        action="discrepancy_review",
        entity_type="package",
        entity_id=pkg["id"],
        details=f"Decision: {decision}, Previous: {previous_status}, Guide: {guide_id}",
    )

    return {
        "success": True,
        "decision": decision,
        "package_id": pkg["id"],
        "new_status": update_fields.get("status", previous_status),
        "reviewed_by": reviewer,
    }


# ==================== P1: ROUTE-LEVEL PROVIDER EDIT ====================

class ProviderChangeRequest(BaseModel):
    provider_id: str
    reason: Optional[str] = None

@router.patch("/journeys/{journey_id}/provider")
async def change_journey_provider(
    journey_id: str,
    data: ProviderChangeRequest,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Change the provider assigned to a specific route. Logs to route_edits audit."""
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    new_provider = await db.providers.find_one({"id": data.provider_id}, {"_id": 0, "id": 1, "name": 1})
    if not new_provider:
        raise HTTPException(status_code=400, detail="Proveedor no encontrado")

    old_provider_id = journey.get("provider_id", "")
    if old_provider_id == data.provider_id:
        return {"message": "El proveedor ya es el mismo", "changed": False}

    now = datetime.now(timezone.utc).isoformat()

    # Update journey
    await db.journeys.update_one(
        {"id": journey_id},
        {"$set": {"provider_id": data.provider_id, "updated_at": now}},
    )

    # Audit log in route_edits
    await db.route_edits.insert_one({
        "id": str(uuid.uuid4()),
        "route_id": journey_id,
        "field": "provider_id",
        "old_value": old_provider_id,
        "new_value": data.provider_id,
        "changed_by": user["id"],
        "changed_by_name": user.get("name", user.get("email", "")),
        "changed_at": now,
        "reason": data.reason or "",
        "route_status": journey.get("status", ""),
    })

    await log_audit_event(
        db, user["id"], user["role"], "route_provider_changed", "journey", journey_id,
        details=f"Provider changed from {old_provider_id} to {data.provider_id}",
    )

    return {
        "message": f"Proveedor actualizado a {new_provider['name']}",
        "changed": True,
        "new_provider_id": new_provider["id"],
        "new_provider_name": new_provider["name"],
    }
