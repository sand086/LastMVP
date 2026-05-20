"""Agent Panel routes (PROMPT 08).

  GET   /api/agent/queue                       my queue + unassigned tickets
  POST  /api/agent/tickets/{id}/take           claim an unassigned ticket
  PATCH /api/agent/tickets/{id}/status         change status (in_progress, waiting_*, resolved, claim)
  PATCH /api/agent/tickets/{id}/solucion       attach a solucion + channel
  POST  /api/agent/tickets/{id}/automate       evaluate R03 + (stub) execute
"""
from __future__ import annotations
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator

from core.errors import RbacDeniedException, ResourceNotFoundException, MyEException, ErrorCode
from core.response import fail, ok
from middleware.rbac import require_min_role
from repositories.tickets import TicketRepository, TERMINAL_TICKET_STATUSES
from services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Anyone agent+ may see/operate the panel; client_viewer is excluded.
_RBAC = require_min_role("agent")


def _t(request: Request) -> str:
    return request.state.user.tenant_id


# ------------------------- Models ----------------------------------------
class StatusChange(BaseModel):
    status: Literal["pending", "in_progress", "waiting_client", "waiting_carrier",
                    "resolved", "closed", "claim"]
    reason: Optional[str] = Field(default=None, max_length=500)


class SolucionAttach(BaseModel):
    solucion_id: str = Field(min_length=36, max_length=36)
    channel: Literal["email", "whatsapp", "api", "internal"] = "email"


class AutomationRequest(BaseModel):
    channel: Literal["email", "whatsapp", "api"] = "email"


class BulkTicketIds(BaseModel):
    ticket_ids: list[str] = Field(min_length=1, max_length=200)


class GuiaCancelPayload(BaseModel):
    """Body para `POST /api/agent/guias/{guia_id}/cancel`.

    `project_id` es opcional: si la guía ya tiene `carrier_meta.routal_project_id`
    persistido (ingesta multi-proyecto), se usa ese y NO hace falta enviarlo.
    Si el front lo manda explícito, gana sobre el persistido.
    `comments` se incluye en el payload outbound del carrier.
    """
    project_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    comments: Optional[str] = Field(default=None, max_length=500)

class BulkStatusChange(BulkTicketIds):
    status: Literal["pending", "in_progress", "waiting_client", "waiting_carrier",
                    "resolved", "closed", "claim"]
    reason: Optional[str] = Field(default=None, max_length=500)


class CommentPayload(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    visibility: Literal["internal", "external"] = "internal"
    # Bundle iter44 — destinatarios del email cuando visibility=external.
    # Pre-llenados por el frontend desde guia.recipient.email, pero editables
    # por el agente para garantizar que se contacte el correo correcto.
    # El servicio de envío real (Resend) usa estos arrays.
    to: list[str] = Field(default_factory=list, max_length=10)
    cc: list[str] = Field(default_factory=list, max_length=10)
    bcc: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def _validate_emails(cls, v):
        import re
        rx = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
        for em in v:
            if not rx.match(em):
                raise ValueError(f"Email inválido: {em}")
        return v


# ------------------------- Endpoints -------------------------------------
@router.get("/queue")
async def queue(
    request: Request,
    include_unassigned: bool = Query(default=True),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(_RBAC),
):
    repo = TicketRepository(tenant_id=_t(request))
    me = request.state.user.id
    or_clause = [{"assigned_agent_id": me}]
    if include_unassigned:
        or_clause.append({"assigned_agent_id": None})
    query: dict = {"$or": or_clause}
    if status:
        query["status"] = status
    else:
        query["status"] = {"$nin": list(TERMINAL_TICKET_STATUSES)}
    items = await repo.find(query, sort=[("created_at", -1)], limit=limit)
    # Iter49 — enrich con `incident_type_label` (legible) e `incident_label`
    # (final: prefiere `guia.carrier_incidence` cuando existe). Batch lookup
    # a guias para evitar N+1.
    # Iter51 — además traemos `carrier_code` y `tracking_id` desde la guia
    # para que la vista Tabla del agente pueda mostrar el carrier real.
    from services.incident_labels import enrich_incident_label_many
    guia_ids = [t["guia_id"] for t in items if t.get("guia_id")]
    cmap: dict[str, str] = {}
    if guia_ids:
        from core.db import get_db
        cursor = get_db().guias.find(
            {"tenant_id": _t(request), "id": {"$in": guia_ids}},
            {"_id": 0, "id": 1, "carrier_incidence": 1,
             "carrier_code": 1, "tracking_id": 1},
        )
        guia_by_id: dict[str, dict] = {}
        async for g in cursor:
            guia_by_id[g["id"]] = g
            ci = g.get("carrier_incidence")
            if ci:
                cmap[g["id"]] = ci
        # Enrich ticket con carrier_code + tracking_id desde la guía (sin
        # pisar si el ticket ya los tiene seteados — los ticket pueden
        # cachearlos al crearse).
        for t in items:
            gid = t.get("guia_id")
            if not gid:
                continue
            g = guia_by_id.get(gid)
            if not g:
                continue
            if not t.get("carrier_code") and g.get("carrier_code"):
                t["carrier_code"] = g["carrier_code"]
            if not t.get("tracking_id") and g.get("tracking_id"):
                t["tracking_id"] = g["tracking_id"]
    enrich_incident_label_many(items, carrier_incidence_by_guia=cmap)
    mine = [t for t in items if t.get("assigned_agent_id") == me]
    pool = [t for t in items if t.get("assigned_agent_id") is None]
    return ok({
        "mine": mine,
        "pool": pool,
        "totals": {"mine": len(mine), "pool": len(pool)},
    })


@router.post("/tickets/{ticket_id}/take")
async def take_ticket(ticket_id: str, request: Request, _: object = Depends(_RBAC)):
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    t = await repo.find_one({"id": ticket_id})
    if not t:
        raise ResourceNotFoundException()
    if t.get("assigned_agent_id") and t["assigned_agent_id"] != user.id:
        raise MyEException(ErrorCode.RBAC_DENIED, "Ticket ya asignado a otro agente.")
    await repo.assign(ticket_id, user.id, actor_id=user.id)
    return ok(await repo.find_one({"id": ticket_id}))


@router.patch("/tickets/{ticket_id}/status")
async def change_status(ticket_id: str, payload: StatusChange, request: Request,
                        _: object = Depends(_RBAC)):
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    t = await repo.find_one({"id": ticket_id})
    if not t:
        raise ResourceNotFoundException()
    # Only the owner (or admin+) can change status
    from middleware.rbac import ROLE_RANK
    if t.get("assigned_agent_id") not in (user.id, None) and ROLE_RANK.get(user.role, 0) < ROLE_RANK["admin"]:
        raise RbacDeniedException()
    await repo.change_status(ticket_id, payload.status, actor_id=user.id, reason=payload.reason)
    return ok(await repo.find_one({"id": ticket_id}))


@router.patch("/tickets/{ticket_id}/solucion")
async def attach_solucion(ticket_id: str, payload: SolucionAttach, request: Request,
                          _: object = Depends(_RBAC)):
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    t = await repo.find_one({"id": ticket_id})
    if not t:
        raise ResourceNotFoundException()
    # Verify the solucion exists in the same tenant — R01/R08
    from repositories.catalog import SolucionRepository
    sol = await SolucionRepository(tenant_id=user.tenant_id).find_one({"id": payload.solucion_id})
    if not sol:
        raise ResourceNotFoundException("Solución no encontrada en este tenant.")
    await repo.set_solucion(ticket_id, solucion_id=payload.solucion_id, channel=payload.channel,
                            actor_id=user.id)
    return ok(await repo.find_one({"id": ticket_id}))


@router.post("/tickets/{ticket_id}/automate")
async def evaluate_and_run_automation(ticket_id: str, payload: AutomationRequest,
                                      request: Request, _: object = Depends(_RBAC)):
    """Evaluates R03 + executes automation when allowed (PROMPT 11).

    - email: envía un email vía Resend al ops_contact_email del cliente.
    - whatsapp: genera un deeplink wa.me listo para que el agente lo abra.
    - api: reservado para PROMPT 20 (HTTP a carrier).
    """
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    ticket = await repo.find_one({"id": ticket_id})
    if not ticket:
        raise ResourceNotFoundException()
    engine = WorkflowEngine(tenant_id=user.tenant_id)
    reason = await engine.evaluate_automation_for_ticket(ticket, channel=payload.channel)
    if reason != "ok":
        return ok({
            "can_automate": False, "reason": reason, "executed": False,
        })
    from services.automation_service import AutomationService
    svc = AutomationService(tenant_id=user.tenant_id, actor_id=user.id)
    outcome = await svc.execute_for_ticket(ticket_id, channel=payload.channel)
    return ok({
        "can_automate": True, "reason": outcome.reason,
        "executed": outcome.executed, "channel": outcome.channel,
        "artifact": outcome.artifact or {},
    })


class ReopenRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


@router.post("/tickets/{ticket_id}/request-reopen")
async def request_reopen(ticket_id: str, payload: ReopenRequest,
                         request: Request, _: object = Depends(_RBAC)):
    """Bundle B · FIX-B2 — Solicitud de reapertura de ticket terminal.

    NO reabre directamente. Crea una entrada en `reopen_requests` para que
    el supervisor la apruebe. Devuelve 422 si el ticket no es terminal.

    Bundle B · Iter30 · Idempotencia (Mayo 2026): si el mismo usuario ya
    tiene una solicitud pendiente para este ticket, devolvemos la existente
    con `idempotent_hit=True` en lugar de crear duplicado. Evita ruido en
    la cola del supervisor cuando el agente clica dos veces el botón.
    """
    from datetime import datetime, timezone
    from core.db import get_db
    from core.uuid import new_id
    from services.rules.evaluators.r02 import TERMINAL_TICKET_STATUSES

    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    ticket = await repo.find_one({"id": ticket_id})
    if not ticket:
        raise ResourceNotFoundException()
    status = (ticket.get("status") or "").lower()
    is_terminal = bool(ticket.get("is_terminal")) or status in TERMINAL_TICKET_STATUSES
    if not is_terminal:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "El ticket no está en estado terminal — no requiere reapertura.",
                    field="ticket_id")
    db = get_db()
    # Idempotencia: ¿existe una request pending del mismo user para este ticket?
    existing = await db.reopen_requests.find_one(
        {
            "tenant_id": user.tenant_id,
            "ticket_id": ticket_id,
            "requested_by": user.id,
            "status": "pending",
        },
        {"_id": 0},
    )
    if existing:
        return ok({"request": existing, "idempotent_hit": True})

    doc = {
        "id": new_id(),
        "tenant_id": user.tenant_id,
        "ticket_id": ticket_id,
        "requested_by": user.id,
        "requested_by_email": user.email,
        "reason": payload.reason,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decided_at": None,
        "decided_by": None,
    }
    await db.reopen_requests.insert_one(doc)
    doc.pop("_id", None)
    # Audit trail vía timeline
    await db.timeline_events.insert_one({
        "id": new_id(), "tenant_id": user.tenant_id,
        "ticket_id": ticket_id,
        "event_type": "action",
        "actor_type": "user", "actor_id": user.id,
        "payload": {"action": "request_reopen", "reason": payload.reason},
        "created_at": doc["created_at"],
    })
    return ok({"request": doc, "idempotent_hit": False})


# ════════════════════════ Detail + Comment + Bulk ═══════════════════════
@router.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: str, request: Request, _: object = Depends(_RBAC)):
    """Detalle del ticket para el agente (mismo shape que admin/tickets/{id}
    pero con scope tenant + visibilidad agent). Incluye timeline, guía,
    reclamo activo y conteo de evidencias para el panel de contexto.
    """
    from core.db import get_db
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    ticket = await repo.find_one({"id": ticket_id})
    if not ticket:
        raise ResourceNotFoundException()
    db = get_db()
    timeline = await db.timeline_events.find(
        {"tenant_id": user.tenant_id, "ticket_id": ticket_id}, {"_id": 0},
    ).sort("created_at", 1).limit(500).to_list(length=500)
    guia = None
    if ticket.get("guia_id"):
        guia = await db.guias.find_one(
            {"tenant_id": user.tenant_id, "id": ticket["guia_id"]},
            {"_id": 0, "raw_payload": 0},
        )
        # Iter67 — Exponer stop_id de Routal en la guía (sin filtrar todo
        # raw_payload). Necesario para el bloque "Comentarios al driver".
        if guia and (guia.get("carrier_code") or "").lower() == "routal":
            full = await db.guias.find_one(
                {"id": ticket["guia_id"]},
                {"_id": 0, "raw_payload.stop_id": 1,
                 "raw_payload.plan_id": 1})
            if full and full.get("raw_payload"):
                guia["raw_payload"] = full["raw_payload"]
    active_claim = await db.claims.find_one(
        {"tenant_id": user.tenant_id, "ticket_id": ticket_id, "is_terminal": False},
        {"_id": 0},
    )
    evidence_count = await db.evidences.count_documents(
        {"tenant_id": user.tenant_id, "ticket_id": ticket_id},
    )
    client = None
    if ticket.get("client_id"):
        client = await db.clients.find_one(
            {"tenant_id": user.tenant_id, "id": ticket["client_id"]},
            {"_id": 0, "name": 1, "slug": 1, "automation_enabled": 1,
             "ops_contact_email": 1},
        )
    # Bundle B · R50 — proyección de reglas para la UI (R02, R03).
    from services.rules.projection_service import projection_service
    projection = await projection_service.project_for_ticket(
        tenant_id=user.tenant_id, ticket_id=ticket_id,
        user_id=user.id, user_role=user.role,
    )
    # Iter49 — agrega `incident_type_label` (enum) e `incident_label` (final
    # con jerarquía guia.carrier_incidence > label español > raw).
    from services.incident_labels import enrich_incident_label
    enrich_incident_label(
        ticket,
        carrier_incidence=(guia or {}).get("carrier_incidence"),
    )
    return ok({
        "ticket": ticket, "timeline": timeline, "guia": guia,
        "active_claim": active_claim, "evidence_count": evidence_count,
        "client": client,
        "projection": projection,
    })


@router.post("/tickets/{ticket_id}/comment")
async def add_comment(ticket_id: str, payload: CommentPayload,
                      request: Request, _: object = Depends(_RBAC)):
    """Append-only comment en timeline_events. Default visibility=internal."""
    from core.db import get_db
    from core.uuid import new_id
    from datetime import datetime, timezone

    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    t = await repo.find_one({"id": ticket_id})
    if not t:
        raise ResourceNotFoundException()
    # Bundle iter44 — validaciones de comunicación externa
    if payload.visibility == "external" and not payload.to:
        from core.errors import MyEException, ErrorCode
        raise MyEException(
            ErrorCode.VALIDATION_FAILED,
            "Se requiere al menos un destinatario en 'Para' para enviar al cliente.",
            field="to",
        )
    now = datetime.now(timezone.utc).isoformat()
    event_payload = {"body": payload.body, "visibility": payload.visibility}
    if payload.visibility == "external":
        event_payload.update({
            "to": payload.to, "cc": payload.cc, "bcc": payload.bcc,
        })
    event = {
        "id": new_id(), "tenant_id": user.tenant_id,
        "ticket_id": ticket_id,
        "event_type": "comm" if payload.visibility == "external" else "action",
        "actor_id": user.id, "actor_role": user.role,
        "description": ("Nota interna" if payload.visibility == "internal"
                        else f"Comunicación al cliente ({', '.join(payload.to)})")
                       + f": {payload.body[:80]}",
        "payload": event_payload,
        "created_at": now,
    }
    # iter47 — usa EmailDispatcher (multi-buzón) cuando es external.
    # Resolución: workflow_type='ticket_notification', client_id si lo tiene
    # el guia, motivo_id del ticket. R53 fail-loud si no resuelve.
    if payload.visibility == "external":
        from services.email_dispatcher import EmailDispatcher
        from models.email_multibuzon import EmailContext, EmailPayload
        from services.notification_service import render_agent_message
        # Buscar guia para tracking + client_id
        tracking_id = t.get("tracking_id") or ""
        guia_client_id = None
        if t.get("guia_id"):
            guia = await get_db().guias.find_one(
                {"id": t["guia_id"], "tenant_id": user.tenant_id},
                {"_id": 0, "tracking_id": 1, "client_id": 1},
            )
            if guia:
                tracking_id = tracking_id or guia.get("tracking_id", "")
                guia_client_id = guia.get("client_id")
        tenant_doc = await get_db().tenants.find_one(
            {"id": user.tenant_id}, {"_id": 0, "name": 1},
        ) or {}
        html, text = render_agent_message(
            agent_name=user.name or user.email,
            body=payload.body,
            ticket_id=ticket_id,
            tracking_id=tracking_id or None,
            tenant_name=tenant_doc.get("name", "MyExcellence"),
        )
        subject = (f"[{tenant_doc.get('name', 'MyExcellence')}] Actualización de tu envío "
                   f"{tracking_id}" if tracking_id
                   else f"[{tenant_doc.get('name', 'MyExcellence')}] Actualización de tu caso")
        dispatcher = EmailDispatcher(user.tenant_id)
        result = await dispatcher.send(
            EmailContext(
                tenant_id=user.tenant_id,
                workflow_type="ticket_notification",
                client_id=guia_client_id or t.get("client_id"),
                motivo_id=t.get("motivo_codigo"),
                entity_type="ticket", entity_id=ticket_id,
            ),
            EmailPayload(
                to=payload.to, cc=payload.cc, bcc=payload.bcc,
                subject=subject, body_html=html, body_text=text,
                tags={"ticket_id": ticket_id, "agent_id": user.id},
            ),
        )
        event_payload["email_id"] = result.provider_message_id
        event_payload["email_ok"] = result.success
        event_payload["email_mock"] = result.mock
        event_payload["mailbox_id"] = result.mailbox_id
        if not result.success:
            event_payload["email_error"] = (
                f"[{result.error_code}] {result.error_message}")
    await get_db().timeline_events.insert_one(event)
    event.pop("_id", None)
    return ok({"event": event})


@router.post("/tickets/bulk-take")
async def bulk_take(payload: BulkTicketIds, request: Request,
                    _: object = Depends(_RBAC)):
    """Atomic-style bulk take. Si un ticket ya está asignado a OTRO agente,
    se omite con motivo `already_assigned` en lugar de fallar todo el batch.
    """
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    taken: list[str] = []
    skipped: list[dict] = []
    for tid in payload.ticket_ids:
        t = await repo.find_one({"id": tid})
        if not t:
            skipped.append({"id": tid, "reason": "not_found"})
            continue
        owner = t.get("assigned_agent_id")
        if owner and owner != user.id:
            skipped.append({"id": tid, "reason": "already_assigned"})
            continue
        await repo.assign(tid, user.id, actor_id=user.id)
        taken.append(tid)
    return ok({"taken": taken, "skipped": skipped,
               "totals": {"taken": len(taken), "skipped": len(skipped)}})


@router.post("/tickets/bulk-status")
async def bulk_status(payload: BulkStatusChange, request: Request,
                      _: object = Depends(_RBAC)):
    """Bulk status change scoped to the agent's tickets (admin+ may force)."""
    from middleware.rbac import ROLE_RANK
    user = request.state.user
    repo = TicketRepository(tenant_id=user.tenant_id)
    is_admin_plus = ROLE_RANK.get(user.role, 0) >= ROLE_RANK["admin"]
    updated: list[str] = []
    skipped: list[dict] = []
    for tid in payload.ticket_ids:
        t = await repo.find_one({"id": tid})
        if not t:
            skipped.append({"id": tid, "reason": "not_found"})
            continue
        if not is_admin_plus and t.get("assigned_agent_id") not in (user.id, None):
            skipped.append({"id": tid, "reason": "not_owner"})
            continue
        await repo.change_status(tid, payload.status, actor_id=user.id,
                                  reason=payload.reason)
        updated.append(tid)
    return ok({"updated": updated, "skipped": skipped,
               "totals": {"updated": len(updated), "skipped": len(skipped)}})


# ────────────────────── Outbound carrier instructions ─────────────────────
@router.post("/guias/{guia_id}/cancel")
async def cancel_guia_on_carrier(
    guia_id: str, payload: GuiaCancelPayload, request: Request,
    _: object = Depends(_RBAC),
):
    """Cierra el loop outbound 1:1: envía cancelación al carrier real usando
    el `project_id` (o `account_number`, según carrier) persistido en
    `guia.carrier_meta` al momento de la ingesta. Hoy soporta **Routal**.

    Pipeline:
      1. Resolver guía tenant-scoped.
      2. Resolver project_id efectivo (payload > carrier_meta > default cfg).
      3. Resolver credenciales del cliente via ClientRepository.get_carrier_config.
      4. Instanciar adapter y llamar `send_instruction({status:'canceled', ...})`.
      5. Persistir `timeline_events` (carrier_outbound_sent) en el ticket
         asociado (si existe). Auditoría queda visible al cliente.
      6. Si recibido OK, marcar la guía con `outbound_last_status='canceled'`
         + timestamp para evitar reintentos duplicados.
    """
    from core.db import get_db
    from core.uuid import new_id
    from datetime import datetime, timezone
    from services.cae.adapters.anchor_stubs import ADAPTER_REGISTRY
    from services.carrier_config_resolver import resolve_carrier_config

    user = request.state.user
    db = get_db()
    guia = await db.guias.find_one(
        {"tenant_id": user.tenant_id, "id": guia_id}, {"_id": 0})
    if not guia:
        raise ResourceNotFoundException("Guía no encontrada.")

    carrier_code = (guia.get("carrier_code") or "").lower()
    if not carrier_code:
        raise MyEException(ErrorCode.VALIDATION_FAILED,
                           "La guía no tiene carrier_code asignado")
    AdapterCls = ADAPTER_REGISTRY.get(carrier_code)
    if AdapterCls is None:
        raise MyEException(ErrorCode.VALIDATION_FAILED,
                           f"No hay adapter registrado para {carrier_code!r}")

    client_id = guia.get("client_id")
    if not client_id:
        raise MyEException(ErrorCode.VALIDATION_FAILED,
                           "La guía no tiene client_id asignado")

    # Resolver client > tenant > platform with audit trail
    cfg = await resolve_carrier_config(
        tenant_id=user.tenant_id, client_id=client_id, code=carrier_code)
    if not cfg or not cfg.get("api_key"):
        raise MyEException(
            ErrorCode.VALIDATION_FAILED,
            f"No hay credenciales {carrier_code} resueltas para este cliente "
            f"(ni a nivel cliente, tenant o plataforma)")

    # Resolve project_id (Routal-specific; otros adapters pueden ignorarlo)
    project_id = payload.project_id \
        or (guia.get("carrier_meta") or {}).get("routal_project_id") \
        or cfg.get("default_project_id")

    adapter_kwargs = {
        "api_key": cfg["api_key"],
        "project_ids": cfg.get("project_ids") or [],
        "base_url": cfg.get("base_url"),
    }
    if cfg.get("client_secret"):
        adapter_kwargs["client_secret"] = cfg["client_secret"]
    adapter = AdapterCls(**adapter_kwargs)
    res = await adapter.send_instruction(
        guia["tracking_id"],
        {"status": "canceled", "project_id": project_id,
         "comments": payload.comments},
    )

    now = datetime.now(timezone.utc).isoformat()
    config_source = cfg.get("config_source", "unknown")
    # Append timeline event en el ticket si la guía tiene uno asociado
    ticket = await db.tickets.find_one(
        {"tenant_id": user.tenant_id, "guia_id": guia_id}, {"_id": 0, "id": 1})
    if ticket:
        await db.timeline_events.insert_one({
            "id": new_id(), "tenant_id": user.tenant_id,
            "ticket_id": ticket["id"],
            "event_type": "carrier_outbound_sent",
            "actor_id": user.id, "actor_role": user.role,
            "description": (f"Cancelación enviada a {carrier_code}"
                            + (f" (project {project_id})" if project_id else "")
                            + f" · creds={config_source}"
                            + (" — OK" if res.received else " — Falló")),
            "payload": {
                "carrier_code": carrier_code,
                "tracking_id": guia["tracking_id"],
                "project_id": project_id,
                "outbound_status": "canceled",
                "received": res.received,
                "http_status": res.status,
                "fallback_to_email": res.fallback_to_email,
                "config_source": config_source,
            },
            "created_at": now,
        })

    # Persistir el resultado en la guía para auditoría e idempotencia
    update = {
        "outbound_last_action": "cancel",
        "outbound_last_status": "received" if res.received else "failed",
        "outbound_last_at": now,
        "outbound_last_http": res.status,
        "outbound_last_config_source": config_source,
    }
    if project_id:
        update["carrier_meta.routal_project_id"] = project_id
    await db.guias.update_one({"id": guia_id}, {"$set": update})

    return ok({
        "received": res.received,
        "status": res.status,
        "fallback_to_email": res.fallback_to_email,
        "project_id": project_id,
        "carrier_code": carrier_code,
        "tracking_id": guia["tracking_id"],
        "config_source": config_source,
    })
