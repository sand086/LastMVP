"""DHL Shipment Tracking adapter (real HTTP + mock fallback).

Reference: https://developer.dhl.com/api-reference/shipment-tracking
Auth: ``DHL-API-Key`` request header (Consumer Key from developer.dhl.com).
Endpoint:
  - sandbox: ``https://api-test.dhl.com/track/shipments``
  - prod:    ``https://api-eu.dhl.com/track/shipments``

Rate limits (default app):
  - 250 calls/day, max 1 every 5 seconds.

We keep the deterministic mock fallback (used by the rest of the test suite via
``_mock_event``) when no ``api_key`` is configured, so existing tests continue
to pass without secret material.

Mapping (DHL ``shipment.status.statusCode`` → MyExcellence canonical):
  pre-transit → in_transit
  transit     → in_transit
  delivered   → delivered (terminal)
  failure     → exception (action needed)
  unknown     → unknown
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from core.logger import log
from ..interface import ApiResponse, RawCarrierEvent
from ._base import _BaseAdapter, _now


class DhlAdapter(_BaseAdapter):
    carrier_id = "dhl"
    DEFAULT_API_VERSION: ClassVar[str] = "v1.5"

    #: raw_code → (canonical, incident_type, is_terminal, requires_action, display_label_es, confidence)
    NATIVE_CODES: ClassVar[dict[str, tuple]] = {
        "pre-transit": ("in_transit", None,         False, False, "Etiqueta creada",      90),
        "transit":     ("in_transit", None,         False, False, "En tránsito",          98),
        "delivered":   ("delivered",  None,         True,  False, "Entregado",            100),
        "failure":     ("exception",  "failed",     False, True,  "Incidencia",           90),
        "unknown":     ("unknown",    None,         False, False, "Estado desconocido",   50),
    }

    def __init__(self, *,
                 api_key: str | None = None,
                 project_ids: list[str] | None = None,   # noqa: ARG002 — accepted for consistency with the SaaS pattern but DHL has no project_id concept
                 base_url: str | None = None,
                 timeout: float | None = None) -> None:
        # NB: project_ids is accepted-and-ignored to keep the same SaaS
        # constructor signature across carriers; DHL bills the API key directly.
        self.api_key: str = api_key or os.environ.get("DHL_API_KEY", "")
        self.base_url: str = base_url or os.environ.get(
            "DHL_BASE_URL", "https://api-eu.dhl.com/track")
        self.timeout: float = float(timeout if timeout is not None
                                    else os.environ.get("DHL_TIMEOUT", "10"))

    # When no api_key is configured we keep returning deterministic mock data
    # so the rest of the test suite continues to operate without secrets.
    @property
    def mock_mode(self) -> bool:
        if not self.api_key:
            return True
        # An env-level override allows force-mock e.g. in CI even with a key set.
        return os.environ.get("MYE_CAE_REAL_MODE", "1") == "0"

    async def validate_config(self) -> bool:
        if self.mock_mode:
            return True
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                # DHL's recommended demo tracking number; returns 200 even with
                # real key (mocked response). Verifies auth + reachability.
                r = await ac.get(f"{self.base_url}/shipments",
                                 params={"trackingNumber": "7777777770"},
                                 headers={"DHL-API-Key": self.api_key})
            # 200 = found, 404 = not found (still means key auth worked),
            # 401/403 = bad credentials.
            return r.status_code in (200, 404)
        except httpx.HTTPError:
            return False

    async def _fetch_real(self, tracking_id: str) -> RawCarrierEvent:
        """Real HTTP call to DHL Shipment Tracking. Returns a normalized
        RawCarrierEvent; on auth or transport failure returns an `unknown`
        event so the workflow engine can still operate gracefully."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                r = await ac.get(
                    f"{self.base_url}/shipments",
                    params={"trackingNumber": tracking_id, "language": "es"},
                    headers={"DHL-API-Key": self.api_key,
                             "Accept": "application/json"},
                )
        except httpx.HTTPError as e:
            log.warning("dhl_get_status_failed", extra={"context": {
                "tracking_id": tracking_id, "error": str(e),
            }})
            return self._raw_unknown(tracking_id,
                                      payload={"error": str(e), "found": False})

        if r.status_code == 404:
            return self._raw_unknown(tracking_id,
                                      payload={"http": 404, "found": False})
        if r.status_code >= 400:
            log.warning("dhl_get_status_non_200", extra={"context": {
                "tracking_id": tracking_id, "status": r.status_code,
                "body": r.text[:200],
            }})
            return self._raw_unknown(tracking_id,
                                      payload={"http": r.status_code,
                                                "body": r.text[:200]})
        try:
            data = r.json() or {}
        except Exception:  # noqa: BLE001
            return self._raw_unknown(tracking_id,
                                      payload={"http": r.status_code,
                                                "found": False})
        shipments = data.get("shipments") or []
        if not shipments:
            return self._raw_unknown(tracking_id,
                                      payload={"http": 200, "found": False,
                                                "shipments": 0})
        shp = shipments[0]
        status = (shp.get("status") or {})
        raw_code = (status.get("statusCode") or status.get("status")
                    or "unknown").lower()
        # DHL returns lots of variations — normalize what we don't have in
        # NATIVE_CODES into "unknown".
        if raw_code not in self.NATIVE_CODES:
            raw_code = "unknown"
        meta = self.NATIVE_CODES.get(raw_code) or self.NATIVE_CODES["unknown"]
        description = (status.get("description") or status.get("status")
                       or meta[4])
        ts_raw = (status.get("timestamp") or shp.get("estimatedTimeOfDelivery")
                  or _now().isoformat())
        try:
            event_at = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            event_at = _now()
        # Pull last event details if present
        events = shp.get("events") or []
        last = events[-1] if events else {}
        loc = (last.get("location") or {}).get("address") or {}
        return RawCarrierEvent(
            carrier_id=self.carrier_id,
            tracking_id=tracking_id,
            raw_code=raw_code,
            raw_description=description,
            raw_payload={
                "tracking_id": tracking_id,
                "service": shp.get("service"),
                "origin_country": ((shp.get("origin") or {}).get("address") or {}).get("countryCode"),
                "destination_country": ((shp.get("destination") or {}).get("address") or {}).get("countryCode"),
                "estimated_delivery": shp.get("estimatedTimeOfDelivery"),
                "events_count": len(events),
                "last_event_description": last.get("description"),
                "last_event_location": {
                    "city": loc.get("addressLocality"),
                    "country_code": loc.get("countryCode"),
                },
                "found": True,
            },
            api_version=self.DEFAULT_API_VERSION,
            event_at=event_at if event_at.tzinfo else
                event_at.replace(tzinfo=timezone.utc),
        )

    def _raw_unknown(self, tracking_id: str, *, payload: dict) -> RawCarrierEvent:
        return RawCarrierEvent(
            carrier_id=self.carrier_id,
            tracking_id=tracking_id,
            raw_code="unknown",
            raw_description="Sin información en DHL",
            raw_payload={"tracking_id": tracking_id, **payload},
            api_version=self.DEFAULT_API_VERSION,
            event_at=_now(),
        )

    async def send_instruction(self, tracking_id: str, payload: dict) -> ApiResponse:
        # DHL Tracking API is READ-ONLY (no outbound instructions).
        # Future: integrate DHL Express WS for cancellation if/when activated.
        return ApiResponse(received=False, status=501, fallback_to_email=True)
