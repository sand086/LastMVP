"""
LastMile OS API - Main Application
Modular FastAPI application for last-mile delivery management.
"""
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded
import logging
import os

from dependencies import db, limiter, mongo_client
from middleware import AuditMiddleware, SecurityHeadersMiddleware
from kosmo_sync import start_periodic_sync, stop_periodic_sync, close_http_client
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
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== APP CREATION ====================

app = FastAPI(title="LastMile OS API")

# Attach limiter to app state
app.state.limiter = limiter
app.state.db = db


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: StarletteRequest, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Demasiados intentos. Espera 1 minuto."},
    )


# ==================== ROOT ENDPOINTS ====================

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "LastMile OS API v1.0", "status": "running"}


@api_router.get("/health")
async def health():
    from datetime import datetime, timezone
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


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

app.include_router(api_router)


# Backward compat redirect for /api-docs
@app.get("/api-docs")
async def redirect_api_docs():
    return RedirectResponse(url="/documentation", status_code=301)

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

ALLOWED_ORIGINS = [
    o.strip() for o in
    os.environ.get("CORS_ORIGINS",
        "https://lastmile-mvp.preview.emergentagent.com"
    ).split(",")
    if o.strip() and o.strip() != "*"
] or ["https://lastmile-mvp.preview.emergentagent.com"]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=600,
)

# ==================== STARTUP / SHUTDOWN ====================


@app.on_event("startup")
async def startup_event():
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
    await db.packages.create_index([("tracking_url", 1), ("kosmo_scraped_at", 1)], background=True)
    await db.journeys.create_index("next_sync_at", background=True)

    # Driver indexes
    await db.drivers.create_index("name", unique=True, background=True)
    await db.drivers.create_index("provider_id", background=True)
    await db.drivers.create_index("status", background=True)

    # TTL indexes for cleanup (Audit P0)
    await db.request_metrics.create_index("timestamp", expireAfterSeconds=2592000, background=True)
    await db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0, background=True)

    # Journey indexes
    await db.journeys.create_index("date", background=True)
    await db.journeys.create_index("status", background=True)
    await db.journeys.create_index("client_id", background=True)
    await db.journeys.create_index("provider_id", background=True)
    await db.journeys.create_index([("date", -1), ("status", 1)], background=True)

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
    await db.token_usage_log.create_index([("timestamp", -1), ("entregable", 1)], background=True)
    await db.token_usage_log.create_index("client_id", background=True)

    # Audit logs
    await db.audit_logs.create_index("timestamp", background=True)
    await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)], background=True)

    # Webhooks
    await db.webhooks.create_index("is_active", background=True)
    await db.webhook_deliveries.create_index([("webhook_id", 1), ("timestamp", -1)], background=True)

    # Compound indexes for production performance
    await db.journeys.create_index([("client_id", 1), ("date", -1)], background=True)
    await db.journeys.create_index([("provider_id", 1), ("date", -1)], background=True)
    await db.journeys.create_index([("driver", 1), ("date", -1)], background=True)
    await db.packages.create_index([("journey_id", 1), ("evidence_score", 1)], background=True)
    await db.packages.create_index("delivery_type", background=True, sparse=True)
    await db.training_samples.create_index([("labeled_at", -1)], background=True)
    await db.training_samples.create_index("human_label", background=True)
    await db.incidents.create_index([("status", 1), ("severity", 1)], background=True)
    await db.token_usage_log.create_index([("client_id", 1), ("timestamp", -1)], background=True)

    logger.info("Production indexes created/verified")

    start_periodic_sync(db)


@app.on_event("shutdown")
async def shutdown_db_client():
    stop_periodic_sync()
    await close_http_client()
    mongo_client.close()
