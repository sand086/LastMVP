"""MyExcellence MVP — front controller.

Mirrors the role of /public/index.php in the canonical PHP stack:
  - Loads .env
  - Wires the middleware stack
  - Mounts /api/* routers
  - Runs the schema bootstrap on startup
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from core.config import APP_ENV, APP_VERSION, CORS_ORIGINS_RAW  # noqa: E402
from core.errors import (  # noqa: E402
    ErrorCode,
    MyEException,
)
from core.logger import log  # noqa: E402
from core.response import fail  # noqa: E402
from middleware.stack import (  # noqa: E402
    AuthTenantMiddleware,
    CorrelationMiddleware,
    ThrottleMiddleware,
)
from routes.auth import router as auth_router  # noqa: E402
from routes.admin_automation import router as admin_automation_router  # noqa: E402
from routes.admin_cae_catalog import router as admin_cae_catalog_router  # noqa: E402
from routes.admin_catalog import router as admin_catalog_router  # noqa: E402
from routes.admin_carriers_health import router as admin_carriers_health_router  # noqa: E402
from routes.admin_client_carriers import router as admin_client_carriers_router  # noqa: E402
from routes.platform_carriers import router as platform_carriers_router  # noqa: E402
from routes.admin_cron import router as admin_cron_router  # noqa: E402
from routes.admin_hierarchy import router as admin_hierarchy_router  # noqa: E402
from routes.admin_ingest_health import router as admin_ingest_health_router  # noqa: E402
from routes.admin_routal_enrich import router as admin_routal_enrich_router  # noqa: E402
from routes.agent_routal_proxy import router as agent_routal_proxy_router  # noqa: E402
from routes.agent_routal_comments import router as agent_routal_comments_router  # noqa: E402
from routes.admin_maintenance import router as admin_maintenance_router  # noqa: E402
from routes.admin_notifications import router as admin_notifications_router  # noqa: E402
from routes.admin_test_domains import router as admin_test_domains_router  # noqa: E402
from routes.admin_rules_debug import router as admin_rules_debug_router  # noqa: E402
from routes.admin_currency import router as admin_currency_router  # noqa: E402
from routes.util_cp import router as util_cp_router  # noqa: E402
from routes.admin_tenants import router as admin_tenants_router  # noqa: E402
from routes.admin_tickets import router as admin_tickets_router  # noqa: E402
from routes.agent import router as agent_router  # noqa: E402
from routes.cae_admin import router as cae_admin_router  # noqa: E402
from routes.claims import router as claims_router, router_ingest as claims_ingest_router  # noqa: E402
from routes.dashboard import router as dashboard_router  # noqa: E402
from routes.evidences import router as evidences_router  # noqa: E402
from routes.inbox import router as inbox_router  # noqa: E402
from routes.ai import router_admin as ai_admin_router, router_invoke as ai_invoke_router  # noqa: E402
from routes.whatsapp import router_admin as wa_admin_router, router_public as wa_public_router, router_webhook as wa_webhook_router  # noqa: E402
from routes.heatmap_bulk import router_admin as hb_admin_router, router_dash as hb_dash_router  # noqa: E402
from routes.webhooks import router as webhooks_admin_router  # noqa: E402
from routes.webhooks_resend import router as webhooks_resend_router  # noqa: E402
from routes.webhook_test import router as webhook_test_router  # noqa: E402
from routes.security import router as security_router  # noqa: E402
from routes.saved_filters import router as saved_filters_router  # noqa: E402
from routes.admin_seed import router as admin_seed_router  # noqa: E402
from routes.admin_email_templates import router as admin_email_templates_router  # noqa: E402
from routes.admin_email_settings import router as admin_email_settings_router  # noqa: E402
from routes.admin_email_multibuzon import router as admin_email_mb_router  # noqa: E402
from routes.admin_users import router as admin_users_router  # noqa: E402
from routes.users_onboarding import router as users_onboarding_router  # noqa: E402
from routes.admin_onboarding import router as admin_onboarding_router  # noqa: E402
from routes.ingest import router_admin as ingest_admin_router, router_public as ingest_public_router  # noqa: E402
from routes.supervisor import router as supervisor_router  # noqa: E402
from routes.system import router as system_router  # noqa: E402
from repositories.claims import ensure_claim_indexes  # noqa: E402
from repositories.ai import ensure_ai_indexes  # noqa: E402
from seeds.cae_catalog import run as run_cae_catalog_seed  # noqa: E402
from seeds.initial_schema import run as run_initial_schema  # noqa: E402
from seeds.ai_catalog import run as run_ai_catalog_seed  # noqa: E402
from seeds.webhook_catalog import run as run_webhook_catalog_seed  # noqa: E402
from repositories.webhooks import ensure_webhook_indexes  # noqa: E402
from services import scheduler as cron_scheduler  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", extra={"context": {"version": APP_VERSION, "env": APP_ENV}})
    try:
        await run_initial_schema()
        await run_cae_catalog_seed()
        await ensure_claim_indexes()
        await ensure_ai_indexes()
        await run_ai_catalog_seed()
        await run_webhook_catalog_seed()
        await ensure_webhook_indexes()
        # Bundle D · Parte 2 — sembrar festivos MX 2026-2030 (idempotente)
        from services.calendar import seed_holidays_if_empty
        await seed_holidays_if_empty()
    except Exception:  # noqa: BLE001
        log.exception("schema_bootstrap_failed")
    cron_scheduler.start()
    yield
    cron_scheduler.shutdown()
    log.info("shutdown")


app = FastAPI(title="MyExcellence", version=APP_VERSION, lifespan=lifespan)

# ---- middleware stack — order is strict (last added runs first) ----------
# Final order on requests: Correlation -> CORS -> AuthTenant -> Throttle -> route
app.add_middleware(ThrottleMiddleware)
app.add_middleware(AuthTenantMiddleware)

# CORS: explicit origins, credentials enabled
_origins = [o.strip() for o in CORS_ORIGINS_RAW.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationMiddleware)


# ---- typed exception handler -> JSON envelope ----------------------------
@app.exception_handler(MyEException)
async def _myexc_handler(request: Request, exc: MyEException):  # noqa: ARG001
    return fail(exc.code, exc.message, field=exc.field)


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):  # noqa: ARG001
    # Surface the first error in our standard envelope (R10).
    errs = exc.errors()
    if errs:
        first = errs[0]
        loc = ".".join(str(p) for p in first.get("loc", [])[1:])  # skip 'body'
        return fail(ErrorCode.VALIDATION_FAILED, first.get("msg", "Validación fallida."), field=loc or None)
    return fail(ErrorCode.VALIDATION_FAILED, "Validación fallida.")


@app.exception_handler(Exception)
async def _generic_handler(request: Request, exc: Exception):  # noqa: ARG001
    log.exception("unhandled", extra={"context": {"path": request.url.path}})
    if APP_ENV == "production":
        return fail(ErrorCode.INTERNAL_ERROR, "Internal error.")
    # Development — surface the message but NEVER the traceback in JSON
    return fail(ErrorCode.INTERNAL_ERROR, str(exc))


# ---- routers --------------------------------------------------------------
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(cae_admin_router)
app.include_router(admin_cae_catalog_router)
app.include_router(admin_tenants_router)
app.include_router(admin_hierarchy_router)
app.include_router(admin_catalog_router)
app.include_router(admin_automation_router)
app.include_router(admin_cron_router)
app.include_router(admin_notifications_router)
app.include_router(admin_ingest_health_router)
app.include_router(admin_routal_enrich_router)
app.include_router(agent_routal_proxy_router)
app.include_router(agent_routal_comments_router)
app.include_router(admin_maintenance_router)
app.include_router(admin_test_domains_router)
app.include_router(admin_rules_debug_router)
app.include_router(admin_currency_router)
app.include_router(util_cp_router)
app.include_router(admin_carriers_health_router)
app.include_router(admin_client_carriers_router)
app.include_router(platform_carriers_router)
app.include_router(admin_tickets_router)
app.include_router(agent_router)
app.include_router(supervisor_router)
app.include_router(dashboard_router)
app.include_router(ingest_public_router)
app.include_router(ingest_admin_router)
app.include_router(claims_ingest_router)
app.include_router(claims_router)
app.include_router(evidences_router)
app.include_router(inbox_router)
app.include_router(ai_invoke_router)
app.include_router(ai_admin_router)
app.include_router(wa_admin_router)
app.include_router(wa_public_router)
app.include_router(wa_webhook_router)
app.include_router(hb_admin_router)
app.include_router(hb_dash_router)
app.include_router(webhooks_admin_router)
app.include_router(webhooks_resend_router)
app.include_router(webhook_test_router)
app.include_router(security_router)
app.include_router(saved_filters_router)
app.include_router(admin_seed_router)
app.include_router(admin_email_templates_router)
app.include_router(admin_email_settings_router)
app.include_router(admin_email_mb_router)
app.include_router(admin_users_router)
app.include_router(users_onboarding_router)
app.include_router(admin_onboarding_router)


@app.get("/")
async def root():
    return {"name": "MyExcellence API", "version": APP_VERSION}
