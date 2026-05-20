"""Per-client carrier configuration (multi-project SaaS) — PROMPT 20.x

Today only Routal needs this (1 ApiKey → N project_ids), but the schema is
generic enough to host the same pattern for FedEx (multi-account), DHL OAuth
per account, etc.

  GET    /api/admin/clients/{client_id}/carriers/{code}
  PUT    /api/admin/clients/{client_id}/carriers/{code}
  DELETE /api/admin/clients/{client_id}/carriers/{code}
  POST   /api/admin/clients/{client_id}/carriers/{code}/test
            body={tracking_id?: str, project_id?: str}

All routes are admin+ scoped and tenant-isolated.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from core.errors import ErrorCode, ResourceNotFoundException
from core.response import fail, ok
from middleware.rbac import require_min_role
from models.admin import ClientCarrierConfigPut
from repositories.clients import ClientRepository
from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY


router = APIRouter(prefix="/api/admin/clients",
                    tags=["admin-client-carriers"])
_RBAC = require_min_role("admin")


class TestRequest(BaseModel):
    tracking_id: str | None = Field(default=None, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)


async def _resolve_client(request: Request, client_id: str) -> dict:
    repo = ClientRepository(tenant_id=request.state.user.tenant_id)
    doc = await repo.find_one({"id": client_id})
    if not doc:
        raise ResourceNotFoundException("Cliente no encontrado.")
    return doc


@router.get("/{client_id}/carriers/{code}")
async def get_carrier_config(
    request: Request,
    client_id: str = Path(..., min_length=36, max_length=36),
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    await _resolve_client(request, client_id)
    repo = ClientRepository(tenant_id=request.state.user.tenant_id)
    cfg = await repo.get_carrier_config_public(client_id, code)
    if not cfg:
        return ok({"carrier_code": code, "configured": False})
    return ok({"carrier_code": code, "configured": True, **cfg})


@router.put("/{client_id}/carriers/{code}")
async def put_carrier_config(
    payload: ClientCarrierConfigPut,
    request: Request,
    client_id: str = Path(..., min_length=36, max_length=36),
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    await _resolve_client(request, client_id)
    repo = ClientRepository(tenant_id=request.state.user.tenant_id)
    patch = payload.model_dump(exclude_unset=True)
    cfg = await repo.set_carrier_config(client_id, code, patch)
    return ok({"carrier_code": code, "configured": True, **cfg})


@router.delete("/{client_id}/carriers/{code}")
async def delete_carrier_config(
    request: Request,
    client_id: str = Path(..., min_length=36, max_length=36),
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    await _resolve_client(request, client_id)
    repo = ClientRepository(tenant_id=request.state.user.tenant_id)
    deleted = await repo.delete_carrier_config(client_id, code)
    return ok({"deleted": deleted})


@router.post("/{client_id}/carriers/{code}/test")
async def test_carrier_config(
    payload: TestRequest,
    request: Request,
    client_id: str = Path(..., min_length=36, max_length=36),
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    """Live probe of the per-client config.

    * Sin tracking_id: corre `validate_config()` (lista 1 plan en el primer
      project) y devuelve `{pingable: bool}`.
    * Con tracking_id: hace `get_raw_status(tracking_id, project_id?)` y
      devuelve el evento raw + normalized.
    """
    await _resolve_client(request, client_id)
    AdapterCls = ADAPTER_REGISTRY.get(code)
    if AdapterCls is None:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"No hay adapter registrado para {code!r}")
    repo = ClientRepository(tenant_id=request.state.user.tenant_id)
    cfg = await repo.get_carrier_config(client_id, code)
    if not cfg or not cfg.get("api_key"):
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Cliente sin api_key configurada para este carrier")
    adapter = AdapterCls(
        api_key=cfg["api_key"],
        project_ids=cfg["project_ids"],
        base_url=cfg.get("base_url"),
    )
    if not payload.tracking_id:
        pingable = False
        try:
            pingable = await adapter.validate_config()
        except Exception:  # noqa: BLE001
            pingable = False
        return ok({
            "configured": True,
            "pingable": pingable,
            "project_ids": cfg["project_ids"],
            "default_project_id": cfg.get("default_project_id"),
        })
    try:
        event = await adapter.get_raw_status(payload.tracking_id,
                                              project_id=payload.project_id)
    except Exception as e:  # noqa: BLE001
        return fail(ErrorCode.VALIDATION_FAILED, str(e))
    return ok({
        "configured": True,
        "raw": {
            "raw_code": event.raw_code,
            "raw_description": event.raw_description,
            "raw_payload": event.raw_payload,
            "event_at": event.event_at.isoformat(),
        },
    })
