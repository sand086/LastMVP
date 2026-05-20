"""Evidence repository + filesystem storage — PROMPT 11.6.

Las evidencias se guardan en disco bajo
  ``/app/data/evidences/{tenant_id}/{owner_kind}/{owner_id}/{evidence_id}.{ext}``

con lectura sólo via endpoint autenticado (no se sirven directo desde nginx).
"""
from __future__ import annotations
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.uuid import new_id
from repositories.base import BaseRepository

EVIDENCE_ROOT = Path(os.environ.get("EVIDENCE_ROOT", "/app/data/evidences"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ext(filename: str | None, mime: str) -> str:
    """Devuelve una extensión razonable (sin .exe ni paths)."""
    fallback = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
                "image/heic": "heic", "image/heif": "heif",
                "application/pdf": "pdf"}.get(mime, "bin")
    if not filename:
        return fallback
    ext = Path(filename).suffix.lstrip(".").lower()
    return ext if ext.isalnum() and 1 <= len(ext) <= 8 else fallback


def _path_for(*, tenant_id: str, owner_kind: str, owner_id: str, evidence_id: str, ext: str) -> Path:
    folder = EVIDENCE_ROOT / tenant_id / owner_kind / owner_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{evidence_id}.{ext}"


class EvidenceRepository(BaseRepository):
    collection_name = "evidences"

    async def store(self, *, owner_kind: str, owner_id: str, uploader_id: str,
                    filename: str, mime: str, kind: str, content: bytes,
                    lat: Optional[float], lng: Optional[float],
                    location_label: Optional[str], note: Optional[str]) -> dict:
        eid = new_id()
        ext = _safe_ext(filename, mime)
        target = _path_for(
            tenant_id=self.tenant_id, owner_kind=owner_kind,
            owner_id=owner_id, evidence_id=eid, ext=ext,
        )
        # Atómico: escribe a tmp + rename
        tmp = target.with_suffix(target.suffix + f".tmp.{secrets.token_hex(4)}")
        tmp.write_bytes(content)
        tmp.replace(target)
        doc = {
            "id": eid, "tenant_id": self.tenant_id,
            "ticket_id": owner_id if owner_kind == "ticket" else None,
            "claim_id":  owner_id if owner_kind == "claim" else None,
            "uploader_id": uploader_id,
            "filename": filename, "mime": mime, "kind": kind,
            "size_bytes": len(content),
            "lat": lat, "lng": lng, "location_label": location_label,
            "note": note,
            "file_path": str(target),
            "created_at": _now_iso(),
        }
        await self.col.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list_for(self, *, ticket_id: Optional[str] = None,
                       claim_id: Optional[str] = None) -> list[dict]:
        q: dict = {}
        if ticket_id:
            q["ticket_id"] = ticket_id
        if claim_id:
            q["claim_id"] = claim_id
        return await self.find(q, sort=[("created_at", 1)], limit=500)

    async def delete_with_file(self, evidence_id: str) -> bool:
        doc = await self.find_one({"id": evidence_id})
        if not doc:
            return False
        try:
            Path(doc["file_path"]).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        deleted = await self.delete_one({"id": evidence_id})
        return deleted > 0
