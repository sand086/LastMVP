"""
AI Evaluation Queue Worker — Asynchronous, background evaluation engine.
Uses MongoDB as job queue (no Redis/Celery dependency).
"""
import os
import asyncio
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from ai_eval_config import get_ai_eval_config, is_worker_paused

logger = logging.getLogger(__name__)

# Static config (env-only, rarely changed)
RETRY_BACKOFF_BASE = int(os.environ.get("AI_EVAL_RETRY_BACKOFF_BASE", "1"))
CRON_INTERVAL_MINUTES = int(os.environ.get("AI_EVAL_CRON_INTERVAL_MINUTES", "30"))
WORKER_POLL_SECONDS = 10

# Dynamic config (read from DB at start of each job):
#   timeout_per_guia, max_routes_concurrent, batch_size_per_route, max_retries, model

_worker_task = None
_cron_task = None
# Smart autopause cooldown: after triggering, NO re-checkear por N segundos para
# evitar que el worker quede atascado en pause/resume loop si la racha persiste
_last_shadow_check_ts = 0.0
SHADOW_CHECK_INTERVAL_SECONDS = 60  # cada 60s mientras el worker corre


async def _check_shadow_autopause(db: AsyncIOMotorDatabase, cfg: dict) -> bool:
    """Smart autopause: si shadow_cost_pct excede umbral en ventana reciente,
    pausar el worker automaticamente. Retorna True si se disparó la pausa.

    Usa pipelines paralelos para minimizar latencia (<50ms total).
    """
    if not cfg.get("shadow_autopause_enabled", True):
        return False
    threshold_pct = cfg.get("shadow_threshold_pct", 10)
    window_min = cfg.get("shadow_window_minutes", 15)
    min_events = cfg.get("shadow_min_events", 10)
    pause_minutes = cfg.get("shadow_autopause_minutes", 20)

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(minutes=window_min)).isoformat()

    # Una sola pipeline que cuenta total events + shadow events + costos en una pasada
    pipeline = [
        {"$match": {
            "timestamp": {"$gte": cutoff},
            "entregable": {"$in": ["evaluacion", "evaluacion_ia"]},
        }},
        {"$group": {
            "_id": None,
            "total_events": {"$sum": 1},
            "shadow_events": {"$sum": {"$cond": [{"$eq": ["$is_shadow_cost", True]}, 1, 0]}},
            "total_cost": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
            "shadow_cost": {"$sum": {"$cond": [{"$eq": ["$is_shadow_cost", True]}, {"$ifNull": ["$cost_usd", 0]}, 0]}},
        }},
    ]
    try:
        result = await db.token_usage_log.aggregate(pipeline).to_list(1)
    except Exception as e:
        logger.warning(f"shadow autopause check failed: {e}")
        return False
    if not result:
        return False
    r = result[0]
    total_events = r.get("total_events", 0)
    shadow_events = r.get("shadow_events", 0)
    total_cost = r.get("total_cost", 0) or 0
    shadow_cost = r.get("shadow_cost", 0) or 0

    # Necesitamos baseline mínimo para evitar disparar con 1 fallo aislado
    if total_events < min_events:
        return False

    # Calcular pct: usar costo si hay datos, fallback a count si los costos son cero
    if total_cost > 0:
        actual_pct = round(shadow_cost / total_cost * 100, 1)
    else:
        actual_pct = round(shadow_events / total_events * 100, 1) if total_events else 0

    if actual_pct < threshold_pct:
        return False

    # ¡Trigger! Pausar via set_ai_eval_config para que el cache se invalide.
    from ai_eval_config import set_ai_eval_config
    until = (now_utc + timedelta(minutes=pause_minutes)).isoformat()
    reason = (
        f"Autopause IA: {actual_pct}% shadow cost en ult. {window_min} min "
        f"({shadow_events}/{total_events} eventos, ${shadow_cost:.4f}/${total_cost:.4f} USD)"
    )
    await set_ai_eval_config(db, {
        "paused_until": until,
        "pause_reason": reason[:200],
    }, user_email="system_autopause")
    logger.warning(f"[AUTOPAUSE TRIGGERED] {reason} — paused for {pause_minutes} min")
    return True


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


async def _evaluate_single_guia(db, pkg_id: str, job_id: str, timeout_s: int) -> dict:
    """Evaluate a single package using the existing AI evaluation engine."""
    from evidence_scoring import evaluate_single_package_ai
    try:
        pkg = await db.packages.find_one({"id": pkg_id}, {"_id": 0})
        if not pkg:
            # Guía eliminada: NO reintentar (el retry no la va a resucitar)
            return {"status": "Error", "tokens": 0, "error": "Paquete eliminado", "_skip_retry": True}
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
            timeout=timeout_s,
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
        # Excluir metadata interno que no debe persistirse al paquete.
        _internal_keys = {"tokens_used", "error", "image_count"}
        for k, v in (result or {}).items():
            if k not in _internal_keys:
                update_fields[k] = v

        await db.packages.update_one({"id": pkg_id}, {"$set": update_fields})
        return {"status": "Evaluada", "tokens": tokens, "error": None}

    except asyncio.TimeoutError:
        # El shadow log ya se realiza dentro de _call_ai_vision (evidence_scoring.py)
        # cuando chat.send_message falla. Aquí solo marcamos el resultado.
        return {"status": "Error", "tokens": 0, "error": f"Timeout ({timeout_s}s)"}
    except Exception as e:
        msg = str(e)
        # Circuit breaker abierto: no es un fallo del paquete, es una pausa controlada.
        if "circuit OPEN" in msg or "CircuitOpenError" in type(e).__name__:
            return {"status": "Error", "tokens": 0, "error": "LLM en circuit breaker (recuperándose)", "_skip_retry": True}
        # El shadow log ya se realiza dentro de _call_ai_vision cuando send_message
        # lanza una excepción (es el único punto donde Anthropic ya facturó).
        # Aquí solo mapeamos el error a un mensaje friendly.
        if "Budget has been exceeded" in msg or "budget" in msg.lower():
            friendly = "Saldo de Emergent LLM Key agotado. Recarga en Perfil → Clave Universal."
        elif "rate_limit" in msg.lower() or "rate limit" in msg.lower():
            friendly = "Rate limit de Anthropic alcanzado. Reintenta en unos minutos."
        elif "AuthenticationError" in msg or "authentication" in msg.lower():
            friendly = "Error de autenticación con Emergent LLM. Revisa la clave."
        else:
            friendly = msg[:200]
        return {"status": "Error", "tokens": 0, "error": friendly}


async def _evaluate_batch_with_retry(db, batch: list, job_id: str, timeout_s: int, max_retries: int) -> list:
    """Ejecuta un batch de guias en paralelo, con reintentos por guia fallida.
    Actualiza el progreso por guia en el job. Retorna lista de results paralelos al batch."""
    # Marcar batch como 'Evaluando'
    for g in batch:
        await db.ai_evaluation_jobs.update_one(
            {"job_id": job_id, "guias_detail.guia_id": g["guia_id"]},
            {"$set": {"guias_detail.$.status": "Evaluando"}},
        )

    tasks = [_evaluate_single_guia(db, g["guia_id"], job_id, timeout_s) for g in batch]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    normalized = []
    for g, result in zip(batch, results):
        if isinstance(result, Exception):
            result = {"status": "Error", "tokens": 0, "error": str(result)[:200]}

        # Reintentar en caso de error (con backoff exponencial, max 16s)
        # Skip retry para errores terminales (paquete eliminado)
        if result["status"] == "Error" and not result.get("_skip_retry") and g.get("retries", 0) < max_retries:
            retry_num = g.get("retries", 0) + 1
            wait = min(RETRY_BACKOFF_BASE * (4 ** (retry_num - 1)), 16)
            await asyncio.sleep(wait)
            retry_result = await _evaluate_single_guia(db, g["guia_id"], job_id, timeout_s)
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
            "last_progress_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


async def _finalize_job(db, job_id: str, start: datetime, evaluated: int, errors: int, total: int, total_tokens: int):
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start).total_seconds()
    final_status = "Evaluada" if errors == 0 else ("Parcial" if evaluated > 0 else "Error")

    # Si todo falló, detectar si la causa es uniforme (ej. Budget exceeded) para exponerla a UI
    error_detail = None
    if evaluated == 0 and errors > 0:
        job = await db.ai_evaluation_jobs.find_one({"job_id": job_id}, {"_id": 0, "guias_detail": 1})
        if job:
            unique_errs = {(g.get("error") or "").strip() for g in (job.get("guias_detail") or []) if g.get("error")}
            if len(unique_errs) == 1:
                error_detail = next(iter(unique_errs))[:300]

    update = {
        "status": final_status,
        "fecha_termino": end_time.isoformat(),
        "duracion_segundos": round(duration),
        "progress_percent": 100,
        "guias_evaluadas": evaluated,
        "guias_con_error": errors,
        "tokens_consumidos": total_tokens,
    }
    if error_detail:
        update["error_detail"] = error_detail

    await db.ai_evaluation_jobs.update_one({"job_id": job_id}, {"$set": update})
    logger.info(f"Job {job_id} finished: {final_status} ({evaluated}/{total}, {errors} errors, {total_tokens} tokens, {round(duration)}s)")
    return final_status


async def _process_job(db: AsyncIOMotorDatabase, job: dict):
    """Procesa un evaluation job — orquesta batches y actualiza progreso."""
    job_id = job["job_id"]
    start = datetime.now(timezone.utc)

    # Lee config dinámico (model/timeout/batch/retries) una vez por job.
    cfg = await get_ai_eval_config(db)
    batch_size = cfg["batch_size_per_route"]
    timeout_s = cfg["timeout_per_guia"]
    max_retries = cfg["max_retries"]

    await db.ai_evaluation_jobs.update_one(
        {"job_id": job_id},
        {"$set": {
            "status": "Evaluando",
            "fecha_inicio": start.isoformat(),
            "last_progress_at": start.isoformat(),
            "model_used": cfg["model"],
        }},
    )

    guias = job.get("guias_detail", [])
    total = len(guias)
    evaluated = 0
    errors = 0
    total_tokens = 0

    for batch_start in range(0, total, batch_size):
        # Guard 1: ¿sigue existiendo la ruta? Si fue eliminada (limpieza), abortar
        # para no seguir gastando créditos IA.
        route_exists = await db.journeys.find_one({"id": job["route_id"]}, {"_id": 0, "id": 1})
        if not route_exists:
            logger.warning(f"Job {job_id} aborted: route {job['route_id'][:12]} no longer exists (deleted during cleanup)")
            # Marcar las guías restantes como Error con motivo claro
            remaining = guias[batch_start:]
            for g in remaining:
                await db.ai_evaluation_jobs.update_one(
                    {"job_id": job_id, "guias_detail.guia_id": g["guia_id"]},
                    {"$set": {
                        "guias_detail.$.status": "Error",
                        "guias_detail.$.error": "Ruta eliminada durante evaluación",
                    }},
                )
                errors += 1
            # Finalizar con error_detail explícito
            end_time = datetime.now(timezone.utc)
            await db.ai_evaluation_jobs.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "Parcial" if evaluated > 0 else "Error",
                    "fecha_termino": end_time.isoformat(),
                    "duracion_segundos": round((end_time - start).total_seconds()),
                    "progress_percent": 100,
                    "guias_evaluadas": evaluated,
                    "guias_con_error": errors,
                    "tokens_consumidos": total_tokens,
                    "error_detail": "Evaluación interrumpida: la ruta fue eliminada durante la limpieza de datos.",
                }},
            )
            return "Aborted"

        batch = guias[batch_start:batch_start + batch_size]
        results = await _evaluate_batch_with_retry(db, batch, job_id, timeout_s, max_retries)

        for result in results:
            if result["status"] == "Evaluada":
                evaluated += 1
            else:
                errors += 1
            total_tokens += result.get("tokens", 0)

        await _update_job_progress(db, job_id, evaluated, errors, total, total_tokens)

        # Guard 2: si el batch completo falló por Budget exceeded, auto-pausa worker
        # 10 min y finaliza job (evita gastar intentos inútiles).
        all_budget_errors = (
            len(results) > 0
            and all(r["status"] == "Error" and r.get("error") and "saldo" in r["error"].lower()
                    for r in results)
        )
        if all_budget_errors:
            logger.error(f"Job {job_id}: budget exceeded on entire batch — auto-pausing worker 10 min")
            try:
                from ai_eval_config import pause_worker
                await pause_worker(db, duration_minutes=10,
                                   reason="Auto-pausa: saldo Emergent LLM agotado",
                                   user_email="system_auto")
            except Exception as pe:
                logger.error(f"Auto-pause failed: {pe}")
            # Marcar guías restantes como Error
            remaining = guias[batch_start + batch_size:]
            for g in remaining:
                await db.ai_evaluation_jobs.update_one(
                    {"job_id": job_id, "guias_detail.guia_id": g["guia_id"]},
                    {"$set": {
                        "guias_detail.$.status": "Error",
                        "guias_detail.$.error": "Saldo IA agotado",
                    }},
                )
                errors += 1
            end_time = datetime.now(timezone.utc)
            await db.ai_evaluation_jobs.update_one(
                {"job_id": job_id},
                {"$set": {
                    "status": "Parcial" if evaluated > 0 else "Error",
                    "fecha_termino": end_time.isoformat(),
                    "duracion_segundos": round((end_time - start).total_seconds()),
                    "progress_percent": 100,
                    "guias_evaluadas": evaluated,
                    "guias_con_error": errors,
                    "tokens_consumidos": total_tokens,
                    "error_detail": "Saldo Emergent LLM agotado. Worker pausado 10 min automáticamente.",
                }},
            )
            return "BudgetExhausted"

    return await _finalize_job(db, job_id, start, evaluated, errors, total, total_tokens)


async def _kill_active_jobs_due_to_pause(db, reason: str) -> int:
    """Mark all Evaluando jobs as Error immediately (kill switch).
    Guías already marked Evaluada keep their results."""
    now_iso = datetime.now(timezone.utc).isoformat()
    # Per-guia: mark any Evaluando as Error
    await db.ai_evaluation_jobs.update_many(
        {"status": "Evaluando"},
        {"$set": {"guias_detail.$[g].status": "Error",
                  "guias_detail.$[g].error": "Worker pausado"}},
        array_filters=[{"g.status": "Evaluando"}],
    )
    # Count per-job totals manually (cannot finalize in single update)
    killed = 0
    async for job in db.ai_evaluation_jobs.find({"status": "Evaluando"}, {"_id": 0}):
        from collections import Counter
        cnt = Counter(g["status"] for g in job.get("guias_detail") or [])
        evaluated = cnt.get("Evaluada", 0)
        errors = cnt.get("Error", 0) + cnt.get("En_Cola", 0) + cnt.get("Evaluando", 0)
        # Any remaining En_Cola guías: mark as Error too
        await db.ai_evaluation_jobs.update_one(
            {"job_id": job["job_id"]},
            {"$set": {
                "status": "Parcial" if evaluated > 0 else "Error",
                "fecha_termino": now_iso,
                "progress_percent": 100,
                "guias_evaluadas": evaluated,
                "guias_con_error": errors,
                "error_detail": f"Evaluación abortada: {reason}",
            }},
        )
        # Mark leftover En_Cola guías
        await db.ai_evaluation_jobs.update_many(
            {"job_id": job["job_id"]},
            {"$set": {"guias_detail.$[g].status": "Error",
                      "guias_detail.$[g].error": "Worker pausado"}},
            array_filters=[{"g.status": {"$in": ["En_Cola", "Evaluando"]}}],
        )
        killed += 1
    return killed


async def _worker_loop(db: AsyncIOMotorDatabase):
    """Main worker loop — polls for queued jobs and processes them."""
    global _last_shadow_check_ts
    ticks_since_recovery = 0
    was_paused = False
    while True:
        try:
            await asyncio.sleep(WORKER_POLL_SECONDS)

            # Cada ~5 min (30 ticks de 10s) revisar orphans/stuck jobs
            ticks_since_recovery += 1
            if ticks_since_recovery >= 30:
                ticks_since_recovery = 0
                await _recover_orphan_jobs(db)

            # Lee configuración dinámica
            cfg = await get_ai_eval_config(db)

            # Smart autopause: chequea shadow cost cada SHADOW_CHECK_INTERVAL_SECONDS
            now_ts = time.monotonic()
            if not was_paused and (now_ts - _last_shadow_check_ts) >= SHADOW_CHECK_INTERVAL_SECONDS:
                _last_shadow_check_ts = now_ts
                triggered = await _check_shadow_autopause(db, cfg)
                if triggered:
                    # Re-leer config para ver el pause aplicado
                    cfg = await get_ai_eval_config(db, force_refresh=True)

            # Kill switch: si el worker está pausado, aborta jobs activos y no toma nuevos
            paused, reason = is_worker_paused(cfg)
            if paused:
                if not was_paused:
                    killed = await _kill_active_jobs_due_to_pause(db, reason)
                    logger.warning(f"Worker PAUSED ({reason}) — killed {killed} active jobs")
                    was_paused = True
                continue
            if was_paused:
                logger.info("Worker RESUMED — resumen polling jobs")
                was_paused = False

            max_concurrent = cfg["max_routes_concurrent"]

            # Count running jobs
            running = await db.ai_evaluation_jobs.count_documents({"status": "Evaluando"})
            if running >= max_concurrent:
                continue

            slots = max_concurrent - running

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
    """Cron job — every N minutes, find unqueued terminal packages and enqueue them.

    Sweep ORDER: ejecutar primero, dormir despues. Ası­ tras cualquier restart del
    backend el primer barrido ocurre en <1s en vez de esperar 30 min (lo que daba
    impresion de "worker muerto" cuando en realidad simplemente esperaba el sleep).
    """
    # Pequeño delay inicial para que el bg loop principal y leader_election
    # se asienten antes de ejecutar la primera consulta pesada.
    await asyncio.sleep(15)
    while True:
        try:
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

            if routes_to_eval:
                logger.info(f"Cron sweep: encontradas {len(routes_to_eval)} rutas con packages pendientes de evaluar")

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

            await asyncio.sleep(CRON_INTERVAL_MINUTES * 60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"AI eval cron error: {e}")
            # Wait 60s on error to avoid tight crash-loop
            await asyncio.sleep(60)


async def _recover_orphan_jobs(db: AsyncIOMotorDatabase):
    """Recupera jobs 'Evaluando' y 'En_Cola' estancados por reinicio o saturación.
    - Evaluando sin progreso >10 min (last_progress_at) → Error
    - Evaluando iniciados hace >15 min sin heartbeat (legacy/post-restart) → Error
    - En_Cola esperando >2h → Error (probable saturación de créditos/workers)
    Idempotente. Para recovery manual con thresholds más agresivos, usa
    POST /api/ai-evaluation/recover-stuck."""
    now = datetime.now(timezone.utc)
    stuck_cutoff = (now - timedelta(minutes=10)).isoformat()
    legacy_cutoff = (now - timedelta(minutes=15)).isoformat()
    queue_cutoff = (now - timedelta(hours=2)).isoformat()

    # 1) Jobs con heartbeat estancado (>15 min sin progreso)
    result1 = await db.ai_evaluation_jobs.update_many(
        {"status": "Evaluando", "last_progress_at": {"$lt": stuck_cutoff}},
        {"$set": {
            "status": "Error",
            "fecha_termino": now.isoformat(),
            "error_detail": "Job estancado (sin progreso >15 min). Posible saturación o error de integración. Usa 'Reintentar' para reencolar.",
        }},
    )
    # 2) Legacy (sin heartbeat) iniciados hace >15 min
    result2 = await db.ai_evaluation_jobs.update_many(
        {"status": "Evaluando", "last_progress_at": {"$exists": False}, "$or": [
            {"fecha_inicio": {"$lt": legacy_cutoff}},
            {"fecha_inicio": None},
        ]},
        {"$set": {
            "status": "Error",
            "fecha_termino": now.isoformat(),
            "error_detail": "Job huérfano (sin heartbeat >15 min). Probable reinicio del backend o fallo en primera llamada Claude. Usa 'Reintentar' para reencolar.",
        }},
    )
    # 3) En_Cola >2h — no fueron tomados por el worker
    result3 = await db.ai_evaluation_jobs.update_many(
        {"status": "En_Cola", "fecha_creacion": {"$lt": queue_cutoff}},
        {"$set": {
            "status": "Error",
            "fecha_termino": now.isoformat(),
            "error_detail": "Job En_Cola >2h sin procesar (probable saturación IA). Usa 'Reintentar'.",
        }},
    )
    total = (result1.modified_count or 0) + (result2.modified_count or 0) + (result3.modified_count or 0)
    if total > 0:
        logger.warning(
            f"AI Eval worker: recovered {total} stale jobs → Error "
            f"(evaluando:{result1.modified_count}+{result2.modified_count}, en_cola:{result3.modified_count})"
        )


def start_ai_eval_worker(db: AsyncIOMotorDatabase):
    global _worker_task, _cron_task
    # Recuperacion de jobs huerfanos (backend restart con jobs a medio evaluar)
    asyncio.create_task(_recover_orphan_jobs(db))
    _worker_task = asyncio.create_task(_worker_loop(db))
    _cron_task = asyncio.create_task(_cron_sweep(db))
    logger.info(f"AI Eval worker started (config-driven; cron every {CRON_INTERVAL_MINUTES}min)")


def stop_ai_eval_worker():
    global _worker_task, _cron_task
    if _worker_task:
        _worker_task.cancel()
    if _cron_task:
        _cron_task.cancel()
    _worker_task = None
    _cron_task = None
