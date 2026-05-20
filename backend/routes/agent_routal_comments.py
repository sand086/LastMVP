"""Iter67 — Comentarios bidireccionales con Routal.

Endpoints (agent+ scope):
  GET  /api/agent/routal/comments?ticket_id=...
       Lee el comentario actual del stop de Routal + historial local.
  POST /api/agent/routal/comments
       body: { ticket_id, comment, mode: "append" | "replace" }
       Envía el comentario al stop vía `PUT api.routal.com/v2/stop/{stop_id}`
       y guarda audit en `guia.carrier_meta.routal_comments_history[]`.

Modo "append" (default) antepone un header timestamped:
  [12/05 5:34pm · @carina.hernandez@thinkme.com.mx]
  Llamar antes de llegar al 5555555555
  ---
  <comentario previo>

Esto preserva auditoría para el driver y el historial completo.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.db import get_db
from core.errors import ResourceNotFoundException
from core.response import ok
from middleware.rbac import require_min_role
from routes.admin_routal_enrich import _resolve_routal_api_key

router = APIRouter(prefix="/api/agent/routal", tags=["agent-routal-comments"])

_RBAC = require_min_role("agent")


async def _ticket_to_routal_context(db, request: Request, ticket_id: str):
    user = request.state.user
    ticket = await db.tickets.find_one(
        {"id": ticket_id, "tenant_id": user.tenant_id}, {"_id": 0})
    if not ticket:
        raise ResourceNotFoundException("Ticket no encontrado")
    guia = await db.guias.find_one(
        {"id": ticket.get("guia_id"), "tenant_id": user.tenant_id},
        {"_id": 0})
    if not guia:
        raise ResourceNotFoundException("Guía no encontrada")
    if (guia.get("carrier_code") or "").lower() != "routal":
        raise HTTPException(status_code=400,
                            detail="La guía no es de Routal")
    stop_id = (guia.get("raw_payload") or {}).get("stop_id")
    if not stop_id:
        raise HTTPException(
            status_code=400,
            detail="Guía sin stop_id de Routal (re-pull necesario)")
    client = await db.clients.find_one(
        {"id": guia["client_id"], "tenant_id": user.tenant_id}, {"_id": 0})
    if not client:
        raise ResourceNotFoundException("Cliente no encontrado")
    api_key, base_url = await _resolve_routal_api_key(db, client)
    if not api_key:
        raise HTTPException(status_code=503,
                            detail="Routal API key no configurada")
    return user, ticket, guia, stop_id, api_key, base_url


@router.get("/comments")
async def get_comments(
    request: Request,
    ticket_id: str = Query(...),
    _: object = Depends(_RBAC),
):
    """Lee el comentario actual de Routal + historial local."""
    db = get_db()
    user, ticket, guia, stop_id, api_key, base_url = \
        await _ticket_to_routal_context(db, request, ticket_id)

    # Lee el stop fresh para obtener el comments actual real
    current = ""
    try:
        url = f"{base_url}/v2/plan/{guia['raw_payload'].get('plan_id')}/stops"
        async with httpx.AsyncClient(timeout=15) as ac:
            r = await ac.get(url, params={"private_key": api_key})
        if r.status_code == 200:
            stops = r.json()
            if isinstance(stops, dict):
                stops = stops.get("docs") or []
            for s in stops:
                if (s.get("id") or s.get("_id")) == stop_id:
                    current = s.get("comments") or ""
                    break
    except Exception:  # noqa: BLE001
        current = (guia.get("carrier_meta") or {}).get(
            "routal_comments_last", "")

    history = (guia.get("carrier_meta") or {}).get(
        "routal_comments_history") or []
    return ok({
        "ticket_id": ticket_id,
        "stop_id": stop_id,
        "current_comment": current,
        "history": history,
    })


class SendCommentRequest(BaseModel):
    ticket_id: str
    comment: str = Field(min_length=1, max_length=4000)
    mode: str = Field(default="append", pattern="^(append|replace)$")


def _format_header(user, now: datetime) -> str:
    label = (user.email or user.id or "agente").split("@")[0]
    # Hora en formato compacto local (CDMX → assume UTC-6, sin lib externa).
    # Para auditoría usamos ISO también en el audit log; la vista al driver
    # usa formato humano corto.
    stamp = now.strftime("%d/%m %H:%M UTC")
    return f"[{stamp} · @{label}]"


@router.post("/comments")
async def send_comment(
    payload: SendCommentRequest,
    request: Request,
    _: object = Depends(_RBAC),
):
    db = get_db()
    user, ticket, guia, stop_id, api_key, base_url = \
        await _ticket_to_routal_context(db, request, payload.ticket_id)

    now = datetime.now(timezone.utc)
    new_text = payload.comment.strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="Comentario vacío")

    # Build final payload según mode
    if payload.mode == "replace":
        final_comment = new_text
    else:
        # append: prepend header + new + sep + previous
        # Leemos el actual de Routal para no perder lo que esté allá.
        previous = ""
        try:
            url = f"{base_url}/v2/plan/{guia['raw_payload'].get('plan_id')}/stops"
            async with httpx.AsyncClient(timeout=15) as ac:
                r = await ac.get(url, params={"private_key": api_key})
            if r.status_code == 200:
                stops = r.json()
                if isinstance(stops, dict):
                    stops = stops.get("docs") or []
                for s in stops:
                    if (s.get("id") or s.get("_id")) == stop_id:
                        previous = (s.get("comments") or "").strip()
                        break
        except Exception:  # noqa: BLE001
            previous = ""
        header = _format_header(user, now)
        if previous:
            final_comment = f"{header}\n{new_text}\n---\n{previous}"
        else:
            final_comment = f"{header}\n{new_text}"
        # Soft cap @ 4000 chars (Routal acepta más pero mantenemos legible)
        if len(final_comment) > 4000:
            final_comment = final_comment[:4000].rstrip()

    # PUT a Routal
    success = False
    error_msg = None
    try:
        async with httpx.AsyncClient(timeout=20) as ac:
            r = await ac.put(
                f"{base_url}/v2/stop/{stop_id}",
                params={"private_key": api_key},
                json={"comments": final_comment},
            )
        if r.status_code == 200:
            success = True
        else:
            error_msg = f"Routal HTTP {r.status_code}: {r.text[:200]}"
    except httpx.HTTPError as e:  # noqa: BLE001
        error_msg = f"Routal connection error: {str(e)[:200]}"

    # Audit log local (siempre, incluso si falla — para diagnóstico)
    audit_entry = {
        "at": now.isoformat(),
        "agent_id": user.id,
        "agent_email": user.email,
        "agent_role": getattr(user, "role", None),
        "comment": new_text,
        "mode": payload.mode,
        "final_sent": final_comment if success else None,
        "success": success,
        "error": error_msg,
    }
    update_doc = {"$push": {
        "carrier_meta.routal_comments_history": audit_entry,
    }}
    if success:
        update_doc["$set"] = {
            "carrier_meta.routal_comments_last": final_comment,
            "carrier_meta.routal_comments_last_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
    await db.guias.update_one({"id": guia["id"]}, update_doc)

    # Timeline del ticket (para auditoría en la UI del agente)
    try:
        await db.ticket_events.insert_one({
            "ticket_id": ticket["id"],
            "tenant_id": user.tenant_id,
            "type": "carrier_comment_sent",
            "at": now.isoformat(),
            "actor_id": user.id,
            "actor_email": user.email,
            "payload": {
                "carrier": "routal", "stop_id": stop_id,
                "comment": new_text, "mode": payload.mode,
                "success": success,
            },
        })
    except Exception:  # noqa: BLE001
        pass

    if not success:
        raise HTTPException(
            status_code=502,
            detail=error_msg or "Error enviando comentario a Routal")

    return ok({
        "ticket_id": payload.ticket_id,
        "stop_id": stop_id,
        "current_comment": final_comment,
        "history_count": len(
            (guia.get("carrier_meta") or {}).get(
                "routal_comments_history") or []) + 1,
        "mode": payload.mode,
    })
