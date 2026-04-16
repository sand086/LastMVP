"""
Lumi AI Chatbot — LastMile OS
POST /api/chat/lumi
GET /api/lumi/active-context
GET /api/lumi/tools/journey-lookup
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from dependencies import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Lumi"])


class LumiChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    period: str = "7d"
    client_id: Optional[str] = None
    provider_id: Optional[str] = None
    journey_id: Optional[str] = None


def _resolve_period(period: str):
    now = datetime.now(timezone.utc)

    def fmt(d):
        return d.strftime("%Y-%m-%d")

    if period == "15d":
        return fmt(now - timedelta(days=14)), fmt(now), "Ultimos 15 dias"
    elif period == "current_month":
        return fmt(now.replace(day=1)), fmt(now), "Mes actual"
    elif period == "prev_month":
        first = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
        last = now.replace(day=1) - timedelta(days=1)
        return fmt(first), fmt(last), "Mes anterior"
    elif period == "prev_week":
        start = now - timedelta(days=now.weekday() + 7)
        end = start + timedelta(days=6)
        return fmt(start), fmt(end), "Semana anterior"
    else:
        return fmt(now - timedelta(days=6)), fmt(now), "Ultimos 7 dias"


async def _build_journey_context(journey_id: str) -> dict:
    """Build rich context for a specific journey, reading directly from DB."""
    query = {"id": journey_id} if len(journey_id) > 20 else {
        "$or": [{"id": journey_id}, {"order_id": journey_id}, {"cosmo_route_id": journey_id}]
    }
    journey = await db.journeys.find_one(query, {"_id": 0})
    if not journey:
        return None

    j_id = journey["id"]
    # Get provider/client names
    provider = await db.providers.find_one({"id": journey.get("provider_id")}, {"_id": 0, "name": 1})
    client = await db.clients.find_one({"id": journey.get("client_id")}, {"_id": 0, "name": 1})

    # Get packages summary
    packages = await db.packages.find(
        {"journey_id": j_id},
        {"_id": 0, "status": 1, "evidence_score": 1, "kosmo_status_raw": 1}
    ).to_list(500)
    total = len(packages)
    delivered = sum(1 for p in packages if p.get("status") == "delivered")
    failed = sum(1 for p in packages if p.get("status") == "failed")
    pending = total - delivered - failed
    pct = round(delivered / total * 100, 1) if total > 0 else 0

    # Evidence scores
    scored = [p["evidence_score"] for p in packages if p.get("evidence_score") is not None]
    avg_score = round(sum(scored) / len(scored), 1) if scored else 0

    # Get incidents
    incidents = await db.incidents.find(
        {"journey_id": j_id}, {"_id": 0, "status": 1, "incident_type": 1, "severity": 1, "description": 1}
    ).to_list(100)
    open_incidents = [i for i in incidents if i.get("status") == "open"]

    # Timestamps
    start_data = journey.get("start_data") or {}
    started_at = start_data.get("started_at", "")
    last_sync = journey.get("last_sync_at", "")

    # Minutes since last update
    minutes_ago = ""
    if last_sync:
        try:
            last_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            diff = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            minutes_ago = f"{int(diff)} min"
        except Exception:
            pass

    status_labels = {"scheduled": "Programada", "in_progress": "En Progreso", "closed": "Cerrada"}

    return {
        "journey_id": j_id,
        "journey_code": journey.get("order_id") or journey.get("cosmo_route_id") or j_id[:12],
        "status": status_labels.get(journey.get("status"), journey.get("status", "")),
        "date": journey.get("date", "")[:10],
        "client": client["name"] if client else "",
        "provider": provider["name"] if provider else "",
        "zone": journey.get("route_type", "CDMX"),
        "driver": {
            "name": journey.get("driver_name", ""),
        },
        "progress": {
            "packages_delivered": delivered,
            "packages_failed": failed,
            "packages_pending": pending,
            "packages_total": total,
            "percentage": pct,
        },
        "evidence": {
            "avg_score": avg_score,
            "scored_count": len(scored),
        },
        "incidents": {
            "open_count": len(open_incidents),
            "total_count": len(incidents),
            "details": [{"type": i.get("incident_type"), "severity": i.get("severity"), "desc": i.get("description", "")[:80]} for i in open_incidents[:5]],
        },
        "timestamps": {
            "started_at": started_at,
            "last_sync": last_sync,
            "minutes_ago": minutes_ago,
        },
    }


# ── GET /api/lumi/active-context ────────────────────────────────
@router.get("/lumi/active-context")
async def get_active_context(
    journey_id: str = Query(...),
    user: dict = Depends(get_current_user),
):
    ctx = await _build_journey_context(journey_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return ctx


# ── GET /api/lumi/tools/journey-lookup ──────────────────────────
@router.get("/lumi/tools/journey-lookup")
async def journey_lookup(
    identifier: str = Query(...),
    user: dict = Depends(get_current_user),
):
    ctx = await _build_journey_context(identifier)
    if not ctx:
        raise HTTPException(status_code=404, detail="Ruta no encontrada en la base de datos")
    return ctx


# ── Report context builder (unchanged) ──────────────────────────
async def build_lumi_context(client_id, provider_id, period):
    date_from, date_to, period_label = _resolve_period(period)

    j_query = {"date": {"$gte": date_from, "$lte": date_to}}
    if client_id:
        j_query["client_id"] = client_id
    if provider_id:
        j_query["provider_id"] = provider_id

    journeys = await db.journeys.find(j_query, {"_id": 0}).limit(500).to_list(500)
    journey_ids = [j["id"] for j in journeys]

    clients_map = {c["id"]: c["name"] for c in await db.clients.find({}, {"_id": 0}).to_list(100)}
    providers_map = {p["id"]: p["name"] for p in await db.providers.find({}, {"_id": 0}).to_list(100)}

    total_journeys = len(journeys)
    packages_total = sum(j.get("packages_total", 0) for j in journeys)
    packages_delivered = sum(j.get("packages_delivered", 0) for j in journeys)
    packages_failed = sum(j.get("packages_failed", 0) for j in journeys)
    total_km = sum((j.get("close_data") or {}).get("km_traveled", 0) for j in journeys)

    delivery_rate = round(packages_delivered / packages_total * 100, 1) if packages_total > 0 else 0
    visited = packages_delivered + packages_failed
    visit_rate = round(visited / packages_total * 100, 1) if packages_total > 0 else 0

    incidents = await db.incidents.find(
        {"journey_id": {"$in": journey_ids}}, {"_id": 0, "status": 1, "incident_type": 1, "severity": 1}
    ).limit(1000).to_list(1000)
    incidents_open = sum(1 for i in incidents if i.get("status") == "open")

    quality_data = await db.packages.aggregate([
        {"$match": {"journey_id": {"$in": journey_ids}, "evidence_score": {"$exists": True}}},
        {"$group": {"_id": None, "avg_score": {"$avg": "$evidence_score"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    quality_score = round(quality_data[0]["avg_score"], 1) if quality_data else 0

    prov_stats = {}
    for j in journeys:
        pid = j.get("provider_id", "")
        pname = providers_map.get(pid, "Desconocido")
        if pname not in prov_stats:
            prov_stats[pname] = {"routes": 0, "delivered": 0, "total": 0}
        prov_stats[pname]["routes"] += 1
        prov_stats[pname]["delivered"] += j.get("packages_delivered", 0)
        prov_stats[pname]["total"] += j.get("packages_total", 0)

    providers_summary = ""
    for pname, ps in prov_stats.items():
        rate = round(ps["delivered"] / ps["total"] * 100, 1) if ps["total"] > 0 else 0
        providers_summary += f"- {pname}: {ps['routes']} rutas, {ps['delivered']}/{ps['total']} entregados ({rate}%)\n"

    driver_stats = {}
    for j in journeys:
        dname = j.get("driver_name") or "Sin driver"
        if dname not in driver_stats:
            driver_stats[dname] = {"delivered": 0, "total": 0}
        driver_stats[dname]["delivered"] += j.get("packages_delivered", 0)
        driver_stats[dname]["total"] += j.get("packages_total", 0)

    drivers_alerts = ""
    for dname, ds in sorted(driver_stats.items(), key=lambda x: x[1]["delivered"] / max(x[1]["total"], 1)):
        rate = round(ds["delivered"] / ds["total"] * 100, 1) if ds["total"] > 0 else 0
        if rate < 70:
            drivers_alerts += f"- {dname}: {rate}% entrega ({ds['delivered']}/{ds['total']})\n"
    if not drivers_alerts:
        drivers_alerts = "Ningun driver por debajo del 70%"

    sla_config = await db.config.find_one({"key": "sla_targets"}, {"_id": 0})
    sla_target = 75
    if sla_config and sla_config.get("brackets"):
        active = [b for b in sla_config["brackets"] if b.get("status") == "active"]
        if active:
            sla_target = active[0].get("target", 75)

    client_name = "Todos"
    if client_id:
        client_name = clients_map.get(client_id, client_id)

    return {
        "period_label": period_label,
        "date_from": date_from,
        "date_to": date_to,
        "client_name": client_name,
        "total_journeys": total_journeys,
        "packages_total": packages_total,
        "delivery_rate": delivery_rate,
        "visit_rate": visit_rate,
        "quality_score": quality_score,
        "sla_actual": delivery_rate,
        "sla_target": sla_target,
        "incidents_open": incidents_open,
        "total_km": total_km,
        "providers_summary": providers_summary or "Sin datos de proveedores",
        "drivers_alerts": drivers_alerts,
        "quality_errors_summary": f"Score promedio: {quality_score}%",
    }


def build_system_prompt(data: dict, user_name: str, active_journey: dict = None) -> str:
    base = f"""Eres Lumi, asistente de inteligencia operacional de LastMile OS para Mensajeria y Estrategias (ME).
Estas ayudando a {user_name}.

DATOS OPERATIVOS DEL REPORTE:
- Periodo: {data['period_label']} ({data['date_from']} a {data['date_to']})
- Cliente: {data['client_name']}
- Rutas operadas: {data['total_journeys']}
- Paquetes: {data['packages_total']}
- Tasa de entrega: {data['delivery_rate']}%
- Tasa de visita: {data['visit_rate']}%
- Calidad evidencias: {data['quality_score']}%
- SLA actual: {data['sla_actual']}% (target: {data['sla_target']}%)
- Incidencias abiertas: {data['incidents_open']}
- Km totales: {data['total_km']}

PROVEEDORES:
{data['providers_summary']}

DRIVERS CON ALERTAS:
{data['drivers_alerts']}

TOP ERRORES EVIDENCIA:
{data['quality_errors_summary']}"""

    if active_journey:
        aj = active_journey
        prog = aj.get("progress", {})
        inc = aj.get("incidents", {})
        ts = aj.get("timestamps", {})
        ev = aj.get("evidence", {})
        inc_details = ""
        for d in inc.get("details", []):
            inc_details += f"  - {d.get('type','')}: {d.get('desc','')}\n"

        base += f"""

## CONTEXTO DE RUTA ACTIVA (datos en vivo de BD operativa)
El usuario tiene abierta la ruta {aj.get('journey_code','')}:
- ID: {aj.get('journey_id','')}
- Codigo: {aj.get('journey_code','')}
- Estado: {aj.get('status','')}
- Fecha: {aj.get('date','')}
- Cliente: {aj.get('client','')}
- Proveedor: {aj.get('provider','')}
- Zona: {aj.get('zone','')}
- Driver: {aj.get('driver',{}).get('name','')}
- Progreso: {prog.get('packages_delivered',0)}/{prog.get('packages_total',0)} entregados ({prog.get('percentage',0)}%)
- Pendientes: {prog.get('packages_pending',0)}
- Fallidos: {prog.get('packages_failed',0)}
- Calidad evidencia: {ev.get('avg_score',0)}% (de {ev.get('scored_count',0)} evaluados)
- Incidencias abiertas: {inc.get('open_count',0)} / Total: {inc.get('total_count',0)}
{inc_details}- Inicio de ruta: {ts.get('started_at','')}
- Ultima sincronizacion: {ts.get('last_sync','')} (hace {ts.get('minutes_ago','?')})

REGLAS DE USO DEL CONTEXTO ACTIVO:
1. Si el usuario pregunta por la ruta {aj.get('journey_code','')}, usa SIEMPRE este contexto. NO respondas "no se encuentra".
2. Este contexto viene directamente de la BD operativa y es mas reciente que el dataset del reporte.
3. Si el usuario pregunta por OTRA ruta distinta, usa el dataset del reporte.
4. Al responder con datos de la ruta activa, cierra con: "Datos en vivo de la ruta activa · actualizado hace {ts.get('minutes_ago','?')}"
"""

    base += """

INSTRUCCIONES:
- Responde siempre en espanol
- Se directo y usa cifras concretas del contexto
- Respuestas de 2-4 oraciones salvo que pidan analisis detallado
- Usa **negritas** para resaltar metricas clave
- Si te preguntan algo fuera del contexto operativo de LastMile, redirige amablemente
- Si el SLA esta por debajo del target, senalalo proactivamente

TRANSPARENCIA DE FUENTE:
- Si usas datos de la ruta activa, cierra con: "Datos en vivo de la ruta activa"
- Si usas el dataset del reporte, cierra con: "Fuente: reporte consolidado {date_from} a {date_to}"
- Si la ruta no existe en ningun contexto, di: "No encontre la ruta [codigo]. Verifica el codigo o intenta con el periodo correcto."
""".format(date_from=data['date_from'], date_to=data['date_to'])

    return base


@router.post("/chat/lumi")
async def lumi_chat(payload: LumiChatRequest, user: dict = Depends(get_current_user)):
    llm_key = os.environ.get("EMERGENT_LLM_KEY")
    if not llm_key:
        raise HTTPException(status_code=500, detail="LLM key no configurada")

    # Build report context
    ctx = await build_lumi_context(
        client_id=payload.client_id,
        provider_id=payload.provider_id,
        period=payload.period,
    )

    # Build active journey context if journey_id provided
    active_journey = None
    if payload.journey_id:
        active_journey = await _build_journey_context(payload.journey_id)

    # Don't block if report has no data but active journey exists
    if ctx["total_journeys"] == 0 and not active_journey:
        return {"reply": f"No hay datos de rutas para el periodo **{ctx['period_label']}** ({ctx['date_from']} a {ctx['date_to']}). Prueba seleccionando un rango de fechas diferente."}

    system_prompt = build_system_prompt(ctx, user.get("name", "Usuario"), active_journey)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import uuid

        chat = LlmChat(
            api_key=llm_key,
            session_id=f"lumi-{uuid.uuid4()}",
            system_message=system_prompt,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")

        full_prompt = ""
        for msg in payload.history[-12:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                full_prompt += f"[Usuario]: {content}\n"
            else:
                full_prompt += f"[Lumi]: {content}\n"
        full_prompt += f"[Usuario]: {payload.message}\n[Lumi]:"

        msg = UserMessage(text=full_prompt)
        reply = await chat.send_message(msg)

        try:
            from token_logger import log_token_usage
            await log_token_usage(
                db=db,
                entregable="lumi",
                modelo="claude-sonnet-4-5",
                referencia=payload.message[:80],
                input_text=full_prompt,
                output_text=reply or "",
                system_prompt=system_prompt,
                user_id=user.get("id"),
                client_id=payload.client_id,
            )
        except Exception as log_err:
            logger.debug(f"Token log skipped: {log_err}")

        return {"reply": reply, "source": "active_journey" if active_journey else "report"}

    except Exception as e:
        logger.error(f"Lumi chat error: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar con IA")
