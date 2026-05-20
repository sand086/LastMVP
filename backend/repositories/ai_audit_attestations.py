"""Auditor attestation log (PROMPT 26 V2 backlog item).

Cada vez que un usuario con permisos de auditoría descarga el CSV firmado o
firma una atestación voluntaria ("He revisado este lote"), se appendea un
evento append-only.

Esto cierra el loop de compliance: además del log inmutable de invocaciones IA
(R37), tenemos un log inmutable de QUIÉN auditó QUÉ y CUÁNDO.
"""
from __future__ import annotations
from typing import Optional


from .append_only import _AppendOnlyRepository


class AIAuditAttestationRepository(_AppendOnlyRepository):
    """Append-only — sin update/delete por diseño."""
    collection_name = "ai_audit_attestations"

    async def record_download(
        self, *, user_id: str, signature: str, rows: int,
        filters: dict, ip: Optional[str] = None,
    ) -> dict:
        return await self.append({
            "kind": "csv_download",
            "user_id": user_id,
            "signature": signature,
            "rows": rows,
            "filters": filters,
            "ip": ip,
            "comment": None,
        })

    async def record_review(
        self, *, user_id: str, signature: str, rows: int, comment: str,
        filters: dict, ip: Optional[str] = None,
    ) -> dict:
        """Atestación voluntaria 'He revisado este lote'."""
        return await self.append({
            "kind": "review_attestation",
            "user_id": user_id,
            "signature": signature,
            "rows": rows,
            "filters": filters,
            "comment": (comment or "").strip()[:500] or None,
            "ip": ip,
        })

    async def list_recent(self, *, limit: int = 100) -> list[dict]:
        cursor = self.col.find(
            {"tenant_id": self.tenant_id}, {"_id": 0},
        ).sort("created_at", -1).limit(limit)
        return await cursor.to_list(length=limit)
