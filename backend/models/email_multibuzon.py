"""Bundle G · Email Multi-Buzón — modelos Pydantic + tipos compartidos.

Reglas R52-R55:
  R52 — todo tenant tiene mínimo 1 buzón.
  R53 — fallar visible si no resuelve buzón (NO inventar default).
  R54 — verificación de dominio independiente del buzón.
  R55 — credenciales por dominio + tenant.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


WorkflowType = Literal[
    "ticket_notification",  # alerta operativa de ticket al cliente
    "claim_communication",  # comunicación de reclamo a CxC
    "sla_alert",            # alerta de SLA
    "admin_notification",   # invitación, reset password, etc.
    "generic",              # fallback
]


# ──────────────────────────────────────────────────────────────
# Dispatcher DTOs
# ──────────────────────────────────────────────────────────────
class EmailContext(BaseModel):
    tenant_id: str
    workflow_type: WorkflowType
    client_id: Optional[str] = None
    motivo_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    explicit_mailbox_id: Optional[str] = None


class EmailPayload(BaseModel):
    to: list[str] = Field(min_length=1, max_length=10)
    cc: list[str] = Field(default_factory=list, max_length=10)
    bcc: list[str] = Field(default_factory=list, max_length=10)
    subject: str = Field(min_length=1, max_length=300)
    body_html: str
    body_text: Optional[str] = None
    tags: dict[str, str] = Field(default_factory=dict)


class SendResult(BaseModel):
    success: bool
    status: Literal["queued", "sent", "delivered", "failed"]
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    log_id: str
    mailbox_id: Optional[str] = None
    mock: bool = False


# ──────────────────────────────────────────────────────────────
# Admin API payloads
# ──────────────────────────────────────────────────────────────
class DomainCreate(BaseModel):
    domain: str = Field(min_length=4, max_length=255,
                        pattern=r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$")
    provider: Literal["resend"] = "resend"


class MailboxCreate(BaseModel):
    domain_id: str
    client_id: Optional[str] = None
    display_name: str = Field(min_length=1, max_length=255)
    sender_name: str = Field(min_length=1, max_length=255)
    sender_email: str = Field(min_length=3, max_length=255)
    reply_to_email: Optional[str] = None
    api_key: Optional[str] = None
    daily_send_limit: Optional[int] = None
    is_default_for_tenant: bool = False
    is_default_for_client: bool = False
    workflow_types: list[WorkflowType] = Field(default_factory=lambda: ["generic"])


class MailboxUpdate(BaseModel):
    display_name: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    reply_to_email: Optional[str] = None
    api_key: Optional[str] = None
    daily_send_limit: Optional[int] = None
    is_active: Optional[bool] = None
    is_default_for_tenant: Optional[bool] = None
    is_default_for_client: Optional[bool] = None


class RoutingRuleCreate(BaseModel):
    mailbox_id: str
    workflow_type: WorkflowType
    client_id: Optional[str] = None
    motivo_id: Optional[str] = None
    priority: int = Field(default=100, ge=0, le=10000)
    description: Optional[str] = None


# Public view helpers (sin api_key_ref, etc.)
SAFE_DOMAIN_FIELDS = (
    "id", "tenant_id", "domain", "provider", "verification_status",
    "dkim_verified", "spf_verified", "dmarc_verified", "verified_at",
    "last_check_at", "dns_records", "degraded", "created_at", "updated_at",
)
SAFE_MAILBOX_FIELDS = (
    "id", "tenant_id", "client_id", "domain_id", "display_name",
    "sender_name", "sender_email", "reply_to_email",
    "is_active", "is_default_for_tenant", "is_default_for_client",
    "daily_send_limit", "monthly_send_count", "api_key_last4",
    "workflow_types", "created_at", "updated_at",
)


def public_domain(doc: dict) -> dict:
    return {k: doc.get(k) for k in SAFE_DOMAIN_FIELDS}


def public_mailbox(doc: dict) -> dict:
    return {k: doc.get(k) for k in SAFE_MAILBOX_FIELDS}
