"""Geocoding service con Nominatim/OSM (PROMPT 22).

Política de uso:
  - Max 1 req/s (límite Nominatim free)
  - User-Agent identificable obligatorio
  - Resultados se cachean en `geocode_cache` para evitar re-llamar
"""
from __future__ import annotations
import asyncio
import os
import time
from datetime import datetime, timezone

import httpx

from core.db import get_db
from core.logger import log
from core.uuid import new_id

_NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
_USER_AGENT = os.environ.get("NOMINATIM_USER_AGENT", "MyExcellence/2.1 (ops@myexcellence.local)")
_LAST_CALL = 0.0
_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _rate_limit():
    """Nominatim policy: max 1 req/s."""
    global _LAST_CALL
    async with _lock:
        wait = 1.0 - (time.monotonic() - _LAST_CALL)
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST_CALL = time.monotonic()


async def _cache_get(key: str) -> dict | None:
    db = get_db()
    doc = await db.geocode_cache.find_one({"key": key}, {"_id": 0})
    if not doc:
        return None
    # Iter53 — si lat=None y la cache es vieja (>24h), invalidamos para
    # reintentar. Direcciones que antes fallaron pueden resolverse tras
    # mejoras al pipeline (e.g. cleanup de encoding).
    if doc.get("lat") is None:
        from datetime import datetime as _dt, timezone as _tz, timedelta
        cached_at = doc.get("cached_at")
        if cached_at:
            try:
                age = _dt.now(_tz.utc) - _dt.fromisoformat(cached_at)
                if age > timedelta(hours=24):
                    return None  # stale negative cache → retry
            except Exception:  # noqa: BLE001
                return None
    return doc


async def _cache_put(key: str, lat: float | None, lng: float | None,
                     display_name: str | None) -> None:
    db = get_db()
    await db.geocode_cache.update_one(
        {"key": key},
        {"$set": {
            "key": key, "lat": lat, "lng": lng,
            "display_name": display_name,
            "cached_at": _now_iso(),
        }, "$setOnInsert": {"id": new_id()}},
        upsert=True,
    )


def _build_geocode_query(*, address: str | None,
                         state: str | None = None,
                         cp: str | None = None) -> str | None:
    """Iter53 — arma una query optimizada para Nominatim.

    Estrategia: para heatmaps de operación CS la **zona** (colonia, municipio)
    importa más que la casa exacta. Extraemos lo que sigue a "col." (Colonia
    + Municipio en Layout V2 MX) y agregamos estado + CP + país.

    Ejemplos de input:
      "Privada Jimenez,444 SN  col. Guadalupe Centro, Guadalupe"
    Output:
      "Guadalupe Centro, Guadalupe, Nuevo León, 67100, México"

    Si el address no tiene "col.", caemos al address completo limpiado.
    """
    from services.text_normalizer import clean_text
    import re
    if not address:
        return None
    a = clean_text(address) or ""
    # Buscar "col. <colonia>, <municipio>" — formato típico Layout V2.
    locality = ""
    m = re.search(r"\bcol\.\s*([^,]+(?:,\s*[^,]+)?)", a, flags=re.IGNORECASE)
    if m:
        locality = m.group(1).strip(" ,")
    else:
        # Sin "col." → usamos el address completo pero limpio.
        locality = re.sub(r"\bSN\b|\bS/N\b", "", a, flags=re.IGNORECASE)
        # Espacios pegados entre coma y dígito ("Jimenez,444") rompen Nominatim
        locality = re.sub(r",\s*", " ", locality)
        locality = re.sub(r"\s+", " ", locality).strip(" ,")
    parts: list[str] = []
    if locality:
        parts.append(locality)
    if state:
        s = (clean_text(state) or "").strip()
        if s:
            parts.append(s)
    if cp:
        cp_clean = re.sub(r"\D", "", str(cp))
        if len(cp_clean) == 5:
            parts.append(cp_clean)
    if not parts:
        return None
    parts.append("México")
    return ", ".join(parts)


async def geocode_address(address: str, *, country: str = "mx",
                          state: str | None = None,
                          cp: str | None = None) -> tuple[float | None, float | None, str | None]:
    """Devuelve (lat, lng, display_name) para una dirección, con cache.

    Iter53 — Acepta `state` y `cp` opcionales para construir mejor query.
    """
    if not address or not address.strip():
        return None, None, None
    query = _build_geocode_query(address=address, state=state, cp=cp) or address
    key = f"{country}|{query.strip().lower()[:240]}"
    cached = await _cache_get(key)
    if cached:
        return cached.get("lat"), cached.get("lng"), cached.get("display_name")

    await _rate_limit()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{_NOMINATIM_URL}/search",
                params={"q": query, "countrycodes": country,
                        "format": "json", "limit": 1},
                headers={"User-Agent": _USER_AGENT},
            )
            if r.status_code != 200:
                await _cache_put(key, None, None, None)
                return None, None, None
            data = r.json()
            if not data:
                await _cache_put(key, None, None, None)
                return None, None, None
            top = data[0]
            lat = float(top.get("lat") or 0)
            lng = float(top.get("lon") or 0)
            name = top.get("display_name")
            await _cache_put(key, lat, lng, name)
            return lat, lng, name
    except Exception as e:  # noqa: BLE001
        log.warning("geocode_failed", extra={"context": {"err": str(e)[:120]}})
        return None, None, None


async def heatmap_buckets(*, tenant_id: str, date_from: str | None = None,
                          date_to: str | None = None,
                          motivo_codigo: str | None = None,
                          carrier_code: str | None = None,
                          grid_decimals: int = 2) -> list[dict]:
    """Agrega tickets por celda geográfica (lat,lng truncados a `grid_decimals`).

    Prioriza coords de evidences (pickup); fallback a geocoding del address
    asociado al ticket. El address puede vivir en distintos lugares según
    la versión del ingest:
      - `ticket.address` (legacy directo)
      - `guia.recipient.address` (Layout V2, español)
      - `guia.address` (legacy carrier API)

    Retorna [{lat, lng, count, severity}] donde severity = count normalizado.
    """
    db = get_db()
    q: dict = {"tenant_id": tenant_id}
    if date_from:
        q.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        q.setdefault("created_at", {})["$lte"] = date_to
    if motivo_codigo:
        q["motivo_codigo"] = motivo_codigo
    if carrier_code:
        q["carrier_code"] = carrier_code

    points: list[tuple[float, float]] = []

    # 1) Tickets con join a guías y evidencias.
    # - evs: para coords directas del pickup
    # - guias: para extraer recipient.address (Layout V2)
    pipeline = [
        {"$match": q},
        {"$lookup": {
            "from": "evidences", "localField": "id",
            "foreignField": "ticket_id", "as": "evs",
        }},
        {"$lookup": {
            "from": "guias", "localField": "guia_id",
            "foreignField": "id", "as": "guia",
        }},
        {"$project": {
            "_id": 0, "id": 1,
            "evs.lat": 1, "evs.lng": 1,
            "address": 1,
            # Solo lo necesario de la guía:
            "guia.recipient": 1,
            "guia.address": 1,
        }},
    ]
    async for t in db.tickets.aggregate(pipeline):
        used_evidence = False
        for ev in (t.get("evs") or []):
            lat = ev.get("lat")
            lng = ev.get("lng")
            if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
                points.append((float(lat), float(lng)))
                used_evidence = True
                break
        if used_evidence:
            continue
        # 2) Resolver address. Jerarquía:
        #    a. ticket.address (legacy directo)
        #    b. guia[0].recipient.address (Layout V2) + state/cp para contexto
        #    c. guia[0].address (legacy carrier)
        addr: str | None = None
        state: str | None = None
        cp: str | None = None
        if isinstance(t.get("address"), str) and t["address"].strip():
            addr = t["address"]
        else:
            guia_list = t.get("guia") or []
            if guia_list:
                g = guia_list[0]
                recipient = g.get("recipient") or {}
                if isinstance(recipient.get("address"), str) and recipient["address"].strip():
                    addr = recipient["address"]
                    state = recipient.get("state")
                    cp = recipient.get("cp")
                elif isinstance(g.get("address"), str) and g["address"].strip():
                    addr = g["address"]
        if addr:
            lat, lng, _ = await geocode_address(addr, state=state, cp=cp)
            if lat is not None and lng is not None:
                points.append((lat, lng))

    # Bucket
    factor = 10 ** grid_decimals
    buckets: dict[tuple[float, float], int] = {}
    for lat, lng in points:
        cell = (round(lat * factor) / factor, round(lng * factor) / factor)
        buckets[cell] = buckets.get(cell, 0) + 1

    if not buckets:
        return []
    max_count = max(buckets.values())
    result = [{
        "lat": cell[0], "lng": cell[1],
        "count": count,
        "severity": round(count / max_count, 3),
    } for cell, count in buckets.items()]
    result.sort(key=lambda r: -r["count"])
    return result
