"""
AI Evaluation Queue Worker — Asynchronous, background evaluation engine.
Uses MongoDB as job queue (no Redis/Celery dependency).
"""
import os
import asyncio
import uuid
import logging
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Config from env
MAX_ROUTES_CONCURRENT = int(os.environ.get("AI_EVAL_MAX_ROUTES_CONCURRENT", "3"))
BATCH_SIZE_PER_ROUTE = int(os.environ.get("AI_EVAL_BATCH_SIZE_PER_ROUTE", "5"))
MAX_RETRIES = int(os.environ.get("AI_EVAL_MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = int(os.environ.get("AI_EVAL_RETRY_BACKOFF_BASE", "1"))
TIMEOUT_PER_GUIA = int(os.environ.get("AI_EVAL_TIMEOUT_PER_GUIA", "90"))
CRON_INTERVAL_MINUTES = int(os.environ.get("AI_EVAL_CRON_INTERVAL_MINUTES", "30"))
WORKER_POLL_SECONDS = 10

_worker_task = None
_cron_task = None


async def enqueue_job(
    db: AsyncIOMotorDatabase,
    route_id: str,
    triggered_by: str = "user_manual",
    triggered_by_user: str = None,
    priority: str = "NORMAL",
    force_reevaluate: bool = False,
    guia_ids: list = None,
) -> dict:
    """Create an evaluation job and enqueue it."""
    now = datetime.now(timezone.utc).isoformat()

    journey = await db.journeys.find_one({"id": route_id}, {"_id": 0, "id": 1, "order_id": 1, "cosmo_route_id": 1})
    if not journey:
        return None

    route_name = journey.get("order_id") or journey.get("cosmo_route_id") or route_id[:12]

    # Get eligible packages
    pkg_query = {"journey_id": route_id, "status": {"$in": ["delivered", "failed"]}}
    if guia_ids:
        pkg_query["id"] = {"$in": guia_ids}

    if not force_reevaluate and not guia_ids:
        # Only packages not yet evaluated
        pkg_query["$or"] = [
            {"ai_evaluation.status": {"$exists": False}},
            {"ai_evaluation.status": None},
            {"ai_evaluation.status": "Error"},
        ]

    packages = await db.packages.find(pkg_query, {"_id": 0, "id": 1}).to_list(500)
    if not packages:
        return {"job_id": None, "message": "No hay guias elegibles para evaluacion", "total": 0}

    job_id = str(uuid.uuid4())
    guias_detail = [{"guia_id": p["id"], "status": "En_Cola", "tokens": 0, "error": None, "retries": 0} for p in packages]

    job = {
        "job_id": job_id,
        "route_id": route_id,
        "route_name": route_name,
        "triggered_by": triggered_by,
        "triggered_by_user": triggered_by_user,
        "priority": priority,
        "status": "En_Cola",
        "total_guias": len(packages),
        "guias_evaluadas": 0,
        "guias_con_error": 0,
        "progress_percent": 0,
        "tokens_consumidos": 0,
        "fecha_creacion": now,
        "fecha_inicio": None,
        "fecha_termino": None,
        "duracion_segundos": None,
        "error_detail": None,
        "guias_detail": guias_detail,
        "force_reevaluate": force_reevaluate,
    }
    await db.ai_evaluation_jobs.insert_one(job)

    return {"job_id": job_id, "route_name": route_name, "total": len(packages), "priority": priority}


async def _evaluate_single_guia(db, pkg_id: str, job_id: str) -> dict:
    """Evaluate a single package using the existing AI evaluation engine."""
    from evidence_scoring import evaluate_single_package_ai
    try:
        pkg = await db.packages.find_one({"id": pkg_id}, {"_id": 0})
        if not pkg:
            return {"status": "Error", "tokens": 0, "error": "Paquete no encontrado"}
        if pkg.get("status") not in ("delivered", "failed"):
            return {"status": "Error", "tokens": 0, "error": f"Status no final: {pkg.get('status')}"}

        # Detectar si el paquete tiene incidencia asociada (mismo tracking_number)
        has_incident = False
        tracking = (pkg.get("tracking_number") or "").strip()
        if tracking:
            incident = await db.incidents.find_one(
                {"tracking_number": tracking},
                {"_id": 0, "id": 1},
            )
            has_incident = incident is not None

        result = await asyncio.wait_for(
            evaluate_single_package_ai(pkg, has_incident),
            timeout=TIMEOUT_PER_GUIA,
        )

        if result and "error" in result and not result.get("evidence_score"):
            return {"status": "Error", "tokens": 0, "error": result.get("error", "Evaluacion fallo")[:200]}

        # Persistir el resultado completo (evidence_score, ai_errors, confidence, etc.)
        tokens = result.get("tokens_used", 0) if result else 0
        eval_count = (pkg.get("ai_evaluation", {}).get("evaluation_count", 0) or 0) + 1

        update_fields = {
            "ai_evaluation.status": "Evaluada",
            "ai_evaluation.last_evaluated_at": datetime.now(timezone.utc).isoformat(),
            "ai_evaluation.evaluation_count": eval_count,
            "ai_evaluation.last_job_id": job_id,
        }
        # Merge evaluation result fields (evidence_score, ai_errors, ai_observations, etc.)
        for k, v in (result or {}).items():
            if k not in ("tokens_used", "error"):
                update_fields[k] = v

        await db.packages.update_one({"id": pkg_id}, {"$set": update_fields})
        return {"status": "Evaluada", "tokens": tokens, "error": None}

    except asyncio.TimeoutError:
        return {"status": "Error", "tokens": 0, "error": f"Timeout ({TIMEOUT_PER_GUIA}s)"}
    except Exception as e:
        return {"status": "Error", "tokens": 0, "error": str(e)[:200]}


async def _evaluate_batch_with_retry(db, batch: list, job_id: str) -> list:
    """Ejecuta un batch de guias en paralelo, con reintentos por guia fallida.
    Actualiza el progreso por guia en el job. Retorna lista de results paralelos al batch."""
    # Marcar batch como 'Evaluando'
    for g in batch:
        await db.ai_evaluation_jobs.update_one(
            {"job_id": job_id, "guias_detail.guia_id": g["guia_id"]},
            {"$set": {"guias_detail.$.status": "Evaluando"}},
        )

    tasks = [_evaluate_single_guia(db, g["guia_id"], job_id) for g in batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    normalized = []
    for g, result in zip(batch, results):
        if isinstance(result, Exception):
            result = {"status": "Error", "tokens": 0, "error": str(result)[:200]}

        # Reintentar en caso de error (con backoff exponencial, max 16s)
        if result["status"] == "Error" and g.get("retries", 0) < MAX_RETRIES:
            retry_num = g.get("retries", 0) + 1
            wait = min(RETRY_BACKOFF_BASE * (4 ** (retry_num - 1)), 16)
            await asyncio.sleep(wait)
            retry_result = await _evaluate_single_guia(db, g["guia_id"], job_id)
            if retry_result["status"] != "Error":
                result = retry_result
            await db.ai_evaluation_jobs.update_one(
                {"job_id": job_id, "guias_detail.guia_id": g["guia_id"]},
                {"$set": {"guias_detail.$.retries": retry_num}},
            )

        normalized.append(result)
        await db.ai_evaluation_jobs.update_one(
            {"job_id": job_id, "guias_detail.guia_id": g["guia_id"]},
            {"$set": {
                "guias_detail.$.status": result["status"],
                "guias_detail.$.tokens": result.get("tokens", 0),
                "guias_detail.$.error": result.get("error"),
            }},
        )
    return normalized


async def _update_job_progress(db, job_id: str, evaluated: int, errors: int, total: int, total_tokens: int):
    progress = round((evaluated + errors) / total * 100) if total > 0 else 0
    await db.ai_evaluation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "guias_evaluadas": evaluated,
            "guias_con_error": errors,
            "progress_percent": progress,
            "tokens_consumidos": total_tokens,
        }},
    )


async def _finalize_job(db, job_id: str, start: datetime, evaluated: int, errors: int, total: int, total_tokens: int):
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start).total_seconds()
    final_status = "Evaluada" if errors == 0 else ("Parcial" if evaluated > 0 else "Error")
    await db.ai_evaluation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": final_status,
            "fecha_termino": end_time.isoformat(),
            "duracion_segundos": round(duration),
            "progress_percent": 100,
            "guias_evaluadas": evaluated,
            "guias_con_error": errors,
            "tokens_consumidos": total_tokens,
        }},
    )
    logger.info(f"Job {job_id} finished: {final_status} ({evaluated}/{total}, {errors} errors, {total_tokens} tokens, {round(duration)}s)")
    return final_status


async def _process_job(db: AsyncIOMotorDatabase, job: dict):
    """Procesa un evaluation job — orquesta batches y actualiza progreso."""
    job_id = job["job_id"]
    start = datetime.now(timezone.utc)

    await db.ai_evaluation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {"status": "Evaluando", "fecha_inicio": start.isoformat()}},
    )

    guias = job.get("guias_detail", [])
    total = len(guias)
    evaluated = 0
    errors = 0
    total_tokens = 0

    for batch_start in range(0, total, BATCH_SIZE_PER_ROUTE):
        batch = guias[batch_start:batch_start + BATCH_SIZE_PER_ROUTE]
        results = await _evaluate_batch_with_retry(db, batch, job_id)

        for result in results:
            if result["status"] == "Evaluada":
                evaluated += 1
            else:
                errors += 1
            total_tokens += result.get("tokens", 0)

        await _update_job_progress(db, job_id, evaluated, errors, total, total_tokens)

    return await _finalize_job(db, job_id, start, evaluated, errors, total, total_tokens)


async def _worker_loop(db: AsyncIOMotorDatabase):
    """Main worker loop — polls for queued jobs and processes them."""
    while True:
        try:
            await asyncio.sleep(WORKER_POLL_SECONDS)

            # Count running jobs
            running = await db.ai_evaluation_jobs.count_documents({"status": "Evaluando"})
            if running >= MAX_ROUTES_CONCURRENT:
                continue

            slots = MAX_ROUTES_CONCURRENT - running

            # Fetch next jobs: URGENT first, then FIFO by fecha_creacion
            jobs = await db.ai_evaluation_jobs.find(
                {"status": "En_Cola"},
                {"_id": 0},
            ).sort([("priority", -1), ("fecha_creacion", 1)]).to_list(slots)

            if not jobs:
                continue

            # Process jobs concurrently (up to available slots)
            tasks = [_process_job(db, job) for job in jobs]
            await asyncio.gather(*tasks, return_exceptions=True)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"AI eval worker error: {e}")


async def _cron_sweep(db: AsyncIOMotorDatabase):
    """Cron job — every N minutes, find unqueued terminal packages and enqueue them."""
    while True:
        try:
            await asyncio.sleep(CRON_INTERVAL_MINUTES * 60)

            # Find journeys with unevaluated terminal packages
            pipeline = [
                {"$match": {
                    "status": {"$in": ["delivered", "failed"]},
                    "tracking_url": {"$nin": [None, ""]},
                    "$or": [
                        {"ai_evaluation.status": {"$exists": False}},
                        {"ai_evaluation.status": None},
                    ],
                }},
                {"$group": {"_id": "$journey_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ]

            routes_to_eval = []
            async for doc in db.packages.aggregate(pipeline):
                if doc["_id"]:
                    routes_to_eval.append({"route_id": doc["_id"], "count": doc["count"]})

            for route in routes_to_eval:
                # Check if there's already a pending/running job for this route
                existing = await db.ai_evaluation_jobs.find_one(
                    {"route_id": route["route_id"], "status": {"$in": ["En_Cola", "Evaluando"]}},
                    {"_id": 0, "job_id": 1},
                )
                if existing:
                    continue

                result = await enqueue_job(db, route["route_id"], triggered_by="scheduler_cron", priority="NORMAL")
                if result and result.get("job_id"):
                    logger.info(f"Cron sweep: enqueued {result['total']} guias for route {route['route_id'][:12]} (job {result['job_id'][:8]})")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"AI eval cron error: {e}")


async def _recover_orphan_jobs(db: AsyncIOMotorDatabase):
    """Recupera jobs 'Evaluando' huerfanos cuyo backend fue reiniciado.
    Si un job lleva >30 min en 'Evaluando' lo regresamos a 'En_Cola' para que el
    worker lo retome desde el inicio. Idempotente."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    result = await db.ai_evaluation_jobs.update_many(
        {"status": "Evaluando", "$or": [
            {"fecha_inicio": {"$lt": cutoff}},
            {"fecha_inicio": None},
        ]},
        {"$set": {"status": "En_Cola"}},
    )
    if result.modified_count > 0:
        logger.warning(f"AI Eval worker: recovered {result.modified_count} orphan Evaluando jobs → En_Cola")


def start_ai_eval_worker(db: AsyncIOMotorDatabase):
    global _worker_task, _cron_task
    # Recuperacion de jobs huerfanos (backend restart con jobs a medio evaluar)
    asyncio.create_task(_recover_orphan_jobs(db))
    _worker_task = asyncio.create_task(_worker_loop(db))
    _cron_task = asyncio.create_task(_cron_sweep(db))
    logger.info(f"AI Eval worker started (max {MAX_ROUTES_CONCURRENT} concurrent, batch {BATCH_SIZE_PER_ROUTE}, cron every {CRON_INTERVAL_MINUTES}min)")


def stop_ai_eval_worker():
    global _worker_task, _cron_task
    if _worker_task:
        _worker_task.cancel()
    if _cron_task:
        _cron_task.cancel()
    _worker_task = None
    _cron_task = None
