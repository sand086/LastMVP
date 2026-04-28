"""Routal legacy plan→route journey migration (option 1b).

Legacy model: 1 LastMile journey per Routal plan with all stops merged.
New model: 1 LastMile journey per Routal route with stops filtered by route_id.

This endpoint splits legacy plan-based journeys into N route-based journeys by
re-hydrating each plan from the Routal API and reassigning packages to the
correct (new) journey based on stop.route_id == route.id.

Idempotent: legacy journeys already migrated have routal_route_id set and are skipped.
Safe: original legacy journey is marked migrated_at + migrated_to_journeys[]
(NOT deleted) so AI evaluations and incidents stay traceable.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from dependencies import get_current_user, db
from services.integration_service import IntegrationService
from workers.routal_event_processor import (
    _extract_plan_date, _is_scanner_placeholder, map_routal_stop_to_pkg_fields,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/integrations/routal/migrate-legacy-journeys/{client_id}")
async def migrate_legacy_journeys(
    client_id: str,
    days_back: int = Query(30, ge=1, le=180, description="Días hacia atrás a inspeccionar"),
    dry_run: bool = Query(True, description="Si true, no aplica cambios — solo reporta qué se haría"),
    branch_id: Optional[str] = Query(None, description="Si se da, limita la migración a esa sucursal"),
    user: dict = Depends(get_current_user),
):
    """Migra journeys Routal legacy (creadas con modelo plan=journey) al modelo route=journey.

    Para cada legacy journey con `routal_plan_id` y SIN `routal_route_id`:
      1. Hidrata el plan vía Routal API (`GET /v2/plan/{id}`).
      2. Itera `plan.routes[]` y arma N nuevas journeys (1 por route real).
      3. Reasigna cada package a la journey de su route correspondiente
         (busqueda por package.routal_service_id ∈ stops de esa route).
      4. Marca journey legacy con migrated_at + migrated_to_journeys[].
      5. Skip routes con label 'LastmileScanSessions*' y stops sin route_id.

    Returns dict con counts: scanned, migrated, packages_moved, skipped, errors.
    """
    if user.get("role") not in {"developer", "coordinator"}:
        raise HTTPException(status_code=403, detail="Solo developer/coordinator pueden migrar")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    # Find candidate legacy journeys (excluding already migrated)
    query = {
        "client_id": client_id,
        "source": "routal",
        "routal_plan_id": {"$exists": True, "$ne": None},
        "routal_route_id": {"$exists": False},
        "migrated_to_journeys": {"$exists": False},
        "created_at": {"$gte": cutoff.isoformat()},
    }
    if branch_id:
        query["branch_id"] = branch_id

    legacy_journeys = [j async for j in db.journeys.find(query, {"_id": 0}).limit(500)]
    if not legacy_journeys:
        return {
            "client_id": client_id,
            "dry_run": dry_run,
            "scanned": 0,
            "migrated": 0,
            "skipped_already_migrated": 0,
            "skipped_no_real_routes": 0,
            "errors": 0,
            "details": [],
        }

    # Group by routal_plan_id (one plan_id may map to multiple legacy journeys
    # only in edge cases — usually 1 legacy journey per plan_id)
    by_plan: dict = {}
    for j in legacy_journeys:
        by_plan.setdefault(j["routal_plan_id"], []).append(j)

    svc = IntegrationService(db)
    rc = await svc.get_routal_client(client_id, branch_id=branch_id)
    if not rc:
        raise HTTPException(
            status_code=400,
            detail="La integración Routal no está activa o faltan credenciales para este cliente/sucursal.",
        )

    migrated = 0
    skipped_no_routes = 0
    errors = 0
    packages_moved = 0
    details: list = []

    try:
        for plan_id, journeys_for_plan in by_plan.items():
            try:
                detail = await rc.get_plan(plan_id)
            except Exception as e:
                errors += 1
                details.append({"plan_id": plan_id, "status": "error", "error": str(e)[:200]})
                continue

            stops = detail.get("stops") or []
            routes = detail.get("routes") or []
            real_routes = [
                r for r in routes
                if r.get("id") and not _is_scanner_placeholder(r.get("label"))
            ]
            if not real_routes:
                skipped_no_routes += 1
                details.append({
                    "plan_id": plan_id,
                    "status": "skipped",
                    "reason": "no_real_routes",
                    "routes_total": len(routes),
                })
                continue

            plan_label = detail.get("label")
            project_id = detail.get("project_id") or detail.get("organization_id")
            plan_date_str = _extract_plan_date({"execution_date": detail.get("execution_date")})

            # For the legacy journey(s) under this plan, we'll create N new journeys.
            # Packages are matched to new journey by stop.route_id (via routal_service_id).
            stop_to_route = {s.get("id"): s.get("route_id") for s in stops if s.get("id")}

            for legacy_j in journeys_for_plan:
                legacy_id = legacy_j["id"]
                legacy_branch = legacy_j.get("branch_id")
                packages_in_legacy = [
                    p async for p in db.packages.find(
                        {"journey_id": legacy_id},
                        {"_id": 0},
                    )
                ]

                # Build new journeys + plan for package moves
                new_journeys: list = []
                pkg_moves: list = []  # (pkg_id, new_journey_id)
                for r in real_routes:
                    rid = r.get("id")
                    rlabel = r.get("label") or "Sin asignar"
                    route_stops = [s for s in stops if s.get("route_id") == rid]
                    # Find packages in legacy journey whose stop belongs to this route
                    pkgs_for_route = [
                        p for p in packages_in_legacy
                        if p.get("routal_service_id") and stop_to_route.get(p["routal_service_id"]) == rid
                    ]
                    # Skip empty routes for multi-route plans (administrative shells)
                    if not pkgs_for_route and len(real_routes) > 1:
                        continue

                    new_journey_doc = {
                        "id": str(uuid.uuid4()),
                        "routal_plan_id": plan_id,
                        "routal_plan_label": plan_label,
                        "routal_route_id": rid,
                        "routal_project_id": project_id,
                        "branch_id": legacy_branch,
                        "source": "routal",
                        "client_id": client_id,
                        "driver_name": rlabel,
                        "routal_driver_id": rid,
                        "date": plan_date_str,
                        "status": legacy_j.get("status", "planificada"),
                        "packages_total": len(pkgs_for_route),
                        "packages_delivered": sum(1 for p in pkgs_for_route if p.get("status") == "delivered"),
                        "packages_failed": sum(1 for p in pkgs_for_route if p.get("status") == "failed"),
                        "created_at": legacy_j.get("created_at") or _now_iso(),
                        "updated_at": _now_iso(),
                        "migrated_from": legacy_id,
                        "migrated_at": _now_iso(),
                    }
                    new_journeys.append((new_journey_doc, pkgs_for_route, route_stops, rid, rlabel))
                    for p in pkgs_for_route:
                        pkg_moves.append((p["id"], new_journey_doc["id"]))

                if not new_journeys:
                    skipped_no_routes += 1
                    details.append({
                        "plan_id": plan_id,
                        "legacy_journey_id": legacy_id,
                        "status": "skipped",
                        "reason": "no_packages_match_any_route",
                    })
                    continue

                if dry_run:
                    details.append({
                        "plan_id": plan_id,
                        "legacy_journey_id": legacy_id,
                        "status": "would_split",
                        "new_journeys": [
                            {"route_id": rid, "driver": rlabel, "packages": len(p)}
                            for (_doc, p, _stops, rid, rlabel) in new_journeys
                        ],
                    })
                    continue

                # APPLY: insert new journeys, move packages, mark legacy migrated
                inserted_ids = []
                for (doc, pkgs, route_stops, rid, _rlabel) in new_journeys:
                    await db.journeys.insert_one(doc)
                    inserted_ids.append(doc["id"])

                    if pkgs:
                        pkg_ids = [p["id"] for p in pkgs]
                        await db.packages.update_many(
                            {"id": {"$in": pkg_ids}},
                            {"$set": {
                                "journey_id": doc["id"],
                                "routal_route_id": rid,
                                "updated_at": _now_iso(),
                            }},
                        )
                        # Also propagate to incidents
                        await db.incidents.update_many(
                            {"package_id": {"$in": pkg_ids}, "journey_id": legacy_id},
                            {"$set": {"journey_id": doc["id"]}},
                        )
                        packages_moved += len(pkgs)

                # Handle leftover packages (stops without route_id or unknown) — keep in legacy
                migrated_pkg_ids = [pid for (pid, _) in pkg_moves]
                leftover_count = await db.packages.count_documents({
                    "journey_id": legacy_id,
                    "id": {"$nin": migrated_pkg_ids},
                })

                # Mark legacy journey
                await db.journeys.update_one(
                    {"id": legacy_id},
                    {"$set": {
                        "migrated_at": _now_iso(),
                        "migrated_to_journeys": inserted_ids,
                        "leftover_packages_count": leftover_count,
                        "status": legacy_j.get("status", "planificada"),
                        "_legacy_plan_journey": True,
                        "updated_at": _now_iso(),
                    }},
                )

                migrated += 1
                details.append({
                    "plan_id": plan_id,
                    "legacy_journey_id": legacy_id,
                    "status": "migrated",
                    "new_journeys": inserted_ids,
                    "packages_moved": len(migrated_pkg_ids),
                    "leftover_packages": leftover_count,
                })
                logger.info(
                    f"[migrate] plan={plan_id} legacy={legacy_id} → "
                    f"{len(inserted_ids)} new journeys, {len(migrated_pkg_ids)} pkgs moved, "
                    f"{leftover_count} leftover"
                )
    finally:
        try:
            await rc.aclose()
        except Exception:
            pass

    return {
        "client_id": client_id,
        "branch_id": branch_id,
        "days_back": days_back,
        "dry_run": dry_run,
        "scanned": len(legacy_journeys),
        "plans_inspected": len(by_plan),
        "migrated": migrated,
        "skipped_no_real_routes": skipped_no_routes,
        "errors": errors,
        "packages_moved": packages_moved,
        "details": details[:200],  # cap details to avoid huge payloads
    }
