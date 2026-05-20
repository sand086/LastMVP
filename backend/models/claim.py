"""Reclamos models — PROMPT 13 V1."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

ClaimStatus = Literal[
    "promovido", "expediente_en_armado", "enviado_carrier",
    "en_dictamen_carrier", "aprobado_carrier", "rechazado_carrier",
    "en_conciliacion", "conciliado", "desistido",
]
DamageType = Literal["extravio", "dano_total", "dano_parcial", "retraso"]

# R28 — terminales
TERMINAL_CLAIM_STATUSES = {"conciliado", "desistido"}

# R31 — matriz de transiciones (sec 6 del prompt)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "promovido":            {"expediente_en_armado", "desistido"},
    "expediente_en_armado": {"enviado_carrier", "desistido"},
    "enviado_carrier":      {"en_dictamen_carrier"},
    "en_dictamen_carrier":  {"aprobado_carrier", "rechazado_carrier"},
    "aprobado_carrier":     {"en_conciliacion"},
    "rechazado_carrier":    {"desistido", "en_conciliacion"},
    "en_conciliacion":      {"conciliado", "desistido"},
    "conciliado":           set(),
    "desistido":            set(),
}


class PromoteRequest(BaseModel):
    tipo_dano: DamageType
    monto_reclamado: float = Field(gt=0, le=10_000_000)
    divisa: str = Field(default="MXN", min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    notas_iniciales: Optional[str] = Field(default=None, max_length=2000)


class ExpedienteUpdate(BaseModel):
    """Campos opcionales para completar el expediente (R35)."""
    monto_reclamado: Optional[float] = Field(default=None, gt=0)
    tipo_dano: Optional[DamageType] = None
    declaracion_cliente: Optional[str] = Field(default=None, max_length=8000)
    evidencia_ids: Optional[list[str]] = None  # ids de reclamo_evidencias_carrier ya cargadas


class TransitionRequest(BaseModel):
    target: ClaimStatus
    reason: Optional[str] = Field(default=None, max_length=500)


class CarrierDictamenWebhook(BaseModel):
    carrier_referencia: str = Field(min_length=1, max_length=100)
    tracking_id: str = Field(min_length=1, max_length=100)
    decision: Literal["approved", "rejected"]
    monto_aprobado: Optional[float] = None
    divisa: str = Field(default="MXN", pattern=r"^[A-Z]{3}$")
    razon_rechazo: Optional[str] = Field(default=None, max_length=2000)
    evidencias_url: Optional[list[str]] = None


class ConciliateRequest(BaseModel):
    monto_conciliado: float = Field(gt=0)
    divisa: str = Field(default="MXN", pattern=r"^[A-Z]{3}$")
    notas_conciliacion: Optional[str] = Field(default=None, max_length=2000)


class NotifyClientRequest(BaseModel):
    """P0.5 — comunicación al CxC del cliente (R32: nunca automática sin
    promoción manual del agente, lo cual ya ocurrió antes de llegar acá)."""
    subject: Optional[str] = Field(default=None, max_length=200)
    message: str = Field(min_length=10, max_length=5000)
    cta_url: Optional[str] = Field(default=None, max_length=500)
