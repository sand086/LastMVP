"""AI models — Pydantic schemas for /api/ai and /api/admin/ai-config (PROMPT 26)."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator


# ── Catálogo de features ─────────────────────────────────────────────────
ProviderName = Literal["anthropic", "openai", "gemini"]
DestinatarioKind = Literal["agent_internal", "client_final", "both"]


class FeatureCreate(BaseModel):
    feature_code: str = Field(min_length=2, max_length=100, pattern=r"^[a-z][a-z0-9_]+$")
    feature_name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    recommended_model: str
    recommended_provider: ProviderName = "anthropic"
    avg_input_tokens: int = Field(default=500, ge=0, le=200_000)
    avg_output_tokens: int = Field(default=300, ge=0, le=200_000)
    avg_cost_usd: float = Field(default=0.005, ge=0)
    destinatario: DestinatarioKind = "agent_internal"
    cache_enabled: bool = False
    active: bool = True


class FeatureUpdate(BaseModel):
    feature_name: str | None = None
    description: str | None = None
    recommended_model: str | None = None
    recommended_provider: ProviderName | None = None
    avg_input_tokens: int | None = None
    avg_output_tokens: int | None = None
    avg_cost_usd: float | None = None
    destinatario: DestinatarioKind | None = None
    cache_enabled: bool | None = None
    active: bool | None = None


# ── Brackets ─────────────────────────────────────────────────────────────
class BracketCreate(BaseModel):
    bracket_name: str = Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_]+$")
    included_invocations_per_month: int = Field(ge=0)
    included_tokens_per_month: int = Field(ge=0)
    overage_per_1k_tokens_usd: float = Field(ge=0)
    hard_cap_usd_per_month: float = Field(ge=0)
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)
    monthly_fee_usd: float = Field(ge=0)
    active: bool = True


class BracketUpdate(BaseModel):
    included_invocations_per_month: int | None = None
    included_tokens_per_month: int | None = None
    overage_per_1k_tokens_usd: float | None = None
    hard_cap_usd_per_month: float | None = None
    alert_threshold_pct: int | None = None
    monthly_fee_usd: float | None = None
    active: bool | None = None


# ── Configuración por cliente ────────────────────────────────────────────
class ClientConfigUpsert(BaseModel):
    client_id: str = Field(min_length=8)
    bracket_id: str | None = None
    enabled_features: list[str] = Field(default_factory=list)
    monthly_cap_override_usd: float | None = Field(default=None, ge=0)
    rollover_enabled: bool = False
    is_active: bool = False
    opt_in_signature: str | None = Field(default=None, max_length=500)
    # Override de proveedor (R39 — opcional, default Emergent universal key)
    custom_provider: ProviderName | None = None
    custom_api_key: str | None = Field(default=None, max_length=500)
    # Webhook saliente (P1) — entregamos drafts aprobados al endpoint del cliente
    webhook_outbound_url: str | None = Field(default=None, max_length=500)
    webhook_outbound_secret: str | None = Field(default=None, max_length=200)

    @field_validator("custom_api_key")
    @classmethod
    def _strip_key(cls, v):
        return v.strip() if v else v


class OptOutBody(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


# ── Invoke ───────────────────────────────────────────────────────────────
class InvokeRequest(BaseModel):
    feature_code: str
    ticket_id: str | None = None
    input: dict = Field(default_factory=dict)
