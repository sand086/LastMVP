"""
LastMile OS API - Main Application
Modular FastAPI application for last-mile delivery management.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded
import logging
import os
import time

# P03: in-memory rate-limit buckets para el middleware global
_RATE_BUCKETS: dict = {}

from dependencies import db, limiter, mongo_client
from middleware import AuditMiddleware, SecurityHeadersMiddleware
from kosmo_sync import start_periodic_sync, stop_periodic_sync, close_http_client
from ai_eval_worker import start_ai_eval_worker, stop_ai_eval_worker
from workers.routal_selection_worker import (
    start_selection_scheduler,
    stop_selection_scheduler,
)
from workers.routal_sync_worker import start_routal_sync_worker, stop_routal_sync_worker
from workers.subprocess_manager import (
    start_worker_subprocess,
    stop_worker_subprocess,
    is_worker_alive,
    get_worker_pid,
)
from ws_manager import ws_manager

from routes import (
    auth_router,
    user_router,
    journey_router,
    upload_router,
    dashboard_router,
    analytics_router,
    admin_router,
    quality_criteria_router,
    quality_tab_router,
    webhook_router,
    system_router,
    lumi_router,
    admin_module_router,
    kosmo_router,
    driver_router,
    manual_router,
    ai_eval_router,
    architecture_router,
)

from leader_election import acquire_leader, release_leader, is_leader, worker_id

import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== APP CREATION ====================


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── STARTUP ───
    # IMPORTANTE: este bloque corre ANTES de que uvicorn emita "Application
    # startup complete". Mientras dure, /health y todo el resto NO responde,
    # y NGINX/k8s probe (timeout 10s) marca el pod unhealthy → 520. Por eso
    # SOLO hacemos aquí lo crítico para que las requests funcionen:
    #   1. init_encryption: requerido por casi todas las queries (PII).
    # Lo demás (indices, migraciones one-shot, bootstrap, leader election,
    # workers) se difiere a un background task que arranca DESPUÉS del
    # "startup complete" para no bloquear el probe.
    from utils.encryption import init_encryption

    await init_encryption(db)

    # Spawn deferred initialization without awaiting it. Uvicorn emitirá
    # "Application startup complete" inmediatamente y los probes pasan.
    deferred_init_task = asyncio.create_task(_deferred_startup(app))

    yield

    # ─── SHUTDOWN ───
    if not deferred_init_task.done():
        deferred_init_task.cancel()
    _workers_mode = os.environ.get("WORKERS_MODE", "subprocess").strip().lower()

    # PARCHE: Forzar modo inline en Windows para evitar errores de subprocesos
    if os.name == "nt":
        _workers_mode = "inline"

    if _workers_mode == "subprocess":
        # Stop the standalone subprocess (and its monitor).
        await stop_worker_subprocess(grace_seconds=10)
    if is_leader("bg_tasks"):
        # Only stop inline workers if they were started inline (legacy mode).
        if _workers_mode != "subprocess":
            stop_periodic_sync()
            stop_ai_eval_worker()
            stop_selection_scheduler()
            stop_routal_sync_worker()
        await release_leader(db, role="bg_tasks")
    await close_http_client()
    mongo_client.close()


async def _deferred_startup(app: FastAPI):
    """Inicialización pesada después del 'Application startup complete'.

    Corre en background para no bloquear el probe HTTP del ingress. Los
    workers se inician dentro de los callbacks de leader-election, por eso
    no se llaman directo aquí — solo registramos los callbacks y disparamos
    acquire_leader.
    """
    try:
        await _create_indexes()
        await _auto_migrate_order_id()
        await _auto_migrate_routal_source()

        # R00B / SEL01: bootstrap default client_config (Cubbo)
        try:
            from services.client_config_service import bootstrap_default_clients

            await bootstrap_default_clients(db)
        except Exception as e:
            logger.warning(f"[client_config] bootstrap failed: {e}")

        # ─── Workers startup ───────────────────────────────────────
        # WORKERS_MODE=subprocess (default, capa 6): los workers corren en
        # un proceso Python separado con su propio event loop, eliminando
        # cualquier contención con el HTTP loop de FastAPI. Esto resuelve
        # los timeouts de /health bajo carga pesada de LLM/sync.
        #
        # WORKERS_MODE=inline (legacy): mantiene el comportamiento previo
        # de ejecutar los workers en el mismo event loop de uvicorn. Útil
        # como fallback si el modo subprocess da problemas en producción.
        _workers_mode = os.environ.get("WORKERS_MODE", "subprocess").strip().lower()

        # PARCHE: Forzar modo inline en Windows para evitar errores de subprocesos
        if os.name == "nt":
            _workers_mode = "inline"

        if _workers_mode == "subprocess":
            logger.info(
                "[bg] WORKERS_MODE=subprocess — spawning standalone worker process"
            )
            # No leader-election aquí: la maneja el propio subprocess.
            start_worker_subprocess()
        else:
            # Leader election: when multiple Uvicorn workers run, only ONE spawns
            # background tasks (ai_eval_worker + kosmo_sync). Others skip.
            # Single-worker deploys (current preview) always become leader.
            # NOTA: si NO somos leader inicialmente (lock zombi de pod muerto), el
            # módulo leader_election agenda un retry en background y nos promueve
            # cuando el lock expira. El callback abajo se ejecuta tanto en el acquire
            # inicial como en la promoción via retry, para que los workers arranquen
            # sin importar cuál fue el camino.
            from leader_election import register_on_leader_callback

            def _start_bg_tasks():
                logger.info(
                    f"[bg] Worker {worker_id()} starting bg tasks (AI eval + kosmo sync + selection + routal sync)"
                )
                start_periodic_sync(db)
                start_ai_eval_worker(db)
                start_selection_scheduler(db)
                start_routal_sync_worker(db)

            register_on_leader_callback("bg_tasks", _start_bg_tasks)

            elected = await acquire_leader(db, role="bg_tasks")
            if elected:
                logger.info(
                    f"[bg] Worker {worker_id()} is LEADER — starting AI eval + kosmo sync + selection scheduler + routal sync (INLINE)"
                )
                _start_bg_tasks()
            else:
                logger.info(
                    f"[bg] Worker {worker_id()} is FOLLOWER — bg tasks deferred. "
                    f"Will auto-start when leader lease expires (retry running in background)."
                )
        logger.info("[deferred-startup] complete")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"[deferred-startup] failed: {e}", exc_info=True)


app = FastAPI(title="LastMile OS API", lifespan=lifespan)

# Attach limiter to app state
app.state.limiter = limiter
app.state.db = db


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: StarletteRequest, exc: RateLimitExceeded):
    # P03: header Retry-After para clientes que respeten el estándar
    retry_after = 60
    try:
        # slowapi expone el limit en exc.detail; parseamos cuando se puede
        if hasattr(exc, "limit") and getattr(exc, "limit", None) is not None:
            retry_after = int(getattr(exc.limit, "amount", 60) or 60)
    except Exception:
        retry_after = 60
    client_ip = request.client.host if request.client else "?"
    path = request.url.path
    logger.warning(
        f"[rate-limit] 429 {path} ip={client_ip} ua={request.headers.get('user-agent','-')[:60]}"
    )
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "retry_after_seconds": retry_after},
        headers={"Retry-After": str(retry_after)},
    )


# ==================== ROOT ENDPOINTS ====================

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "LastMile OS API v1.0", "status": "running"}


# P02: Health check completo y rapido (no requiere auth, usado por load balancer)
@api_router.get("/health")
async def health():
    """Estado del sistema: DB + workers + storage + circuit breakers.

    HTTP 200 si healthy/degraded, 503 si unhealthy. Cada check tiene timeout
    individual de 300ms; si excede, se marca 'timeout' sin fallar el endpoint.
    Respuesta total <= 500ms (paralelizado con asyncio.gather).
    """
    import asyncio as _aio
    import os as _os
    from datetime import datetime, timezone

    started = time.monotonic()

    async def _check_db():
        t0 = time.monotonic()
        try:
            await _aio.wait_for(db.command("ping"), timeout=0.3)
            collections = await _aio.wait_for(db.list_collection_names(), timeout=0.3)
            return {
                "status": "ok",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "collections_accessible": len(collections),
            }
        except _aio.TimeoutError:
            return {
                "status": "timeout",
                "latency_ms": round((time.monotonic() - t0) * 1000),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:120]}

    async def _check_ai_eval():
        try:
            queue_depth = await _aio.wait_for(
                db.ai_evaluation_jobs.count_documents({"status": "En_Cola"}),
                timeout=0.3,
            )
            evaluating = await _aio.wait_for(
                db.ai_evaluation_jobs.count_documents({"status": "Evaluando"}),
                timeout=0.3,
            )
            last = await _aio.wait_for(
                db.ai_evaluation_jobs.find_one(
                    {"last_progress_at": {"$exists": True}},
                    {"_id": 0, "last_progress_at": 1},
                    sort=[("last_progress_at", -1)],
                ),
                timeout=0.3,
            )
            last_hb_ago = None
            if last and last.get("last_progress_at"):
                try:
                    ts = datetime.fromisoformat(
                        last["last_progress_at"].replace("Z", "+00:00")
                    )
                    last_hb_ago = round(
                        (datetime.now(timezone.utc) - ts).total_seconds()
                    )
                except Exception:
                    last_hb_ago = None
            return {
                "status": "ok",
                "queue_depth": queue_depth,
                "evaluating": evaluating,
                "last_heartbeat_seconds_ago": last_hb_ago,
            }
        except _aio.TimeoutError:
            return {"status": "timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:120]}

    async def _check_kosmo_sync():
        try:
            # Source of truth: kosmo_sync writes `last_sync_at` on every cycle
            # (see kosmo_sync.py:331). The journey with the freshest stamp
            # represents the worker's last activity.
            last = await _aio.wait_for(
                db.journeys.find_one(
                    {"last_sync_at": {"$exists": True, "$ne": None}},
                    {"_id": 0, "last_sync_at": 1},
                    sort=[("last_sync_at", -1)],
                ),
                timeout=0.3,
            )
            last_hb_ago = None
            if last and last.get("last_sync_at"):
                try:
                    ts = datetime.fromisoformat(
                        str(last["last_sync_at"]).replace("Z", "+00:00")
                    )
                    last_hb_ago = round(
                        (datetime.now(timezone.utc) - ts).total_seconds()
                    )
                except Exception:
                    last_hb_ago = None
            return {"status": "ok", "last_heartbeat_seconds_ago": last_hb_ago}
        except _aio.TimeoutError:
            return {"status": "timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:120]}

    async def _check_routal_sync():
        """Routal sync worker health: latest routal_synced_at on a journey doc.
        If it's > ROUTAL_SYNC_INTERVAL_MINUTES * 3, the worker is likely stuck.
        Also reports active candidates count so we can spot configuration drift.
        """
        try:
            last = await _aio.wait_for(
                db.journeys.find_one(
                    {"routal_synced_at": {"$exists": True, "$ne": None}},
                    {"_id": 0, "routal_synced_at": 1},
                    sort=[("routal_synced_at", -1)],
                ),
                timeout=0.3,
            )
            last_hb_ago = None
            if last and last.get("routal_synced_at"):
                try:
                    ts = datetime.fromisoformat(
                        str(last["routal_synced_at"]).replace("Z", "+00:00")
                    )
                    last_hb_ago = round(
                        (datetime.now(timezone.utc) - ts).total_seconds()
                    )
                except Exception:
                    last_hb_ago = None
            # Count candidates currently pending (matches the worker's own filter)
            from datetime import timedelta as _td

            cutoff_date = (datetime.now(timezone.utc) - _td(days=7)).strftime(
                "%Y-%m-%d"
            )
            skip_synced_after = (
                datetime.now(timezone.utc) - _td(minutes=5)
            ).isoformat()
            candidates = await _aio.wait_for(
                db.journeys.count_documents(
                    {
                        "source": "routal",
                        "status": {
                            "$in": [
                                "planificada",
                                "en_ruta",
                                "in_progress",
                                "scheduled",
                            ]
                        },
                        "date": {"$gte": cutoff_date},
                        "routal_plan_id": {"$exists": True, "$ne": None},
                        "routal_synced_at": {"$not": {"$gte": skip_synced_after}},
                    }
                ),
                timeout=0.3,
            )
            return {
                "status": "ok",
                "last_heartbeat_seconds_ago": last_hb_ago,
                "pending_candidates": candidates,
            }
        except _aio.TimeoutError:
            return {"status": "timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:120]}

    def _check_storage():
        # Storage actual: disco local del pod (Emergent native).
        # Devolver 'local' implica: archivos NO sobreviven redeploy (riesgo conocido P0).
        return {
            "status": "ok",
            "type": "s3" if _os.environ.get("S3_BUCKET_NAME") else "local",
            "warning": (
                None
                if _os.environ.get("S3_BUCKET_NAME")
                else "Local disk; files do not persist across redeploys"
            ),
        }

    def _check_circuit_breakers():
        try:
            from utils.circuit_breaker import all_breaker_status

            return all_breaker_status()
        except Exception as e:
            return {"status": "error", "error": str(e)[:80]}

    db_check, ai_check, kosmo_check, routal_check = await _aio.gather(
        _check_db(),
        _check_ai_eval(),
        _check_kosmo_sync(),
        _check_routal_sync(),
    )
    storage_check = _check_storage()
    breakers = _check_circuit_breakers()

    # Overall status. Threshold ajustable vía env (default 30 min) para evitar
    # falsos positivos cuando el worker IA está pausado intencionalmente por el usuario.
    _hb_threshold = int(_os.environ.get("AI_EVAL_HEARTBEAT_THRESHOLD_SECONDS", "1800"))
    if db_check.get("status") in ("error", "timeout"):
        overall = "unhealthy"
    elif (
        ai_check.get("last_heartbeat_seconds_ago") is not None
        and ai_check["last_heartbeat_seconds_ago"] > _hb_threshold
    ) or any(
        b.get("state") == "OPEN"
        for b in (breakers.values() if isinstance(breakers, dict) else [])
    ):
        overall = "degraded"
    else:
        overall = "healthy"

    payload = {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": _os.environ.get("APP_VERSION", "1.0.0"),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "checks": {
            "database": db_check,
            "ai_eval_worker": ai_check,
            "kosmo_sync": kosmo_check,
            "routal_sync": routal_check,
            "storage": storage_check,
            "circuit_breakers": breakers,
        },
    }
    http_code = 200 if overall in ("healthy", "degraded") else 503
    return JSONResponse(status_code=http_code, content=payload)


# P03: Rate limit DEFAULTS aplicados a todos los endpoints (auth ya tiene su propio limit)
# Endpoints excluidos: /api/health (load balancer), /api/docs.
# Reglas:
#  - 300 req/min para visitantes anonimos por IP
#  - 1000 req/min para usuarios autenticados por user_id
#  - 100 req/min en POST/PUT/DELETE para usuarios autenticados (escritura)
@app.middleware("http")
async def global_rate_limit_middleware(request: StarletteRequest, call_next):
    path = request.url.path
    # Excluir health y docs (y rutas no-API)
    if path in (
        "/api/health",
        "/api/",
        "/api/docs",
        "/api/openapi.json",
    ) or not path.startswith("/api/"):
        return await call_next(request)
    # auth y upload tienen sus propios @limiter.limit, slowapi se encarga
    if path.startswith("/api/auth/") or path.startswith("/api/uploads/"):
        return await call_next(request)
    # R00A: webhooks NO deben ser rate-limited globalmente (los proveedores externos
    # pueden enviar ráfagas durante operaciones masivas; idempotency cubre dedup).
    if path.startswith("/api/webhooks/"):
        return await call_next(request)
    # Resolve a key per request
    user_id = None
    try:
        # Best-effort: read user from JWT (cookie or Bearer). NO bloquear si falta.
        from dependencies import _resolve_user_from_request_unsafe  # type: ignore

        user_id = await _resolve_user_from_request_unsafe(request)
    except Exception:
        user_id = None

    is_write = request.method in ("POST", "PUT", "DELETE", "PATCH")
    # P03: Detectar IP real cuando hay ingress/proxy delante (Emergent K8s usa X-Forwarded-For).
    # Tomar el primer hop de la lista (cliente original) en vez de request.client.host (que es el ingress).
    fwd = request.headers.get("X-Forwarded-For", "")
    real_ip = (
        fwd.split(",")[0].strip()
        if fwd
        else (request.client.host if request.client else "unknown")
    )
    key = f"user:{user_id}" if user_id else f"ip:{real_ip}"

    # Manual sliding-window check (in-memory; consistent with slowapi default store)
    bucket = "write" if is_write and user_id else ("user" if user_id else "anon")
    limit_per_min = {"write": 100, "user": 1000, "anon": 300}[bucket]
    now_s = int(time.monotonic())
    state_key = (key, bucket, now_s // 60)
    cnt = _RATE_BUCKETS.get(state_key, 0) + 1
    _RATE_BUCKETS[state_key] = cnt
    # Cleanup ventanas viejas (mantener solo la actual + la previa)
    if len(_RATE_BUCKETS) > 8000:
        cutoff = now_s // 60 - 1
        for k in list(_RATE_BUCKETS.keys()):
            if k[2] < cutoff:
                _RATE_BUCKETS.pop(k, None)

    if cnt > limit_per_min:
        logger.warning(
            f"[rate-limit-global] 429 {request.method} {path} key={key} count={cnt}/{limit_per_min}min"
        )
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limit_exceeded", "retry_after_seconds": 60},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


# ==================== INCLUDE ALL ROUTE MODULES ====================

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(journey_router)
api_router.include_router(upload_router)
api_router.include_router(dashboard_router)
api_router.include_router(analytics_router)
api_router.include_router(admin_router)
api_router.include_router(quality_criteria_router)
api_router.include_router(quality_tab_router)
api_router.include_router(webhook_router)
api_router.include_router(system_router)
api_router.include_router(lumi_router)
api_router.include_router(admin_module_router)
api_router.include_router(kosmo_router)
api_router.include_router(driver_router)
api_router.include_router(manual_router)
api_router.include_router(ai_eval_router)
api_router.include_router(architecture_router)

# R00A: Multi-tenant integrations + Routal webhook
from routes.integration_routes import router as integration_router
from routes.routal_webhook_routes import router as routal_webhook_router

api_router.include_router(integration_router)
api_router.include_router(routal_webhook_router)

# R00B / SEL01: Selection module + client config
from routes.selection_routes import router as selection_router

api_router.include_router(selection_router)

# RT-13 / iter71: Multi-branch (sucursales)
from routes.branch_routes import router as branch_router

api_router.include_router(branch_router)

# iter79: Routal legacy plan→route journey migration (option 1b)
from routes.routal_migration_routes import router as routal_migration_router

api_router.include_router(routal_migration_router)

app.include_router(api_router)


# Alias bare /health → /api/health for monitors/k8s probes that hit the root path.
# Returns 200 with minimal body to avoid bloating logs; full health is at /api/health.
@app.get("/health", include_in_schema=False)
async def health_alias():
    """Lightweight liveness probe alias.
    Some external monitors/k8s probes call /health (no /api prefix). We respond
    with a minimal 200 to keep them happy without running the full DB check on
    every poll. Use /api/health for the comprehensive readiness payload.
    """
    return {"status": "ok"}


# Backward compat redirect for /api-docs
@app.get("/api-docs")
async def redirect_api_docs():
    return RedirectResponse(url="/documentation", status_code=301)


# ==================== WORKERS SUBPROCESS DIAGNOSTIC ====================
@app.get("/api/admin/workers-process-status", include_in_schema=False)
async def workers_process_status():
    """Diagnostic endpoint — shows whether the standalone worker subprocess
    is alive (capa 6 architecture). Returns mode + pid + alive bool."""
    mode = os.environ.get("WORKERS_MODE", "subprocess").strip().lower()
    return {
        "mode": mode,
        "alive": is_worker_alive() if mode == "subprocess" else None,
        "pid": get_worker_pid() if mode == "subprocess" else None,
    }


# ==================== WEBSOCKET ENDPOINT ====================


@app.websocket("/api/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await ws_manager.connect(websocket, "dashboard")
    try:
        while True:
            # Keep connection alive, receive pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, "dashboard")
    except Exception:
        await ws_manager.disconnect(websocket, "dashboard")


# ==================== MIDDLEWARE (order matters: last added = first executed) ====================

app.add_middleware(AuditMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_cors_env = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,https://lastmile-mvp.preview.emergentagent.com",
)
_is_wildcard = _cors_env.strip() == "*"

if _is_wildcard:
    # Dynamic origin matching — allows any origin while supporting credentials
    ALLOWED_ORIGINS = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origin_regex=r"https?://.*",
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        max_age=600,
    )
else:
    ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        max_age=600,
    )


# ─── CRITICAL: ultra-fast /health bypass (RAW ASGI middleware) ───
# Capa 5 fix (2026-05-15): el @app.middleware("http") anterior usaba
# BaseHTTPMiddleware internamente, que spawnea un task asyncio interno por
# request y bufferea la respuesta via anyio MemoryObjectStream. Bajo carga
# concurrente + HTTP/1.1 keepalive (cómo NGINX hace probes en k8s), esos
# tasks internos se encolan detrás del event loop saturado por LLM calls,
# y /health timeoutea. Issue conocido: encode/starlette#1438.
#
# Esta es una middleware ASGI RAW (no BaseHTTPMiddleware) que intercepta
# /health y /api/health en la capa de transporte ASGI, ANTES de que
# FastAPI/Starlette monten el request, ANTES de cualquier task interno.
# Latencia sub-millisegundo aunque el event loop esté ocupado.
class HealthFastBypass:
    """Raw ASGI middleware — bypasses /health checks before FastAPI machinery."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") in ("/health", "/api/health"):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b'{"status":"ok"}'})
            return
        await self.app(scope, receive, send)


# Registrado al FINAL = outermost = primer middleware en ejecutar.
app.add_middleware(HealthFastBypass)

# ==================== STARTUP / SHUTDOWN HELPERS ====================


async def _create_indexes():
    """Crea/verifica todos los indices de produccion al arranque."""
    # Package indexes
    await db.packages.create_index(
        [("cosmo_route_id", 1), ("order_reference_id", 1)],
        unique=False,
        background=True,
    )
    await db.packages.create_index("order_reference_id", background=True)
    await db.packages.create_index("journey_id", background=True)
    await db.packages.create_index("tracking_number", background=True)
    await db.packages.create_index([("journey_id", 1), ("status", 1)], background=True)
    await db.packages.create_index("status", background=True)
    await db.packages.create_index("address_cp", background=True)
    await db.packages.create_index("evidence_score", background=True)

    # Kosmo sync indexes for adaptive scheduling
    await db.packages.create_index("kosmo_scraped_at", background=True)
    await db.packages.create_index(
        [("tracking_url", 1), ("kosmo_scraped_at", 1)], background=True
    )
    await db.journeys.create_index("next_sync_at", background=True)

    # Driver indexes
    await db.drivers.create_index("name", unique=True, background=True)
    await db.drivers.create_index("provider_id", background=True)
    await db.drivers.create_index("status", background=True)

    # Manual indexes
    await db.manuals.create_index("slug", unique=True, background=True)
    await db.manuals.create_index("section", background=True)
    await db.manuals.create_index("is_published", background=True)

    # TTL indexes for cleanup (Audit P0)
    await db.request_metrics.create_index(
        "timestamp", expireAfterSeconds=2592000, background=True
    )
    await db.revoked_tokens.create_index(
        "expires_at", expireAfterSeconds=0, background=True
    )

    # Journey indexes
    await db.journeys.create_index("date", background=True)
    await db.journeys.create_index("status", background=True)
    await db.journeys.create_index("client_id", background=True)
    await db.journeys.create_index("provider_id", background=True)
    await db.journeys.create_index([("date", -1), ("status", 1)], background=True)
    await db.journeys.create_index("branch_id", background=True)
    # Perf 2026-05-05: indexes for /api/journeys list filters
    await db.journeys.create_index("migrated_to_journeys", background=True, sparse=True)
    await db.journeys.create_index(
        "_legacy_incidents_remaining", background=True, sparse=True
    )
    await db.journeys.create_index(
        [("client_id", 1), ("date", -1), ("status", 1)], background=True
    )
    await db.journeys.create_index([("provider_id", 1), ("date", -1)], background=True)

    # Branch indexes (RT-13 / iter71)
    await db.branches.create_index(
        [("client_id", 1), ("code", 1)], unique=True, background=True
    )
    await db.branches.create_index("active", background=True)

    # Incident indexes
    await db.incidents.create_index("journey_id", background=True)
    await db.incidents.create_index("status", background=True)

    # Config indexes
    await db.config.create_index("key", unique=True, background=True)

    # Training samples indexes
    await db.training_samples.create_index("journey_id", background=True)
    await db.training_samples.create_index("guide", background=True)

    # Token usage log indexes
    await db.token_usage_log.create_index("timestamp", background=True)
    await db.token_usage_log.create_index("entregable", background=True)
    await db.token_usage_log.create_index(
        [("timestamp", -1), ("entregable", 1)], background=True
    )
    await db.token_usage_log.create_index("client_id", background=True)

    # Audit logs
    await db.audit_logs.create_index("timestamp", background=True)
    await db.audit_logs.create_index(
        [("user_id", 1), ("timestamp", -1)], background=True
    )
    await db.audit_logs.create_index(
        "action", background=True
    )  # P06: filtrar por accion

    # Webhooks
    await db.webhooks.create_index("is_active", background=True)
    await db.webhook_deliveries.create_index(
        [("webhook_id", 1), ("timestamp", -1)], background=True
    )

    # Compound indexes for production performance
    await db.journeys.create_index([("client_id", 1), ("date", -1)], background=True)
    await db.journeys.create_index([("provider_id", 1), ("date", -1)], background=True)
    await db.journeys.create_index([("driver", 1), ("date", -1)], background=True)
    await db.packages.create_index(
        [("journey_id", 1), ("evidence_score", 1)], background=True
    )
    await db.packages.create_index("delivery_type", background=True, sparse=True)
    await db.training_samples.create_index([("labeled_at", -1)], background=True)
    await db.training_samples.create_index("human_label", background=True)
    await db.incidents.create_index([("status", 1), ("severity", 1)], background=True)
    await db.token_usage_log.create_index(
        [("client_id", 1), ("timestamp", -1)], background=True
    )

    # AI Evaluation indexes
    await db.ai_evaluation_jobs.create_index("route_id", background=True)
    await db.ai_evaluation_jobs.create_index("status", background=True)
    await db.ai_evaluation_jobs.create_index("fecha_creacion", background=True)
    await db.ai_evaluation_jobs.create_index(
        [("priority", -1), ("fecha_creacion", 1)], background=True
    )
    # P06: cleanup de jobs viejos por status (En_Cola/Error/Evaluada antiguas)
    await db.ai_evaluation_jobs.create_index(
        [("status", 1), ("fecha_creacion", 1)], background=True
    )

    # R00A: Client integrations + Routal events (multi-tenant)
    await db.client_integrations.create_index("client_id", unique=True, background=True)
    await db.client_integrations.create_index("integration_type", background=True)
    await db.client_integrations.create_index(
        [("integration_type", 1), ("status", 1)], background=True
    )
    await db.routal_events.create_index(
        [("event_id", 1), ("client_id", 1)], unique=True, background=True
    )
    await db.routal_events.create_index(
        [("client_id", 1), ("processed", 1), ("received_at", -1)], background=True
    )
    await db.routal_events.create_index(
        [("processed", 1), ("received_at", 1)], background=True
    )
    await db.journeys.create_index([("client_id", 1), ("source", 1)], background=True)
    await db.journeys.create_index("routal_plan_id", background=True, sparse=True)
    await db.journeys.create_index(
        [("client_id", 1), ("routal_route_id", 1)],
        background=True,
        sparse=True,
        name="client_routal_route_idx",
    )
    await db.packages.create_index([("client_id", 1), ("source", 1)], background=True)
    await db.packages.create_index("routal_service_id", background=True, sparse=True)

    # R00B / SEL01: Selection module collections
    await db.client_config.create_index("client_id", unique=True, background=True)
    await db.routal_daily_plans.create_index(
        [("client_id", 1), ("date", 1)], background=True
    )
    await db.routal_daily_plans.create_index(
        [("client_id", 1), ("driver_id", 1), ("date", 1)], unique=True, background=True
    )
    await db.routal_daily_plans.create_index(
        [("client_id", 1), ("date", 1), ("processed", 1)], background=True
    )
    await db.driver_audit_log.create_index(
        [("client_id", 1), ("date", 1)], background=True
    )
    await db.driver_audit_log.create_index(
        [("client_id", 1), ("driver_id", 1), ("date", 1)], unique=True, background=True
    )
    await db.driver_audit_log.create_index(
        [("client_id", 1), ("date", 1), ("selection_status", 1)], background=True
    )

    logger.info("Production indexes created/verified")


async def _auto_migrate_routal_source():
    """Schema migration: legacy journeys/packages get source='kosmo' (idempotent)."""
    j_migrated = await db.journeys.update_many(
        {"source": {"$exists": False}},
        {"$set": {"source": "kosmo"}},
    )
    p_migrated = await db.packages.update_many(
        {"source": {"$exists": False}},
        {"$set": {"source": "kosmo"}},
    )
    if j_migrated.modified_count or p_migrated.modified_count:
        logger.info(
            f"Schema migration: source=kosmo applied to {j_migrated.modified_count} journeys + {p_migrated.modified_count} packages"
        )


async def _auto_migrate_order_id():
    """Auto-migrate: set order_id = cosmo_route_id for journeys missing order_id."""
    migrated = await db.journeys.update_many(
        {
            "cosmo_route_id": {"$nin": [None, ""]},
            "$or": [
                {"order_id": {"$exists": False}},
                {"order_id": None},
                {"order_id": ""},
            ],
        },
        [{"$set": {"order_id": "$cosmo_route_id"}}],
    )
    if migrated.modified_count > 0:
        logger.info(f"Auto-migrated order_id for {migrated.modified_count} journeys")
