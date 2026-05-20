"""Pydantic models para webhooks salientes (PROMPT 39 V3)."""
from __future__ import annotations
from typing import Optional, Literal

from pydantic import BaseModel, Field, field_validator


class WebhookSubscriptionCreate(BaseModel):
    client_id: str = Field(min_length=1)
    endpoint_url: str = Field(min_length=8, max_length=2000)
    event_codes: list[str] = Field(min_length=1)
    include_pii: bool = False
    pii_consent_signature: Optional[str] = Field(default=None, max_length=500)
    filter_jsonpath: Optional[dict] = None
    allow_extra_ports: bool = False

    @field_validator("event_codes")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        clean = [c.strip() for c in v if c.strip()]
        if len(clean) != len(set(clean)):
            raise ValueError("event_codes contiene duplicados")
        return clean


class WebhookSubscriptionUpdate(BaseModel):
    endpoint_url: Optional[str] = Field(default=None, max_length=2000)
    event_codes: Optional[list[str]] = None
    include_pii: Optional[bool] = None
    pii_consent_signature: Optional[str] = None
    filter_jsonpath: Optional[dict] = None
    is_active: Optional[bool] = None


class FeatureCatalogCreate(BaseModel):
    event_code: str = Field(min_length=3, max_length=100,
                            pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    event_name: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    payload_schema: dict
    schema_version: str = Field(default="v1", max_length=20)
    contains_pii: bool = False
    active: bool = True


# Estados terminales/intermedios del delivery_log (R47 — append only)
DeliveryStatus = Literal[
    "delivered", "failed_temporary", "failed_permanent",
    "timeout", "blocked_ssrf", "circuit_open",
]


class DispatchPayload(BaseModel):
    event_type: str
    source_id: str  # ej. ticket_id, claim_id, guia_id
    data: dict
