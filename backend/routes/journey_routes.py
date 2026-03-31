"""
Journey management routes: CRUD, start, close, incidents, cosmo import, bulk update.
"""
import asyncio
import uuid
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from datetime import datetime, timezone

from dependencies import (
    db, get_current_user, require_role, apply_assignment_filter,
    _next_day, _normalize_address,
)
from models import (
    JourneyCreate, JourneyStartData, JourneyCloseData,
    IncidentCreate, IncidentResponse, CosmoJourneyCreate, BulkStatusUpdate,
)
from middleware import log_audit_event
from evidence_scoring import (
    evaluate_packages_for_journey,
    evaluate_single_package_for_journey,
)
from ws_manager import ws_manager
from routes.webhook_routes import dispatch_webhook_event
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
        "data": journeys,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
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

    journey["packages"] = packages

    incidents = await db.incidents.find({"journey_id": journey_id}, {"_id": 0}).to_list(100)
    journey["incidents"] = incidents
    journey["incidents_count"] = len(incidents)
    journey["open_incidents_count"] = len([i for i in incidents if i["status"] == "open"])

    return journey


@router.post("/journeys")
async def create_journey(data: JourneyCreate, user: dict = Depends(require_role(["coordinator", "agent"]))):
    journey_id = str(uuid.uuid4())
    journey = {
        "id": journey_id,
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

    for pkg in data.packages:
        package = {
            "id": str(uuid.uuid4()),
            "journey_id": journey_id,
            "tracking_number": pkg.get("tracking_number", ""),
            "recipient_name": pkg.get("recipient_name", ""),
            "address": pkg.get("address", ""),
            "zone": pkg.get("zone", ""),
            "delivery_window": pkg.get("delivery_window", ""),
            "status": "pending",
            "is_retry": False,
        }
        await db.packages.insert_one(package)

    for pkg_id in data.retry_packages:
        await db.packages.update_one(
            {"id": pkg_id},
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
async def create_incident(data: IncidentCreate, user: dict = Depends(require_role(["coordinator", "agent"]))):
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
    }))

    return {k: v for k, v in incident.items() if k != "_id"}


@router.put("/incidents/{incident_id}")
async def update_incident(incident_id: str, data: dict, user: dict = Depends(require_role(["coordinator", "agent"]))):
    update_data = {k: v for k, v in data.items() if k not in ["id", "_id"]}
    if data.get("status") == "resolved":
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
        update_data["resolved_by"] = user["id"]
    result = await db.incidents.update_one({"id": incident_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return {"message": "Incidencia actualizada"}


@router.delete("/incidents/{incident_id}")
async def delete_incident(incident_id: str, user: dict = Depends(require_role(["coordinator", "agent"]))):
    result = await db.incidents.delete_one({"id": incident_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")
    return {"message": "Incidencia eliminada"}


@router.put("/incidents/journey/{journey_id}/resolve-all")
async def resolve_all_incidents(journey_id: str, user: dict = Depends(require_role(["coordinator", "agent"]))):
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
        {"$set": {"reviewed_by": user.get("name", user["email"]), "reviewed_at": now}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return {"message": "Paquete marcado como revisado", "reviewed_by": user.get("name", user["email"]), "reviewed_at": now}


# ==================== COSMO JOURNEY CREATION ====================

@router.post("/journeys/from-cosmo")
async def create_journeys_from_cosmo(
    data: CosmoJourneyCreate,
    user: dict = Depends(require_role(["coordinator", "agent"])),
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

    for route in data.route_summary:
        route_id = route.get("route_id", "")
        driver_name = route.get("driver_name", "")
        if not route_id:
            continue

        provider_id = mappings.get(driver_name)
        if not provider_id:
            existing_mapping = await db.messenger_mappings.find_one({"messenger_name": driver_name}, {"_id": 0})
            if existing_mapping:
                provider_id = existing_mapping.get("provider_id")
        if not provider_id:
            errors.append(f"Sin proveedor asignado para mensajero: {driver_name}")
            continue

        existing_journey = await db.journeys.find_one({"cosmo_route_id": route_id}, {"_id": 0})
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
                            await db.packages.update_one({"id": pkg_data["id"]}, {"$set": update_fields})
                            route_updated += 1

            if route_updated > 0:
                j_id = existing_journey["id"]
                delivered = await db.packages.count_documents({"journey_id": j_id, "status": "delivered"})
                failed = await db.packages.count_documents({"journey_id": j_id, "status": "failed"})
                await db.journeys.update_one(
                    {"id": j_id},
                    {"$set": {"packages_delivered": delivered, "packages_failed": failed}},
                )
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
                        await db.packages.update_one({"id": pkg_data["id"]}, {"$set": update_fields})
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
    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    async def _run_ai_eval():
        try:
            await evaluate_packages_for_journey(db, journey_id, use_ai=True)
            logger.info(f"AI evidence evaluation completed for journey {journey_id}")
        except Exception as e:
            logger.error(f"AI evidence evaluation failed for journey {journey_id}: {e}")

    asyncio.create_task(_run_ai_eval())

    packages = await db.packages.find(
        {"journey_id": journey_id, "evidence_score": {"$ne": None}},
        {"_id": 0, "evidence_score": 1, "evidence_method": 1},
    ).to_list(5000)
    scores = [p["evidence_score"] for p in packages]
    ai_count = sum(1 for p in packages if p.get("evidence_method") == "ai")
    return {
        "status": "started",
        "message": "Evaluación IA iniciada en segundo plano. Recargue la página en unos momentos.",
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
    """Re-scrape all packages in a journey that have a tracking_url but 0 proofs or unknown status."""
    from kosmo_sync import scrape_kosmo_page

    journey = await db.journeys.find_one({"id": journey_id}, {"_id": 0})
    if not journey:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    # Find packages needing rescrape
    candidates = await db.packages.find(
        {
            "journey_id": journey_id,
            "tracking_url": {"$nin": [None, ""]},
            "$or": [
                {"kosmo_proof_count": 0},
                {"kosmo_proof_count": None},
                {"kosmo_proof_count": {"$exists": False}},
                {"kosmo_status_raw": "unknown"},
                {"kosmo_status_raw": None},
                {"kosmo_status_raw": {"$exists": False}},
            ],
        },
        {"_id": 0, "id": 1, "tracking_url": 1, "tracking_number": 1, "order_reference_id": 1, "journey_id": 1},
    ).to_list(500)

    if not candidates:
        return {"total": 0, "recovered": 0, "errors": 0, "message": "No hay paquetes que necesiten re-sincronización"}

    now = datetime.now(timezone.utc)
    semaphore = asyncio.Semaphore(3)
    recovered = 0
    errors = 0
    STATUS_MAP = {
        "delivered": "delivered",
        "cancelled": "failed",
        "failed": "failed",
        "returned": "returned",
    }

    async def process_one(pkg):
        nonlocal recovered, errors
        async with semaphore:
            try:
                result = await scrape_kosmo_page(pkg["tracking_url"])
                if result.get("error"):
                    errors += 1
                    return

                kosmo_raw = result.get("order_status") or "unknown"
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

                await db.packages.update_one({"id": pkg["id"]}, {"$set": update_fields})

                if result.get("proof_count", 0) > 0:
                    recovered += 1
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

    return {
        "total": len(candidates),
        "recovered": recovered,
        "errors": errors,
        "message": f"Re-sincronización completa: {recovered} paquetes recuperados de {len(candidates)}",
    }
