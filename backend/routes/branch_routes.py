"""
Client branches (sucursales) — RT-13 / iter71.

A "branch" is a sub-unit of a client (e.g. Cubbo CDMX, GDL, MOR, MTY, PUE, QRO).
Each branch can have its own Routal API key + project_id (RT-01) and is the unit
where SEL01 selection runs (then aggregated to client level — RT-09).

Schema (collection: client_branches):
    {
      "id": uuid,
      "client_id": <Client.id>,
      "code": "CDMX" | "GDL" | "MOR" | "MTY" | "PUE" | "QRO" | <free>,
      "name": "Cubbo CDMX",
      "active": bool,
      "created_at": iso,
      "updated_at": iso,
    }

Migrations: legacy journeys without branch_id keep working — branch_id is optional
on journeys/packages and only used by the new SEL01 multi-project flow.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies import get_current_user, db

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_CODES_HINT = {"CDMX", "GDL", "MOR", "MTY", "PUE", "QRO", "PACHUCA"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_role(user: dict, roles: list):
    role = user.get("role")
    if role not in roles:
        raise HTTPException(status_code=403, detail=f"Requiere rol: {' o '.join(roles)}")


class BranchCreate(BaseModel):
    client_id: str
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=200)
    active: bool = True


class BranchUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=32)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    active: Optional[bool] = None


class BranchResponse(BaseModel):
    id: str
    client_id: str
    client_name: Optional[str] = None
    code: str
    name: str
    active: bool
    created_at: str
    updated_at: str
    journeys_count: Optional[int] = None
    has_routal_credentials: Optional[bool] = None


@router.get("/branches", response_model=List[BranchResponse])
async def list_branches(
    client_id: Optional[str] = None,
    active_only: bool = False,
    user: dict = Depends(get_current_user),
):
    """List all branches (optionally filtered by client_id and active status)."""
    q = {}
    if client_id:
        q["client_id"] = client_id
    if active_only:
        q["active"] = True

    # Collect client names in one query
    clients_map = {c["id"]: c["name"] async for c in db.clients.find({}, {"_id": 0, "id": 1, "name": 1})}

    out = []
    async for b in db.branches.find(q, {"_id": 0}).sort([("client_id", 1), ("code", 1)]):
        b["client_name"] = clients_map.get(b["client_id"])
        # journeys count (best-effort)
        b["journeys_count"] = await db.journeys.count_documents({"branch_id": b["id"]})
        # has_routal_credentials: check client_integrations.branches[branch_id]
        integ = await db.client_integrations.find_one(
            {"client_id": b["client_id"], "integration_type": "routal", "status": "active"},
            {"_id": 0, "branches": 1},
        )
        has_creds = False
        if integ:
            br_map = integ.get("branches") or {}
            entry = br_map.get(b["id"])
            if entry and entry.get("active", True) and entry.get("credentials_encrypted"):
                has_creds = True
        b["has_routal_credentials"] = has_creds
        out.append(b)
    return out


@router.post("/branches", response_model=BranchResponse)
async def create_branch(
    payload: BranchCreate,
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer", "coordinator"])
    # Validate client exists
    cli = await db.clients.find_one({"id": payload.client_id}, {"_id": 0, "id": 1, "name": 1})
    if not cli:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    # Unique (client_id, code) — case-insensitive
    code_upper = payload.code.upper()
    existing = await db.branches.find_one(
        {"client_id": payload.client_id, "code": code_upper},
        {"_id": 0, "id": 1},
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Ya existe sucursal '{code_upper}' para este cliente")
    doc = {
        "id": str(uuid.uuid4()),
        "client_id": payload.client_id,
        "code": code_upper,
        "name": payload.name,
        "active": payload.active,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.branches.insert_one(doc)
    logger.info(f"[branches] created {doc['id']} {cli['name']}/{code_upper} by {user.get('email')}")
    doc["client_name"] = cli["name"]
    doc["journeys_count"] = 0
    doc["has_routal_credentials"] = False
    return doc


@router.patch("/branches/{branch_id}", response_model=BranchResponse)
async def update_branch(
    branch_id: str,
    payload: BranchUpdate,
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer", "coordinator"])
    update = {}
    if payload.code is not None:
        update["code"] = payload.code.upper()
    if payload.name is not None:
        update["name"] = payload.name
    if payload.active is not None:
        update["active"] = payload.active
    if not update:
        raise HTTPException(status_code=400, detail="Sin cambios")
    update["updated_at"] = _now()
    res = await db.branches.update_one({"id": branch_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    b = await db.branches.find_one({"id": branch_id}, {"_id": 0})
    cli = await db.clients.find_one({"id": b["client_id"]}, {"_id": 0, "name": 1})
    b["client_name"] = cli["name"] if cli else None
    b["journeys_count"] = await db.journeys.count_documents({"branch_id": branch_id})
    b["has_routal_credentials"] = False  # cheap default; UI re-fetches list to refresh
    logger.info(f"[branches] updated {branch_id} by {user.get('email')} → {update}")
    return b


@router.delete("/branches/{branch_id}")
async def delete_branch(
    branch_id: str,
    user: dict = Depends(get_current_user),
):
    _require_role(user, ["developer"])
    # Soft-delete: mark inactive instead of removing (preserves journey history)
    res = await db.branches.update_one(
        {"id": branch_id},
        {"$set": {"active": False, "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    logger.info(f"[branches] soft-deleted {branch_id} by {user.get('email')}")
    return {"ok": True, "soft_deleted": True}


@router.post("/branches/migrate-cubbo-cities")
async def migrate_cubbo_cities(
    dry_run: bool = True,
    user: dict = Depends(get_current_user),
):
    """One-shot migration helper: for the Cubbo client, create branches CDMX/GDL/MOR/MTY/PUE/QRO
    if they don't exist. Idempotent.
    """
    _require_role(user, ["developer"])
    cubbo = await db.clients.find_one({"name": {"$regex": "^Cubbo$", "$options": "i"}}, {"_id": 0, "id": 1, "name": 1})
    if not cubbo:
        raise HTTPException(status_code=404, detail="Cliente Cubbo no encontrado")
    target_codes = ["CDMX", "GDL", "MOR", "MTY", "PUE", "QRO"]
    created = []
    skipped = []
    for code in target_codes:
        ex = await db.branches.find_one({"client_id": cubbo["id"], "code": code}, {"_id": 0, "id": 1})
        if ex:
            skipped.append(code)
            continue
        if not dry_run:
            doc = {
                "id": str(uuid.uuid4()),
                "client_id": cubbo["id"],
                "code": code,
                "name": f"Cubbo {code}",
                "active": True,
                "created_at": _now(),
                "updated_at": _now(),
            }
            await db.branches.insert_one(doc)
        created.append(code)
    return {
        "ok": True,
        "dry_run": dry_run,
        "client_id": cubbo["id"],
        "client_name": cubbo["name"],
        "created": created,
        "skipped_existing": skipped,
    }


# ─────────────── Branch-level Routal credentials (RT-01) ───────────────

class BranchRoutalCredsPayload(BaseModel):
    routal_api_key: Optional[str] = None
    routal_project_id: Optional[str] = None
    routal_webhook_secret: Optional[str] = None
    active: Optional[bool] = None


@router.put("/branches/{branch_id}/routal-credentials")
async def set_branch_routal_credentials(
    branch_id: str,
    payload: BranchRoutalCredsPayload,
    user: dict = Depends(get_current_user),
):
    """Set or update Routal API credentials for a specific branch (RT-01 multi-project).
    Each branch (e.g. Cubbo CDMX, Cubbo GDL) has its own api_key + project_id.
    """
    _require_role(user, ["developer", "coordinator"])
    branch = await db.branches.find_one({"id": branch_id}, {"_id": 0})
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    from services.integration_service import IntegrationService
    svc = IntegrationService(db)
    try:
        result = await svc.set_branch_credentials(
            client_id=branch["client_id"],
            branch_id=branch_id,
            api_key=payload.routal_api_key,
            project_id=payload.routal_project_id,
            webhook_secret=payload.routal_webhook_secret,
            active=payload.active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info(f"[branches] {user.get('email')} updated routal creds for branch={branch_id}")
    result["branch"] = branch
    return result


@router.get("/branches/{branch_id}/routal-credentials")
async def get_branch_routal_credentials(
    branch_id: str,
    user: dict = Depends(get_current_user),
):
    """Returns metadata about a branch's Routal credentials (booleans, never raw values)."""
    _require_role(user, ["developer", "coordinator"])
    branch = await db.branches.find_one({"id": branch_id}, {"_id": 0})
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    integ = await db.client_integrations.find_one(
        {"client_id": branch["client_id"], "integration_type": "routal"},
        {"_id": 0, "branches": 1},
    )
    if not integ:
        return {"branch_id": branch_id, "configured": False, "active": False}
    branches = integ.get("branches") or {}
    entry = branches.get(branch_id)
    if not entry:
        return {"branch_id": branch_id, "configured": False, "active": False}
    from utils.encryption import decrypt_credentials, public_credentials_summary
    creds = decrypt_credentials(entry.get("credentials_encrypted") or "")
    return {
        "branch_id": branch_id,
        "configured": bool(entry.get("credentials_encrypted")),
        "active": entry.get("active", True),
        "credentials_summary": public_credentials_summary(creds),
        "updated_at": entry.get("updated_at"),
    }


@router.patch("/branches/{branch_id}/routal-toggle")
async def toggle_branch_routal(
    branch_id: str,
    active: bool,
    user: dict = Depends(get_current_user),
):
    """Enable/disable Routal integration for this branch (RT-02 manual rollback).
    When disabled, this branch falls back to Kosmo flow (no webhook processing,
    no SEL01 routal sync).
    """
    _require_role(user, ["developer", "coordinator"])
    branch = await db.branches.find_one({"id": branch_id}, {"_id": 0})
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    integ = await db.client_integrations.find_one(
        {"client_id": branch["client_id"], "integration_type": "routal"},
        {"_id": 0, "branches": 1},
    )
    if not integ:
        raise HTTPException(status_code=400, detail="Cliente sin integración Routal")
    branches = integ.get("branches") or {}
    if branch_id not in branches:
        raise HTTPException(status_code=400, detail="Sucursal sin credenciales Routal configuradas")
    branches[branch_id]["active"] = active
    branches[branch_id]["updated_at"] = _now()
    await db.client_integrations.update_one(
        {"client_id": branch["client_id"], "integration_type": "routal"},
        {"$set": {"branches": branches, "updated_at": datetime.now(timezone.utc)}},
    )
    logger.info(f"[branches] {user.get('email')} toggled branch={branch_id} routal active={active}")
    return {"ok": True, "branch_id": branch_id, "active": active}
