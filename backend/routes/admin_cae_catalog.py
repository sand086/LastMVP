"""CAE catalog admin routes — PROMPT 06.

Endpoints (root_dev | superadmin only — sec 14.6):
  GET  /api/admin/cae/catalog              (already exists)
  POST /api/admin/cae/catalog              create entry
  PATCH /api/admin/cae/catalog/{id}        edit
  DELETE /api/admin/cae/catalog/{id}        soft delete (active=false)
  POST /api/admin/cae/sandbox              simulate normalization
  POST /api/admin/cae/promote-unmapped     promote an unmapped code into the catalog
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.errors import ResourceNotFoundException
from core.response import ok
from core.uuid import new_id
from middleware.rbac import require_min_role
from repositories.append_only import CaeAuditRepository
from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY

router = APIRouter(prefix="/api/admin/cae", tags=["cae-admin-extra"])

# Iter59 — Bajamos el umbral de root_dev|superadmin a admin+ para permitir
# que admins de tenant remapeen códigos (p.ej. routal/canceled→exception)
# sin requerir intervención del superadmin global.
_RBAC = require_min_role("admin")


# --- Pydantic --------------------------------------------------------------
CanonicalStatus = Literal["in_transit", "delivered", "returned", "exception", "cancelled", "unknown"]
IncidentType = Optional[Literal["address_issue", "refused", "recipient_absent", "customs", "damage", "lost", "failed", "exception", "returned", "other"]]


class CatalogCreate(BaseModel):
    carrier_id: str = Field(min_length=2, max_length=50)
    raw_code: str = Field(min_length=1, max_length=100)
    api_version: str = Field(default="v1", max_length=20)
    canonical_status: CanonicalStatus
    incident_type: IncidentType = None
    is_terminal: bool = False
    requires_action: bool = False
    display_label_es: str = Field(min_length=1, max_length=255)
    confidence: int = Field(default=95, ge=0, le=100)
    active: bool = True
    scope: Literal["tenant", "global"] = "tenant"


class CatalogUpdate(BaseModel):
    canonical_status: Optional[CanonicalStatus] = None
    incident_type: IncidentType = None
    is_terminal: Optional[bool] = None
    requires_action: Optional[bool] = None
    display_label_es: Optional[str] = None
    confidence: Optional[int] = Field(default=None, ge=0, le=100)
    active: Optional[bool] = None


class SandboxRequest(BaseModel):
    carrier_id: str
    raw_code: str
    api_version: str = "v1"
    raw_description: Optional[str] = None


class PromoteUnmapped(BaseModel):
    carrier_id: str
    raw_code: str
    api_version: str = "v1"
    canonical_status: CanonicalStatus
    incident_type: IncidentType = None
    is_terminal: bool = False
    requires_action: bool = False
    display_label_es: str
    confidence: int = Field(default=90, ge=0, le=100)
    scope: Literal["tenant", "global"] = "tenant"


def _tenant(request: Request) -> str:
    return request.state.user.tenant_id


# --- Endpoints -------------------------------------------------------------
@router.post("/catalog", status_code=201)
async def create_catalog(payload: CatalogCreate, request: Request, _: object = Depends(_RBAC)):
    tenant_id = _tenant(request) if payload.scope == "tenant" else None
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "carrier_id": payload.carrier_id,
        "raw_code": payload.raw_code,
        "api_version": payload.api_version,
        "canonical_status": payload.canonical_status,
        "incident_type": payload.incident_type,
        "is_terminal": payload.is_terminal,
        "requires_action": payload.requires_action,
        "display_label_es": payload.display_label_es,
        "confidence": payload.confidence,
        "active": payload.active,
        "source": "manual",
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.carrier_status_catalog.insert_one(doc)
    except Exception:  # duplicate key
        return ok({"duplicate": True, "carrier_id": payload.carrier_id, "raw_code": payload.raw_code}, status_code=200)
    doc.pop("_id", None)

    audit = CaeAuditRepository(tenant_id=_tenant(request))
    await audit.record(
        user_id=request.state.user.id, action="create",
        entity="carrier_status_catalog", entity_id=doc["id"],
        before_json=None, after_json=doc,
    )
    return ok(doc, status_code=201)


@router.patch("/catalog/{entry_id}")
async def update_catalog(entry_id: str, payload: CatalogUpdate, request: Request,
                         _: object = Depends(_RBAC)):
    db = get_db()
    user = request.state.user
    before = await db.carrier_status_catalog.find_one(
        {"id": entry_id, "$or": [{"tenant_id": user.tenant_id}, {"tenant_id": None}]},
        {"_id": 0},
    )
    if not before:
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.carrier_status_catalog.update_one({"id": entry_id}, {"$set": updates})
    after = await db.carrier_status_catalog.find_one({"id": entry_id}, {"_id": 0})
    await CaeAuditRepository(tenant_id=user.tenant_id).record(
        user_id=user.id, action="update",
        entity="carrier_status_catalog", entity_id=entry_id,
        before_json=before, after_json=after,
    )
    return ok(after)


@router.delete("/catalog/{entry_id}")
async def delete_catalog(entry_id: str, request: Request, _: object = Depends(_RBAC)):
    """Soft delete — sets active=false. Cataloged history must remain (R27)."""
    db = get_db()
    user = request.state.user
    before = await db.carrier_status_catalog.find_one(
        {"id": entry_id, "$or": [{"tenant_id": user.tenant_id}, {"tenant_id": None}]},
        {"_id": 0},
    )
    if not before:
        raise ResourceNotFoundException()
    await db.carrier_status_catalog.update_one(
        {"id": entry_id},
        {"$set": {"active": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await CaeAuditRepository(tenant_id=user.tenant_id).record(
        user_id=user.id, action="delete",
        entity="carrier_status_catalog", entity_id=entry_id,
        before_json=before, after_json={"active": False},
    )
    return ok({"id": entry_id, "active": False})


@router.post("/sandbox")
async def sandbox(payload: SandboxRequest, request: Request, _: object = Depends(_RBAC)):
    """Run the normalizer in dry-run mode without affecting unmapped counters."""
    user = request.state.user
    # Construct a synthetic event but DO NOT call normalize directly because
    # it auto-registers unmapped. Replicate the lookup manually for the sandbox.
    db = get_db()
    row = await db.carrier_status_catalog.find_one(
        {
            "carrier_id": payload.carrier_id,
            "raw_code": payload.raw_code,
            "api_version": payload.api_version,
            "active": True,
            "$or": [{"tenant_id": user.tenant_id}, {"tenant_id": None}],
        },
        {"_id": 0},
        sort=[("tenant_id", -1)],
    )
    if row:
        return ok({
            "matched": True,
            "scope": "tenant" if row.get("tenant_id") == user.tenant_id else "global",
            "canonical_status": row["canonical_status"],
            "incident_type": row.get("incident_type"),
            "is_terminal": row.get("is_terminal", False),
            "requires_action": row.get("requires_action", False),
            "display_label_es": row.get("display_label_es"),
            "confidence": row.get("confidence", 100),
            "source": row.get("source", "manual"),
        })
    # Suggest a default from the in-code adapter if available
    suggestion = None
    cls = ADAPTER_REGISTRY.get(payload.carrier_id)
    if cls and payload.raw_code in cls.NATIVE_CODES:
        c, inc, term, req, label, conf = cls.NATIVE_CODES[payload.raw_code]
        suggestion = {
            "canonical_status": c, "incident_type": inc,
            "is_terminal": term, "requires_action": req,
            "display_label_es": label, "confidence": conf,
            "source": "adapter_default",
        }
    return ok({"matched": False, "suggestion": suggestion})


@router.post("/promote-unmapped", status_code=201)
async def promote_unmapped(payload: PromoteUnmapped, request: Request, _: object = Depends(_RBAC)):
    db = get_db()
    user = request.state.user
    now = datetime.now(timezone.utc).isoformat()
    tenant_id = user.tenant_id if payload.scope == "tenant" else None
    doc = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "carrier_id": payload.carrier_id,
        "raw_code": payload.raw_code,
        "api_version": payload.api_version,
        "canonical_status": payload.canonical_status,
        "incident_type": payload.incident_type,
        "is_terminal": payload.is_terminal,
        "requires_action": payload.requires_action,
        "display_label_es": payload.display_label_es,
        "confidence": payload.confidence,
        "active": True,
        "source": "promoted_from_unmapped",
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.carrier_status_catalog.insert_one(doc)
    except Exception:
        return ok({"duplicate": True}, status_code=200)
    doc.pop("_id", None)
    # Drop the unmapped row now that it has a home
    await db.cae_unmapped_codes.delete_one({
        "carrier_id": payload.carrier_id, "raw_code": payload.raw_code,
        "api_version": payload.api_version,
    })
    await CaeAuditRepository(tenant_id=user.tenant_id).record(
        user_id=user.id, action="create",
        entity="carrier_status_catalog", entity_id=doc["id"],
        before_json=None, after_json=doc,
    )
    return ok(doc, status_code=201)



# ─────────────────────────────────────────────────────────────────────────
# Iter60 — Reclasificación retroactiva de guías existentes según catálogo
# ─────────────────────────────────────────────────────────────────────────
@router.get("/catalog/{entry_id}/reclassify-preview")
async def reclassify_preview(entry_id: str, request: Request,
                             _: object = Depends(_RBAC)):
    """Cuenta cuántas guías del tenant matchean (carrier, raw_code) y desglosa
    su estado actual. Útil antes de ejecutar la reclasificación.
    """
    db = get_db()
    user = request.state.user
    entry = await db.carrier_status_catalog.find_one(
        {"id": entry_id,
         "$or": [{"tenant_id": user.tenant_id}, {"tenant_id": None}]},
        {"_id": 0},
    )
    if not entry:
        raise ResourceNotFoundException()
    pipeline = [
        {"$match": {
            "tenant_id": user.tenant_id,
            "carrier_code": entry["carrier_id"],
            "raw_code": entry["raw_code"],
        }},
        {"$group": {
            "_id": {"internal_status": "$internal_status",
                    "is_terminal": "$is_terminal"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    rows = await db.guias.aggregate(pipeline).to_list(length=50)
    breakdown = [{"internal_status": r["_id"]["internal_status"],
                  "is_terminal": r["_id"]["is_terminal"],
                  "count": r["count"]} for r in rows]
    total = sum(r["count"] for r in breakdown)
    target = {
        "internal_status": entry["canonical_status"],
        "is_terminal": entry.get("is_terminal", False),
        "incident_type": entry.get("incident_type"),
        "requires_action": entry.get("requires_action", False),
    }
    # Cuántas REQUIEREN cambio (estado actual difiere del target)
    needs_change = sum(
        b["count"] for b in breakdown
        if b["internal_status"] != target["internal_status"]
        or bool(b["is_terminal"]) != bool(target["is_terminal"])
    )
    return ok({
        "entry_id": entry_id,
        "carrier_id": entry["carrier_id"],
        "raw_code": entry["raw_code"],
        "total_guias": total,
        "needs_change": needs_change,
        "current_breakdown": breakdown,
        "target": target,
    })


class ReclassifyRequest(BaseModel):
    dry_run: bool = False
    create_tickets: bool = True


@router.post("/catalog/{entry_id}/reclassify")
async def reclassify(entry_id: str, payload: ReclassifyRequest,
                     request: Request, _: object = Depends(_RBAC)):
    """Aplica el mapeo del catálogo a guías existentes (carrier, raw_code).

    Actualiza ``internal_status``, ``is_terminal``, ``incident_type`` y
    (opcionalmente) dispara WorkflowEngine para crear tickets de incidencia
    cuando el target canonical sea ``exception``/``cancelled`` con
    ``requires_action=True``.

    Idempotente: las guías que ya estén en el estado target se omiten.
    Bypasea R02 (terminal-no-overwrite) sólo para esta operación explícita
    de admin — necesaria cuando el remapeo cambia un estado de "terminal"
    (returned) a "no terminal" (exception) o viceversa.
    """
    from services.workflow_engine import WorkflowEngine

    db = get_db()
    user = request.state.user
    entry = await db.carrier_status_catalog.find_one(
        {"id": entry_id,
         "$or": [{"tenant_id": user.tenant_id}, {"tenant_id": None}]},
        {"_id": 0},
    )
    if not entry:
        raise ResourceNotFoundException()

    target_internal = entry["canonical_status"]
    target_terminal = bool(entry.get("is_terminal", False))
    target_incident = entry.get("incident_type")

    match = {
        "tenant_id": user.tenant_id,
        "carrier_code": entry["carrier_id"],
        "raw_code": entry["raw_code"],
    }

    if payload.dry_run:
        total = await db.guias.count_documents(match)
        return ok({"dry_run": True, "would_process": total,
                   "target": {"internal_status": target_internal,
                              "is_terminal": target_terminal}})

    now = datetime.now(timezone.utc).isoformat()
    cursor = db.guias.find(match, {"_id": 0})
    processed = 0
    updated = 0
    tickets_created = 0
    errors: list[str] = []
    wf = WorkflowEngine(tenant_id=user.tenant_id)

    async for guia in cursor:
        processed += 1
        needs_update = (
            guia.get("internal_status") != target_internal
            or bool(guia.get("is_terminal")) != target_terminal
        )
        if needs_update:
            try:
                await db.guias.update_one(
                    {"id": guia["id"]},
                    {"$set": {
                        "internal_status": target_internal,
                        "is_terminal": target_terminal,
                        "updated_at": now,
                    }},
                )
                updated += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"{guia.get('tracking_id')}: {str(e)[:120]}")
                continue

        # Dispara workflow SIEMPRE que el target sea incidencia y la guía
        # aún no tenga ticket abierto. Idempotente vía
        # ``tickets.open_for_guia`` dentro del engine.
        if payload.create_tickets and target_internal in ("exception", "cancelled"):
            refreshed = await db.guias.find_one({"id": guia["id"]},
                                                {"_id": 0})
            if not refreshed:
                continue
            try:
                outcome = await wf.process_post_ingest(
                    guia=refreshed,
                    ingest_action="updated",
                    normalized_canonical=target_internal,
                    normalized_incident_type=target_incident,
                )
                if outcome.action == "ticket_created":
                    tickets_created += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"workflow {guia.get('tracking_id')}: "
                              f"{str(e)[:120]}")

    await CaeAuditRepository(tenant_id=user.tenant_id).record(
        user_id=user.id, action="reclassify",
        entity="carrier_status_catalog", entity_id=entry_id,
        before_json=None,
        after_json={"processed": processed, "updated": updated,
                    "tickets_created": tickets_created,
                    "target_internal_status": target_internal,
                    "target_is_terminal": target_terminal},
    )
    return ok({
        "entry_id": entry_id,
        "carrier_id": entry["carrier_id"],
        "raw_code": entry["raw_code"],
        "processed": processed,
        "updated": updated,
        "tickets_created": tickets_created,
        "errors": errors[:50],
    })
