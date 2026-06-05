"""FedEx Track API adapter (real OAuth2 + mock fallback).

Reference: https://developer.fedex.com/api/es-us/catalog/track/v1/docs.html
Auth: OAuth2 client_credentials → bearer token.
Endpoints:
  - sandbox: ``https://apis-sandbox.fedex.com``
  - prod:    ``https://apis.fedex.com``

Tokens last ~60 minutes; we cache for 55 to avoid edge-of-window errors.

Mapping (FedEx ``latestStatusDetail.code`` → MyExcellence canonical):
  see NATIVE_CODES.
"""
from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from typing import ClassVar

import httpx

from core.logger import log
from ..interface import ApiResponse, RawCarrierEvent
from ._base import _BaseAdapter, _now


class FedExAdapter(_BaseAdapter):
    carrier_id = "fedex"
    DEFAULT_API_VERSION: ClassVar[str] = "v1"

    NATIVE_CODES: ClassVar[dict[str, tuple]] = {
        # raw_code: (canonical, incident_type, is_terminal, requires_action, display_label_es, confidence)
        "PU": ("in_transit",  None,             False, False, "Recolectado",                95),
        "IT": ("in_transit",  None,             False, False, "En tránsito",                98),
        "OD": ("in_transit",  None,             False, False, "En ruta de entrega",         98),
        "DL": ("delivered",   None,             True,  False, "Entregado",                  100),
        "DE": ("exception",   "address_issue",  False, True,  "Excepción de dirección",     90),
        "RS": ("returned",    "returned",       True,  True,  "Devuelto al remitente",      95),
        "CA": ("cancelled",   None,             True,  False, "Cancelado",                  100),
    }

    def __init__(self, *,
                 api_key: str | None = None,            # client_id
                 client_secret: str | None = None,
                 account_number: str | None = None,
                 project_ids: list[str] | None = None,  # noqa: ARG002 — generic SaaS pattern
                 base_url: str | None = None,
                 timeout: float | None = None) -> None:
        # NB: api_key alias = client_id (so the generic CarrierConfigDialog +
        # ClientRepository encryption code keeps a single "api_key" secret).
        self.client_id: str = api_key if api_key is not None else os.environ["FEDEX_CLIENT_ID"]
        self.client_secret: str = (
            client_secret if client_secret is not None else os.environ["FEDEX_CLIENT_SECRET"])
        self.account_number: str = (
            account_number if account_number is not None else os.environ["FEDEX_ACCOUNT_NUMBER"])
        self.base_url: str = base_url if base_url is not None else os.environ["FEDEX_BASE_URL"]
        self.timeout: float = float(timeout if timeout is not None
                                    else os.environ["FEDEX_TIMEOUT"])
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def mock_mode(self) -> bool:
        if not self.client_id or not self.client_secret:
            return True
        return os.environ["MYE_CAE_REAL_MODE"] == "0"

    async def _get_token(self) -> str | None:
        """Cached OAuth2 client_credentials. Returns None on auth failure."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                r = await ac.post(
                    f"{self.base_url}/oauth/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as e:
            log.warning("fedex_oauth_failed", extra={"context": {"error": str(e)}})
            return None
        if r.status_code != 200:
            log.warning("fedex_oauth_non_200", extra={"context": {
                "status": r.status_code, "body": r.text[:200]}})
            return None
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            return None
        self._token = data.get("access_token")
        # access_token expires_in is seconds
        self._token_expires_at = time.time() + float(data.get("expires_in", 3600))
        return self._token

    async def validate_config(self) -> bool:
        if self.mock_mode:
            return True
        token = await self._get_token()
        return bool(token)

    async def _fetch_real(self, tracking_id: str) -> RawCarrierEvent:
        token = await self._get_token()
        if not token:
            return self._raw_unknown(tracking_id, payload={"auth": "failed"})
        body = {
            "trackingInfo": [{
                "trackingNumberInfo": {"trackingNumber": tracking_id},
            }],
            "includeDetailedScans": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as ac:
                r = await ac.post(
                    f"{self.base_url}/track/v1/trackingnumbers",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "x-locale": "es_MX",
                    },
                )
        except httpx.HTTPError as e:
            log.warning("fedex_track_failed", extra={"context": {
                "tracking_id": tracking_id, "error": str(e),
            }})
            return self._raw_unknown(tracking_id, payload={"error": str(e)})
        if r.status_code != 200:
            log.warning("fedex_track_non_200", extra={"context": {
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
                                      payload={"http": 200, "parse": "failed"})
        outputs = ((data.get("output") or {}).get("completeTrackResults") or [])
        if not outputs:
            return self._raw_unknown(tracking_id,
                                      payload={"http": 200, "found": False})
        result = outputs[0].get("trackResults") or [{}]
        first = result[0]
        latest = first.get("latestStatusDetail") or {}
        raw_code = (latest.get("code") or "").upper() or "IT"
        if raw_code not in self.NATIVE_CODES:
            # Fallback to derivedStatus mapping if FedEx returned a code we
            # don't know about — keep workflow flowing as "in_transit".
            raw_code = "IT"
        meta = self.NATIVE_CODES.get(raw_code) or self.NATIVE_CODES["IT"]
        description = latest.get("description") or latest.get("statusByLocale") or meta[4]
        scans = first.get("scanEvents") or []
        last_scan = scans[0] if scans else {}
        ts_raw = (last_scan.get("date") or _now().isoformat())
        try:
            event_at = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            event_at = _now()
        scan_loc = last_scan.get("scanLocation") or {}
        return RawCarrierEvent(
            carrier_id=self.carrier_id,
            tracking_id=tracking_id,
            raw_code=raw_code,
            raw_description=description,
            raw_payload={
                "tracking_id": tracking_id,
                "service_type": (first.get("serviceDetail") or {}).get("type"),
                "delivery_attempts": first.get("deliveryDetails", {}).get("deliveryAttempts"),
                "estimated_delivery": (
                    (first.get("estimatedDeliveryTimeWindow") or {})
                    .get("window") or {}).get("ends"),
                "last_scan_event": last_scan.get("eventDescription"),
                "last_scan_location": {
                    "city": scan_loc.get("city"),
                    "country_code": scan_loc.get("countryCode"),
                    "postal_code": scan_loc.get("postalCode"),
                },
                "scans_count": len(scans),
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
            raw_code="IT",  # mapped to in_transit (no terminal)
            raw_description="Sin información en FedEx",
            raw_payload={"tracking_id": tracking_id, **payload},
            api_version=self.DEFAULT_API_VERSION,
            event_at=_now(),
        )

    async def send_instruction(self, tracking_id: str, payload: dict) -> ApiResponse:
        # FedEx Track API is read-only; cancellations live under a different
        # FedEx API (Cancel Shipment) which requires account_number. Out of
        # scope for this iteration — return 501 so the agent can fall back
        # to email/whatsapp.
        return ApiResponse(received=False, status=501, fallback_to_email=True)
