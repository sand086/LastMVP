"""
Lumi AI Chatbot — LastMile OS
POST /api/chat/lumi
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from dependencies import db, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class LumiChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    period: str = "7d"
    client_id: Optional[str] = None
    provider_id: Optional[str] = None


def _resolve_period(period: str):
    now = datetime.now(timezone.utc)

    def fmt(d):
        return d.strftime("%Y-%m-%d")

    if period == "15d":
        return fmt(now - timedelta(days=14)), fmt(now), "Últimos 15 días"
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
        return fmt(now - timedelta(days=6)), fmt(now), "Últimos 7 días"


async def build_lumi_context(client_id, provider_id, period):
    date_from, date_to, period_label = _resolve_period(period)

    j_query = {"date": {"$gte": date_from, "$lte": date_to}}
    if client_id:
        j_query["client_id"] = client_id
    if provider_id:
        j_query["provider_id"] = provider_id

    journeys = await db.journeys.find(j_query, {"_id": 0}).to_list(5000)
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
    ).to_list(5000)
    incidents_open = sum(1 for i in incidents if i.get("status") == "open")

    quality_data = await db.packages.aggregate([
        {"$match": {"journey_id": {"$in": journey_ids}, "evidence_score": {"$exists": True}}},
        {"$group": {"_id": None, "avg_score": {"$avg": "$evidence_score"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    quality_score = round(quality_data[0]["avg_score"], 1) if quality_data else 0

    # Provider summary
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

    # Drivers with alerts
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
        drivers_alerts = "Ningún driver por debajo del 70%"

    # SLA
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


def build_system_prompt(data: dict, user_name: str) -> str:
    return f"""Eres Lumi, asistente de inteligencia operacional de LastMile OS para Mensajería y Estrategias (ME).
Estás ayudando a {user_name}.

DATOS OPERATIVOS ACTIVOS:
- Período: {data['period_label']} ({data['date_from']} a {data['date_to']})
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
{data['quality_errors_summary']}

INSTRUCCIONES:
- Responde siempre en español
- Sé directo y usa cifras concretas del contexto
- Respuestas de 2-4 oraciones salvo que pidan análisis detallado
- Usa **negritas** para resaltar métricas clave
- Si te preguntan algo fuera del contexto operativo de LastMile, redirige amablemente
- Si el SLA está por debajo del target, señálalo proactivamente"""


@router.post("/chat/lumi")
async def lumi_chat(payload: LumiChatRequest, user: dict = Depends(get_current_user)):
    llm_key = os.environ.get("EMERGENT_LLM_KEY")
    if not llm_key:
        raise HTTPException(status_code=500, detail="LLM key no configurada")

    # Build context
    ctx = await build_lumi_context(
        client_id=payload.client_id,
        provider_id=payload.provider_id,
        period=payload.period,
    )

    if ctx["total_journeys"] == 0:
        return {"reply": f"No hay datos de rutas para el período **{ctx['period_label']}** ({ctx['date_from']} a {ctx['date_to']}). Prueba seleccionando un rango de fechas diferente."}

    system_prompt = build_system_prompt(ctx, user.get("name", "Usuario"))

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import uuid

        chat = LlmChat(
            api_key=llm_key,
            session_id=f"lumi-{uuid.uuid4()}",
            system_message=system_prompt,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")

        # Build conversation with history
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
        return {"reply": reply}

    except Exception as e:
        logger.error(f"Lumi chat error: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar con IA")
