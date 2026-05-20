"""Carrier health & tracking — endpoints transversales (PROMPT 20).

Estos endpoints despachan a los adapters registrados en ADAPTER_REGISTRY,
así que sirven a CUALQUIER carrier (Routal hoy; FedEx/DHL/etc. cuando dejen
de ser mocks). El carrier se identifica por su `id` (UUID) o por su `code`
(ej. "routal") dentro del tenant del usuario.

  GET  /api/admin/carriers/{carrier_id_or_code}/health
  POST /api/admin/carriers/{carrier_id_or_code}/track  body={tracking_id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from core.errors import ErrorCode, ResourceNotFoundException
from core.response import fail, ok
from middleware.rbac import require_min_role
from repositories.carriers import CarrierRepository
from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY
from services.cae.normalizer import StatusNormalizer

router = APIRouter(prefix="/api/admin/carriers", tags=["admin-carriers-health"])
_RBAC = require_min_role("admin")


class TrackRequest(BaseModel):
    tracking_id: str = Field(min_length=1, max_length=128)


async def _resolve_carrier(request: Request, identifier: str) -> dict:
    """Busca el carrier por id o code dentro del tenant. Devuelve el doc o
    levanta 404. Centraliza la transversalidad: cualquier carrier creado en
    /admin/jerarquia es enrutable aquí."""
    repo = CarrierRepository(tenant_id=request.state.user.tenant_id)
    doc = await repo.find_one({"id": identifier})
    if not doc:
        doc = await repo.find_one({"code": identifier})
    if not doc:
        raise ResourceNotFoundException("Carrier no encontrado.")
    return doc


@router.get("/{carrier_id}/health")
async def carrier_health(
    request: Request,
    carrier_id: str = Path(..., min_length=1, max_length=128),
    _: object = Depends(_RBAC),
):
    carrier = await _resolve_carrier(request, carrier_id)
    code = carrier.get("code")
    AdapterCls = ADAPTER_REGISTRY.get(code)
    if AdapterCls is None:
        return ok({
            "carrier_id": carrier["id"], "code": code, "name": carrier.get("name"),
            "has_adapter": False, "configured": False, "pingable": False,
            "is_mock": False, "note": "No hay adapter registrado para este code.",
        })
    adapter = AdapterCls()
    pingable = False
    try:
        pingable = await adapter.validate_config()
    except Exception:  # noqa: BLE001
        pingable = False
    is_mock = code in {"fedex", "dhl", "estafeta", "99min", "paqex"}
    return ok({
        "carrier_id": carrier["id"], "code": code, "name": carrier.get("name"),
        "has_adapter": True,
        "is_mock": is_mock,
        "configured": pingable or is_mock,
        "pingable": pingable,
    })


@router.post("/{carrier_id}/track")
async def carrier_track(
    payload: TrackRequest,
    request: Request,
    carrier_id: str = Path(..., min_length=1, max_length=128),
    _: object = Depends(_RBAC),
):
    user = request.state.user
    carrier = await _resolve_carrier(request, carrier_id)
    code = carrier.get("code")
    AdapterCls = ADAPTER_REGISTRY.get(code)
    if AdapterCls is None:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"No hay adapter para carrier code={code!r}.")
    adapter = AdapterCls()
    try:
        raw_event = await adapter.get_raw_status(payload.tracking_id)
    except Exception as e:  # noqa: BLE001
        return fail(ErrorCode.VALIDATION_FAILED, str(e))
    normalizer = StatusNormalizer(tenant_id=user.tenant_id)
    normalized = await normalizer.normalize(raw_event)
    return ok({
        "carrier": {"id": carrier["id"], "code": code, "name": carrier.get("name")},
        "raw": {
            "carrier_id": raw_event.carrier_id,
            "tracking_id": raw_event.tracking_id,
            "raw_code": raw_event.raw_code,
            "raw_description": raw_event.raw_description,
            "raw_payload": raw_event.raw_payload,
            "api_version": raw_event.api_version,
            "event_at": raw_event.event_at.isoformat(),
        },
        "normalized": {
            "canonical_status": normalized.canonical_status,
            "incident_type": normalized.incident_type,
            "is_terminal": normalized.is_terminal,
            "requires_action": normalized.requires_action,
            "display_label_es": normalized.display_label_es,
            "confidence": normalized.confidence,
        },
    })
