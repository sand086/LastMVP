"""
Analytics & reporting routes: heatmap, quality reports, Power BI, report generation, token consumption.
"""
import io
import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import Response as FastResponse
from starlette.responses import StreamingResponse
from starlette.requests import Request as StarletteRequest
from typing import Optional
from datetime import datetime, timezone, timedelta

import pandas as pd

from dependencies import (
    db, limiter, get_current_user, require_role, apply_assignment_filter, _next_day,
)
from models import ReportRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics"])


# ==================== HEATMAP ====================

@router.get("/analytics/heatmap")
async def get_heatmap_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "address_cp",
    user: dict = Depends(get_current_user),
):
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    j_query = apply_assignment_filter(user, j_query)

    journeys = await db.journeys.find(j_query, {"_id": 0, "id": 1}).to_list(500)
    journey_ids = [j["id"] for j in journeys]
    if not journey_ids:
        return {"group_by": group_by, "total_packages": 0, "areas": []}

    if group_by not in ("address_cp", "address_municipio", "address_estado", "zone"):
        group_by = "address_cp"

    pipeline = [
        {"$match": {"journey_id": {"$in": journey_ids}, group_by: {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": f"${group_by}",
            "total": {"$sum": 1},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
        {"$limit": 100},
    ]
    results = await db.packages.aggregate(pipeline).to_list(100)

    areas = []
    for r in results:
        area_name = r["_id"] or "Sin dato"
        total = r["total"]
        delivered = r["delivered"]
        rate = round(delivered / total * 100, 1) if total > 0 else 0
        areas.append({
            "area": area_name,
            "total": total,
            "delivered": delivered,
            "failed": r["failed"],
            "pending": r["pending"],
            "delivery_rate": rate,
        })

    total_pkgs = sum(a["total"] for a in areas)
    return {"group_by": group_by, "total_packages": total_pkgs, "areas": areas}


@router.post("/analytics/heatmap-export")
async def export_heatmap_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "address_cp",
    user: dict = Depends(get_current_user),
):
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    j_query = apply_assignment_filter(user, j_query)

    journeys_list = await db.journeys.find(j_query, {"_id": 0, "id": 1}).to_list(500)
    journey_ids = [j["id"] for j in journeys_list]

    if not journey_ids:
        df = pd.DataFrame(columns=["Código Postal", "Colonia", "Municipio", "Estado", "Zona", "Total", "Entregados", "Fallidos", "Pendientes", "Tasa %"])
    else:
        pipeline = [
            {"$match": {"journey_id": {"$in": journey_ids}}},
            {"$group": {
                "_id": {
                    "cp": {"$ifNull": ["$address_cp", ""]},
                    "colonia": {"$ifNull": ["$address_colonia", ""]},
                    "municipio": {"$ifNull": ["$address_municipio", ""]},
                    "estado": {"$ifNull": ["$address_estado", ""]},
                    "zone": {"$ifNull": ["$zone", ""]},
                },
                "total": {"$sum": 1},
                "delivered": {"$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
            }},
            {"$sort": {"total": -1}},
        ]
        results = await db.packages.aggregate(pipeline).to_list(5000)
        rows = []
        for r in results:
            gid = r["_id"]
            total = r["total"]
            delivered = r["delivered"]
            rate = round(delivered / total * 100, 1) if total > 0 else 0
            rows.append({
                "Código Postal": gid.get("cp", ""),
                "Colonia": gid.get("colonia", ""),
                "Municipio": gid.get("municipio", ""),
                "Estado": gid.get("estado", ""),
                "Zona": gid.get("zone", ""),
                "Total paquetes": total,
                "Entregados": delivered,
                "Fallidos": r["failed"],
                "Pendientes": r["pending"],
                "Tasa de entrega %": rate,
            })
        df = pd.DataFrame(rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Heatmap")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=heatmap_{group_by}.xlsx"},
    )


# ==================== QUALITY REPORTS ====================

@router.get("/reports/quality")
@limiter.limit("30/minute")
async def get_quality_report(
    request: StarletteRequest,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    provider_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    if not date_from:
        d = datetime.now(timezone.utc)
        date_from = (d - timedelta(days=6)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    journey_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}, "status": {"$in": ["closed", "in_progress", "scheduled"]}}
    journey_query = apply_assignment_filter(user, journey_query)
    if provider_id:
        journey_query["provider_id"] = provider_id

    journeys = await db.journeys.find(journey_query, {"_id": 0}).to_list(1000)
    journey_ids = [j["id"] for j in journeys]

    if not journey_ids:
        return {
            "by_provider": [],
            "by_type": [],
            "worst_packages": [],
            "summary": {"avg_score": 0, "total_evaluated": 0, "complete": 0, "partial": 0, "incomplete": 0},
        }

    packages = await db.packages.find(
        {"journey_id": {"$in": journey_ids}, "evidence_score": {"$ne": None}},
        {"_id": 0},
    ).to_list(50000)

    providers_col = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)}
    providers_data = {}
    for j in journeys:
        pid = j.get("provider_id", "unknown")
        pname = providers_col.get(pid, j.get("provider_name", pid))
        if pid not in providers_data:
            providers_data[pid] = {"name": pname, "routes": 0, "packages": [], "days": set()}
        providers_data[pid]["routes"] += 1
        providers_data[pid]["days"].add(j["date"])

    journey_provider_map = {j["id"]: j.get("provider_id", "unknown") for j in journeys}
    for pkg in packages:
        pid = journey_provider_map.get(pkg.get("journey_id"), "unknown")
        if pid in providers_data:
            providers_data[pid]["packages"].append(pkg)

    by_provider = []
    for pid, pd_data in providers_data.items():
        pkgs = pd_data["packages"]
        delivered_pkgs = [p for p in pkgs if p.get("evidence_type") in ("exitosa", "terceros")]
        scores = [p["evidence_score"] for p in pkgs]
        complete = sum(1 for s in scores if s == 100)
        partial = sum(1 for s in scores if 60 <= s < 100)
        incomplete = sum(1 for s in scores if s < 60)
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        by_provider.append({
            "provider_id": pid,
            "provider_name": pd_data["name"],
            "routes": pd_data["routes"],
            "delivered": len(delivered_pkgs),
            "complete_pct": round(complete / len(scores) * 100, 1) if scores else 0,
            "partial_pct": round(partial / len(scores) * 100, 1) if scores else 0,
            "incomplete_pct": round(incomplete / len(scores) * 100, 1) if scores else 0,
            "avg_score": avg,
        })

    type_map = {}
    for pkg in packages:
        et = pkg.get("evidence_type", "desconocido")
        if et not in type_map:
            type_map[et] = {"count": 0, "scores": [], "perfect": 0}
        type_map[et]["count"] += 1
        type_map[et]["scores"].append(pkg["evidence_score"])
        if pkg["evidence_score"] == 100:
            type_map[et]["perfect"] += 1

    by_type = []
    for et, data in type_map.items():
        by_type.append({
            "type": et,
            "count": data["count"],
            "perfect_pct": round(data["perfect"] / data["count"] * 100, 1) if data["count"] else 0,
            "avg_score": round(sum(data["scores"]) / len(data["scores"]), 1) if data["scores"] else 0,
        })

    worst = sorted(packages, key=lambda p: p.get("evidence_score", 999))[:5]
    worst_packages = []
    for pkg in worst:
        pid = journey_provider_map.get(pkg.get("journey_id"), "unknown")
        pname = providers_data.get(pid, {}).get("name", pid)
        worst_packages.append({
            "tracking_number": pkg.get("tracking_number") or pkg.get("order_reference_id"),
            "provider_name": pname,
            "score": pkg["evidence_score"],
            "missing": pkg.get("evidence_detail", {}).get("missing_items", []),
            "tracking_url": pkg.get("tracking_url"),
        })

    all_scores = [p["evidence_score"] for p in packages]
    summary = {
        "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "total_evaluated": len(all_scores),
        "complete": sum(1 for s in all_scores if s == 100),
        "partial": sum(1 for s in all_scores if 60 <= s < 100),
        "incomplete": sum(1 for s in all_scores if s < 60),
    }

    return {
        "by_provider": by_provider,
        "by_type": by_type,
        "worst_packages": worst_packages,
        "summary": summary,
    }


@router.post("/reports/quality-export")
async def export_quality_report(
    date_from: str = Form(...),
    date_to: str = Form(...),
    provider_id: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    journey_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}, "status": {"$in": ["closed", "in_progress", "scheduled"]}}
    journey_query = apply_assignment_filter(user, journey_query)
    if provider_id:
        journey_query["provider_id"] = provider_id

    journeys = await db.journeys.find(journey_query, {"_id": 0}).to_list(1000)
    journey_map = {j["id"]: j for j in journeys}
    journey_ids = list(journey_map.keys())

    providers_col = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)}

    packages = await db.packages.find(
        {"journey_id": {"$in": journey_ids}, "evidence_score": {"$ne": None, "$lt": 100}},
        {"_id": 0},
    ).to_list(50000)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        rows = []
        for pkg in packages:
            j = journey_map.get(pkg.get("journey_id"), {})
            pid = j.get("provider_id", "")
            rows.append({
                "Fecha": j.get("date", ""),
                "Guía": pkg.get("tracking_number") or pkg.get("order_reference_id", ""),
                "Proveedor": providers_col.get(pid, j.get("provider_name", pid)),
                "Tipo de entrega": pkg.get("evidence_type", ""),
                "Score": pkg.get("evidence_score", 0),
                "Evidencias faltantes": ", ".join(pkg.get("evidence_detail", {}).get("missing_items", [])),
                "Fotos": pkg.get("kosmo_proof_count", 0),
                "Nota del mensajero": pkg.get("kosmo_driver_note", ""),
            })
        pd.DataFrame(rows).to_excel(writer, sheet_name="Calidad de soporte", index=False)

    output.seek(0)
    filename = f"calidad_cubbo_{date_from}_{date_to}.xlsx"
    return FastResponse(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================== CUSTOM REPORT GENERATION ====================

@router.post("/reports/generate")
async def generate_report(data: ReportRequest, user: dict = Depends(get_current_user)):
    j_query = {"date": {"$gte": data.date_from, "$lt": _next_day(data.date_to)}}
    j_query = apply_assignment_filter(user, j_query)
    if data.client_id:
        j_query["client_id"] = data.client_id
    if data.provider_id:
        j_query["provider_id"] = data.provider_id

    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    if not journeys:
        return {"error": "No hay datos para el período seleccionado"}

    journey_ids = [j["id"] for j in journeys]
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    incidents = await db.incidents.find({"journey_id": {"$in": journey_ids}}, {"_id": 0}).to_list(10000)

    report_data = {
        "period": f"{data.date_from} - {data.date_to}",
        "total_journeys": len(journeys),
        "total_packages": sum(j.get("packages_total", 0) for j in journeys),
        "total_delivered": sum(j.get("packages_delivered", 0) for j in journeys),
        "total_failed": sum(j.get("packages_failed", 0) for j in journeys),
        "total_km": sum((j.get("close_data") or {}).get("km_traveled", 0) for j in journeys),
        "total_incidents": len(incidents),
    }
    total_pkg = report_data["total_packages"]
    report_data["delivery_rate"] = round((report_data["total_delivered"] / total_pkg * 100) if total_pkg > 0 else 0, 2)
    report_data["total_retry"] = total_pkg - report_data["total_delivered"] - report_data["total_failed"]

    provider_metrics = {}
    for j in journeys:
        pid = j.get("provider_id", "")
        pname = providers.get(pid, "Sin proveedor")
        if pname not in provider_metrics:
            provider_metrics[pname] = {
                "days_operated": set(), "routes": 0, "packages_loaded": 0,
                "delivered": 0, "failed": 0, "km_total": 0,
            }
        pm = provider_metrics[pname]
        pm["days_operated"].add(j.get("date", ""))
        pm["routes"] += 1
        pm["packages_loaded"] += j.get("packages_total", 0)
        pm["delivered"] += j.get("packages_delivered", 0)
        pm["failed"] += j.get("packages_failed", 0)
        pm["km_total"] += (j.get("close_data") or {}).get("km_traveled", 0)

    for pname in provider_metrics:
        pm = provider_metrics[pname]
        pm["days_operated"] = len(pm["days_operated"])
        pm["retry"] = pm["packages_loaded"] - pm["delivered"] - pm["failed"]
        pm["delivery_rate"] = round((pm["delivered"] / pm["packages_loaded"] * 100) if pm["packages_loaded"] > 0 else 0, 2)

    driver_metrics = {}
    for j in journeys:
        dname = j.get("driver_name", "Sin driver")
        if not dname:
            dname = "Sin driver"
        if dname not in driver_metrics:
            driver_metrics[dname] = {
                "days_operated": set(), "routes": 0, "packages_loaded": 0,
                "delivered": 0, "failed": 0, "km_total": 0,
            }
        dm = driver_metrics[dname]
        dm["days_operated"].add(j.get("date", ""))
        dm["routes"] += 1
        dm["packages_loaded"] += j.get("packages_total", 0)
        dm["delivered"] += j.get("packages_delivered", 0)
        dm["failed"] += j.get("packages_failed", 0)
        dm["km_total"] += (j.get("close_data") or {}).get("km_traveled", 0)

    for dname in driver_metrics:
        dm = driver_metrics[dname]
        dm["days_operated"] = len(dm["days_operated"])
        dm["retry"] = dm["packages_loaded"] - dm["delivered"] - dm["failed"]
        dm["delivery_rate"] = round((dm["delivered"] / dm["packages_loaded"] * 100) if dm["packages_loaded"] > 0 else 0, 2)

    incidents_by_type = {}
    incidents_by_imputability = {"ME / Mensajero": 0, "Cliente (destinatario)": 0, "Por definir": 0}
    for inc in incidents:
        itype = inc.get("incident_type", "Otro")
        incidents_by_type[itype] = incidents_by_type.get(itype, 0) + 1
        imp = inc.get("imputability", "Por definir")
        incidents_by_imputability[imp] = incidents_by_imputability.get(imp, 0) + 1

    report_data["provider_metrics"] = provider_metrics
    report_data["driver_metrics"] = driver_metrics
    report_data["incidents_by_type"] = incidents_by_type
    report_data["incidents_by_imputability"] = incidents_by_imputability

    # Build daily_stats for combo chart (orders per day + avg delivery time)
    daily_map = {}
    for j in journeys:
        d = (j.get("date") or "")[:10]  # Normalize to YYYY-MM-DD
        if not d or len(d) < 10:
            continue
        if d not in daily_map:
            daily_map[d] = {"packages": 0, "delivered": 0, "delivery_times": []}
        daily_map[d]["packages"] += j.get("packages_total", 0)
        daily_map[d]["delivered"] += j.get("packages_delivered", 0)
        # Estimate delivery time from start/close timestamps
        start_data = j.get("start_data") or {}
        close_data = j.get("close_data") or {}
        if start_data.get("started_at") and close_data.get("closed_at"):
            try:
                from datetime import datetime as dt
                t_start = dt.fromisoformat(start_data["started_at"].replace("Z", "+00:00"))
                t_close = dt.fromisoformat(close_data["closed_at"].replace("Z", "+00:00"))
                minutes = (t_close - t_start).total_seconds() / 60
                if 0 < minutes < 1440:  # Reasonable range: 0-24 hours
                    daily_map[d]["delivery_times"].append(minutes)
            except Exception:
                pass

    daily_stats = []
    for d in sorted(daily_map.keys()):
        dm = daily_map[d]
        avg_time = round(sum(dm["delivery_times"]) / len(dm["delivery_times"])) if dm["delivery_times"] else 0
        daily_stats.append({"date": d, "packages": dm["packages"], "delivered": dm["delivered"], "avg_delivery_time": avg_time})
    report_data["daily_stats"] = daily_stats

    report_data["ai_insights"] = ""
    return report_data


@router.post("/reports/generate-excel")
async def generate_report_excel(data: ReportRequest, user: dict = Depends(get_current_user)):
    j_query = {"date": {"$gte": data.date_from, "$lt": _next_day(data.date_to)}}
    j_query = apply_assignment_filter(user, j_query)
    if data.client_id:
        j_query["client_id"] = data.client_id
    if data.provider_id:
        j_query["provider_id"] = data.provider_id

    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    journey_ids = [j["id"] for j in journeys]
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers_map = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    incidents = await db.incidents.find({"journey_id": {"$in": journey_ids}}, {"_id": 0}).to_list(10000)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        routes_data = []
        for j in journeys:
            cd = j.get("close_data") or {}
            sd = j.get("start_data") or {}
            routes_data.append({
                "Fecha": j.get("date", ""),
                "Cliente": clients.get(j.get("client_id"), ""),
                "Proveedor": providers_map.get(j.get("provider_id"), ""),
                "Driver": j.get("driver_name", ""),
                "Tipo Ruta": j.get("route_type", "CDMX / Zona Metro"),
                "Ciudad": j.get("city", ""),
                "Estado": j.get("status", ""),
                "Paquetes Total": j.get("packages_total", 0),
                "Entregados": j.get("packages_delivered", 0),
                "Fallidos": j.get("packages_failed", 0),
                "Reintento": j.get("packages_total", 0) - j.get("packages_delivered", 0) - j.get("packages_failed", 0),
                "Tasa Entrega %": cd.get("delivery_rate", 0),
                "Km": cd.get("km_traveled", 0),
                "Hora Inicio": sd.get("departure_time", ""),
                "Hora Cierre": cd.get("closed_at", ""),
            })
        pd.DataFrame(routes_data).to_excel(writer, sheet_name="Rutas", index=False)

        inc_data = []
        j_map = {j["id"]: j for j in journeys}
        for inc in incidents:
            j = j_map.get(inc.get("journey_id"), {})
            inc_data.append({
                "Fecha Ruta": j.get("date", ""),
                "Proveedor": providers_map.get(j.get("provider_id"), ""),
                "Driver": j.get("driver_name", ""),
                "Tipo": inc.get("incident_type", ""),
                "Severidad": inc.get("severity", ""),
                "Imputabilidad": inc.get("imputability", "Por definir"),
                "Descripción": inc.get("description", ""),
                "Estado": inc.get("status", ""),
            })
        pd.DataFrame(inc_data).to_excel(writer, sheet_name="Incidencias", index=False)

        prov_summary = {}
        for j in journeys:
            pname = providers_map.get(j.get("provider_id"), "")
            if pname not in prov_summary:
                prov_summary[pname] = {"days": set(), "routes": 0, "loaded": 0, "delivered": 0, "failed": 0, "km": 0}
            ps = prov_summary[pname]
            ps["days"].add(j.get("date", ""))
            ps["routes"] += 1
            ps["loaded"] += j.get("packages_total", 0)
            ps["delivered"] += j.get("packages_delivered", 0)
            ps["failed"] += j.get("packages_failed", 0)
            ps["km"] += (j.get("close_data") or {}).get("km_traveled", 0)

        prov_rows = []
        for pname, ps in prov_summary.items():
            prov_rows.append({
                "Proveedor": pname,
                "Días Operados": len(ps["days"]),
                "Total Rutas": ps["routes"],
                "Paquetes Cargados": ps["loaded"],
                "Entregados": ps["delivered"],
                "Fallidos": ps["failed"],
                "Reintentos": ps["loaded"] - ps["delivered"] - ps["failed"],
                "Tasa Entrega %": round((ps["delivered"] / ps["loaded"] * 100) if ps["loaded"] > 0 else 0, 2),
                "Km Totales": ps["km"],
            })
        pd.DataFrame(prov_rows).to_excel(writer, sheet_name="Resumen Proveedores", index=False)

    output.seek(0)
    filename = f"reporte_{data.date_from}_{data.date_to}.xlsx"
    return FastResponse(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================== EXPORT ====================

@router.get("/export/journeys")
async def export_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
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

    journeys = await db.journeys.find(query, {"_id": 0}).to_list(1000)
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    export_data = []
    for j in journeys:
        close_data = j.get("close_data") or {}
        start_data = j.get("start_data") or {}
        export_data.append({
            "Fecha": j.get("date", ""),
            "Cliente": clients.get(j.get("client_id"), ""),
            "Proveedor": providers.get(j.get("provider_id"), ""),
            "Estado": j.get("status", ""),
            "Paquetes Total": j.get("packages_total", 0),
            "Entregados": j.get("packages_delivered", 0),
            "Fallidos": j.get("packages_failed", 0),
            "Km Recorridos": close_data.get("km_traveled", 0),
            "Tasa Entrega (%)": close_data.get("delivery_rate", 0),
            "Hora Inicio": start_data.get("departure_time", ""),
            "Hora Cierre": close_data.get("closed_at", ""),
        })

    df = pd.DataFrame(export_data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return FastResponse(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=rutas_export_{datetime.now().strftime('%Y%m%d')}.xlsx"},
    )


@router.get("/export/incidents")
async def export_incidents(
    journey_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query = {}
    if journey_id:
        query["journey_id"] = journey_id
    if date_from or date_to:
        j_query = {}
        if date_from:
            j_query["date"] = {"$gte": date_from}
        if date_to:
            j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
        journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(500)
        query["journey_id"] = {"$in": [j["id"] for j in journeys]}

    incidents = await db.incidents.find(query, {"_id": 0}).to_list(1000)
    export_data = []
    for inc in incidents:
        export_data.append({
            "Fecha/Hora": inc.get("occurred_at", ""),
            "Tipo": inc.get("incident_type", ""),
            "Descripción": inc.get("description", ""),
            "Severidad": inc.get("severity", ""),
            "Imputabilidad": inc.get("imputability", "Por definir"),
            "No. Guía": inc.get("tracking_number", ""),
            "Estado": inc.get("status", ""),
            "Acción Tomada": inc.get("action_taken", ""),
        })

    df = pd.DataFrame(export_data)
    output = io.StringIO()
    df.to_csv(output, index=False)
    return FastResponse(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=incidencias_export_{datetime.now().strftime('%Y%m%d')}.csv"},
    )


# ==================== TOKEN CONSUMPTION ====================

@router.get("/system/token-consumption")
async def get_token_consumption(user: dict = Depends(require_role(["coordinator", "developer"]))):
    config = await db.system_config.find_one({"key": "token_consumption"}, {"_id": 0})
    exchange_config = await db.system_config.find_one({"key": "exchange_rate"}, {"_id": 0})
    exchange_rate = float((exchange_config or {}).get("value", 20.50))

    if not config:
        pass

    ai_count = await db.packages.count_documents({"evidence_method": "ai"})
    est_tokens = ai_count * 2000
    cost_usd = round(est_tokens / 1000 * 0.01, 2)
    cost_mxn = round(cost_usd * exchange_rate, 2)
    fixed_costs_usd = 25.0

    return {
        "ai_evaluations": ai_count,
        "estimated_tokens": est_tokens,
        "variable_cost_usd": cost_usd,
        "variable_cost_mxn": cost_mxn,
        "fixed_cost_usd": fixed_costs_usd,
        "fixed_cost_mxn": round(fixed_costs_usd * exchange_rate, 2),
        "total_cost_usd": round(cost_usd + fixed_costs_usd, 2),
        "total_cost_mxn": round((cost_usd + fixed_costs_usd) * exchange_rate, 2),
        "exchange_rate": exchange_rate,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@router.put("/system/exchange-rate")
async def update_exchange_rate(
    rate: float,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    if rate <= 0:
        raise HTTPException(status_code=400, detail="Tipo de cambio debe ser positivo")
    await db.system_config.update_one(
        {"key": "exchange_rate"},
        {"$set": {"value": rate, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user["id"]}},
        upsert=True,
    )
    return {"exchange_rate": rate, "message": "Tipo de cambio actualizado"}


# ==================== REPORTING API (Power BI / Tableau) ====================

@router.get("/reports/journeys")
async def report_journeys(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    status: Optional[str] = None,
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

    journeys = await db.journeys.find(query, {"_id": 0}).to_list(10000)
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    # Batch incident counts to avoid N+1
    journey_ids = [j["id"] for j in journeys]
    incident_counts_map = {}
    if journey_ids:
        incident_pipeline = [
            {"$match": {"journey_id": {"$in": journey_ids}}},
            {"$group": {
                "_id": "$journey_id",
                "total": {"$sum": 1},
                "open": {"$sum": {"$cond": [{"$eq": ["$status", "open"]}, 1, 0]}},
            }},
        ]
        async for doc in db.incidents.aggregate(incident_pipeline):
            incident_counts_map[doc["_id"]] = {"total": doc["total"], "open": doc["open"]}

    result = []
    for j in journeys:
        close_data = j.get("close_data") or {}
        start_data = j.get("start_data") or {}
        counts = incident_counts_map.get(j["id"], {"total": 0, "open": 0})
        incidents_count = counts["total"]
        open_incidents = counts["open"]
        result.append({
            "journey_id": j["id"],
            "date": j.get("date"),
            "client_id": j.get("client_id"),
            "client_name": clients.get(j.get("client_id"), ""),
            "provider_id": j.get("provider_id"),
            "provider_name": providers.get(j.get("provider_id"), ""),
            "driver_name": j.get("driver_name", ""),
            "status": j.get("status"),
            "route_type": j.get("route_type", "CDMX / Zona Metro"),
            "city": j.get("city", ""),
            "packages_total": j.get("packages_total", 0),
            "packages_delivered": j.get("packages_delivered", 0),
            "packages_failed": j.get("packages_failed", 0),
            "packages_retry": j.get("packages_retry", 0),
            "delivery_rate": close_data.get("delivery_rate", 0),
            "km_traveled": close_data.get("km_traveled", 0),
            "odometer_start": start_data.get("odometer_start", 0),
            "odometer_end": close_data.get("odometer_end", 0),
            "departure_time": start_data.get("departure_time"),
            "closed_at": close_data.get("closed_at"),
            "fuel_level": start_data.get("fuel_level", ""),
            "incidents_total": incidents_count,
            "incidents_open": open_incidents,
            "created_at": j.get("created_at"),
        })
    return {"data": result, "total": len(result)}


@router.get("/reports/packages")
async def report_packages(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    journey_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)

    if journey_id:
        journey_ids = [journey_id]
    else:
        journeys = await db.journeys.find(j_query, {"id": 1, "_id": 0}).to_list(10000)
        journey_ids = [j["id"] for j in journeys]

    pkg_query = {"journey_id": {"$in": journey_ids}}
    if status:
        pkg_query["status"] = status

    packages = await db.packages.find(pkg_query, {"_id": 0}).to_list(50000)

    journeys_list = await db.journeys.find({"id": {"$in": journey_ids}}, {"_id": 0}).to_list(10000)
    journeys_map = {j["id"]: j for j in journeys_list}

    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    result = []
    for pkg in packages:
        journey = journeys_map.get(pkg.get("journey_id"), {})
        result.append({
            "package_id": pkg.get("id"),
            "journey_id": pkg.get("journey_id"),
            "cosmo_route_id": pkg.get("cosmo_route_id", ""),
            "journey_date": journey.get("date"),
            "tracking_number": pkg.get("tracking_number") or pkg.get("order_reference_id"),
            "tracking_url": pkg.get("tracking_url", ""),
            "recipient_name": pkg.get("recipient_name"),
            "address": pkg.get("address"),
            "zone": pkg.get("zone"),
            "status": pkg.get("status"),
            "cosmo_status": pkg.get("cosmo_status", ""),
            "failure_reason": pkg.get("failure_reason", ""),
            "delivery_attempt": pkg.get("delivery_attempt", 1),
            "evidence_score": pkg.get("evidence_score"),
            "evidence_type": pkg.get("evidence_type"),
            "kosmo_proof_count": pkg.get("kosmo_proof_count", 0),
            "reviewed_by": pkg.get("reviewed_by"),
            "reviewed_at": pkg.get("reviewed_at"),
            "client_name": clients.get(journey.get("client_id"), ""),
            "provider_name": providers.get(journey.get("provider_id"), ""),
            "driver_name": journey.get("driver_name", ""),
        })
    return {"data": result, "total": len(result)}


@router.get("/reports/incidents")
async def report_incidents(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)

    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    journey_ids = [j["id"] for j in journeys]
    journeys_map = {j["id"]: j for j in journeys}

    inc_query = {"journey_id": {"$in": journey_ids}}
    if severity:
        inc_query["severity"] = severity
    if status:
        inc_query["status"] = status
    if incident_type:
        inc_query["incident_type"] = incident_type

    incidents = await db.incidents.find(inc_query, {"_id": 0}).to_list(10000)
    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    result = []
    for inc in incidents:
        journey = journeys_map.get(inc.get("journey_id"), {})
        result.append({
            "incident_id": inc.get("id"),
            "journey_id": inc.get("journey_id"),
            "journey_date": journey.get("date"),
            "occurred_at": inc.get("occurred_at"),
            "incident_type": inc.get("incident_type"),
            "description": inc.get("description"),
            "severity": inc.get("severity"),
            "imputability": inc.get("imputability", "Por definir"),
            "status": inc.get("status"),
            "tracking_number": inc.get("tracking_number", ""),
            "action_taken": inc.get("action_taken", ""),
            "resolved_at": inc.get("resolved_at"),
            "client_name": clients.get(journey.get("client_id"), ""),
            "provider_name": providers.get(journey.get("provider_id"), ""),
            "driver_name": journey.get("driver_name", ""),
            "created_at": inc.get("created_at"),
        })
    return {"data": result, "total": len(result)}


@router.get("/reports/kpis")
async def report_kpis(
    period: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "day",
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    if period and not date_from:
        if period == "current_month":
            date_from = now.replace(day=1).strftime("%Y-%m-%d")
        elif period == "prev_month":
            first_this = now.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            date_from = last_prev.replace(day=1).strftime("%Y-%m-%d")
            date_to = last_prev.strftime("%Y-%m-%d")
        elif period == "7d":
            date_from = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        elif period == "30d":
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        elif period == "90d":
            date_from = (now - timedelta(days=90)).strftime("%Y-%m-%d")

    if not date_from:
        date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not date_to:
        date_to = now.strftime("%Y-%m-%d")

    journeys = await db.journeys.find(
        {"date": {"$gte": date_from, "$lt": _next_day(date_to)}}, {"_id": 0}
    ).to_list(10000)

    clients = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    groups = {}
    for j in journeys:
        if group_by == "provider":
            key = providers.get(j.get("provider_id"), "Sin proveedor")
        elif group_by == "client":
            key = clients.get(j.get("client_id"), "Sin cliente")
        elif group_by == "week":
            d = datetime.strptime(j.get("date", date_from)[:10], "%Y-%m-%d")
            key = f"{d.year}-W{d.isocalendar()[1]:02d}"
        elif group_by == "month":
            key = j.get("date", "")[:7]
        else:
            key = j.get("date", "")[:10]

        if key not in groups:
            groups[key] = {
                "group": key,
                "journeys_count": 0,
                "journeys_completed": 0,
                "packages_total": 0,
                "packages_delivered": 0,
                "packages_failed": 0,
                "km_total": 0,
                "incidents_count": 0,
            }

        close_data = j.get("close_data") or {}
        groups[key]["journeys_count"] += 1
        if j.get("status") == "closed":
            groups[key]["journeys_completed"] += 1
        groups[key]["packages_total"] += j.get("packages_total", 0)
        groups[key]["packages_delivered"] += j.get("packages_delivered", 0)
        groups[key]["packages_failed"] += j.get("packages_failed", 0)
        groups[key]["km_total"] += close_data.get("km_traveled", 0)

    result = []
    for key, data in groups.items():
        data["delivery_rate"] = round(
            (data["packages_delivered"] / data["packages_total"] * 100)
            if data["packages_total"] > 0 else 0, 2,
        )
        result.append(data)

    result.sort(key=lambda x: x["group"])

    total_journeys = sum(d["journeys_count"] for d in result)
    total_packages = sum(d["packages_total"] for d in result)
    total_delivered = sum(d["packages_delivered"] for d in result)

    return {
        "data": result,
        "total": len(result),
        "date_from": date_from,
        "date_to": date_to,
        "has_data": len(result) > 0,
        "summary": {
            "total_journeys": total_journeys,
            "total_packages": total_packages,
            "total_delivered": total_delivered,
            "delivery_rate": round(total_delivered / total_packages * 100, 1) if total_packages > 0 else 0,
        },
    }


# ==================== GEO HEATMAP FOR DASHBOARD ====================

@router.get("/reports/heatmap")
async def get_reports_heatmap(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Heatmap data with CP coordinates for the dashboard map."""
    import re
    from cp_coordinates import CP_COORDS

    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    if client_id:
        j_query["client_id"] = client_id
    if provider_id:
        j_query["provider_id"] = provider_id
    j_query = apply_assignment_filter(user, j_query)

    journeys = await db.journeys.find(j_query, {"_id": 0, "id": 1}).to_list(5000)
    journey_ids = [j["id"] for j in journeys]
    if not journey_ids:
        return []

    pipeline = [
        {"$match": {"journey_id": {"$in": journey_ids}}},
        {"$group": {
            "_id": "$address_cp",
            "total": {"$sum": 1},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$status", "delivered"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$ne": ["$status", "delivered"]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    results = await db.packages.aggregate(pipeline).to_list(500)

    output = []
    for r in results:
        cp = str(r["_id"] or "").strip()
        if not cp:
            continue
        # Try to match CP in dictionary
        coords = CP_COORDS.get(cp)
        if not coords:
            # Try extracting 5-digit CP from field
            match = re.search(r'\b(\d{5})\b', cp)
            if match:
                coords = CP_COORDS.get(match.group(1))
                cp = match.group(1)
        if not coords:
            continue
        total = r["total"]
        delivered = r["delivered"]
        output.append({
            "cp": cp,
            "zone": coords["zone"],
            "lat": coords["lat"],
            "lng": coords["lng"],
            "delivered": delivered,
            "failed": r["failed"],
            "total": total,
            "rate": round(delivered / total, 3) if total > 0 else 0,
        })
    return output




# ==================== ATTEMPTS (NEW) ====================

@router.get("/reports/attempts")
async def report_attempts(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Delivery attempts distribution and retry causes."""
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    if client_id:
        j_query["client_id"] = client_id
    if provider_id:
        j_query["provider_id"] = provider_id
    j_query = apply_assignment_filter(user, j_query)

    journeys = await db.journeys.find(j_query, {"_id": 0, "id": 1}).to_list(5000)
    journey_ids = [j["id"] for j in journeys]
    if not journey_ids:
        return {
            "first_attempt": {"count": 0, "pct": 0},
            "second_attempt": {"count": 0, "pct": 0},
            "third_attempt": {"count": 0, "pct": 0},
            "retry_causes": {},
        }

    # Count packages by attempt_number if exists, else infer
    pkgs = await db.packages.find(
        {"journey_id": {"$in": journey_ids}},
        {"_id": 0, "status": 1, "attempt_number": 1, "retry_cause": 1},
    ).to_list(50000)

    total = len(pkgs)
    first = sum(1 for p in pkgs if p.get("attempt_number", 1) == 1)
    second = sum(1 for p in pkgs if p.get("attempt_number") == 2)
    third = sum(1 for p in pkgs if p.get("attempt_number", 0) >= 3)

    # If no attempt_number data, estimate from delivery/fail ratios
    if second == 0 and third == 0 and total > 0:
        delivered = sum(1 for p in pkgs if p.get("status") == "delivered")
        failed = sum(1 for p in pkgs if p.get("status") == "failed")
        pending = total - delivered - failed
        first = delivered
        second = failed
        third = pending

    pct = lambda n: round(n / total * 100) if total > 0 else 0

    # Retry causes from incidents or package data
    incidents = await db.incidents.find(
        {"journey_id": {"$in": journey_ids}},
        {"_id": 0, "incident_type": 1},
    ).to_list(10000)

    cause_map = {
        "driver_management": 0,
        "client_absent": 0,
        "wrong_address": 0,
        "zone_no_access": 0,
    }
    for inc in incidents:
        itype = (inc.get("incident_type") or "").lower()
        if "driver" in itype or "mensajero" in itype or "tardanza" in itype:
            cause_map["driver_management"] += 1
        elif "ausente" in itype or "destinatario" in itype or "cliente" in itype:
            cause_map["client_absent"] += 1
        elif "dirección" in itype or "address" in itype or "direccion" in itype:
            cause_map["wrong_address"] += 1
        elif "zona" in itype or "acceso" in itype:
            cause_map["zone_no_access"] += 1
        else:
            cause_map["driver_management"] += 1

    cause_total = sum(cause_map.values()) or 1
    retry_causes = {}
    for k, v in cause_map.items():
        retry_causes[k] = {"count": v, "pct": round(v / cause_total * 100)}

    return {
        "first_attempt": {"count": first, "pct": pct(first)},
        "second_attempt": {"count": second, "pct": pct(second)},
        "third_attempt": {"count": third, "pct": pct(third)},
        "retry_causes": retry_causes,
        "total_packages": total,
    }


# ==================== SLA (NEW) ====================

@router.get("/reports/sla")
async def report_sla(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    client_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """SLA vs Target reporting."""
    j_query = {}
    if date_from:
        j_query["date"] = {"$gte": date_from}
    if date_to:
        j_query.setdefault("date", {})["$lt"] = _next_day(date_to)
    if client_id:
        j_query["client_id"] = client_id
    if provider_id:
        j_query["provider_id"] = provider_id
    j_query = apply_assignment_filter(user, j_query)

    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    providers_map = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    total_pkg = sum(j.get("packages_total", 0) for j in journeys)
    total_delivered = sum(j.get("packages_delivered", 0) for j in journeys)
    actual_sla = round(total_delivered / total_pkg * 100, 1) if total_pkg > 0 else 0

    # Load brackets from config
    sla_config = await db.config.find_one({"key": "sla_targets"}, {"_id": 0})
    brackets = [
        {"label": "Mes 1-2", "target": 65, "status": "exceeded"},
        {"label": "Mes 3-4", "target": 75, "status": "active"},
        {"label": "Mes 5+", "target": 90, "status": "pending"},
    ]
    if sla_config and sla_config.get("brackets"):
        brackets = sla_config["brackets"]

    active_target = 75
    for b in brackets:
        if b.get("status") == "active":
            active_target = b["target"]
            break

    # By provider
    prov_groups = {}
    for j in journeys:
        pid = j.get("provider_id", "")
        pname = providers_map.get(pid, "Sin proveedor")
        if pname not in prov_groups:
            prov_groups[pname] = {"delivered": 0, "total": 0, "provider_id": pid}
        prov_groups[pname]["delivered"] += j.get("packages_delivered", 0)
        prov_groups[pname]["total"] += j.get("packages_total", 0)

    by_provider = []
    for pname, pg in prov_groups.items():
        sla = round(pg["delivered"] / pg["total"] * 100, 1) if pg["total"] > 0 else 0
        gap = round(sla - active_target, 1)
        by_provider.append({
            "provider_name": pname,
            "provider_id": pg["provider_id"],
            "sla_actual": sla,
            "target": active_target,
            "gap_pp": gap,
            "status": "above" if sla >= active_target else "below",
        })

    # By driver
    driver_groups = {}
    for j in journeys:
        dname = j.get("driver_name") or "Sin driver"
        if dname not in driver_groups:
            driver_groups[dname] = {"delivered": 0, "total": 0}
        driver_groups[dname]["delivered"] += j.get("packages_delivered", 0)
        driver_groups[dname]["total"] += j.get("packages_total", 0)

    by_driver = []
    for dname, dg in sorted(driver_groups.items(), key=lambda x: x[1]["delivered"] / max(x[1]["total"], 1), reverse=True):
        sla = round(dg["delivered"] / dg["total"] * 100, 1) if dg["total"] > 0 else 0
        by_driver.append({
            "driver_name": dname,
            "sla_actual": sla,
            "target": active_target,
            "gap_pp": round(sla - active_target, 1),
            "status": "above" if sla >= active_target else "below",
        })

    return {
        "consolidated": {"actual": actual_sla, "target": active_target},
        "by_provider": by_provider,
        "by_driver": by_driver[:10],
        "brackets": brackets,
    }


@router.patch("/config/sla-targets")
async def update_sla_targets(
    payload: dict,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Persist SLA brackets configuration."""
    brackets = payload.get("brackets", [])
    if not brackets:
        raise HTTPException(status_code=400, detail="brackets requeridos")

    await db.config.update_one(
        {"key": "sla_targets"},
        {"$set": {"brackets": brackets, "updated_by": user.get("email"), "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "message": "SLA targets actualizados"}


# ==================== GENERATE AI REPORT (UPDATED) ====================

@router.post("/reports/generate-ai")
async def generate_ai_report(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """Generate AI narrative report v2.0 — structured JSON input, 2-block output (cards + markdown)."""
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")
    client_id = payload.get("client_id")
    provider_id = payload.get("provider_id")

    if not date_from or not date_to:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        date_to = now.strftime("%Y-%m-%d")
        date_from = (now - timedelta(days=6)).strftime("%Y-%m-%d")

    j_query = {"date": {"$gte": date_from, "$lt": _next_day(date_to)}}
    if client_id:
        j_query["client_id"] = client_id
    if provider_id:
        j_query["provider_id"] = provider_id
    j_query = apply_assignment_filter(user, j_query)

    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(10000)
    if not journeys:
        return {"narrative": "No hay datos de rutas para el periodo seleccionado.", "cards": [], "period": f"{date_from} — {date_to}"}

    journey_ids = [j["id"] for j in journeys]
    providers_map = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}
    clients_map = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    incidents = await db.incidents.find({"journey_id": {"$in": journey_ids}}, {"_id": 0}).to_list(10000)

    # Build structured data for AI
    total_pkg = sum(j.get("packages_total", 0) for j in journeys)
    total_delivered = sum(j.get("packages_delivered", 0) for j in journeys)
    total_failed = sum(j.get("packages_failed", 0) for j in journeys)
    total_km = sum((j.get("close_data") or {}).get("km_traveled", 0) for j in journeys)
    delivery_rate = round(total_delivered / total_pkg * 100, 1) if total_pkg > 0 else 0

    # Provider breakdown
    prov_data = {}
    for j in journeys:
        pn = providers_map.get(j.get("provider_id", ""), "Desconocido")
        if pn not in prov_data:
            prov_data[pn] = {"routes": 0, "delivered": 0, "failed": 0, "total": 0, "km": 0, "days": set()}
        prov_data[pn]["routes"] += 1
        prov_data[pn]["delivered"] += j.get("packages_delivered", 0)
        prov_data[pn]["failed"] += j.get("packages_failed", 0)
        prov_data[pn]["total"] += j.get("packages_total", 0)
        prov_data[pn]["km"] += (j.get("close_data") or {}).get("km_traveled", 0)
        prov_data[pn]["days"].add(j.get("date", "")[:10])

    prov_summary = []
    for pn, pd_val in prov_data.items():
        r = round(pd_val["delivered"] / pd_val["total"] * 100, 1) if pd_val["total"] > 0 else 0
        prov_summary.append({"name": pn, "routes": pd_val["routes"], "days": len(pd_val["days"]), "delivered": pd_val["delivered"], "failed": pd_val["failed"], "total": pd_val["total"], "rate": r, "km": pd_val["km"]})

    # Incidents breakdown
    inc_types = {}
    inc_severity = {"Alta": 0, "Media": 0, "Baja": 0}
    for inc in incidents:
        t = inc.get("incident_type", "Otro")
        inc_types[t] = inc_types.get(t, 0) + 1
        sev = inc.get("severity", "Media")
        inc_severity[sev] = inc_severity.get(sev, 0) + 1

    # SLA config
    sla_config = None
    try:
        sla_doc = await db.config.find_one({"key": "sla_config"}, {"_id": 0})
        if sla_doc:
            sla_config = sla_doc.get("value", {})
    except Exception:
        pass

    structured_input = {
        "periodo": {"desde": date_from, "hasta": date_to},
        "resumen": {
            "total_rutas": len(journeys),
            "total_paquetes": total_pkg,
            "entregados": total_delivered,
            "fallidos": total_failed,
            "tasa_entrega": delivery_rate,
            "km_totales": total_km,
            "total_incidencias": len(incidents),
        },
        "proveedores": prov_summary,
        "incidencias_por_tipo": inc_types,
        "incidencias_por_severidad": inc_severity,
        "sla_target": sla_config.get("target", 75) if sla_config else 75,
    }

    llm_key = os.environ.get("EMERGENT_LLM_KEY")
    if not llm_key:
        return {"narrative": "Clave de IA no configurada.", "cards": [], "period": f"{date_from} — {date_to}"}

    system_prompt = """Eres el motor de BI de LastMile OS — plataforma de gestion de entregas de ultima milla.
Tu rol es generar un reporte ejecutivo accionable para coordinadores de operaciones logisticas.

REGLAS ANTI-ALUCINACION:
- Solo usa datos del JSON proporcionado. Si un campo no existe, escribe "Sin datos".
- No inventes proveedores, drivers ni cifras.
- Los porcentajes deben coincidir con los datos exactos.
- No menciones tecnologias internas, APIs ni bases de datos.

FORMATO DE RESPUESTA — OBLIGATORIO usar exactamente este formato:

---CARDS---
[
  {"tipo": "alerta|tendencia|logro", "titulo": "Titulo corto (max 60 chars)", "cuerpo": "Detalle accionable en 1-2 lineas (max 140 chars)", "metrica": "Cifra clave", "variacion": "+X.X%|-X.X%|N/A"}
]
---CARDS---

Genera exactamente 3 cards. Tipos:
- alerta: Riesgo operativo o SLA en peligro (color rojo)
- tendencia: Patron emergente importante (color azul)
- logro: Meta cumplida o mejora notable (color verde)

Despues de las cards, genera el reporte en Markdown con estas secciones:
## Resumen Ejecutivo
## Desempeno por Proveedor
## Analisis de Incidencias
## Cumplimiento SLA
## Riesgos y Alertas
## Recomendaciones

Usa **negritas** para cifras clave. Maximo 600 palabras total."""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import json as json_module
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"report-ai-{uuid.uuid4()}",
            system_message=system_prompt,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")

        msg = UserMessage(text=f"Genera el reporte ejecutivo para estos datos:\n\n{json_module.dumps(structured_input, ensure_ascii=False, indent=2)}")
        raw_response = await chat.send_message(msg)

        # Parse cards from response
        cards = []
        narrative = raw_response
        if "---CARDS---" in raw_response:
            parts = raw_response.split("---CARDS---")
            if len(parts) >= 3:
                try:
                    cards_json = parts[1].strip()
                    cards = json_module.loads(cards_json)
                except Exception:
                    cards = []
                narrative = parts[2].strip()
            elif len(parts) == 2:
                narrative = parts[1].strip()

        return {"narrative": narrative, "cards": cards, "period": f"{date_from} — {date_to}"}
    except Exception as e:
        logger.error(f"AI report error: {e}")
        return {"narrative": "Error al generar el reporte con IA. Intenta de nuevo.", "cards": [], "period": f"{date_from} — {date_to}"}




@router.get("/reports/schema")
async def report_schema():
    return {
        "api_version": "1.0",
        "endpoints": [
            {
                "name": "Journeys Report",
                "endpoint": "/api/reports/journeys",
                "method": "GET",
                "description": "Datos de rutas con métricas de entrega",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "client_id", "type": "string", "required": False},
                    {"name": "provider_id", "type": "string", "required": False},
                    {"name": "status", "type": "string", "enum": ["scheduled", "in_progress", "closed"], "required": False},
                ],
                "fields": [
                    "journey_id", "date", "client_id", "client_name", "provider_id", "provider_name",
                    "driver_name", "status", "packages_total", "packages_delivered", "packages_failed",
                    "delivery_rate", "km_traveled", "incidents_total", "incidents_open",
                ],
            },
            {
                "name": "Packages Report",
                "endpoint": "/api/reports/packages",
                "method": "GET",
                "description": "Datos detallados de paquetes",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "status", "type": "string", "enum": ["pending", "delivered", "failed", "returned"], "required": False},
                    {"name": "journey_id", "type": "string", "required": False},
                ],
                "fields": [
                    "package_id", "journey_id", "cosmo_route_id", "journey_date", "tracking_number", "tracking_url",
                    "recipient_name", "address", "zone", "status", "failure_reason", "delivery_attempt",
                    "evidence_score", "evidence_type", "kosmo_proof_count", "kosmo_proof_urls",
                    "reviewed_by", "reviewed_at", "client_name", "provider_name", "driver_name",
                ],
            },
            {
                "name": "Incidents Report",
                "endpoint": "/api/reports/incidents",
                "method": "GET",
                "description": "Datos de incidencias",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "severity", "type": "string", "enum": ["Alto", "Medio", "Bajo"], "required": False},
                    {"name": "status", "type": "string", "enum": ["open", "resolved"], "required": False},
                    {"name": "incident_type", "type": "string", "required": False},
                ],
                "fields": [
                    "incident_id", "journey_id", "journey_date", "occurred_at", "incident_type",
                    "description", "severity", "status", "action_taken", "resolved_at",
                    "client_name", "provider_name", "driver_name",
                ],
            },
            {
                "name": "KPIs Report",
                "endpoint": "/api/reports/kpis",
                "method": "GET",
                "description": "KPIs agregados por período o dimensión. Soporta period shortcut o fechas explícitas.",
                "parameters": [
                    {"name": "period", "type": "string", "enum": ["current_month", "prev_month", "7d", "30d", "90d"], "required": False},
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "group_by", "type": "string", "enum": ["day", "week", "month", "provider", "client"], "default": "day"},
                ],
                "fields": [
                    "group", "journeys_count", "journeys_completed", "packages_total",
                    "packages_delivered", "packages_failed", "km_total", "delivery_rate",
                    "has_data", "summary.total_journeys", "summary.delivery_rate",
                ],
            },
            {
                "name": "Custom Report (AI)",
                "endpoint": "/api/reports/generate",
                "method": "POST",
                "description": "Genera reporte personalizable con insights de IA (Claude)",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "sections", "type": "array", "enum": ["provider_metrics", "driver_metrics", "incidents_breakdown"], "required": False},
                ],
                "fields": [
                    "total_journeys", "total_packages", "total_delivered", "total_failed",
                    "delivery_rate", "provider_metrics", "driver_metrics", "incidents_by_type",
                    "incidents_by_imputability", "ai_insights",
                ],
            },
            {
                "name": "Report Excel Export",
                "endpoint": "/api/reports/generate-excel",
                "method": "POST",
                "description": "Descarga reporte en formato Excel con hojas de rutas, incidencias y resumen por proveedor",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True},
                ],
                "fields": ["Archivo .xlsx con 3 hojas: Rutas, Incidencias, Resumen Proveedores"],
            },
            {
                "name": "Kosmo Tracking Sync",
                "endpoint": "/api/sync/tracking",
                "method": "POST",
                "description": "Sincroniza estatus de paquetes scrapeando páginas públicas de Kosmo.",
                "parameters": [],
                "fields": ["status", "message"],
            },
            {
                "name": "Kosmo Sync Status",
                "endpoint": "/api/sync/status",
                "method": "GET",
                "description": "Timestamp y stats de la última sincronización de Kosmo.",
                "parameters": [],
                "fields": ["last_sync", "total_checked", "updated", "errors"],
            },
            {
                "name": "Quality Report",
                "endpoint": "/api/reports/quality",
                "method": "GET",
                "description": "Reporte de calidad de soporte basado en estándar Cubbo.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "provider_id", "type": "string", "required": False},
                ],
                "fields": ["by_provider[]", "by_type[]", "worst_packages[]", "summary.avg_score", "summary.complete", "summary.partial", "summary.incomplete"],
            },
            {
                "name": "Quality Excel Export (Cubbo)",
                "endpoint": "/api/reports/quality-export",
                "method": "POST",
                "description": "Exporta Excel para Cubbo con paquetes que tienen score < 100.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "provider_id", "type": "string", "required": False},
                ],
                "fields": ["Archivo .xlsx: fecha, guía, proveedor, tipo entrega, score, evidencias faltantes"],
            },
            {
                "name": "Package Search",
                "endpoint": "/api/packages/search",
                "method": "GET",
                "description": "Busca paquetes por guía o referencia.",
                "parameters": [{"name": "q", "type": "string", "required": True}],
                "fields": ["id", "tracking_number", "order_reference_id", "recipient_name", "status", "journey_id", "journey_date", "provider_name"],
            },
            {
                "name": "Cleanup Routes & Packages",
                "endpoint": "/api/cleanup/routes-packages",
                "method": "POST",
                "description": "Elimina todas las rutas, paquetes e incidencias. Solo coordinator/developer.",
                "parameters": [],
                "fields": ["deleted.journeys", "deleted.packages", "deleted.incidents"],
            },
            {
                "name": "Resolve All Incidents",
                "endpoint": "/api/incidents/journey/{journey_id}/resolve-all",
                "method": "PUT",
                "description": "Marca todas las incidencias abiertas de una ruta como resueltas en lote.",
                "parameters": [{"name": "journey_id", "type": "string", "required": True}],
                "fields": ["resolved_count", "message"],
            },
            {
                "name": "Review Package",
                "endpoint": "/api/packages/{package_id}/review",
                "method": "PUT",
                "description": "Marca un paquete como revisado por el usuario actual.",
                "parameters": [{"name": "package_id", "type": "string", "required": True}],
                "fields": ["reviewed_by", "reviewed_at", "message"],
            },
            {
                "name": "Bulk Package Status Update",
                "endpoint": "/api/journeys/{journey_id}/packages/bulk-status",
                "method": "POST",
                "description": "Actualiza el estado de múltiples paquetes en lote.",
                "parameters": [
                    {"name": "journey_id", "type": "string", "required": True},
                    {"name": "package_ids", "type": "array", "required": True},
                    {"name": "new_status", "type": "string", "enum": ["pending", "delivered", "failed", "returned"], "required": True},
                ],
                "fields": ["updated", "new_status", "journey_totals"],
            },
            {
                "name": "Quality Criteria Config",
                "endpoint": "/api/quality/criteria",
                "method": "GET/PUT",
                "description": "Lee o actualiza los criterios de evaluación de calidad de evidencias. Solo coordinator/developer.",
                "parameters": [],
                "fields": ["version", "third_party_keywords", "delivery_types", "ai_evaluation"],
            },
            {
                "name": "WebSocket Dashboard",
                "endpoint": "/ws/dashboard",
                "method": "WS",
                "description": "Conexión WebSocket para actualizaciones en tiempo real del dashboard. Eventos: stats_update, journey_update, incident_update, sync_update.",
                "parameters": [],
                "fields": ["type", "data", "timestamp"],
            },
            # ---- NEW v2 ENDPOINTS ----
            {
                "name": "Quality Summary (per Journey)",
                "endpoint": "/api/journeys/{journey_id}/quality-summary",
                "method": "GET",
                "description": "Resumen de calidad IA para una ruta: KPIs, distribución, errores top, sugerencia de acción.",
                "parameters": [{"name": "journey_id", "type": "string", "required": True}],
                "fields": ["score_avg", "score_target", "distribution", "evaluated_ia", "confidence_avg", "reviewed_count", "error_summary[]", "action_suggestion"],
            },
            {
                "name": "Packages Quality Detail",
                "endpoint": "/api/journeys/{journey_id}/packages-quality",
                "method": "GET",
                "description": "Detalle de calidad por paquete con ia_errors, ia_confidence, attempt_number, review_status.",
                "parameters": [
                    {"name": "journey_id", "type": "string", "required": True},
                    {"name": "alerts_only", "type": "boolean", "required": False},
                    {"name": "page", "type": "integer", "required": False, "default": "1"},
                    {"name": "page_size", "type": "integer", "required": False, "default": "25"},
                ],
                "fields": ["packages[]", "total", "page", "pages"],
            },
            {
                "name": "Training Samples",
                "endpoint": "/api/training/samples",
                "method": "POST",
                "description": "Guarda muestra de entrenamiento supervisado para mejorar el modelo IA.",
                "parameters": [
                    {"name": "journey_id", "type": "string", "required": True},
                    {"name": "guide", "type": "string", "required": True},
                    {"name": "human_label", "type": "string", "enum": ["correct", "incorrect"], "required": True},
                    {"name": "corrected_errors", "type": "array", "required": False},
                ],
                "fields": ["id", "total_samples", "review_status"],
            },
            {
                "name": "Package Review Update",
                "endpoint": "/api/journeys/{journey_id}/packages/{guide}/review",
                "method": "PATCH",
                "description": "Aprueba o rechaza la evaluación de un paquete.",
                "parameters": [
                    {"name": "journey_id", "type": "string", "required": True},
                    {"name": "guide", "type": "string", "required": True},
                    {"name": "review_status", "type": "string", "enum": ["approved", "rejected"], "required": True},
                ],
                "fields": ["success", "review_status"],
            },
            {
                "name": "Delivery Attempts Report",
                "endpoint": "/api/reports/attempts",
                "method": "GET",
                "description": "Distribución de intentos de entrega (1º, 2º, 3er intento) y causas de reintento.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                ],
                "fields": ["attempts_distribution", "retry_causes", "total_packages"],
            },
            {
                "name": "SLA Report",
                "endpoint": "/api/reports/sla",
                "method": "GET",
                "description": "Datos de SLA vs targets por proveedor y driver.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                ],
                "fields": ["sla_consolidated", "by_provider", "by_driver", "brackets"],
            },
            {
                "name": "Heatmap Data",
                "endpoint": "/api/reports/heatmap",
                "method": "GET",
                "description": "Datos geográficos de entregas por código postal para mapas de calor.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                ],
                "fields": ["points[]", "total_packages", "zones_count"],
            },
            {
                "name": "AI Report Generation",
                "endpoint": "/api/reports/generate-ai",
                "method": "POST",
                "description": "Genera reporte narrativo con insights de IA usando Claude Sonnet.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": True},
                    {"name": "sections", "type": "array", "required": False},
                ],
                "fields": ["narrative", "sections", "generated_at"],
            },
            {
                "name": "Lumi AI Chat",
                "endpoint": "/api/chat/lumi",
                "method": "POST",
                "description": "Chatbot IA operativo con contexto de entregas, incidencias y rendimiento.",
                "parameters": [
                    {"name": "message", "type": "string", "required": True},
                    {"name": "session_id", "type": "string", "required": False},
                ],
                "fields": ["response", "session_id"],
            },
            {
                "name": "Evaluate IA (Non-Blocking)",
                "endpoint": "/api/journeys/{journey_id}/evaluate-ia",
                "method": "POST",
                "description": "Lanza evaluación IA de evidencias en segundo plano. No bloquea operaciones (login, dashboard). Procesa paquetes en lotes de 3 con semáforo.",
                "parameters": [
                    {"name": "journey_id", "type": "string", "required": True},
                ],
                "fields": ["status", "message", "current_stats"],
            },
            {
                "name": "Admin IA Consumption Summary",
                "endpoint": "/api/admin/ia-consumption/summary",
                "method": "GET",
                "description": "Resumen de consumo de tokens LLM (Claude Sonnet) por periodo.",
                "parameters": [
                    {"name": "period", "type": "string", "enum": ["current_month", "prev_month", "7d"], "required": False},
                ],
                "fields": ["total_tokens", "total_cost_usd", "total_cost_mxn", "by_endpoint", "by_model"],
            },
            {
                "name": "Admin Routes Report",
                "endpoint": "/api/admin/routes-report",
                "method": "GET",
                "description": "Reporte detallado de rutas para administradores con export a Excel.",
                "parameters": [
                    {"name": "date_from", "type": "string", "format": "YYYY-MM-DD", "required": False},
                    {"name": "date_to", "type": "string", "format": "YYYY-MM-DD", "required": False},
                ],
                "fields": ["routes[]", "total", "summary"],
            },
            {
                "name": "Update User",
                "endpoint": "/api/users/{user_id}",
                "method": "PUT",
                "description": "Actualiza datos de un usuario. Solo coordinator/developer.",
                "parameters": [
                    {"name": "user_id", "type": "string", "required": True},
                    {"name": "name", "type": "string", "required": False},
                    {"name": "phone", "type": "string", "required": False},
                    {"name": "status", "type": "string", "required": False},
                ],
                "fields": ["message"],
            },
            {
                "name": "Quality Settings (Master)",
                "endpoint": "/api/config/quality-settings",
                "method": "GET/PATCH",
                "description": "Lee todas las configuraciones de calidad o actualiza una sección (kpi_targets, sla_brackets, ia_config, error_catalog, etc.).",
                "parameters": [
                    {"name": "section", "type": "string", "required": True, "enum": ["kpi_targets", "sla_brackets", "sla_targets_by_rubro", "penalty_rules", "strike_policy", "ia_config", "error_catalog"]},
                    {"name": "value", "type": "object", "required": True},
                ],
                "fields": ["kpi_targets", "sla_brackets", "sla_targets_by_rubro", "penalty_rules", "strike_policy", "ia_config", "error_catalog", "_meta"],
            },
        ],
        "webhooks": {
            "description": "Sistema Plug&Play de webhooks para integrar LastMile OS con sistemas externos",
            "endpoints": [
                {"method": "GET",  "path": "/api/webhooks/events", "description": "Lista eventos disponibles"},
                {"method": "GET",  "path": "/api/webhooks", "description": "Lista webhooks configurados"},
                {"method": "POST", "path": "/api/webhooks", "description": "Crea nuevo webhook"},
                {"method": "PUT",  "path": "/api/webhooks/{id}", "description": "Actualiza webhook"},
                {"method": "DELETE", "path": "/api/webhooks/{id}", "description": "Elimina webhook"},
                {"method": "POST", "path": "/api/webhooks/{id}/test", "description": "Envia payload de prueba"},
                {"method": "GET",  "path": "/api/webhooks/{id}/deliveries", "description": "Log de entregas"},
                {"method": "POST", "path": "/api/webhooks/{id}/regenerate-secret", "description": "Regenera HMAC secret"},
            ],
            "events": [
                "journey.started", "journey.closed", "incident.created",
                "incident.resolved", "package.status_changed",
                "layout.uploaded", "quality.evaluated",
            ],
            "delivery": {
                "method": "POST",
                "content_type": "application/json",
                "headers": [
                    "X-Webhook-Event: nombre del evento",
                    "X-Webhook-Signature: sha256={hmac_hex}",
                    "X-Webhook-Id: id del webhook",
                ],
                "retry_policy": "3 intentos con backoff: 5s, 30s, 120s",
                "timeout": "10 segundos por intento",
            },
            "payload_example": {
                "event": "journey.closed",
                "timestamp": "2026-03-31T20:00:00Z",
                "data": {
                    "journey_id": "uuid",
                    "client_id": "CUBBO",
                    "provider_id": "ME",
                    "close_data": {"delivery_rate": 95.2, "km_traveled": 142},
                },
            },
        },
        "authentication": {
            "type": "Bearer Token",
            "header": "Authorization",
            "format": "Bearer <token>",
            "obtain_token": "POST /api/auth/login with {email, password}",
            "expiry": "8 horas (configurable via JWT_EXPIRY_HOURS)",
            "auto_logout": "Frontend redirige a /login con reason=expired al recibir 401",
        },
        "security": {
            "cors": "Restringido a dominios autorizados (configurable via CORS_ORIGINS)",
            "hsts": "Strict-Transport-Security: max-age=31536000; includeSubDomains",
            "headers": [
                "X-Frame-Options: DENY",
                "X-Content-Type-Options: nosniff",
                "X-XSS-Protection: 1; mode=block",
                "Referrer-Policy: strict-origin-when-cross-origin",
                "Cache-Control: no-store (en rutas /api/)",
            ],
            "jwt_secret": "Configurado via variable de entorno JWT_SECRET",
        },
    }
