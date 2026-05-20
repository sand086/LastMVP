"""Hierarchy admin — projects/clients/subclients/carriers within current tenant.

Per sec 8.3: admin / coordinator / superadmin / root_dev can manage hierarchy.
All endpoints are tenant-scoped — repositories enforce R01.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request

from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from models.admin import (
    CarrierCreate, CarrierUpdate,
    ClientCreate, ClientUpdate,
    ProjectCreate, ProjectUpdate,
    SubclientCreate, SubclientUpdate,
)
from repositories.carriers import CarrierRepository, public_view as carrier_public
from repositories.clients import ClientRepository, public_view as client_public
from repositories.projects import ProjectRepository
from repositories.subclients import SubclientRepository

router = APIRouter(prefix="/api/admin", tags=["admin-hierarchy"])

_RBAC = require_min_role("admin")


def _tenant_id(request: Request) -> str:
    return request.state.user.tenant_id


# ---------- PROJECTS ------------------------------------------------------
@router.get("/projects")
async def list_projects(request: Request, _: object = Depends(_RBAC)):
    repo = ProjectRepository(tenant_id=_tenant_id(request))
    items = await repo.find({}, sort=[("created_at", 1)], limit=500)
    return ok({"items": items, "count": len(items)})


@router.post("/projects", status_code=201)
async def create_project(payload: ProjectCreate, request: Request, _: object = Depends(_RBAC)):
    repo = ProjectRepository(tenant_id=_tenant_id(request))
    doc = await repo.create(name=payload.name, status=payload.status)
    return ok(doc, status_code=201)


@router.patch("/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdate, request: Request,
                         _: object = Depends(_RBAC)):
    repo = ProjectRepository(tenant_id=_tenant_id(request))
    if not await repo.find_one({"id": project_id}):
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        await repo.update_one({"id": project_id}, updates)
    refreshed = await repo.find_one({"id": project_id})
    return ok(refreshed)


# ---------- CLIENTS -------------------------------------------------------
@router.get("/clients")
async def list_clients(request: Request, _: object = Depends(_RBAC)):
    repo = ClientRepository(tenant_id=_tenant_id(request))
    rows = await repo.find({}, sort=[("created_at", 1)], limit=500)
    return ok({"items": [client_public(r) for r in rows], "count": len(rows)})


@router.post("/clients", status_code=201)
async def create_client(payload: ClientCreate, request: Request, _: object = Depends(_RBAC)):
    tenant_id = _tenant_id(request)
    # Verify the project belongs to the same tenant — R01 + R08
    pj_repo = ProjectRepository(tenant_id=tenant_id)
    if not await pj_repo.find_one({"id": payload.project_id}):
        raise ResourceNotFoundException("Proyecto no encontrado en este tenant.")
    repo = ClientRepository(tenant_id=tenant_id)
    doc = await repo.create(
        project_id=payload.project_id,
        name=payload.name,
        ingest_mode=payload.ingest_mode,
        api_url=payload.api_url,
        api_auth_type=payload.api_auth_type,
        api_creds=payload.api_creds,
        pulling_freq_min=payload.pulling_freq_min,
        preferred_channel=payload.preferred_channel,
        ops_contact_name=payload.ops_contact_name,
        ops_contact_email=payload.ops_contact_email,
        ops_contact_wa=payload.ops_contact_wa,
        cxc_contact_name=payload.cxc_contact_name,
        cxc_contact_email=payload.cxc_contact_email,
        status_map=payload.status_map,
    )
    return ok(client_public(doc), status_code=201)


@router.patch("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientUpdate, request: Request,
                        _: object = Depends(_RBAC)):
    repo = ClientRepository(tenant_id=_tenant_id(request))
    if not await repo.find_one({"id": client_id}):
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        await repo.update_with_secret(client_id, updates)
    refreshed = await repo.find_one({"id": client_id})
    return ok(client_public(refreshed))


# ---------- SUBCLIENTS ----------------------------------------------------
@router.get("/subclients")
async def list_subclients(request: Request, _: object = Depends(_RBAC)):
    repo = SubclientRepository(tenant_id=_tenant_id(request))
    items = await repo.find({}, sort=[("created_at", 1)], limit=500)
    return ok({"items": items, "count": len(items)})


@router.post("/subclients", status_code=201)
async def create_subclient(payload: SubclientCreate, request: Request, _: object = Depends(_RBAC)):
    tenant_id = _tenant_id(request)
    cli_repo = ClientRepository(tenant_id=tenant_id)
    if not await cli_repo.find_one({"id": payload.client_id}):
        raise ResourceNotFoundException("Cliente no encontrado en este tenant.")
    repo = SubclientRepository(tenant_id=tenant_id)
    doc = await repo.create(client_id=payload.client_id, name=payload.name, status=payload.status)
    return ok(doc, status_code=201)


@router.patch("/subclients/{subclient_id}")
async def update_subclient(subclient_id: str, payload: SubclientUpdate, request: Request,
                           _: object = Depends(_RBAC)):
    repo = SubclientRepository(tenant_id=_tenant_id(request))
    if not await repo.find_one({"id": subclient_id}):
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        await repo.update_one({"id": subclient_id}, updates)
    return ok(await repo.find_one({"id": subclient_id}))


# ---------- CARRIERS ------------------------------------------------------
@router.get("/carriers")
async def list_carriers(request: Request, _: object = Depends(_RBAC)):
    repo = CarrierRepository(tenant_id=_tenant_id(request))
    rows = await repo.find({}, sort=[("created_at", 1)], limit=500)
    return ok({"items": [carrier_public(r) for r in rows], "count": len(rows)})


@router.post("/carriers", status_code=201)
async def create_carrier(payload: CarrierCreate, request: Request, _: object = Depends(_RBAC)):
    repo = CarrierRepository(tenant_id=_tenant_id(request))
    # Code is unique per tenant
    existing = await repo.find_one({"code": payload.code})
    if existing:
        return ok(carrier_public(existing), status_code=200)
    doc = await repo.create(
        name=payload.name, code=payload.code, has_api=payload.has_api,
        api_url=payload.api_url, api_creds=payload.api_creds,
        pulling_supported=payload.pulling_supported,
        webhook_supported=payload.webhook_supported,
        status=payload.status,
    )
    return ok(carrier_public(doc), status_code=201)


@router.patch("/carriers/{carrier_id}")
async def update_carrier(carrier_id: str, payload: CarrierUpdate, request: Request,
                         _: object = Depends(_RBAC)):
    repo = CarrierRepository(tenant_id=_tenant_id(request))
    if not await repo.find_one({"id": carrier_id}):
        raise ResourceNotFoundException()
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        await repo.update_with_secret(carrier_id, updates)
    return ok(carrier_public(await repo.find_one({"id": carrier_id})))
