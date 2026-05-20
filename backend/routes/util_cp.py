"""Lookup de código postal mexicano — Bundle D · Mejora MxAddressInput.

Proxy + cache para `zippopotam.us` (gratuito, sin token). Para CPs mexicanos:
    https://api.zippopotam.us/MX/06700
→ { "country": "Mexico", "country abbreviation": "MX",
    "post code": "06700",
    "places": [{"place name": "Roma Norte", "state": "Ciudad de México", ...}] }

Cache en colección `cp_lookup_cache` (60 días TTL — los CP no cambian).

Si el servicio externo cae, devolvemos el último cache aunque haya expirado.
Aceptable porque los CP son estables.

Rate-limit defensivo (in-memory): 30 req/min por tenant.
"""
from __future__ import annotations
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Path, Request

from core.db import get_db
from core.errors import ErrorCode
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import require_min_role

router = APIRouter(prefix="/api/util", tags=["util-cp"])
_RBAC = require_min_role("agent")  # cualquier usuario logueado puede usarlo

_INDEX_CREATED = False
# Rate-limit muy permisivo por tenant: 30 req/min — anti-abuse de UI.
# Estructura: { tenant_id: [(timestamp_unix), ...] } limpiada lazy.
_rate_limit: dict[str, list[float]] = {}
_RATE_WINDOW_SECS = 60
_RATE_MAX = 30


def _rate_ok(tenant_id: str) -> bool:
    now = time.time()
    window_start = now - _RATE_WINDOW_SECS
    history = [t for t in _rate_limit.get(tenant_id, []) if t > window_start]
    if len(history) >= _RATE_MAX:
        _rate_limit[tenant_id] = history
        return False
    history.append(now)
    _rate_limit[tenant_id] = history
    return True


async def _ensure_index() -> None:
    global _INDEX_CREATED
    if _INDEX_CREATED:
        return
    db = get_db()
    await db.cp_lookup_cache.create_index([("cp", 1)], unique=True)
    await db.cp_lookup_cache.create_index(
        "expires_at", expireAfterSeconds=0,
    )
    _INDEX_CREATED = True


async def _fetch_zippopotam(cp: str) -> Optional[dict]:
    url = f"https://api.zippopotam.us/MX/{cp}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.0)) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return None
        data = r.json()
        places = data.get("places", [])
        if not places:
            return None
        # zippopotam devuelve N places por CP (mismo CP cubre varias colonias).
        # Mapeamos cada uno a colonia + ciudad + estado.
        colonias = []
        for p in places:
            colonias.append({
                "colonia": (p.get("place name") or "").strip(),
                "estado": (p.get("state") or "").strip(),
                "ciudad": (p.get("state") or "").strip(),  # zippopotam no separa
            })
        # Heurística: usar el estado del primer place como estado base.
        return {
            "cp": cp,
            "estado": colonias[0]["estado"] if colonias else "",
            "ciudad": colonias[0]["ciudad"] if colonias else "",
            "colonias": colonias,
        }
    except Exception:  # noqa: BLE001
        return None


@router.get("/cp-lookup/{cp}")
async def cp_lookup(
    request: Request,
    cp: str = Path(min_length=5, max_length=5, pattern=r"^\d{5}$"),
    _: object = Depends(_RBAC),
):
    """Devuelve estado / ciudad / lista de colonias para un CP MX."""
    user = request.state.user
    await _ensure_index()
    db = get_db()

    # Rate limit suave por tenant
    if not _rate_ok(user.tenant_id):
        return fail(ErrorCode.RATE_LIMITED,
                    "Demasiados lookups en el último minuto. Esperá un poco.",
                    field="cp")

    # 1) Cache
    cached = await db.cp_lookup_cache.find_one({"cp": cp}, {"_id": 0})
    if cached and cached.get("expires_at"):
        try:
            exp = datetime.fromisoformat(cached["expires_at"])
            if exp > datetime.now(timezone.utc):
                return ok({"data": cached["data"], "source": "cache"})
        except Exception:  # noqa: BLE001
            pass

    # 2) Fetch externo
    data = await _fetch_zippopotam(cp)
    if not data:
        # Fallback: si tenemos un cache expirado, devolverlo (mejor que nada)
        if cached:
            return ok({"data": cached["data"], "source": "stale_cache"})
        return fail(ErrorCode.RESOURCE_NOT_FOUND,
                    f"No se encontró el código postal {cp}.",
                    field="cp")

    # 3) Persistir cache (60 días)
    now = datetime.now(timezone.utc)
    await db.cp_lookup_cache.update_one(
        {"cp": cp},
        {"$set": {
            "cp": cp,
            "data": data,
            "fetched_at": now.isoformat(),
            "expires_at": (now + timedelta(days=60)).isoformat(),
        }, "$setOnInsert": {"id": new_id()}},
        upsert=True,
    )
    return ok({"data": data, "source": "zippopotam"})
