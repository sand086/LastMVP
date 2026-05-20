"""Pydantic models for catalog + automation permissions (PROMPT 03)."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

# ---------- Motivos -------------------------------------------------------
class MotivoCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=2, max_length=255)
    restricted: bool = False
    active: bool = True


class MotivoUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    restricted: Optional[bool] = None
    active: Optional[bool] = None


# ---------- Soluciones ----------------------------------------------------
class SolucionStep(BaseModel):
    order: int = Field(ge=1)
    instruction: str = Field(min_length=2, max_length=500)


class SolucionCreate(BaseModel):
    motivo_id: str = Field(min_length=36, max_length=36)
    name: str = Field(min_length=2, max_length=255)
    steps: list[SolucionStep] = Field(default_factory=list)
    template_email: Optional[str] = Field(default=None, max_length=8000)
    template_wa: Optional[str] = Field(default=None, max_length=2000)
    automatable: bool = False


class SolucionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    steps: Optional[list[SolucionStep]] = None
    template_email: Optional[str] = None
    template_wa: Optional[str] = None
    automatable: Optional[bool] = None


# ---------- Automation permissions (the matrix) --------------------------
Channel = Literal["email", "whatsapp", "api"]


class AutomationPermissionUpsert(BaseModel):
    client_id: str = Field(min_length=36, max_length=36)
    solucion_id: str = Field(min_length=36, max_length=36)
    channel: Channel
    allowed: bool
