"""Evidencias routes — PROMPT 11.6.

  POST   /api/evidencias/upload            multipart/form-data + query params
  GET    /api/evidencias?ticket_id=...     list by anchor
  GET    /api/evidencias?claim_id=...
  GET    /api/evidencias/{id}/file         serve the binary (auth required)
  DELETE /api/evidencias/{id}              hard-delete (uploader o admin+)
"""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from core.errors import (
    ErrorCode, MyEException, ResourceNotFoundException,
    TerminalStateException,
)
from core.response import fail, ok
from middleware.rbac import require_min_role, ROLE_RANK
from models.evidence import ALLOWED_MIME, MAX_BYTES, EvidenceMeta
from repositories.claims import ClaimRepository
from repositories.evidences import EvidenceRepository
from repositories.tickets import TicketRepository

router = APIRouter(prefix="/api/evidencias", tags=["evidencias"])
_RBAC = require_min_role("agent")


def _t(request: Request) -> str:
    return request.state.user.tenant_id


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    ticket_id: str | None = Form(default=None),
    claim_id: str | None = Form(default=None),
    lat: float | None = Form(default=None),
    lng: float | None = Form(default=None),
    location_label: str | None = Form(default=None),
    note: str | None = Form(default=None),
    _: object = Depends(_RBAC),
):
    user = request.state.user
    # Validate metadata via Pydantic (centralizes the XOR rule + ranges)
    try:
        meta = EvidenceMeta(
            ticket_id=ticket_id, claim_id=claim_id,
            lat=lat, lng=lng, location_label=location_label, note=note,
        )
    except Exception as e:  # noqa: BLE001
        return fail(ErrorCode.VALIDATION_FAILED, str(e))

    mime = (file.content_type or "").lower()
    if mime not in ALLOWED_MIME:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"Tipo no permitido: {mime}. Sólo imágenes (JPG/PNG/WebP/HEIC) o PDF.",
                    field="file")

    # Validate anchor exists in tenant + check terminal state
    if meta.ticket_id:
        ticket = await TicketRepository(tenant_id=user.tenant_id).find_one({"id": meta.ticket_id})
        if not ticket:
            raise ResourceNotFoundException()
        owner_kind, owner_id = "ticket", meta.ticket_id
    else:
        claim = await ClaimRepository(tenant_id=user.tenant_id).find_one({"id": meta.claim_id})
        if not claim:
            raise ResourceNotFoundException()
        if claim.get("is_terminal"):
            raise TerminalStateException("Reclamo en estado terminal — no admite evidencias nuevas.")
        owner_kind, owner_id = "claim", meta.claim_id

    # Read body with size guard
    content = await file.read()
    if len(content) > MAX_BYTES:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"Archivo excede {MAX_BYTES // (1024*1024)} MB.", field="file")
    if not content:
        return fail(ErrorCode.VALIDATION_FAILED, "Archivo vacío.", field="file")

    repo = EvidenceRepository(tenant_id=user.tenant_id)
    doc = await repo.store(
        owner_kind=owner_kind, owner_id=owner_id, uploader_id=user.id,
        filename=file.filename or "evidence.bin", mime=mime,
        kind=ALLOWED_MIME[mime], content=content,
        lat=meta.lat, lng=meta.lng, location_label=meta.location_label,
        note=meta.note,
    )
    # Mirror in timeline (R04) for tickets and (R30) for claims
    if owner_kind == "ticket":
        await TicketRepository(tenant_id=user.tenant_id).timeline.record(
            ticket_id=owner_id, event_type="evidence_added",
            actor_type="user", actor_id=user.id, channel="internal",
            payload={"evidence_id": doc["id"], "kind": doc["kind"],
                     "size_bytes": doc["size_bytes"],
                     "geo": bool(meta.lat and meta.lng)},
        )
    else:
        from repositories.claims import ClaimEventRepository
        await ClaimEventRepository(tenant_id=user.tenant_id).record(
            claim_id=owner_id, event_type="evidence_added",
            actor_type="agent", actor_id=user.id,
            payload={"evidence_id": doc["id"], "kind": doc["kind"],
                     "size_bytes": doc["size_bytes"],
                     "geo": bool(meta.lat and meta.lng)},
        )
    # Strip server path from response
    public = {k: v for k, v in doc.items() if k != "file_path"}
    return ok(public, status_code=201)


@router.get("")
async def list_evidences(
    request: Request,
    ticket_id: str | None = Query(default=None),
    claim_id: str | None = Query(default=None),
    _: object = Depends(_RBAC),
):
    if not ticket_id and not claim_id:
        return fail(ErrorCode.VALIDATION_FAILED, "ticket_id o claim_id obligatorio.")
    repo = EvidenceRepository(tenant_id=_t(request))
    items = await repo.list_for(ticket_id=ticket_id, claim_id=claim_id)
    public = [{k: v for k, v in it.items() if k != "file_path"} for it in items]
    return ok({"items": public, "count": len(public)})


@router.get("/{evidence_id}/file")
async def serve_file(evidence_id: str, request: Request, _: object = Depends(_RBAC)):
    repo = EvidenceRepository(tenant_id=_t(request))
    doc = await repo.find_one({"id": evidence_id})
    if not doc:
        raise ResourceNotFoundException()
    p = Path(doc["file_path"])
    if not p.exists():
        raise ResourceNotFoundException("Archivo no encontrado en disco.")
    return FileResponse(
        path=str(p), media_type=doc["mime"],
        filename=doc["filename"] or f"evidence-{evidence_id[:8]}",
    )


@router.delete("/{evidence_id}")
async def delete_evidence(evidence_id: str, request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    repo = EvidenceRepository(tenant_id=user.tenant_id)
    doc = await repo.find_one({"id": evidence_id})
    if not doc:
        raise ResourceNotFoundException()
    is_admin = ROLE_RANK.get(user.role, 0) >= ROLE_RANK["admin"]
    if doc["uploader_id"] != user.id and not is_admin:
        raise MyEException(ErrorCode.RBAC_DENIED, "Sólo el uploader o admin pueden borrar.")
    # Block deleting evidences referenced by a non-terminal claim's expediente
    if doc.get("claim_id"):
        claim = await ClaimRepository(tenant_id=user.tenant_id).find_one({"id": doc["claim_id"]})
        if claim and not claim.get("is_terminal"):
            evidence_ids = (claim.get("expediente") or {}).get("evidencia_ids") or []
            if evidence_id in evidence_ids:
                return fail(ErrorCode.TERMINAL_STATE,
                            "Evidencia incluida en expediente activo — quítala primero.")
    ok_del = await repo.delete_with_file(evidence_id)
    return ok({"deleted": ok_del, "id": evidence_id})
