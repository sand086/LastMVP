"""Iter65 — Proxy autenticado para imágenes de reports de Routal.

Las URLs ``https://api.routal.com/v3/stop/report/{rid}/image/{iid}`` requieren
auth con ``private_key=`` como query param. No podemos exponer el key al
frontend, así que el agente abre las fotos vía este proxy:

  GET /api/agent/routal/image-proxy?ticket_id=...&report_id=...&image_id=...

Verifica que el agente tenga acceso al ticket (scope chequeado abajo) y
streamea la imagen.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse

from core.db import get_db
from core.errors import ResourceNotFoundException
from middleware.rbac import require_min_role
from routes.admin_routal_enrich import _resolve_routal_api_key

router = APIRouter(prefix="/api/agent/routal", tags=["agent-routal-proxy"])

_RBAC = require_min_role("agent")


@router.get("/image-proxy")
async def routal_image_proxy(
    request: Request,
    ticket_id: str = Query(...),
    report_id: str = Query(...),
    image_id: str = Query(...),
    _: object = Depends(_RBAC),
):
    """Streamea una imagen del report Routal con auth backend.

    Requisitos:
      - ``ticket_id`` debe existir y pertenecer al tenant del usuario.
      - ``report_id``/``image_id`` deben matchear el ``routal_report``
        guardado en la guía del ticket (anti-IDOR: el agente sólo puede ver
        imágenes asociadas a tickets que él puede consultar).
    """
    db = get_db()
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

    # Validar que image_id está en el report guardado en la guía → anti-IDOR
    rr = (guia.get("carrier_meta") or {}).get("routal_report") or {}
    detail_imgs = (ticket.get("carrier_incident_detail") or {}).get("images") or []
    rr_imgs = rr.get("images") or []
    valid_ids = {im.get("id") for im in (rr_imgs + detail_imgs) if im}
    if image_id not in valid_ids:
        raise HTTPException(status_code=403,
                            detail="Image not associated with this ticket")

    client = await db.clients.find_one(
        {"id": guia["client_id"], "tenant_id": user.tenant_id}, {"_id": 0})
    if not client:
        raise ResourceNotFoundException("Cliente no encontrado")
    api_key, base_url = await _resolve_routal_api_key(db, client)
    if not api_key:
        raise HTTPException(status_code=503,
                            detail="Routal API key not configured")

    url = f"{base_url}/v3/stop/report/{report_id}/image/{image_id}"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as ac:
        upstream = await ac.get(url, params={"private_key": api_key})
    if upstream.status_code != 200:
        raise HTTPException(
            status_code=upstream.status_code,
            detail=f"Routal returned {upstream.status_code}")

    content_type = upstream.headers.get("content-type", "image/jpeg")

    async def _stream():
        yield upstream.content

    return StreamingResponse(
        _stream(),
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )
