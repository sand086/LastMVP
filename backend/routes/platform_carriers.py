"""Platform-level carrier endpoints (root_dev / superadmin only).

  GET    /api/platform/carriers                        — list all
  GET    /api/platform/carriers/{code}                 — single carrier cfg
  PUT    /api/platform/carriers/{code}                 — upsert cfg (secrets cifrados)
  DELETE /api/platform/carriers/{code}                 — drop platform cfg
  POST   /api/platform/carriers/{code}/test            — live ping with platform creds
  PUT    /api/platform/carriers/{code}/access/{tenant} — grant/update tenant whitelist
  DELETE /api/platform/carriers/{code}/access/{tenant} — revoke tenant access

The /test endpoint is platform-level (no per-tenant filtering). The whitelist
enforcement only applies when tenants RESOLVE the platform creds via the
``carrier_config_resolver``.
"""
from __future__ import annotations
from typing import Optional, Literal

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.errors import ErrorCode, ResourceNotFoundException
from core.response import fail, ok
from middleware.rbac import require_role
from repositories.platform_carriers import PlatformCarrierRepository
from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY


router = APIRouter(prefix="/api/platform/carriers",
                    tags=["platform-carriers"])
_RBAC = require_role("root_dev", "superadmin")


class PlatformCarrierPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, max_length=120)
    api_key: Optional[str] = Field(default=None, max_length=4096)
    client_secret: Optional[str] = Field(default=None, max_length=4096)
    base_url: Optional[str] = Field(default=None, max_length=500)
    enabled: Optional[bool] = None
    billing_mode: Optional[Literal["platform_pays",
                                    "tenant_pays_overage"]] = None


class TenantAccessPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_ids: Optional[list[str]] = Field(default=None, max_length=50)
    rate_limit_per_min: Optional[int] = Field(default=None, ge=1, le=10_000)
    enabled: bool = True

    @field_validator("project_ids")
    @classmethod
    def _validate_projects(cls, v):
        if v is None:
            return None
        cleaned = [p.strip() for p in v if isinstance(p, str) and p.strip()]
        # de-dup preserving order
        seen, out = set(), []
        for p in cleaned:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out


class TestRequest(BaseModel):
    tracking_id: Optional[str] = Field(default=None, max_length=128)


@router.get("")
async def list_platform_carriers(
    request: Request, _: object = Depends(_RBAC),
):
    repo = PlatformCarrierRepository()
    items = await repo.list_all()
    from repositories.platform_carriers import public_view
    return ok({"items": [public_view(c) for c in items],
                "total": len(items)})


@router.get("/{code}")
async def get_platform_carrier(
    request: Request,
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    repo = PlatformCarrierRepository()
    cfg = await repo.get(code)
    if not cfg:
        return ok({"code": code, "configured": False})
    from repositories.platform_carriers import public_view
    return ok({"code": code, "configured": True, **public_view(cfg)})


@router.put("/{code}")
async def put_platform_carrier(
    payload: PlatformCarrierPut,
    request: Request,
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    repo = PlatformCarrierRepository()
    patch = payload.model_dump(exclude_unset=True)
    cfg = await repo.upsert(code, patch)
    return ok({"code": code, "configured": True, **cfg})


@router.delete("/{code}")
async def delete_platform_carrier(
    request: Request,
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    repo = PlatformCarrierRepository()
    deleted = await repo.delete(code)
    return ok({"deleted": deleted})


@router.post("/{code}/test")
async def test_platform_carrier(
    payload: TestRequest,
    request: Request,
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    _: object = Depends(_RBAC),
):
    AdapterCls = ADAPTER_REGISTRY.get(code)
    if AdapterCls is None:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"No hay adapter registrado para {code!r}")
    repo = PlatformCarrierRepository()
    cfg = await repo.get_decrypted(code)
    if not cfg or not cfg.get("api_key"):
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Platform carrier sin api_key configurada")
    kwargs = {
        "api_key": cfg["api_key"],
        "base_url": cfg.get("base_url"),
    }
    # FedEx needs client_secret too; safe to pass via kwarg (DHL ignores it).
    if cfg.get("client_secret"):
        kwargs["client_secret"] = cfg["client_secret"]
    adapter = AdapterCls(**kwargs)
    if not payload.tracking_id:
        pingable = False
        try:
            pingable = await adapter.validate_config()
        except Exception:  # noqa: BLE001
            pingable = False
        return ok({"configured": True, "pingable": pingable})
    try:
        event = await adapter.get_raw_status(payload.tracking_id)
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


@router.put("/{code}/access/{tenant_id}")
async def grant_tenant_access(
    payload: TenantAccessPut,
    request: Request,
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    tenant_id: str = Path(..., min_length=36, max_length=36),
    _: object = Depends(_RBAC),
):
    repo = PlatformCarrierRepository()
    body = payload.model_dump()
    result = await repo.grant_access(
        code, tenant_id,
        project_ids=body.get("project_ids"),
        rate_limit_per_min=body.get("rate_limit_per_min"),
        enabled=body.get("enabled", True),
    )
    if result is None:
        raise ResourceNotFoundException(
            f"No existe la config de plataforma para {code!r}")
    return ok({"code": code, "tenant_id": tenant_id, **result})


@router.delete("/{code}/access/{tenant_id}")
async def revoke_tenant_access(
    request: Request,
    code: str = Path(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$"),
    tenant_id: str = Path(..., min_length=36, max_length=36),
    _: object = Depends(_RBAC),
):
    repo = PlatformCarrierRepository()
    revoked = await repo.revoke_access(code, tenant_id)
    return ok({"revoked": revoked})
