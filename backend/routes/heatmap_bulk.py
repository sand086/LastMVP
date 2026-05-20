"""Routes Heatmap (PROMPT 22) + Bulk + PDF (PROMPT 23).

Bundle A · FIX-A1 (Mayo 2026): the `close` and `change_status` bulk actions
now require typed confirmation when ``len(ticket_ids) >= 10`` and write to
``bulk_close_transactions`` so the user has a 30-second undo window through
``POST /api/admin/tickets/bulk-undo``.
"""
from __future__ import annotations
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.errors import ErrorCode, ResourceNotFoundException
from core.response import fail, ok
from core.uuid import new_id
from middleware.rbac import require_min_role
from repositories.bulk_close_transactions import (
    BULK_UNDO_WINDOW_SECONDS, BulkCloseTransactionsRepository,
)
from services.geocoding import heatmap_buckets
from services.pdf_export import (
    render_bulk_zip, render_ticket_pdf,
    render_claim_pdf, render_claims_bulk_zip,
)


router_dash = APIRouter(prefix="/api/dashboard", tags=["heatmap"])
router_admin = APIRouter(prefix="/api/admin", tags=["bulk-pdf"])

_AGENT_RBAC = require_min_role("agent")
_ADMIN_RBAC = require_min_role("admin")


# ─── Heatmap ─────────────────────────────────────────────────────────────
@router_dash.get("/heatmap")
async def heatmap(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    motivo_codigo: str | None = Query(default=None),
    carrier_code: str | None = Query(default=None),
    grid_decimals: int = Query(default=2, ge=1, le=4),
    _: object = Depends(_AGENT_RBAC),
):
    user = request.state.user
    points = await heatmap_buckets(
        tenant_id=user.tenant_id,
        date_from=date_from, date_to=date_to,
        motivo_codigo=motivo_codigo, carrier_code=carrier_code,
        grid_decimals=grid_decimals,
    )
    return ok({"items": points, "count": len(points)})


# ─── Bulk actions ────────────────────────────────────────────────────────
BulkAction = Literal["close", "assign", "add_comment", "change_status", "export_pdf"]

# Bundle A · FIX-A1: typed confirmation required for bulk close/change_status
# when count >= this threshold. Below this, friction is unnecessary.
BULK_TYPED_CONFIRMATION_THRESHOLD = 10
BULK_TYPED_CONFIRMATION_KEYWORD = "CERRAR"


class BulkBody(BaseModel):
    ticket_ids: list[str] = Field(min_length=1, max_length=500)
    action: BulkAction
    payload: dict = Field(default_factory=dict)
    typed_confirmation: Optional[str] = None


@router_admin.post("/tickets/bulk")
async def bulk_action(body: BulkBody, request: Request, _: object = Depends(_ADMIN_RBAC)):
    user = request.state.user
    db = get_db()
    # Filtrar a tickets del tenant
    cursor = db.tickets.find(
        {"id": {"$in": body.ticket_ids}, "tenant_id": user.tenant_id},
        {"_id": 0, "id": 1, "is_terminal": 1, "status": 1, "client_id": 1},
    )
    valid = [t async for t in cursor]
    valid_ids = [t["id"] for t in valid]
    skipped = [tid for tid in body.ticket_ids if tid not in valid_ids]

    # Bundle A · FIX-A1: typed-confirmation guard for close/change_status
    if body.action in {"close", "change_status"} and \
            len(body.ticket_ids) >= BULK_TYPED_CONFIRMATION_THRESHOLD and \
            (body.typed_confirmation or "") != BULK_TYPED_CONFIRMATION_KEYWORD:
        return fail(
            ErrorCode.VALIDATION_FAILED,
            f"Para cerrar {len(body.ticket_ids)} tickets debes escribir "
            f"'{BULK_TYPED_CONFIRMATION_KEYWORD}' en el campo typed_confirmation.",
            field="typed_confirmation",
        )

    if body.action == "close":
        # R02: no sobrescribir terminal
        ids_to_close = [t["id"] for t in valid if not t.get("is_terminal")]
        # Bundle A · FIX-A1: capturar previous_states ANTES del update
        previous_states = [
            {"ticket_id": t["id"], "status": t.get("status"),
             "is_terminal": bool(t.get("is_terminal", False))}
            for t in valid if not t.get("is_terminal")
        ]
        result = await db.tickets.update_many(
            {"id": {"$in": ids_to_close}, "tenant_id": user.tenant_id},
            {"$set": {"status": "closed", "is_terminal": True,
                      "closed_at": _now(), "updated_at": _now(),
                      "closed_by": user.id}},
        )
        for tid in ids_to_close:
            await _append_event(db, user.tenant_id, tid, "bulk_close",
                                {"actor": user.id})
        # Bundle A · FIX-A1: persistir transacción para habilitar undo
        txn_repo = BulkCloseTransactionsRepository(tenant_id=user.tenant_id)
        txn = await txn_repo.create(
            user_id=user.id, action_type="close",
            tickets_count=result.modified_count,
            ticket_ids=ids_to_close,
            previous_states=previous_states,
        )
        return ok({"affected": result.modified_count, "skipped_count": len(skipped),
                   "skipped_ids": skipped[:50],
                   "transaction_id": txn["id"],
                   "undo_window_seconds": BULK_UNDO_WINDOW_SECONDS})

    if body.action == "assign":
        agent_id = body.payload.get("agent_id")
        if not agent_id:
            return fail("VALIDATION_FAILED", "Falta payload.agent_id", field="payload")
        # Verificar que agent existe en el tenant
        a = await db.users.find_one({"id": agent_id, "tenant_id": user.tenant_id,
                                     "role": {"$in": ["agent", "supervisor"]}},
                                    {"_id": 0, "id": 1})
        if not a:
            return fail("VALIDATION_FAILED", "Agent no válido", field="payload.agent_id")
        result = await db.tickets.update_many(
            {"id": {"$in": valid_ids}, "tenant_id": user.tenant_id},
            {"$set": {"assigned_to": agent_id, "updated_at": _now()}},
        )
        for tid in valid_ids:
            await _append_event(db, user.tenant_id, tid, "bulk_assign",
                                {"agent_id": agent_id, "actor": user.id})
        return ok({"affected": result.modified_count, "skipped_count": len(skipped)})

    if body.action == "add_comment":
        text = (body.payload.get("text") or "").strip()
        if not text:
            return fail("VALIDATION_FAILED", "Falta payload.text", field="payload")
        for tid in valid_ids:
            await _append_event(db, user.tenant_id, tid, "comment",
                                {"text": text[:2000], "actor": user.id})
        return ok({"affected": len(valid_ids), "skipped_count": len(skipped)})

    if body.action == "change_status":
        status = body.payload.get("status")
        terminal_set = {"closed", "cancelled", "resolved"}
        if not status:
            return fail("VALIDATION_FAILED", "Falta payload.status", field="payload")
        # R02: no sobrescribir terminal
        ids = [t["id"] for t in valid if not t.get("is_terminal")]
        # Bundle A · FIX-A1: capturar previous_states ANTES del update
        previous_states = [
            {"ticket_id": t["id"], "status": t.get("status"),
             "is_terminal": bool(t.get("is_terminal", False))}
            for t in valid if not t.get("is_terminal")
        ]
        result = await db.tickets.update_many(
            {"id": {"$in": ids}, "tenant_id": user.tenant_id},
            {"$set": {"status": status, "updated_at": _now(),
                      "is_terminal": status in terminal_set}},
        )
        for tid in ids:
            await _append_event(db, user.tenant_id, tid, "bulk_status_change",
                                {"status": status, "actor": user.id})
        # Bundle A · FIX-A1: registrar transacción para undo
        txn_repo = BulkCloseTransactionsRepository(tenant_id=user.tenant_id)
        txn = await txn_repo.create(
            user_id=user.id, action_type="change_status",
            tickets_count=result.modified_count,
            ticket_ids=ids,
            previous_states=previous_states,
            target_status=status,
        )
        return ok({"affected": result.modified_count, "skipped_count": len(skipped),
                   "transaction_id": txn["id"],
                   "undo_window_seconds": BULK_UNDO_WINDOW_SECONDS})

    if body.action == "export_pdf":
        from fastapi.responses import Response
        zip_bytes = await render_bulk_zip(tenant_id=user.tenant_id,
                                          ticket_ids=valid_ids)
        return Response(
            content=zip_bytes, media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="tickets-{len(valid_ids)}.zip"',
                "X-MyE-Bulk-Count": str(len(valid_ids)),
            },
        )

    return fail("VALIDATION_FAILED", f"Acción '{body.action}' no soportada", field="action")


# ─── Bundle A · FIX-A1: bulk undo ────────────────────────────────────────
class BulkUndoBody(BaseModel):
    transaction_id: str = Field(min_length=8, max_length=64)


@router_admin.post("/tickets/bulk-undo")
async def bulk_undo(body: BulkUndoBody, request: Request,
                    _: object = Depends(_ADMIN_RBAC)):
    """Revierte una transacción de bulk close/change_status dentro de la
    ventana de 30s, respetando R02 (no reabrir terminales por carrier) y
    sin sobrescribir tickets modificados por otro actor.
    """
    from datetime import datetime, timezone
    user = request.state.user
    db = get_db()
    txn_repo = BulkCloseTransactionsRepository(tenant_id=user.tenant_id)
    txn = await txn_repo.find_by_id(body.transaction_id)
    if not txn:
        return fail(ErrorCode.RESOURCE_NOT_FOUND,
                    "Transacción no encontrada.",
                    field="transaction_id")
    # Ownership: el undo lo dispara el mismo usuario que ejecutó la acción.
    if txn.get("user_id") != user.id:
        return fail(ErrorCode.RBAC_DENIED,
                    "Sólo el usuario que ejecutó la acción puede revertirla.",
                    field="transaction_id")
    # Ventana de 30 segundos
    if txn.get("undone_at"):
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Esta transacción ya fue revertida.",
                    field="transaction_id")
    window_end = datetime.fromisoformat(txn["undo_window_end"])
    if datetime.now(timezone.utc) > window_end:
        return fail(
            ErrorCode.TERMINAL_STATE,
            "La ventana de 30 segundos para deshacer ya expiró.",
            field="transaction_id",
        )

    executed_at_iso = txn["executed_at"]
    reverted: list[str] = []
    skipped_reasons: list[dict] = []
    for prev in txn.get("previous_states", []):
        tid = prev["ticket_id"]
        current = await db.tickets.find_one(
            {"id": tid, "tenant_id": user.tenant_id},
            {"_id": 0, "is_terminal": 1, "updated_at": 1, "status": 1},
        )
        if not current:
            skipped_reasons.append({"ticket_id": tid, "reason": "not_found"})
            continue
        # R02: si el carrier marcó terminal entre el close y el undo, no reabrir
        if current.get("is_terminal") and prev.get("status") not in {
            "closed", "cancelled", "resolved",
        }:
            # El ticket llegó a terminal por otro proceso después
            if (current.get("updated_at") or "") > executed_at_iso \
               and current.get("status") != "closed":
                skipped_reasons.append(
                    {"ticket_id": tid, "reason": "terminal_state"})
                continue
        # Modificado por otro actor entre executed_at y ahora
        if (current.get("updated_at") or "") > executed_at_iso \
           and current.get("status") not in {"closed", txn.get("target_status")}:
            skipped_reasons.append(
                {"ticket_id": tid, "reason": "modified_by_other"})
            continue
        await db.tickets.update_one(
            {"id": tid, "tenant_id": user.tenant_id},
            {"$set": {
                "status": prev["status"],
                "is_terminal": prev.get("is_terminal", False),
                "updated_at": _now(),
            },
             "$unset": {"closed_at": "", "closed_by": ""}},
        )
        await _append_event(
            db, user.tenant_id, tid, "bulk_undone",
            {"transaction_id": txn["id"], "actor": user.id,
             "reverted_to_status": prev["status"]},
        )
        reverted.append(tid)

    partial = len(skipped_reasons) > 0
    await txn_repo.mark_undone(txn["id"], partial=partial)
    return ok({
        "reverted_count": len(reverted),
        "skipped_count": len(skipped_reasons),
        "skipped_reasons": skipped_reasons,
    })


@router_admin.get("/tickets/{ticket_id}/export.pdf")
async def export_ticket_pdf(ticket_id: str, request: Request, _: object = Depends(_ADMIN_RBAC)):
    from fastapi.responses import Response
    user = request.state.user
    try:
        pdf = await render_ticket_pdf(tenant_id=user.tenant_id, ticket_id=ticket_id)
    except ValueError:
        raise ResourceNotFoundException()
    return Response(
        content=pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ticket-{ticket_id}.pdf"',
        },
    )


# ─── Reclamos: PDF individual + bulk ZIP ──────────────────────────────────
class ClaimsBulkPdfBody(BaseModel):
    claim_ids: list[str] = Field(min_length=1, max_length=200)


@router_admin.get("/claims/{claim_id}/export.pdf")
async def export_claim_pdf(claim_id: str, request: Request,
                            _: object = Depends(_ADMIN_RBAC)):
    """PDF del expediente de un reclamo (PROMPT 13 V1 backlog)."""
    from fastapi.responses import Response
    user = request.state.user
    try:
        pdf = await render_claim_pdf(tenant_id=user.tenant_id, claim_id=claim_id)
    except ValueError:
        raise ResourceNotFoundException()
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="reclamo-{claim_id}.pdf"'},
    )


@router_admin.post("/claims/bulk-export.zip")
async def export_claims_bulk(body: ClaimsBulkPdfBody, request: Request,
                              _: object = Depends(_ADMIN_RBAC)):
    """ZIP con un PDF por reclamo (cap 200)."""
    from fastapi.responses import Response
    user = request.state.user
    db = get_db()
    # Sólo IDs del tenant
    cursor = db.claims.find(
        {"id": {"$in": body.claim_ids}, "tenant_id": user.tenant_id},
        {"_id": 0, "id": 1},
    )
    valid_ids = [d["id"] async for d in cursor]
    if not valid_ids:
        raise ResourceNotFoundException()
    zip_bytes = await render_claims_bulk_zip(
        tenant_id=user.tenant_id, claim_ids=valid_ids,
    )
    return Response(
        content=zip_bytes, media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="reclamos-bulk-{len(valid_ids)}.zip"',
            "X-MyE-Bulk-Count": str(len(valid_ids)),
        },
    )


# ─── Helpers ─────────────────────────────────────────────────────────────
def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def _append_event(db, tenant_id: str, ticket_id: str,
                        event_type: str, payload: dict) -> None:
    await db.ticket_events.insert_one({
        "id": new_id(), "tenant_id": tenant_id, "ticket_id": ticket_id,
        "event_type": event_type, "payload": payload,
        "description": event_type, "created_at": _now(),
    })
