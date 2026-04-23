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
from ai_eval_config import (
    get_ai_eval_config,
    set_ai_eval_config,
    pause_worker,
    resume_worker,
    is_worker_paused,
    DEFAULTS as AI_EVAL_DEFAULTS,
    VALID_BOUNDS as AI_EVAL_BOUNDS,
    MODEL_MAP,
)
from pagination_utils import paginated_response

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

    return paginated_response(jobs, total=total, page=page, page_size=limit)


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


# ── POST /api/ai-evaluation/jobs/retry-errors ───────────────────
class RetryErrorsRequest(BaseModel):
    job_ids: Optional[list] = None  # None → all Error jobs
    max_jobs: int = 50


@router.post("/jobs/retry-errors")
async def retry_error_jobs(
    data: RetryErrorsRequest = RetryErrorsRequest(),
    user: dict = Depends(require_role(["coordinator", "developer"])),
):
    """Re-encola rutas de jobs en estado Error. Útil para recuperar tras agotamiento
    de saldo, bugs corregidos, u otros fallos masivos."""
    query = {"status": "Error"}
    if data.job_ids:
        query["job_id"] = {"$in": data.job_ids}

    errored = await db.ai_evaluation_jobs.find(
        query, {"_id": 0, "route_id": 1, "job_id": 1}
    ).sort("fecha_creacion", -1).to_list(max(1, min(data.max_jobs, 200)))

    if not errored:
        return {"message": "No hay jobs Error para reintentar", "retried": 0}

    # Deduplicate por route_id
    seen = set()
    unique_routes = []
    for j in errored:
        rid = j.get("route_id")
        if rid and rid not in seen:
            seen.add(rid)
            unique_routes.append(rid)

    retried = 0
    skipped = 0
    for route_id in unique_routes:
        # Skip if there's already a pending/running job for this route
        existing = await db.ai_evaluation_jobs.find_one(
            {"route_id": route_id, "status": {"$in": ["En_Cola", "Evaluando"]}},
            {"_id": 0, "job_id": 1},
        )
        if existing:
            skipped += 1
            continue

        result = await enqueue_job(
            db,
            route_id=route_id,
            triggered_by="user_manual",
            triggered_by_user=user.get("email", user.get("name", "")),
            priority="NORMAL",
            force_reevaluate=True,
        )
        if result and result.get("job_id"):
            retried += 1

    return {
        "message": f"{retried} rutas reencoladas ({skipped} ya estaban en curso)",
        "retried": retried,
        "skipped": skipped,
        "total_routes": len(unique_routes),
    }


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



# ═══════════════ AI EVAL RUNTIME CONFIG ═══════════════

class AiEvalConfigPatch(BaseModel):
    model: Optional[str] = None               # 'haiku-4-5' | 'sonnet-4-5'
    timeout_per_guia: Optional[int] = None    # 30–180
    max_routes_concurrent: Optional[int] = None  # 1–5
    batch_size_per_route: Optional[int] = None   # 1–10
    max_retries: Optional[int] = None         # 0–5


@router.get("/config")
async def get_config(user: dict = Depends(require_role(["developer", "coordinator", "executive"]))):
    cfg = await get_ai_eval_config(db, force_refresh=True)
    paused, reason = is_worker_paused(cfg)
    return {
        "config": cfg,
        "defaults": AI_EVAL_DEFAULTS,
        "bounds": {k: list(v) if isinstance(v, tuple) else v for k, v in AI_EVAL_BOUNDS.items()},
        "model_map": MODEL_MAP,
        "pause_state": {"is_paused": paused, "reason": reason, "paused_until": cfg.get("paused_until")},
    }


@router.put("/config")
async def update_config(
    patch: AiEvalConfigPatch,
    user: dict = Depends(require_role(["developer", "coordinator"])),
):
    patch_dict = {k: v for k, v in patch.dict().items() if v is not None}
    if not patch_dict:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un campo")
    new_cfg = await set_ai_eval_config(db, patch_dict, user_email=user.get("email"))
    return {"message": "Configuración actualizada", "config": new_cfg}


# ══════ PAUSE / RESUME (kill switch) ══════

class PauseRequest(BaseModel):
    duration_minutes: int
    reason: Optional[str] = None


@router.post("/pause")
async def pause_ai_worker(
    data: PauseRequest,
    user: dict = Depends(require_role(["developer", "coordinator"])),
):
    if data.duration_minutes < 1 or data.duration_minutes > 60 * 48:
        raise HTTPException(status_code=400, detail="duration_minutes debe estar entre 1 y 2880 (48h)")
    cfg = await pause_worker(db, data.duration_minutes, data.reason, user.get("email"))
    return {
        "message": f"Worker pausado {data.duration_minutes} min. Se aborterán jobs activos en <10s.",
        "paused_until": cfg["paused_until"],
        "pause_reason": cfg["pause_reason"],
    }


@router.post("/resume")
async def resume_ai_worker(user: dict = Depends(require_role(["developer", "coordinator"]))):
    await resume_worker(db, user.get("email"))
    return {"message": "Worker reanudado. Tomará jobs de la cola en <10s."}


class ScheduleWindow(BaseModel):
    name: str
    days: list
    frm: str = ""  # not used
    to: str = ""
    tz: Optional[str] = "America/Mexico_City"


class ScheduleUpdate(BaseModel):
    enabled: bool
    windows: list  # raw dict list with {name, days, from, to, tz}


@router.put("/schedule")
async def update_schedule(
    data: ScheduleUpdate,
    user: dict = Depends(require_role(["developer", "coordinator"])),
):
    new_cfg = await set_ai_eval_config(db, {
        "schedule_enabled": data.enabled,
        "schedule_windows": data.windows,
    }, user_email=user.get("email"))
    return {
        "message": f"Agenda actualizada ({len(new_cfg['schedule_windows'])} ventanas)",
        "schedule_enabled": new_cfg["schedule_enabled"],
        "schedule_windows": new_cfg["schedule_windows"],
    }
