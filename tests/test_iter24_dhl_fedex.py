"""Iter24 — DHL y FedEx adapters reales (HTTP + mock fallback).

Verificamos:
  * Constructor con args propios; sin api_key cae a mock_mode (compat tests).
  * Modo real hace HTTP correcto al endpoint y headers correspondientes.
  * Mapeo NATIVE_CODES → canonical.
  * Auth failure / 404 / 5xx degradan gracefully a raw_code="unknown" (DHL)
    o "IT" (FedEx), nunca raise.
  * FedEx cachea el OAuth token entre llamadas.
  * send_instruction siempre 501 (read-only APIs).
"""
from __future__ import annotations
from unittest.mock import patch, AsyncMock

import httpx
import pytest

from services.cae.adapters.dhl import DhlAdapter
from services.cae.adapters.fedex import FedExAdapter


def _resp(status: int, body):
    """Build an httpx.Response stub."""
    req = httpx.Request("GET", "https://fake")
    if isinstance(body, dict):
        return httpx.Response(status, request=req, json=body)
    return httpx.Response(status, request=req, text=body)


# ──────────────────────────── DHL ───────────────────────────────────
class TestDHLAdapter:
    def test_constructor_falls_back_to_mock_when_no_key(self):
        a = DhlAdapter()
        assert a.api_key == ""
        assert a.mock_mode is True

    def test_constructor_real_mode_when_key_set(self):
        a = DhlAdapter(api_key="KEY", base_url="https://api-test.dhl.com/track")
        assert a.api_key == "KEY"
        assert a.base_url == "https://api-test.dhl.com/track"
        assert a.mock_mode is False

    def test_constructor_accepts_project_ids_ignores_them(self):
        """DHL has no project concept; accept the kwarg for SaaS pattern compat."""
        a = DhlAdapter(api_key="K", project_ids=["ignored1", "ignored2"])
        assert a.api_key == "K"

    async def test_validate_config_pings_dhl(self):
        a = DhlAdapter(api_key="K", base_url="https://api-eu.dhl.com/track")
        captured = {}

        async def fake_get(self, url, **kw):
            captured["url"] = url
            captured["params"] = kw.get("params")
            captured["headers"] = kw.get("headers")
            return _resp(200, {"shipments": []})

        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            assert await a.validate_config() is True
        assert captured["url"] == "https://api-eu.dhl.com/track/shipments"
        assert captured["headers"]["DHL-API-Key"] == "K"
        assert captured["params"]["trackingNumber"] == "7777777770"

    async def test_validate_config_handles_auth_failure(self):
        a = DhlAdapter(api_key="BAD")

        async def fake_get(self, url, **kw):
            return _resp(401, "Unauthorized")

        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            assert await a.validate_config() is False

    async def test_get_raw_status_parses_real_response(self):
        a = DhlAdapter(api_key="K")
        body = {
            "shipments": [{
                "service": "express",
                "status": {
                    "statusCode": "delivered",
                    "description": "Delivered",
                    "timestamp": "2026-05-09T15:30:00Z",
                },
                "origin": {"address": {"countryCode": "MX"}},
                "destination": {"address": {"countryCode": "US"}},
                "estimatedTimeOfDelivery": "2026-05-09",
                "events": [
                    {"description": "Out for delivery",
                     "location": {"address": {"addressLocality": "CDMX",
                                                "countryCode": "MX"}}},
                    {"description": "Delivered",
                     "location": {"address": {"addressLocality": "Houston",
                                                "countryCode": "US"}}},
                ],
            }],
        }

        async def fake_get(self, url, **kw):
            return _resp(200, body)

        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            ev = await a.get_raw_status("TRK-DHL-1")
        assert ev.carrier_id == "dhl"
        assert ev.raw_code == "delivered"
        assert ev.raw_description == "Delivered"
        assert ev.raw_payload["found"] is True
        assert ev.raw_payload["service"] == "express"
        assert ev.raw_payload["destination_country"] == "US"
        assert ev.raw_payload["events_count"] == 2
        assert ev.raw_payload["last_event_location"]["city"] == "Houston"

    async def test_get_raw_status_404_returns_unknown(self):
        a = DhlAdapter(api_key="K")

        async def fake_get(self, url, **kw):
            return _resp(404, "")

        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            ev = await a.get_raw_status("MISSING")
        assert ev.raw_code == "unknown"
        assert ev.raw_payload["found"] is False
        assert ev.raw_payload["http"] == 404

    async def test_get_raw_status_unknown_statuscode_normalizes(self):
        a = DhlAdapter(api_key="K")
        body = {"shipments": [{
            "status": {"statusCode": "weird-future-code",
                       "description": "X", "timestamp": "2026-05-09T10:00:00Z"},
        }]}

        async def fake_get(self, url, **kw):
            return _resp(200, body)

        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            ev = await a.get_raw_status("TRK-X")
        assert ev.raw_code == "unknown"

    async def test_get_raw_status_network_error(self):
        a = DhlAdapter(api_key="K")

        async def fake_get(self, url, **kw):
            raise httpx.ConnectError("boom")

        with patch.object(httpx.AsyncClient, "get", new=fake_get):
            ev = await a.get_raw_status("TRK")
        assert ev.raw_code == "unknown"
        assert "error" in ev.raw_payload

    async def test_get_raw_status_mock_when_no_key(self):
        """Without api_key, the adapter must keep returning deterministic mock
        data — preserves the rest of the legacy test suite."""
        a = DhlAdapter()
        ev = await a.get_raw_status("STUB-DHL")
        assert ev.carrier_id == "dhl"
        assert ev.raw_payload.get("mocked") is True

    async def test_send_instruction_returns_501(self):
        a = DhlAdapter(api_key="K")
        res = await a.send_instruction("TRK", {"status": "canceled"})
        assert res.received is False
        assert res.status == 501
        assert res.fallback_to_email is True


# ──────────────────────────── FedEx ─────────────────────────────────
class TestFedExAdapter:
    def test_constructor_falls_back_to_mock_when_no_creds(self):
        a = FedExAdapter()
        assert a.client_id == ""
        assert a.mock_mode is True

    def test_constructor_real_mode_needs_BOTH_creds(self):
        # Only client_id → still mock
        a = FedExAdapter(api_key="ID")
        assert a.mock_mode is True
        # Both → real
        a = FedExAdapter(api_key="ID", client_secret="SECRET")
        assert a.mock_mode is False
        assert a.client_id == "ID"
        assert a.client_secret == "SECRET"

    def test_constructor_accepts_account_number(self):
        a = FedExAdapter(api_key="ID", client_secret="S",
                          account_number="510087860")
        assert a.account_number == "510087860"

    async def test_validate_config_oauth_success(self):
        a = FedExAdapter(api_key="ID", client_secret="S")

        async def fake_post(self, url, **kw):
            if url.endswith("/oauth/token"):
                return _resp(200, {"access_token": "tok-xyz", "expires_in": 3600})
            return _resp(404, "")

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            assert await a.validate_config() is True

    async def test_validate_config_oauth_failure(self):
        a = FedExAdapter(api_key="ID", client_secret="WRONG")

        async def fake_post(self, url, **kw):
            return _resp(401, '{"errors":[{"code":"NOT.AUTHORIZED"}]}')

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            assert await a.validate_config() is False

    async def test_token_is_cached_across_calls(self):
        a = FedExAdapter(api_key="ID", client_secret="S")
        call_count = {"oauth": 0, "track": 0}

        async def fake_post(self, url, **kw):
            if url.endswith("/oauth/token"):
                call_count["oauth"] += 1
                return _resp(200, {"access_token": "T-1", "expires_in": 3600})
            call_count["track"] += 1
            return _resp(200, {"output": {"completeTrackResults": [{
                "trackResults": [{
                    "latestStatusDetail": {"code": "IT", "description": "in transit"},
                    "scanEvents": [],
                }],
            }]}})

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            await a.get_raw_status("TRK-1")
            await a.get_raw_status("TRK-2")
            await a.get_raw_status("TRK-3")
        assert call_count["oauth"] == 1   # cached!
        assert call_count["track"] == 3

    async def test_get_raw_status_parses_real_response(self):
        a = FedExAdapter(api_key="ID", client_secret="S")
        track_body = {"output": {"completeTrackResults": [{
            "trackResults": [{
                "latestStatusDetail": {
                    "code": "DL", "description": "Delivered",
                    "statusByLocale": "Entregado",
                },
                "serviceDetail": {"type": "FedEx Express"},
                "deliveryDetails": {"deliveryAttempts": "1"},
                "estimatedDeliveryTimeWindow": {
                    "window": {"ends": "2026-05-09T20:00:00Z"},
                },
                "scanEvents": [
                    {"date": "2026-05-09T18:00:00Z",
                     "eventDescription": "Delivered at front door",
                     "scanLocation": {"city": "Houston", "countryCode": "US",
                                       "postalCode": "77001"}},
                ],
            }],
        }]}}

        async def fake_post(self, url, **kw):
            if url.endswith("/oauth/token"):
                return _resp(200, {"access_token": "T", "expires_in": 3600})
            # Validate auth header is bearer
            assert kw.get("headers", {}).get("Authorization") == "Bearer T"
            return _resp(200, track_body)

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            ev = await a.get_raw_status("FX-TRK")
        assert ev.carrier_id == "fedex"
        assert ev.raw_code == "DL"
        assert ev.raw_description == "Delivered"
        assert ev.raw_payload["found"] is True
        assert ev.raw_payload["service_type"] == "FedEx Express"
        assert ev.raw_payload["last_scan_location"]["postal_code"] == "77001"
        assert ev.raw_payload["scans_count"] == 1

    async def test_unknown_code_normalizes_to_IT(self):
        a = FedExAdapter(api_key="ID", client_secret="S")

        async def fake_post(self, url, **kw):
            if url.endswith("/oauth/token"):
                return _resp(200, {"access_token": "T", "expires_in": 3600})
            return _resp(200, {"output": {"completeTrackResults": [{
                "trackResults": [{
                    "latestStatusDetail": {"code": "FUTURE_CODE",
                                            "description": "?"},
                    "scanEvents": [],
                }],
            }]}})

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            ev = await a.get_raw_status("TRK")
        assert ev.raw_code == "IT"

    async def test_track_auth_failure_returns_unknown(self):
        a = FedExAdapter(api_key="ID", client_secret="S")

        async def fake_post(self, url, **kw):
            if url.endswith("/oauth/token"):
                return _resp(401, "")  # token fails
            return _resp(200, {})

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            ev = await a.get_raw_status("TRK")
        # Adapter falls through to _raw_unknown
        assert ev.raw_code == "IT"
        assert ev.raw_payload.get("auth") == "failed"

    async def test_get_raw_status_mock_when_no_creds(self):
        a = FedExAdapter()
        ev = await a.get_raw_status("STUB-FX")
        assert ev.carrier_id == "fedex"
        assert ev.raw_payload.get("mocked") is True

    async def test_send_instruction_returns_501(self):
        a = FedExAdapter(api_key="ID", client_secret="S")
        res = await a.send_instruction("TRK", {"status": "canceled"})
        assert res.received is False
        assert res.status == 501


# ─────────── Registry override ───────────────────────────────────────
class TestRegistryWiring:
    def test_dhl_and_fedex_registered_as_real_classes(self):
        from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY
        from services.cae.adapters.dhl import DhlAdapter as RealDhl
        from services.cae.adapters.fedex import FedExAdapter as RealFedEx
        from services.cae.adapters.routal import RoutalAdapter
        assert ADAPTER_REGISTRY["dhl"] is RealDhl
        assert ADAPTER_REGISTRY["fedex"] is RealFedEx
        assert ADAPTER_REGISTRY["routal"] is RoutalAdapter
