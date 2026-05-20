"""Pydantic models for the admin hierarchy CRUD (PROMPT 02).

These define the *wire* contracts. Persistence dicts in MongoDB add
``id``, ``tenant_id`` and ``created_at`` server-side.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ---------- Tenants -------------------------------------------------------
TenantStatus = Literal["active", "maintenance", "suspended"]


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    status: TenantStatus = "active"


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    status: Optional[TenantStatus] = None


# ---------- Projects ------------------------------------------------------
ProjectStatus = Literal["active", "inactive"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    status: ProjectStatus = "active"


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    status: Optional[ProjectStatus] = None


# ---------- Clients -------------------------------------------------------
IngestMode = Literal["webhook", "pulling", "layout"]
ApiAuthType = Literal["bearer", "basic", "apikey", "none"]
PreferredChannel = Literal["email", "whatsapp", "both"]


# Bundle D · Mejora — Dirección estructurada MX (UX-LATAM-007).
# Pydantic la valida superficialmente; el formulario hace heavy-lifting de UX.
class MxAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calle: Optional[str] = Field(default=None, max_length=255)
    numero_exterior: Optional[str] = Field(default=None, max_length=20)
    numero_interior: Optional[str] = Field(default=None, max_length=20)
    colonia: Optional[str] = Field(default=None, max_length=180)
    codigo_postal: Optional[str] = Field(default=None, min_length=5, max_length=5,
                                          pattern=r"^\d{5}$")
    ciudad: Optional[str] = Field(default=None, max_length=120)
    estado: Optional[str] = Field(default=None, max_length=120)
    referencias: Optional[str] = Field(default=None, max_length=500)
    country: str = Field(default="MX", min_length=2, max_length=2)


class ClientCreate(BaseModel):
    project_id: str = Field(min_length=36, max_length=36)
    name: str = Field(min_length=2, max_length=255)
    ingest_mode: IngestMode = "webhook"
    api_url: Optional[str] = Field(default=None, max_length=500)
    api_auth_type: ApiAuthType = "none"
    api_creds: Optional[str] = Field(default=None, max_length=2048)  # plaintext; encrypted server-side
    pulling_freq_min: int = Field(default=15, ge=1, le=1440)
    preferred_channel: PreferredChannel = "email"
    ops_contact_name: Optional[str] = Field(default=None, max_length=255)
    ops_contact_email: Optional[EmailStr] = None
    ops_contact_wa: Optional[str] = Field(default=None, max_length=20)
    cxc_contact_name: Optional[str] = Field(default=None, max_length=255)
    cxc_contact_email: Optional[EmailStr] = None
    status_map: dict = Field(default_factory=dict)
    address_mx: Optional[MxAddress] = None

    @field_validator("ops_contact_wa")
    @classmethod
    def _wa(cls, v):
        if v is None or v == "":
            return None
        if not v.startswith("+"):
            raise ValueError("ops_contact_wa debe iniciar con +<código país>")
        return v


class ClientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    ingest_mode: Optional[IngestMode] = None
    api_url: Optional[str] = None
    api_auth_type: Optional[ApiAuthType] = None
    api_creds: Optional[str] = None
    pulling_freq_min: Optional[int] = Field(default=None, ge=1, le=1440)
    preferred_channel: Optional[PreferredChannel] = None
    ops_contact_name: Optional[str] = None
    ops_contact_email: Optional[EmailStr] = None
    ops_contact_wa: Optional[str] = None
    cxc_contact_name: Optional[str] = None
    cxc_contact_email: Optional[EmailStr] = None
    status_map: Optional[dict] = None
    address_mx: Optional[MxAddress] = None


# ---------- Subclients ----------------------------------------------------
class SubclientCreate(BaseModel):
    client_id: str = Field(min_length=36, max_length=36)
    name: str = Field(min_length=2, max_length=255)
    status: ProjectStatus = "active"


class SubclientUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[ProjectStatus] = None


# ---------- Carriers ------------------------------------------------------
class CarrierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    has_api: bool = False
    api_url: Optional[str] = Field(default=None, max_length=500)
    api_creds: Optional[str] = Field(default=None, max_length=2048)
    pulling_supported: bool = False
    webhook_supported: bool = False
    status: ProjectStatus = "active"


class CarrierUpdate(BaseModel):
    name: Optional[str] = None
    has_api: Optional[bool] = None
    api_url: Optional[str] = None
    api_creds: Optional[str] = None
    pulling_supported: Optional[bool] = None
    webhook_supported: Optional[bool] = None
    status: Optional[ProjectStatus] = None


# ---------- Per-client carrier config (multi-project SaaS) ---------------
# Used today by Routal (1 ApiKey → N project_ids). Generic enough to host
# the same pattern for future carriers (FedEx multi-account, etc.).

class ClientCarrierConfigPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: Optional[str] = Field(default=None, max_length=2048)
    project_ids: Optional[list[str]] = Field(default=None, max_length=50)
    default_project_id: Optional[str] = Field(default=None, max_length=128)
    base_url: Optional[str] = Field(default=None, max_length=500)
    enabled: Optional[bool] = None

    @field_validator("project_ids")
    @classmethod
    def _projects(cls, v):
        if v is None:
            return None
        cleaned = [p.strip() for p in v if isinstance(p, str) and p.strip()]
        # de-dup preserving order
        seen, out = set(), []
        for p in cleaned:
            if p not in seen:
                seen.add(p)
                out.append(p)
        if len(out) > 50:
            raise ValueError("máximo 50 project_ids")
        return out

