"""Shared `_BaseAdapter` for all carrier adapters.

Extracted from ``anchor_stubs`` so that real adapters (DHL, FedEx, Routal) can
import the base without creating a circular dependency through the registry.

`_BaseAdapter` provides:
  - deterministic mock_mode (md5(tracking_id) % len(NATIVE_CODES))
  - default ``validate_config`` / ``send_instruction`` that return mock
  - a hook ``_fetch_real`` real adapters override to make HTTP calls
"""
from __future__ import annotations
import hashlib
import os
from datetime import datetime, timezone
from typing import ClassVar

from core.errors import NotImplementedStubException
from ..interface import ApiResponse, CarrierAdapterInterface, RawCarrierEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _BaseAdapter(CarrierAdapterInterface):
    """Shared helpers for all adapters."""

    #: Map of raw_code → (canonical_status, incident_type, is_terminal, requires_action, display_label_es, confidence)
    NATIVE_CODES: ClassVar[dict[str, tuple]] = {}
    DEFAULT_API_VERSION: ClassVar[str] = "v1"

    @property
    def mock_mode(self) -> bool:
        return os.environ.get("MYE_CAE_REAL_MODE", "0") != "1"

    async def get_raw_status(self, tracking_id: str) -> RawCarrierEvent:
        if self.mock_mode:
            return self._mock_event(tracking_id)
        return await self._fetch_real(tracking_id)

    async def validate_config(self) -> bool:
        return self.mock_mode

    async def send_instruction(self, tracking_id: str, payload: dict) -> ApiResponse:
        if self.mock_mode:
            return ApiResponse(received=True, status=200)
        raise NotImplementedStubException(f"{self.carrier_id} send_instruction — requires real credentials")

    async def _fetch_real(self, tracking_id: str) -> RawCarrierEvent:  # pragma: no cover
        raise NotImplementedStubException(
            f"{self.carrier_id} real-mode — provee credenciales y completa _fetch_real()"
        )

    def _mock_event(self, tracking_id: str) -> RawCarrierEvent:
        """Generate a deterministic raw event for end-to-end testing."""
        if not self.NATIVE_CODES:
            raise NotImplementedStubException(f"{self.carrier_id} adapter has no NATIVE_CODES seeded")
        codes = sorted(self.NATIVE_CODES)
        idx = int(hashlib.md5(tracking_id.encode("utf-8")).hexdigest(), 16) % len(codes)
        raw = codes[idx]
        meta = self.NATIVE_CODES[raw]
        return RawCarrierEvent(
            carrier_id=self.carrier_id,
            tracking_id=tracking_id,
            raw_code=raw,
            raw_description=meta[4],
            raw_payload={"mocked": True, "tracking_id": tracking_id},
            api_version=self.DEFAULT_API_VERSION,
            event_at=_now(),
        )
