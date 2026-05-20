"""Bundle D · Parte 2 — Endpoint admin de tipos de cambio."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.errors import ErrorCode
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import require_min_role
from services.currency import currency_service

router = APIRouter(prefix="/api/admin/currency", tags=["admin-currency"])
_RBAC = require_min_role("admin")
_SUPERADMIN = require_min_role("superadmin")


@router.get("/rates")
async def list_rates(request: Request, _: object = Depends(_RBAC)):
    """Devuelve tipos de cambio cacheados + última actualización."""
    db = get_db()
    pairs = [("USD", "MXN"), ("EUR", "MXN"), ("MXN", "USD")]
    rates = []
    for from_c, to_c in pairs:
        info = await currency_service.get_rate(from_c, to_c)
        rates.append(info.as_dict())
    last_call = await db.currency_rates_history.find_one(
        {}, {"_id": 0, "fetched_at": 1, "source": 1},
        sort=[("fetched_at", -1)],
    )
    return ok({
        "rates": rates,
        "last_call": last_call,
        "cache_status": "fresh" if last_call else "empty",
    })


class ManualOverrideBody(BaseModel):
    from_curr: Literal["USD", "MXN", "EUR"] = Field(...)
    to_curr: Literal["USD", "MXN", "EUR"] = Field(...)
    rate: float = Field(gt=0)


@router.put("/manual-override")
async def set_manual_override(payload: ManualOverrideBody, request: Request,
                              _: object = Depends(_SUPERADMIN)):
    if payload.from_curr == payload.to_curr:
        return fail(ErrorCode.VALIDATION_FAILED, "from y to no pueden ser iguales",
                    field="from_curr")
    db = get_db()
    user = request.state.user
    now = datetime.now(timezone.utc).isoformat()
    await db.currency_rates_manual.update_one(
        {"from_curr": payload.from_curr, "to_curr": payload.to_curr},
        {"$set": {
            "rate": payload.rate, "updated_at": now,
            "updated_by": user.id,
        }, "$setOnInsert": {"id": new_id(), "created_at": now}},
        upsert=True,
    )
    # Invalidar cache para forzar refetch
    await db.currency_rates_history.delete_many({
        "from_curr": payload.from_curr, "to_curr": payload.to_curr,
    })
    return ok({"updated": True, "from": payload.from_curr,
               "to": payload.to_curr, "rate": payload.rate})
