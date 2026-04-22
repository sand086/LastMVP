"""
AI Evaluation Jobs — Monitor de Procesos API routes.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio

from dependencies import db, get_current_user, require_role
from ai_eval_worker import enqueue_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-evaluation", tags=["AI Evaluation"])


class ManualJobRequest(BaseModel):
    route_id: str
    force_reevaluate: bool = False


class ManualGuiaRequest(BaseModel):
    guia_id: str
    force_reevaluate: bool = False


# ── GET /api/ai-evaluation/jobs ─────────────────────────────────
@router.get("/jobs")
async def list_jobs(
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    route_id: Optional[str] = None,
    status: Optional[str] = None,
    triggered_by: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    query = {}
    if fecha_desde:
        query.setdefault("fecha_creacion", {})["$gte"] = fecha_desde
    if fecha_hasta:
        query.setdefault("fecha_creacion", {})["$lte"] = fecha_hasta + "T23:59:59"
    if route_id:
        query["route_id"] = route_id
    if status and status != "all":
        query["status"] = status
    if triggered_by and triggered_by != "all":
        query["triggered_by"] = triggered_by

    total = await db.ai_evaluation_jobs.count_documents(query)
    skip = (page - 1) * limit

    jobs = await db.ai_evaluation_jobs.find(
        query, {"_id": 0, "guias_detail": 0}
    ).sort("fecha_creacion", -1).skip(skip).to_list(limit)

    return {"data": jobs, "total": total, "page": page, "pages": max(1, (total + limit - 1) // limit)}


# ── GET /api/ai-evaluation/jobs/{job_id} ────────────────────────
@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await db.ai_evaluation_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job


# ── POST /api/ai-evaluation/jobs/manual ─────────────────────────
@router.post("/jobs/manual")
async def create_manual_job(
    data: ManualJobRequest,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    result = await enqueue_job(
        db,
        route_id=data.route_id,
        triggered_by="user_manual",
        triggered_by_user=user.get("email", user.get("name", "")),
        priority="URGENT",
        force_reevaluate=data.force_reevaluate,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return result


# ── POST /api/ai-evaluation/jobs/manual/guia ────────────────────
@router.post("/jobs/manual/guia")
async def create_manual_guia_job(
    data: ManualGuiaRequest,
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    pkg = await db.packages.find_one({"id": data.guia_id}, {"_id": 0, "journey_id": 1, "status": 1})
    if not pkg:
        raise HTTPException(status_code=404, detail="Guia no encontrada")
    if pkg.get("status") not in ("delivered", "failed"):
        raise HTTPException(status_code=400, detail=f"Guia con status '{pkg.get('status')}' no es elegible (requiere delivered/failed)")

    result = await enqueue_job(
        db,
        route_id=pkg["journey_id"],
        triggered_by="user_manual",
        triggered_by_user=user.get("email", user.get("name", "")),
        priority="URGENT",
        force_reevaluate=data.force_reevaluate,
        guia_ids=[data.guia_id],
    )
    if not result:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return result


# ── DELETE /api/ai-evaluation/jobs/{job_id} ─────────────────────
@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    job = await db.ai_evaluation_jobs.find_one({"job_id": job_id}, {"_id": 0, "status": 1})
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.get("status") != "En_Cola":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden cancelar jobs en estado 'En_Cola' (actual: '{job.get('status')}')",
        )
    await db.ai_evaluation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "Error", "error_detail": "Cancelado por usuario"}},
    )
    return {"message": "Job cancelado"}


# ── GET /api/ai-evaluation/health ───────────────────────────────
@router.get("/health")
async def worker_health(user: dict = Depends(get_current_user)):
    """Estado operativo del AI Eval Worker para monitoreo (Grafana/uptime)."""
    from datetime import datetime, timezone
    from ai_eval_worker import MAX_ROUTES_CONCURRENT, CRON_INTERVAL_MINUTES

    evaluando = await db.ai_evaluation_jobs.count_documents({"status": "Evaluando"})
    en_cola = await db.ai_evaluation_jobs.count_documents({"status": "En_Cola"})
    slots_free = max(0, MAX_ROUTES_CONCURRENT - evaluando)

    # Edad del Evaluando mas antiguo (detecta orphans/stuck jobs)
    oldest = await db.ai_evaluation_jobs.find_one(
        {"status": "Evaluando"},
        {"_id": 0, "fecha_inicio": 1},
        sort=[("fecha_inicio", 1)],
    )
    oldest_age_seconds = None
    if oldest and oldest.get("fecha_inicio"):
        try:
            started = datetime.fromisoformat(oldest["fecha_inicio"].replace("Z", "+00:00"))
            oldest_age_seconds = int((datetime.now(timezone.utc) - started).total_seconds())
        except (ValueError, TypeError):
            pass

    # Ultimo job terminado (health signal)
    last_terminal = await db.ai_evaluation_jobs.find_one(
        {"status": {"$in": ["Evaluada", "Parcial", "Error"]}, "fecha_termino": {"$ne": None}},
        {"_id": 0, "fecha_termino": 1, "status": 1},
        sort=[("fecha_termino", -1)],
    )

    # Salud general: "healthy" / "saturated" / "stuck"
    if evaluando >= MAX_ROUTES_CONCURRENT and en_cola > 0:
        status = "saturated"
    elif oldest_age_seconds and oldest_age_seconds > 30 * 60:
        status = "stuck"
    else:
        status = "healthy"

    return {
        "status": status,
        "worker": {
            "max_concurrent": MAX_ROUTES_CONCURRENT,
            "slots_in_use": evaluando,
            "slots_free": slots_free,
            "cron_interval_minutes": CRON_INTERVAL_MINUTES,
        },
        "queue": {
            "running": evaluando,
            "queued": en_cola,
            "oldest_running_age_seconds": oldest_age_seconds,
        },
        "last_terminal_job": last_terminal,
    }


# ── GET /api/ai-evaluation/jobs/{job_id}/stream (SSE) ───────────
@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, user: dict = Depends(get_current_user)):
    import json

    async def event_generator():
        last_progress = -1
        for _ in range(300):  # Max 5 min
            job = await db.ai_evaluation_jobs.find_one(
                {"job_id": job_id}, {"_id": 0, "status": 1, "progress_percent": 1, "guias_evaluadas": 1, "total_guias": 1, "guias_con_error": 1, "tokens_consumidos": 1}
            )
            if not job:
                yield f"data: {json.dumps({'error': 'Job no encontrado'})}\n\n"
                break

            progress = job.get("progress_percent", 0)
            if progress != last_progress:
                last_progress = progress
                payload = {
                    "status": job["status"],
                    "progress": progress,
                    "evaluated": job.get("guias_evaluadas", 0),
                    "total": job.get("total_guias", 0),
                    "errors": job.get("guias_con_error", 0),
                    "tokens": job.get("tokens_consumidos", 0),
                }
                yield f"data: {json.dumps(payload)}\n\n"

            if job["status"] in ("Evaluada", "Error", "Parcial"):
                break

            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
