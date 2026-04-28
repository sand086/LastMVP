"""
Routal event processor — multi-tenant (R00A.6).

Cada handler recibe (payload, client_id) y filtra TODAS las queries por client_id
para evitar cruzar datos entre clientes. Idempotente: si un evento ya fue procesado
o el journey/package ya existe con el mismo external id, skip.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_plan_date(payload: dict) -> str:
    """Determine the plan's calendar date (YYYY-MM-DD) from a Routal webhook/API payload.

    Priority:
      1. execution_date (ISO 8601, authoritative — matches Routal UI label exactly).
      2. date (string or ISO).
      3. UTC today (last-resort fallback).

    Routal stores execution_date as `YYYY-MM-DDT18:00:00.000Z` for CDMX operations
    (18:00 UTC = 12:00 CDMX), which yields the same calendar day in both UTC and
    America/Mexico_City. Earlier code used `payload.get("date")` first, but that
    field is sometimes absent or in a different timezone, producing 1-day offsets
    vs. the Routal Planner UI.
    """
    exd = payload.get("execution_date")
    if exd:
        try:
            pdt = datetime.fromisoformat(str(exd).replace("Z", "+00:00"))
            return pdt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    raw = payload.get("date")
    if raw:
        s = str(raw)
        # Plain "YYYY-MM-DD" — keep as-is (already a calendar date)
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return s
        try:
            pdt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return pdt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _format_routal_address(location: dict) -> str:
    """Build a single human-readable address string from Routal stop.location dict."""
    if not isinstance(location, dict):
        return ""
    if location.get("label"):
        return location["label"]
    parts = []
    street = location.get("street") or ""
    house = location.get("house_number") or ""
    if street:
        parts.append(f"{street} {house}".strip())
    if location.get("postal_code"):
        parts.append(f"CP {location['postal_code']}")
    if location.get("city"):
        parts.append(location["city"])
    if location.get("state"):
        parts.append(location["state"])
    return ", ".join(p for p in parts if p)


def map_routal_stop_to_pkg_fields(stop: dict) -> dict:
    """Extract recipient_name / address / phone / tracking from a Routal stop doc.
    Used by _handle_plan_created_direct and routal_sync to keep field semantics
    consistent. Mimics the Kosmo pipeline (which already populates these fields).
    """
    label = stop.get("label") or ""
    recipient_name = (stop.get("recipient") or {}).get("name") or stop.get("recipient_name") or label
    location = stop.get("location") or {}
    address = stop.get("address") or _format_routal_address(location)
    phone = stop.get("phone") or (stop.get("recipient") or {}).get("phone")
    tracking = (
        stop.get("tracking_number")
        or stop.get("reference")
        or stop.get("client_external_id")
        or stop.get("fixed_id")
        or stop.get("id")
    )
    order_ref = stop.get("client_external_id") or stop.get("fixed_id") or stop.get("id")
    return {
        "recipient_name": recipient_name,
        "address": address,
        "recipient_phone": phone,
        "tracking_number": tracking,
        "order_reference_id": order_ref,
    }


async def _handle_plan_created_direct(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    """Original behavior: insert Journey + Packages directly.
    Reused by selection worker after deciding a driver should be audited.
    Returns journey_id (str) on success, or status string when skipped.
    """
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"

    existing = await db.journeys.find_one(
        {"routal_plan_id": plan_id, "client_id": client_id},
        {"_id": 0, "id": 1},
    )
    if existing:
        return existing["id"]

    driver_name = (payload.get("driver") or {}).get("name") or payload.get("driver_name") or "Sin asignar"
    services = payload.get("services") or payload.get("stops") or []
    plan_date_str = _extract_plan_date(payload)
    plan_label = payload.get("label") or payload.get("plan_label")

    journey_id = str(uuid.uuid4())
    journey = {
        "id": journey_id,
        "routal_plan_id": plan_id,
        "routal_plan_label": plan_label,
        "routal_project_id": payload.get("project_id") or payload.get("organization_id"),
        "branch_id": branch_id,
        "source": "routal",
        "client_id": client_id,
        "driver_name": driver_name,
        "routal_driver_id": (payload.get("driver") or {}).get("id"),
        "date": plan_date_str,
        "status": "planificada",
        "packages_total": len(services),
        "packages_delivered": 0,
        "packages_failed": 0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.journeys.insert_one(journey)

    pkg_docs = []
    for svc in services:
        svc_id = svc.get("id") or svc.get("service_id")
        if not svc_id:
            continue
        mapped = map_routal_stop_to_pkg_fields(svc)
        pkg_docs.append({
            "id": str(uuid.uuid4()),
            "journey_id": journey_id,
            "client_id": client_id,
            "source": "routal",
            "routal_service_id": svc_id,
            "tracking_number": mapped["tracking_number"] or svc_id,
            "tracking_url": svc.get("tracking_url"),
            "order_reference_id": mapped["order_reference_id"],
            "recipient_name": mapped["recipient_name"],
            "recipient_phone": mapped["recipient_phone"],
            "address": mapped["address"],
            "status": "pending",
            "created_at": _now_iso(),
        })
    # PII at-rest: encrypt before insert
    if pkg_docs:
        from utils.pii import encrypt_pkg_pii
        for d in pkg_docs:
            if branch_id:
                d["branch_id"] = branch_id
            encrypt_pkg_pii(d)
        await db.packages.insert_many(pkg_docs)

    logger.info(f"[routal] plan_created plan={plan_id} client={client_id} pkgs={len(pkg_docs)}")
    return journey_id


async def _handle_plan_created(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    """SEL01: when client has selection_enabled=True, stage the plan instead of
    creating the Journey immediately. The selection worker will later create
    Journeys only for selected drivers. Falls back to direct creation otherwise.
    """
    cfg = await db.client_config.find_one(
        {"client_id": client_id},
        {"_id": 0, "selection_enabled": 1, "active": 1},
    )
    if not cfg or not cfg.get("selection_enabled") or not cfg.get("active", True):
        # Non-breaking path
        result = await _handle_plan_created_direct(db, payload, client_id, branch_id=branch_id)
        # _handle_plan_created_direct returns either journey_id (uuid) or "skipped: ..." string
        if result and not str(result).startswith("skipped"):
            return f"created journey {result}"
        return result

    # Selection-enabled path: stage in routal_daily_plans
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"
    drv = (payload.get("driver") or {}).get("id") or payload.get("driver_id")
    if not drv:
        return "skipped: no driver_id (selection requires driver)"
    drv_name = (payload.get("driver") or {}).get("name") or payload.get("driver_name") or "Sin asignar"
    plan_date_str = _extract_plan_date(payload)
    try:
        plan_date = datetime.strptime(plan_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        plan_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Idempotent staging by (client_id, driver_id, date)
    await db.routal_daily_plans.update_one(
        {"client_id": client_id, "driver_id": drv, "date": plan_date},
        {"$set": {
            "client_id": client_id,
            "branch_id": branch_id,
            "driver_id": drv,
            "driver_name": drv_name,
            "date": plan_date,
            "plan_id_routal": plan_id,
            "route_metadata": payload,
            "received_at": _now_iso(),
            "processed": False,
        }},
        upsert=True,
    )
    logger.info(f"[selection] plan staged plan={plan_id} client={client_id} driver={drv}")
    return f"staged plan {plan_id} for selection (driver={drv})"


async def _handle_plan_started(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"
    result = await db.journeys.update_one(
        {"routal_plan_id": plan_id, "client_id": client_id, "status": {"$ne": "completada"}},
        {"$set": {"status": "en_ruta", "started_at": payload.get("started_at") or _now_iso(), "updated_at": _now_iso()}},
    )
    return f"plan_started: matched={result.matched_count}"


async def _handle_stop_completed(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    svc_id = payload.get("service_id") or (payload.get("service") or {}).get("id") or payload.get("stop_id")
    if not svc_id:
        return "skipped: no service_id"
    result = await db.packages.update_one(
        {"routal_service_id": svc_id, "client_id": client_id},
        {"$set": {
            "status": "delivered",
            "delivered_at": payload.get("completed_at") or _now_iso(),
            "updated_at": _now_iso(),
        }},
    )
    if result.matched_count == 0:
        return f"warn: package not found (service={svc_id}, client={client_id})"
    # Increment journey counter
    journey_id_doc = await db.packages.find_one(
        {"routal_service_id": svc_id, "client_id": client_id},
        {"_id": 0, "journey_id": 1},
    )
    if journey_id_doc:
        await db.journeys.update_one(
            {"id": journey_id_doc["journey_id"]},
            {"$inc": {"packages_delivered": 1}, "$set": {"updated_at": _now_iso()}},
        )
    return f"delivered: svc={svc_id}"


async def _handle_stop_failed(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    svc_id = payload.get("service_id") or (payload.get("service") or {}).get("id") or payload.get("stop_id")
    if not svc_id:
        return "skipped: no service_id"
    result = await db.packages.update_one(
        {"routal_service_id": svc_id, "client_id": client_id},
        {"$set": {
            "status": "failed",
            "failed_at": payload.get("failed_at") or _now_iso(),
            "fail_reason": payload.get("reason") or payload.get("failure_reason"),
            "updated_at": _now_iso(),
        }},
    )
    if result.matched_count == 0:
        return f"warn: package not found (service={svc_id})"
    pkg = await db.packages.find_one(
        {"routal_service_id": svc_id, "client_id": client_id},
        {"_id": 0, "journey_id": 1, "id": 1},
    )
    if pkg:
        await db.journeys.update_one(
            {"id": pkg["journey_id"]},
            {"$inc": {"packages_failed": 1}, "$set": {"updated_at": _now_iso()}},
        )
        # Auto-create incident record
        await db.incidents.insert_one({
            "id": str(uuid.uuid4()),
            "journey_id": pkg["journey_id"],
            "package_id": pkg["id"],
            "client_id": client_id,
            "incident_type": "Otro",
            "description": payload.get("reason") or "Fallo reportado por Routal",
            "occurred_at": _now_iso(),
            "source": "routal_auto",
            "status": "open",
        })
    return f"failed: svc={svc_id}"


async def _handle_plan_completed(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"
    result = await db.journeys.update_one(
        {"routal_plan_id": plan_id, "client_id": client_id},
        {"$set": {"status": "completada", "closed_at": payload.get("completed_at") or _now_iso(), "updated_at": _now_iso()}},
    )
    return f"plan_completed: matched={result.matched_count}"


async def _handle_plan_cancelled(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"
    result = await db.journeys.update_one(
        {"routal_plan_id": plan_id, "client_id": client_id},
        {"$set": {"status": "cancelada", "cancelled_at": _now_iso(), "updated_at": _now_iso()}},
    )
    return f"plan_cancelled: matched={result.matched_count}"


HANDLERS = {
    "plan_created": _handle_plan_created,
    "plan.created": _handle_plan_created,
    "plan_started": _handle_plan_started,
    "plan.started": _handle_plan_started,
    "stop_completed": _handle_stop_completed,
    "stop.completed": _handle_stop_completed,
    "stop_failed": _handle_stop_failed,
    "stop.failed": _handle_stop_failed,
    "plan_completed": _handle_plan_completed,
    "plan.completed": _handle_plan_completed,
    "plan_cancelled": _handle_plan_cancelled,
    "plan.cancelled": _handle_plan_cancelled,
}


async def process_routal_event(db, event_id: str, client_id: str) -> Optional[str]:
    """Idempotent processing of a single Routal event."""
    evt = await db.routal_events.find_one({"event_id": event_id, "client_id": client_id})
    if not evt:
        logger.warning(f"[routal] event not found: {event_id} (client={client_id})")
        return None
    if evt.get("processed"):
        return "already processed"

    event_type = evt.get("event_type") or ""
    handler = HANDLERS.get(event_type)
    if not handler:
        await db.routal_events.update_one(
            {"event_id": event_id, "client_id": client_id},
            {"$set": {"processed": True, "result": f"no handler for {event_type}"}},
        )
        return f"no handler for {event_type}"

    try:
        branch_id = evt.get("branch_id")
        result = await handler(db, evt.get("payload") or {}, client_id, branch_id=branch_id)
        await db.routal_events.update_one(
            {"event_id": event_id, "client_id": client_id},
            {"$set": {"processed": True, "processed_at": _now_iso(), "result": str(result)[:200]}},
        )
        # Update last_sync_at on integration
        await db.client_integrations.update_one(
            {"client_id": client_id},
            {"$set": {"last_sync_at": _now_iso(), "last_error": None}},
        )
        return result
    except Exception as e:
        err = str(e)[:200]
        logger.error(f"[routal] handler {event_type} failed for client {client_id}: {err}")
        await db.routal_events.update_one(
            {"event_id": event_id, "client_id": client_id},
            {"$set": {"error": err, "last_attempt_at": _now_iso(), "attempts": evt.get("attempts", 0) + 1}},
        )
        await db.client_integrations.update_one(
            {"client_id": client_id},
            {"$set": {"last_error": err}},
        )
        return None


async def reprocess_failed_events(db) -> int:
    """Periodic: re-attempt events that haven't been processed >5 min after receipt."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    count = 0
    async for evt in db.routal_events.find(
        {"processed": False, "received_at": {"$lt": cutoff}, "attempts": {"$lt": 5}},
        {"_id": 0, "event_id": 1, "client_id": 1},
    ).limit(50):
        await process_routal_event(db, evt["event_id"], evt["client_id"])
        count += 1
    return count
