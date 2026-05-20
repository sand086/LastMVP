"""Iter53 · Heatmap fix — geocoding desde guia.recipient + query optimizada.

Bug reproducido: en `/api/dashboard/heatmap` el servicio buscaba
`tickets.address` que no existe; la dirección vive en
`guia.recipient.address` (Layout V2). Además el formato "Calle X,444 SN col."
rompía a Nominatim por las comas pegadas a dígitos.

Cubre:
  - `_build_geocode_query` extrae Colonia, Municipio de address "col. X, Y".
  - `_build_geocode_query` con state + cp agrega contexto.
  - Cache invalidación de negative results > 24h.
  - `heatmap_buckets` hace $lookup a guias y geocodea desde recipient.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.uuid import new_id
from services.geocoding import _build_geocode_query, _cache_get, heatmap_buckets


class TestBuildGeocodeQuery:
    def test_extrae_colonia_y_municipio(self):
        q = _build_geocode_query(
            address="Privada Jimenez,444 SN  col. Guadalupe Centro, Guadalupe",
            state="Nuevo León", cp="67100",
        )
        assert q is not None
        assert "Guadalupe Centro" in q
        assert "Guadalupe" in q
        assert "Nuevo León" in q
        assert "67100" in q
        assert "México" in q
        # Y críticamente: NO incluye "Jimenez,444" (que rompe Nominatim)
        assert "Jimenez" not in q
        assert ",444" not in q

    def test_address_sin_col_usa_completo_pero_limpio(self):
        q = _build_geocode_query(
            address="Av. Reforma 100", state="CDMX", cp="06600",
        )
        # No tiene "col." → usa el address completo, sin ruido
        assert "Reforma" in q
        assert "100" in q
        assert "CDMX" in q
        assert "06600" in q
        assert "México" in q

    def test_address_con_comas_pegadas_quita_comas(self):
        q = _build_geocode_query(address="Calle X,123 Y,45", state=None, cp=None)
        # Las comas pegadas a dígitos rompen Nominatim → las reemplazamos por
        # espacio
        assert ",123" not in q
        assert ",45" not in q
        assert "Calle X" in q

    def test_empty_returns_none(self):
        assert _build_geocode_query(address=None) is None
        assert _build_geocode_query(address="") is None
        assert _build_geocode_query(address="   ") is None

    def test_cp_invalido_no_se_incluye(self):
        q = _build_geocode_query(address="X", cp="abc")
        assert "abc" not in q


@pytest.mark.asyncio
class TestNegativeCacheInvalidation:
    async def test_stale_none_cache_returns_none_for_retry(self, db):
        # Insertamos una entry vieja con lat=None
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        await db.geocode_cache.insert_one({
            "id": new_id(), "key": "mx|test stale",
            "lat": None, "lng": None, "display_name": None,
            "cached_at": old_ts,
        })
        result = await _cache_get("mx|test stale")
        assert result is None  # debe forzar retry

    async def test_fresh_none_cache_returns_cached(self, db):
        fresh = datetime.now(timezone.utc).isoformat()
        await db.geocode_cache.insert_one({
            "id": new_id(), "key": "mx|fresh none",
            "lat": None, "lng": None, "display_name": None,
            "cached_at": fresh,
        })
        result = await _cache_get("mx|fresh none")
        assert result is not None
        assert result["lat"] is None

    async def test_positive_hit_always_cached(self, db):
        old_ts = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        await db.geocode_cache.insert_one({
            "id": new_id(), "key": "mx|hit",
            "lat": 19.4326, "lng": -99.1332, "display_name": "CDMX",
            "cached_at": old_ts,
        })
        result = await _cache_get("mx|hit")
        assert result is not None
        assert result["lat"] == 19.4326


@pytest.mark.asyncio
class TestHeatmapBuckets:
    async def test_heatmap_geocodes_from_guia_recipient(self, db):
        tid = new_id()
        gid = new_id()
        ticket_id = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.tenants.insert_one(
            {"id": tid, "slug": "ht", "name": "HT", "status": "active"})
        # Guía Layout V2 con recipient.address
        await db.guias.insert_one({
            "id": gid, "tenant_id": tid, "tracking_id": "G-HM-1",
            "recipient": {
                "address": "Privada Jimenez 444",
                "state": "Nuevo León", "cp": "67100",
            },
            "created_at": now, "updated_at": now,
        })
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": tid, "guia_id": gid,
            "status": "in_progress", "created_at": now, "updated_at": now,
        })

        # Mockeamos geocode_address para evitar pegarle a Nominatim en tests
        async def fake_geocode(addr, *, country="mx", state=None, cp=None):
            assert state == "Nuevo León"
            assert cp == "67100"
            return (25.6751, -100.2531, "Guadalupe, NL, México")

        with patch("services.geocoding.geocode_address",
                   new=AsyncMock(side_effect=fake_geocode)):
            result = await heatmap_buckets(tenant_id=tid)

        assert len(result) == 1
        assert result[0]["count"] == 1
        assert result[0]["lat"] == pytest.approx(25.68, abs=0.05)
        assert result[0]["lng"] == pytest.approx(-100.25, abs=0.05)

    async def test_heatmap_uses_evidence_coords_first(self, db):
        tid = new_id()
        ticket_id = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.tenants.insert_one(
            {"id": tid, "slug": "he", "name": "HE", "status": "active"})
        await db.tickets.insert_one({
            "id": ticket_id, "tenant_id": tid,
            "status": "in_progress", "created_at": now, "updated_at": now,
        })
        await db.evidences.insert_one({
            "id": new_id(), "tenant_id": tid, "ticket_id": ticket_id,
            "lat": 19.4326, "lng": -99.1332,
            "created_at": now,
        })
        # Si usa evidencia, NO debe llamar al geocoder.
        with patch("services.geocoding.geocode_address",
                   new=AsyncMock(side_effect=AssertionError("nunca debe llamarse"))):
            result = await heatmap_buckets(tenant_id=tid)
        assert len(result) == 1
        assert result[0]["lat"] == 19.43
        assert result[0]["lng"] == -99.13

    async def test_heatmap_empty_when_no_tickets(self, db):
        tid = new_id()
        await db.tenants.insert_one(
            {"id": tid, "slug": "hz", "name": "HZ", "status": "active"})
        result = await heatmap_buckets(tenant_id=tid)
        assert result == []

    async def test_heatmap_filters_by_date_range(self, db):
        tid = new_id()
        await db.tenants.insert_one(
            {"id": tid, "slug": "hd", "name": "HD", "status": "active"})
        # Ticket viejo (fuera de rango)
        await db.tickets.insert_one({
            "id": new_id(), "tenant_id": tid,
            "status": "in_progress",
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        })
        result = await heatmap_buckets(
            tenant_id=tid, date_from="2026-01-01T00:00:00+00:00")
        assert result == []  # ticket viejo no entra
