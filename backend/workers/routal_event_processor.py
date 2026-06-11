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


def _is_scanner_placeholder(label) -> bool:
    """Routal autogenera planes/routes con prefijo 'LastmileScanSessions - XXXXXX'
    cuando un escáner móvil crea el plan y aún no se asigna driver real.
    Estos NO deben crear journey ni stagearse para SEL01 hasta que se asigne driver.
    """
    if not label:
        return False
    return str(label).startswith("LastmileScanSessions")


def _normalize_routes_from_payload(payload: dict) -> list:
    """Normaliza un plan-payload a una lista de tuplas (route_id, route_label, route_stops, raw_route).

    Acepta dos shapes:
      - Multi-route (backfill / GET /v2/plan/{id}): payload['routes'] poblado.
      - Single-driver (webhook / SEL01 staging): payload['driver'] + payload['stops|services'].

    Para multi-route, cada stop se filtra por stop.route_id == route.id.
    Para single-driver, si los stops traen route_id se filtra por driver.id; si no, se aceptan todos
    (compat con webhooks viejos que mandan solo el subset asignado al driver).
    """
    all_stops = payload.get("stops") or payload.get("services") or []
    if payload.get("routes"):
        out = []
        for r in payload["routes"]:
            rid = r.get("id") or r.get("external_id")
            rlabel = r.get("label") or r.get("name") or "Sin asignar"
            rstops = [s for s in all_stops if s.get("route_id") == r.get("id")]
            out.append((rid, rlabel, rstops, r))
        return out
    drv = payload.get("driver") or {}
    drv_id = drv.get("id") or payload.get("driver_id")
    drv_name = drv.get("name") or payload.get("driver_name") or "Sin asignar"
    if drv_id is None:
        return []
    has_route_ids = any(s.get("route_id") for s in all_stops)
    if has_route_ids:
        rstops = [s for s in all_stops if s.get("route_id") == drv_id]
    else:
        rstops = all_stops
    return [(drv_id, drv_name, rstops, drv)]


async def _handle_plan_created_direct(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    """Crea N journeys (1 por route real) desde un plan-payload de Routal.

    Modelo Routal validado contra API:
      Plan ┐
           ├─ Route 1 (driver A) ─┬─ Stop a1, a2, ...
           ├─ Route 2 (driver B) ─┴─ Stop b1, b2, ...
           └─ stops sin route_id → DESCARTADOS

    Comportamiento:
      - 1 route real = 1 journey en LastMile (NO 1 plan = 1 journey como antes).
      - routal_route_id es la nueva clave única (con client_id) por journey.
      - Routes con label 'LastmileScanSessions*' se omiten (placeholder pre-asignación).
      - Stops sin route_id se descartan.
      - Idempotente: si ya existe journey con (routal_route_id, client_id) → reutiliza.
      - Si una journey legacy existe con mismo plan_id pero sin route_id y solo hay 1 route real,
        se hidrata in-place (back-compat sin crear duplicado).

    Returns:
      - First journey_id creado/encontrado (back-compat con callers que esperaban string).
      - 'skipped: <razón>' si nada se creó.
    """
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"

    plan_label = payload.get("label") or payload.get("plan_label")
    project_id = payload.get("project_id") or payload.get("organization_id")
    plan_date_str = _extract_plan_date(payload)

    # Skip plan-level placeholder (still possible to have real routes inside, so we don't bail here)
    routes_iter = _normalize_routes_from_payload(payload)
    if not routes_iter:
        return "skipped: no routes/driver in payload"

    created_ids: list = []
    skipped_placeholder = 0
    skipped_no_id = 0

    for route_id, route_label, route_stops, _route_raw in routes_iter:
        if not route_id:
            skipped_no_id += 1
            continue
        if _is_scanner_placeholder(route_label):
            skipped_placeholder += 1
            continue
        if not route_stops and len(routes_iter) > 1:
            # Multi-route plan: routes with zero stops are administrative shells (no actual deliveries).
            # Creating an empty journey for them pollutes /rutas. Skip.
            continue

        # Idempotency: existing journey by routal_route_id
        existing = await db.journeys.find_one(
            {"routal_route_id": route_id, "client_id": client_id},
            {"_id": 0, "id": 1},
        )
        if existing:
            created_ids.append(existing["id"])
            continue

        # Back-compat: legacy single-route plan journey created BEFORE the route-level model.
        # Only auto-attach if THIS plan has only one real route (not a multi-route plan).
        if len(routes_iter) == 1:
            legacy = await db.journeys.find_one(
                {
                    "routal_plan_id": plan_id,
                    "client_id": client_id,
                    "routal_route_id": {"$exists": False},
                },
                {"_id": 0, "id": 1},
            )
            if legacy:
                await db.journeys.update_one(
                    {"id": legacy["id"]},
                    {"$set": {
                        "routal_route_id": route_id,
                        "driver_name": route_label,
                        "routal_driver_id": route_id,
                        "updated_at": _now_iso(),
                    }},
                )
                created_ids.append(legacy["id"])
                continue

        journey_id = str(uuid.uuid4())
        journey = {
            "id": journey_id,
            "routal_plan_id": plan_id,
            "routal_plan_label": plan_label,
            "routal_route_id": route_id,
            "routal_project_id": project_id,
            "branch_id": branch_id,
            "source": "routal",
            "client_id": client_id,
            "driver_name": route_label,
            "routal_driver_id": route_id,  # Routal: route.id == stop.driver_id
            "date": plan_date_str,
            "status": "planificada",
            "packages_total": len(route_stops),
            "packages_delivered": 0,
            "packages_failed": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        await db.journeys.insert_one(journey)

        pkg_docs = []
        for svc in route_stops:
            svc_id = svc.get("id") or svc.get("service_id")
            if not svc_id:
                continue
            mapped = map_routal_stop_to_pkg_fields(svc)
            pkg_docs.append({
                "id": str(uuid.uuid4()),
                "journey_id": journey_id,
                "client_id": client_id,
                "branch_id": branch_id,
                "source": "routal",
                "routal_service_id": svc_id,
                "routal_route_id": route_id,
                "tracking_number": mapped["tracking_number"] or svc_id,
                "tracking_url": svc.get("tracking_url"),
                "order_reference_id": mapped["order_reference_id"],
                "recipient_name": mapped["recipient_name"],
                "recipient_phone": mapped["recipient_phone"],
                "address": mapped["address"],
                "status": "pending",
                "created_at": _now_iso(),
            })
        if pkg_docs:
            from utils.pii import encrypt_pkg_pii
            for d in pkg_docs:
                encrypt_pkg_pii(d)
            await db.packages.insert_many(pkg_docs)

        created_ids.append(journey_id)
        logger.info(
            f"[routal] route_journey created plan={plan_id} route={route_id} "
            f"driver={route_label!r} pkgs={len(pkg_docs)}"
        )

    if not created_ids:
        return f"skipped: no real routes (placeholder={skipped_placeholder} no_id={skipped_no_id})"
    if skipped_placeholder:
        logger.info(f"[routal] plan={plan_id} skipped {skipped_placeholder} placeholder route(s)")
    return created_ids[0]


async def _handle_plan_created(db, payload: dict, client_id: str, branch_id: Optional[str] = None) -> str:
    """SEL01: when client has selection_enabled=True, stage the plan instead of
    creating the Journey immediately. The selection worker will later create
    Journeys only for selected drivers. Falls back to direct creation otherwise.

    Multi-route plans → 1 staging entry por route real (skip placeholders).
    Single-driver payloads (webhooks tradicionales) → 1 staging entry como antes.
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

    # Selection-enabled path: stage in routal_daily_plans (one row per real route/driver)
    plan_id = payload.get("plan_id") or payload.get("id")
    if not plan_id:
        return "skipped: no plan_id"

    routes_iter = _normalize_routes_from_payload(payload)
    if not routes_iter:
        return "skipped: no routes/driver in payload"

    plan_date_str = _extract_plan_date(payload)
    try:
        plan_date = datetime.strptime(plan_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        plan_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    plan_label = payload.get("label") or payload.get("plan_label")
    project_id = payload.get("project_id") or payload.get("organization_id")
    staged = 0
    skipped_placeholder = 0
    for route_id, route_label, route_stops, _route_raw in routes_iter:
        if not route_id:
            continue
        if _is_scanner_placeholder(route_label):
            skipped_placeholder += 1
            continue
        # Build per-route payload that _handle_plan_created_direct will use later
        route_payload = {
            "id": plan_id,
            "plan_id": plan_id,
            "label": plan_label,
            "execution_date": payload.get("execution_date"),
            "date": plan_date_str,
            "project_id": project_id,
            # RTV2 (2026-06-11): persist Routal `status` (planning / in_progress /
            # completed / cancelled) so the cohort selector can filter by operational
            # state. plan.created webhooks carry status="planning" — that's expected;
            # the scheduler will force_refresh at cutoff to capture the live state.
            "status": payload.get("status") or payload.get("routal_status"),
            "driver": {"id": route_id, "name": route_label},
            "driver_id": route_id,
            "driver_name": route_label,
            "stops": route_stops,
            "services": route_stops,
        }
        await db.routal_daily_plans.update_one(
            {"client_id": client_id, "driver_id": route_id, "date": plan_date},
            {"$set": {
                "client_id": client_id,
                "branch_id": branch_id,
                "driver_id": route_id,
                "driver_name": route_label,
                "date": plan_date,
                "plan_id_routal": plan_id,
                "routal_route_id": route_id,
                "route_metadata": route_payload,
                "received_at": _now_iso(),
                "processed": False,
            }},
            upsert=True,
        )
        staged += 1
    logger.info(
        f"[selection] plan staged plan={plan_id} client={client_id} "
        f"routes_staged={staged} placeholder={skipped_placeholder}"
    )
    if staged == 0:
        return f"skipped: no real routes (placeholder={skipped_placeholder})"
    return f"staged plan {plan_id} for selection (routes={staged})"


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
