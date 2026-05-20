"""Carrier Adapter Engine — interface + stubs.

CAE_Section14.md sec 14.4. The five anchor adapters (FedEx, DHL, Estafeta,
99 Minutos, Paquetexpress) raise NotImplementedStubException at this stage —
real implementations land in PROMPT_07.

R21: WorkflowEngine NEVER receives raw_code. Adapters → Normalizer → Engine.
R22: 1 class per carrier in this directory.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.errors import NotImplementedStubException


@dataclass(frozen=True)
class RawCarrierEvent:
    carrier_id: str
    tracking_id: str
    raw_code: str
    raw_description: str | None
    raw_payload: dict[str, Any]
    api_version: str
    event_at: datetime


@dataclass(frozen=True)
class NormalizedStatus:
    canonical_status: str
    incident_type: str | None
    is_terminal: bool
    requires_action: bool
    display_label_es: str
    confidence: int
    raw_event: RawCarrierEvent


@dataclass(frozen=True)
class ApiResponse:
    received: bool
    status: int
    fallback_to_email: bool = False


class CarrierAdapterInterface(ABC):
    carrier_id: str = ""

    @abstractmethod
    async def get_raw_status(self, tracking_id: str) -> RawCarrierEvent:  # pragma: no cover
        raise NotImplementedError

    @abstractmethod
    async def validate_config(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    @abstractmethod
    async def send_instruction(self, tracking_id: str, payload: dict) -> ApiResponse:  # pragma: no cover
        raise NotImplementedError


def _stub_raw_event(carrier_id: str, tracking_id: str) -> RawCarrierEvent:
    raise NotImplementedStubException(f"{carrier_id} adapter — implementado en PROMPT_07")
