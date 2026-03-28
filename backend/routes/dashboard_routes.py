"""
Dashboard routes: stats, incidents breakdown, provider comparison, search.
"""
from fastapi import APIRouter, Depends
from typing import Optional
from datetime import datetime, timezone

from dependencies import db, get_current_user, apply_assignment_filter, _next_day

router = APIRouter(tags=["Dashboard"])


@router.get("/packages/search")
async def search_packages(q: str, user: dict = Depends(get_current_user)):
    if not q or len(q) < 2:
        return []
    query = {
        "$or": [
            {"order_reference_id": {"$regex": q, "$options": "i"}},
            {"tracking_number": {"$regex": q, "$options": "i"}},
        ]
    }
    packages = await db.packages.find(query, {"_id": 0}).to_list(20)
    journey_ids = list({p.get("journey_id") for p in packages if p.get("journey_id")})
    journeys = await db.journeys.find(
        {"id": {"$in": journey_ids}},
        {"_id": 0, "id": 1, "date": 1, "provider_name": 1, "client_name": 1},
    ).to_list(100)
    j_map = {j["id"]: j for j in journeys}
    for p in packages:
        j = j_map.get(p.get("journey_id"), {})
        p["journey_date"] = j.get("date")
        p["provider_name"] = j.get("provider_name")
        p["client_name"] = j.get("client_name")
    return packages


@router.get("/dashboard/stats")
async def get_dashboard_stats(
    date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if date_from and date_to:
        base_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}}
    elif date:
        base_query = {"date": {"$gte": date, "$lt": _next_day(date)}}
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        base_query = {"date": {"$gte": today, "$lt": _next_day(today)}}

    base_query = apply_assignment_filter(user, base_query)

    active_q = {**base_query, "status": "in_progress"}
    active_journeys = await db.journeys.count_documents(active_q)
    closed_q = {**base_query, "status": "closed"}
    closed_journeys = await db.journeys.count_documents(closed_q)
    total_journeys = await db.journeys.count_documents(base_query)

    journeys_today = await db.journeys.find(base_query, {"_id": 0}).to_list(500)
    journey_ids = [j["id"] for j in journeys_today]

    total_packages = await db.packages.count_documents({"journey_id": {"$in": journey_ids}})
    delivered_packages = await db.packages.count_documents({"journey_id": {"$in": journey_ids}, "status": "delivered"})

    open_incidents = await db.incidents.count_documents({
        "journey_id": {"$in": journey_ids}, "status": "open"
    })

    delivery_rate = (delivered_packages / total_packages * 100) if total_packages > 0 else 0

    total_km = 0
    for j in journeys_today:
        close_data = j.get("close_data", {})
        if close_data:
            total_km += close_data.get("km_traveled", 0)

    closed_journey_ids = [j["id"] for j in journeys_today if j.get("status") == "closed"]
    avg_evidence_score = 0
    packages_incomplete = 0
    if closed_journey_ids:
        scored_pkgs = await db.packages.find(
            {"journey_id": {"$in": closed_journey_ids}, "evidence_score": {"$ne": None}},
            {"_id": 0, "evidence_score": 1},
        ).to_list(10000)
        if scored_pkgs:
            scores = [p["evidence_score"] for p in scored_pkgs]
            avg_evidence_score = round(sum(scores) / len(scores), 1)
            packages_incomplete = sum(1 for s in scores if s < 100)

    return {
        "date": date,
        "active_journeys": active_journeys,
        "closed_journeys": closed_journeys,
        "total_journeys": total_journeys,
        "total_packages": total_packages,
        "delivered_packages": delivered_packages,
        "delivery_rate": round(delivery_rate, 2),
        "open_incidents": open_incidents,
        "total_km": total_km,
        "avg_evidence_score": avg_evidence_score,
        "packages_incomplete_support": packages_incomplete,
    }


@router.get("/dashboard/incidents-breakdown")
async def get_incidents_breakdown(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if not date_from:
        date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from
    j_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}}
    j_query = apply_assignment_filter(user, j_query)
    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(500)
    journey_ids = [j["id"] for j in journeys]
    incidents = await db.incidents.find(
        {"journey_id": {"$in": journey_ids}}, {"_id": 0}
    ).to_list(1000)
    breakdown = {}
    for inc in incidents:
        inc_type = inc.get("incident_type", "Otro")
        breakdown[inc_type] = breakdown.get(inc_type, 0) + 1
    return breakdown


@router.get("/dashboard/provider-comparison")
async def get_provider_comparison(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if not date_from:
        date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not date_to:
        date_to = date_from

    providers = await db.providers.find({}, {"_id": 0}).to_list(100)
    assigned_providers = user.get("assigned_providers", [])
    if assigned_providers:
        providers = [p for p in providers if p["id"] in assigned_providers]
    assigned_clients = user.get("assigned_clients", [])

    comparison = []
    for provider in providers:
        j_query = {
            "provider_id": provider["id"],
            "date": {"$gte": date_from, "$lt": _next_day(date_to)},
        }
        if assigned_clients:
            j_query["client_id"] = {"$in": assigned_clients}
        journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(500)
        if not journeys:
            continue
        total_journeys = len(journeys)
        total_delivered = sum(j.get("packages_delivered", 0) for j in journeys)
        total_packages = sum(j.get("packages_total", 0) for j in journeys)
        total_failed = sum(j.get("packages_failed", 0) for j in journeys)
        total_km = sum((j.get("close_data") or {}).get("km_traveled", 0) for j in journeys)
        journey_ids = [j["id"] for j in journeys]
        incidents_count = await db.incidents.count_documents({"journey_id": {"$in": journey_ids}})
        avg_delivery_rate = (total_delivered / total_packages * 100) if total_packages > 0 else 0
        # Visit rate: delivered + failed with evidence of visit
        visited = total_delivered + total_failed
        visit_rate = round(visited / total_packages * 100, 2) if total_packages > 0 else 0
        comparison.append({
            "provider_id": provider["id"],
            "provider_name": provider["name"],
            "journeys_count": total_journeys,
            "avg_delivery_rate": round(avg_delivery_rate, 2),
            "visit_rate": visit_rate,
            "total_incidents": incidents_count,
            "total_km": total_km,
        })
    return comparison
