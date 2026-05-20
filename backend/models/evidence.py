"""Evidencia model — PROMPT 11.6.

Permite asociar una evidencia (foto/PDF + coordenadas opcionales) a un ticket
o a un reclamo. Las evidencias del reclamo viajan en `expediente.evidencia_ids`
(ya definido en PROMPT 13).
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


EvidenceKind = Literal["photo", "document"]
ALLOWED_MIME = {
    "image/jpeg": "photo",
    "image/png":  "photo",
    "image/webp": "photo",
    "image/heic": "photo",
    "image/heif": "photo",
    "application/pdf": "document",
}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class EvidenceMeta(BaseModel):
    """Metadata adjunta como query string del upload (multipart-friendly)."""
    ticket_id: Optional[str] = Field(default=None, min_length=36, max_length=36)
    claim_id: Optional[str] = Field(default=None, min_length=36, max_length=36)
    lat: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    lng: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    location_label: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _exactly_one_anchor(self) -> "EvidenceMeta":
        if not self.ticket_id and not self.claim_id:
            raise ValueError("ticket_id o claim_id es obligatorio.")
        if self.ticket_id and self.claim_id:
            raise ValueError("Sólo uno: ticket_id o claim_id, no ambos.")
        return self
