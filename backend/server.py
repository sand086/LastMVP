"""
LastMile OS API - Main Application
Modular FastAPI application for last-mile delivery management.
"""
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
import logging

from dependencies import db, limiter, mongo_client
from middleware import AuditMiddleware, SecurityHeadersMiddleware
from system_routes import create_system_router
from kosmo_sync import create_kosmo_router, start_periodic_sync, stop_periodic_sync
from dependencies import get_current_user

from routes import (
    auth_router,
    user_router,
    journey_router,
    upload_router,
    dashboard_router,
    analytics_router,
    admin_router,
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

# Core feature routes (all prefixed under /api via api_router)
api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(journey_router)
api_router.include_router(upload_router)
api_router.include_router(dashboard_router)
api_router.include_router(analytics_router)
api_router.include_router(admin_router)

app.include_router(api_router)

# System routes (factory pattern with injected deps)
system_router = create_system_router(db, get_current_user)
api_system_router = APIRouter(prefix="/api")
api_system_router.include_router(system_router)
app.include_router(api_system_router)

# Kosmo sync routes
kosmo_router = create_kosmo_router(db, get_current_user)
api_kosmo_router = APIRouter(prefix="/api")
api_kosmo_router.include_router(kosmo_router)
app.include_router(api_kosmo_router)

# ==================== MIDDLEWARE (order matters: last added = first executed) ====================

app.add_middleware(AuditMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[
        "https://lastmile-mvp.preview.emergentagent.com",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== STARTUP / SHUTDOWN ====================


@app.on_event("startup")
async def startup_event():
    await db.packages.create_index(
        [("cosmo_route_id", 1), ("order_reference_id", 1)],
        unique=False,
        background=True,
    )
    await db.packages.create_index("order_reference_id", background=True)
    start_periodic_sync(db)


@app.on_event("shutdown")
async def shutdown_db_client():
    stop_periodic_sync()
    mongo_client.close()
