"""Admin Onboarding Wizard — Bundle E (Iter33).

Endpoints:
  GET  /api/admin/onboarding/state       — estado actual + decisión auto-open
  POST /api/admin/onboarding/start       — explicit start (lazy bootstrap)
  POST /api/admin/onboarding/advance     — marca paso completado + persiste data
  POST /api/admin/onboarding/skip-step   — saltar paso opcional (no mandatorios)
  POST /api/admin/onboarding/complete    — finalizar wizard
  POST /api/admin/onboarding/seed-mx-catalog — step 5: cargar catálogo estándar

R51 — Onboarding asistido NO bloqueante: el cliente puede saltar, cerrar y
volver. Solo `welcome` y `catalog` (step 5) son mandatorios.

Determinación de "pre-completado a nivel tenant" (caso 2do admin):
  - `step_2_tenant_info` → existe tenant.name + tenant.address_mx (campos
    capturados en el wizard se persisten en `tenants` collection).
  - `step_3_project_client` → existe ≥1 client en el tenant.
  - `step_4_carriers` → existe ≥1 carrier configurado.
  - `step_5_catalog` → existe ≥1 motivo y ≥1 solución.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request

from core.db import get_db
from core.errors import ErrorCode, MyEException
from core.response import fail, ok
from middleware.rbac import require_min_role
from models.onboarding import (
    MANDATORY_STEPS,
    STEP_CARRIERS,
    STEP_CATALOG,
    STEP_ORDER,
    STEP_PROJECT_CLIENT,
    STEP_TENANT_INFO,
    AdvanceRequest,
    SkipRequest,
)
from repositories.onboarding import AdminOnboardingRepository, compute_next_step
from seeds.mx_catalog import seed_for_tenant


router = APIRouter(prefix="/api/admin/onboarding", tags=["admin-onboarding"])
_RBAC = require_min_role("admin")  # solo admin/superadmin/root_dev


def _repo(request: Request) -> AdminOnboardingRepository:
    return AdminOnboardingRepository(tenant_id=request.state.user.tenant_id)


async def _tenant_age_days(tenant_id: str) -> int:
    """Devuelve la antigüedad del tenant en días. Si no se puede calcular, 0."""
    db = get_db()
    doc = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "created_at": 1})
    if not doc or not doc.get("created_at"):
        return 0
    try:
        created = datetime.fromisoformat(doc["created_at"])
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - created
        return max(0, delta.days)
    except Exception:  # noqa: BLE001
        return 0


async def _pre_completed_by_tenant(tenant_id: str) -> list[str]:
    """Detecta pasos cuyo "estado a nivel tenant" ya está cubierto.

    Para el 2do admin del tenant: si el 1ero ya capturó tenant_info,
    creó cliente, configuró carrier o cargó catálogo, esos pasos no se
    re-piden.
    """
    db = get_db()
    completed: list[str] = []

    # step_2_tenant_info: tenant tiene RFC o address_mx configurado.
    t = await db.tenants.find_one(
        {"id": tenant_id},
        {"_id": 0, "rfc": 1, "address_mx": 1, "phone": 1},
    )
    if t and (t.get("rfc") or t.get("address_mx") or t.get("phone")):
        completed.append(STEP_TENANT_INFO)

    # step_3_project_client: ≥1 client en el tenant.
    clients_count = await db.clients.count_documents({"tenant_id": tenant_id})
    if clients_count > 0:
        completed.append(STEP_PROJECT_CLIENT)

    # step_4_carriers: ≥1 carrier configurado (cualquier tipo).
    carriers_count = await db.client_carrier_configs.count_documents(
        {"tenant_id": tenant_id, "enabled": True},
    )
    if carriers_count > 0:
        completed.append(STEP_CARRIERS)

    # step_5_catalog: ≥1 motivo y ≥1 solución.
    motivos_count = await db.motivos.count_documents({"tenant_id": tenant_id})
    soluciones_count = await db.soluciones.count_documents({"tenant_id": tenant_id})
    if motivos_count > 0 and soluciones_count > 0:
        completed.append(STEP_CATALOG)

    return completed


def _should_auto_open(*, role: str, tenant_age: int, completed_at: str | None) -> bool:
    """E1.1 — criterios de auto-activación:
       admin/superadmin + tenant <30d + sin completed_at.
    """
    if completed_at:
        return False
    if role not in ("admin", "superadmin", "root_dev"):
        return False
    return tenant_age <= 30


@router.get("/state")
async def get_state(request: Request, _: object = Depends(_RBAC)):
    repo = _repo(request)
    await repo.ensure_index()
    user = request.state.user

    doc = await repo.get_for_user(user.id)
    pre_completed = await _pre_completed_by_tenant(user.tenant_id)
    tenant_age = await _tenant_age_days(user.tenant_id)

    completed_at = (doc or {}).get("completed_at")
    auto_open = _should_auto_open(
        role=user.role, tenant_age=tenant_age, completed_at=completed_at,
    )

    return ok({
        "in_progress": bool(doc and not completed_at),
        "current_step": (doc or {}).get("current_step"),
        "steps_completed": list((doc or {}).get("steps_completed") or []),
        "step_data": dict((doc or {}).get("step_data") or {}),
        "started_at": (doc or {}).get("started_at"),
        "last_activity": (doc or {}).get("last_activity"),
        "completed_at": completed_at,
        "should_auto_open": auto_open,
        "is_completed": bool(completed_at),
        "pre_completed_by_tenant": pre_completed,
        "tenant_age_days": tenant_age,
    })


@router.post("/start")
async def start(request: Request, _: object = Depends(_RBAC)):
    """Crea (o devuelve) el doc de progreso para este user×tenant."""
    repo = _repo(request)
    await repo.ensure_index()
    doc = await repo.start_if_absent(request.state.user.id)
    return ok({"current_step": doc["current_step"], "started_at": doc["started_at"]})


@router.post("/advance")
async def advance(
    payload: AdvanceRequest, request: Request, _: object = Depends(_RBAC),
):
    repo = _repo(request)
    await repo.ensure_index()
    user_id = request.state.user.id
    doc = await repo.start_if_absent(user_id)

    if payload.current_step not in STEP_ORDER:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"Paso desconocido: {payload.current_step}",
                    field="current_step")

    steps_completed = list(doc.get("steps_completed") or [])
    if payload.current_step not in steps_completed:
        steps_completed.append(payload.current_step)
    nxt = compute_next_step(payload.current_step, steps_completed)

    doc = await repo.mark_step(
        user_id=user_id, completed_step=payload.current_step,
        step_data={payload.current_step: payload.step_data} if payload.step_data else None,
        next_step=nxt,
    )

    # Si nxt is None → último paso, auto-completar.
    if nxt is None:
        doc = await repo.mark_completed(user_id)

    return ok({
        "current_step": doc.get("current_step"),
        "steps_completed": doc.get("steps_completed") or [],
        "is_completed": bool(doc.get("completed_at")),
    })


@router.post("/skip-step")
async def skip_step(
    payload: SkipRequest, request: Request, _: object = Depends(_RBAC),
):
    """Saltar un paso opcional. Rechaza pasos mandatorios."""
    if payload.current_step in MANDATORY_STEPS:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Este paso es obligatorio y no se puede saltar.",
                    field="current_step")

    repo = _repo(request)
    await repo.ensure_index()
    user_id = request.state.user.id
    doc = await repo.start_if_absent(user_id)

    # No marcamos el paso como `completed`; solo movemos current_step al
    # siguiente. Quedará registro de pasos pendientes via diferencia
    # STEP_ORDER vs steps_completed.
    steps_completed = list(doc.get("steps_completed") or [])
    nxt = compute_next_step(payload.current_step, steps_completed)
    db = get_db()
    await db.admin_onboarding_progress.update_one(
        {"id": doc["id"], "tenant_id": request.state.user.tenant_id},
        {"$set": {
            "current_step": nxt,
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }},
    )

    if nxt is None:
        await repo.mark_completed(user_id)

    return ok({
        "current_step": nxt,
        "skipped_step": payload.current_step,
        "is_completed": nxt is None,
    })


@router.post("/complete")
async def complete(request: Request, _: object = Depends(_RBAC)):
    """Cierra el wizard. Idempotente — un 2do POST no rompe nada."""
    repo = _repo(request)
    await repo.ensure_index()
    doc = await repo.mark_completed(request.state.user.id)
    duration_seconds = 0
    if doc.get("started_at") and doc.get("completed_at"):
        try:
            s = datetime.fromisoformat(doc["started_at"])
            e = datetime.fromisoformat(doc["completed_at"])
            duration_seconds = int((e - s).total_seconds())
        except Exception:  # noqa: BLE001
            duration_seconds = 0
    return ok({
        "completed_at": doc.get("completed_at"),
        "duration_seconds": duration_seconds,
    })


@router.post("/seed-mx-catalog")
async def seed_catalog(request: Request, _: object = Depends(_RBAC)):
    """Step 5 helper — siembra catálogo MX estándar para el tenant.

    Idempotente. Si ya hay registros con el mismo `code`/`name`, no duplica.
    """
    counters = await seed_for_tenant(request.state.user.tenant_id)
    return ok(counters)
