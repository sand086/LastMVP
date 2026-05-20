"""Reclamos routes — PROMPT 13 V1."""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, Query, Request

from core.db import get_db
from core.errors import ErrorCode, ResourceNotFoundException
from core.hmac import verify as hmac_verify
from core.logger import log
from core.response import fail, ok
from middleware.rbac import require_min_role
from models.claim import (
    CarrierDictamenWebhook, ConciliateRequest, ExpedienteUpdate,
    NotifyClientRequest, PromoteRequest, TransitionRequest,
)
from repositories.claims import (
    ClaimEventRepository, ClaimRepository, DuplicateClaimError,
    IndemnizationRepository,
)
from repositories.tickets import TicketRepository
from repositories.clients import ClientRepository
from services.automation_check import can_automate
from services.claim_workflow import (
    ClaimWorkflow, ExpedienteIncompleteException, InvalidTransitionException,
)

router = APIRouter(tags=["claims"])
router_ingest = APIRouter(tags=["claims-ingest"])

_PROMOTE_RBAC = require_min_role("agent")        # P0.2 / R32 — manual promotion
_CLAIM_RBAC = require_min_role("agent")
_COORD_RBAC = require_min_role("coordinator")     # only coordinator+ may conciliate


def _t(request: Request) -> str:
    return request.state.user.tenant_id


# ────────────────────── Promote Ticket → Claim ──────────────────────────
@router.post("/api/tickets/{ticket_id}/promote-to-claim", status_code=201)
async def promote_ticket(ticket_id: str, payload: PromoteRequest, request: Request,
                         _: object = Depends(_PROMOTE_RBAC)):
    user = request.state.user
    tickets = TicketRepository(tenant_id=user.tenant_id)
    ticket = await tickets.find_one({"id": ticket_id})
    if not ticket:
        # R08 — same response as cross-tenant
        raise ResourceNotFoundException()
    if ticket["status"] not in ("resolved", "closed"):
        return fail(
            ErrorCode.TERMINAL_STATE,
            "Sólo tickets en estado resolved/closed pueden promoverse a reclamo.",
            field="status",
        )
    repo = ClaimRepository(tenant_id=user.tenant_id)
    try:
        claim = await repo.create(
            ticket_id=ticket_id, client_id=ticket["client_id"],
            tipo_dano=payload.tipo_dano, monto_reclamado=payload.monto_reclamado,
            divisa=payload.divisa, promoted_by=user.id,
        )
    except DuplicateClaimError:
        return fail(ErrorCode.TERMINAL_STATE,
                    "Ya existe un reclamo activo para este ticket.",
                    field="ticket_id")

    events = ClaimEventRepository(tenant_id=user.tenant_id)
    await events.record(
        claim_id=claim["id"], event_type="promoted", actor_type="agent",
        actor_id=user.id, estado_nuevo="promovido",
        payload={"notas": payload.notas_iniciales} if payload.notas_iniciales else None,
    )
    # Mirror in the source ticket timeline (event_type='promoted_to_claim')
    await tickets.timeline.record(
        ticket_id=ticket_id, event_type="promoted_to_claim",
        actor_type="user", actor_id=user.id, channel="internal",
        payload={"claim_id": claim["id"], "tipo_dano": payload.tipo_dano,
                 "monto_reclamado": payload.monto_reclamado, "divisa": payload.divisa},
    )
    # P1.2 — push in-app notification to coordinators
    from repositories.inbox import InboxRepository
    await InboxRepository(tenant_id=user.tenant_id).push_to_role(
        role="coordinator", kind="claim_promoted",
        title=f"Nuevo reclamo {claim['id'][:8]}",
        body=f"Tipo: {payload.tipo_dano} · Monto: {payload.monto_reclamado} {payload.divisa}",
        link=f"/reclamos/{claim['id']}",
        payload={"claim_id": claim["id"], "ticket_id": ticket_id,
                 "tipo_dano": payload.tipo_dano, "monto_reclamado": payload.monto_reclamado},
    )
    return ok(claim, status_code=201)


# ────────────────────── List + detail ───────────────────────────────────
@router.get("/api/reclamos")
async def list_claims(
    request: Request,
    estado: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _: object = Depends(_CLAIM_RBAC),
):
    repo = ClaimRepository(tenant_id=_t(request))
    query: dict = {}
    if estado:
        query["estado"] = estado
    items = await repo.find(query, sort=[("promoted_at", -1)], limit=limit)
    return ok({"items": items, "count": len(items)})


@router.get("/api/reclamos/{claim_id}")
async def claim_detail(claim_id: str, request: Request, _: object = Depends(_CLAIM_RBAC)):
    repo = ClaimRepository(tenant_id=_t(request))
    claim = await repo.find_one({"id": claim_id})
    if not claim:
        raise ResourceNotFoundException()
    db = get_db()
    events = await db.claim_events.find(
        {"tenant_id": _t(request), "claim_id": claim_id}, {"_id": 0},
    ).sort("created_at", 1).limit(500).to_list(length=500)
    indem = await db.claim_indemnizations.find_one(
        {"tenant_id": _t(request), "claim_id": claim_id}, {"_id": 0},
    )
    # Bundle B · R50 — proyección R28 (estados terminales del reclamo).
    from services.rules.projection_service import projection_service
    user = request.state.user
    projection = await projection_service.project_for_reclamo(
        tenant_id=_t(request), claim_id=claim_id,
        user_id=user.id, user_role=user.role,
    )
    return ok({"claim": claim, "events": events, "indemnization": indem,
               "projection": projection})


# ────────────────────── Expediente + transition ─────────────────────────
@router.patch("/api/reclamos/{claim_id}/expediente")
async def update_expediente(claim_id: str, payload: ExpedienteUpdate, request: Request,
                            _: object = Depends(_CLAIM_RBAC)):
    user = request.state.user
    repo = ClaimRepository(tenant_id=user.tenant_id)
    claim = await repo.find_one({"id": claim_id})
    if not claim:
        raise ResourceNotFoundException()
    if claim.get("is_terminal"):
        return fail(ErrorCode.TERMINAL_STATE, "Reclamo en estado terminal (R28).")

    # Top-level fields go to claim root
    top_updates: dict = {}
    if payload.monto_reclamado is not None:
        top_updates["monto_reclamado"] = payload.monto_reclamado
    if payload.tipo_dano is not None:
        top_updates["tipo_dano"] = payload.tipo_dano
    if top_updates:
        await repo.update_one({"id": claim_id}, top_updates)

    # Expediente-nested fields
    nested = payload.model_dump(exclude_none=True, exclude={"monto_reclamado", "tipo_dano"})
    if nested:
        await repo.patch_expediente(claim_id, nested)

    # Auto-advance from "promovido" once any expediente field is provided
    refreshed = await repo.find_one({"id": claim_id})
    if refreshed["estado"] == "promovido" and (top_updates or nested):
        wf = ClaimWorkflow(tenant_id=user.tenant_id)
        try:
            await wf.transition(claim_id, "expediente_en_armado",
                                actor_type="agent", actor_id=user.id,
                                reason="Auto-advance al iniciar expediente.")
        except InvalidTransitionException:
            pass
        refreshed = await repo.find_one({"id": claim_id})
    return ok(refreshed)


@router.post("/api/reclamos/{claim_id}/transition")
async def transition_claim(claim_id: str, payload: TransitionRequest, request: Request,
                           _: object = Depends(_CLAIM_RBAC)):
    user = request.state.user
    wf = ClaimWorkflow(tenant_id=user.tenant_id)
    try:
        result = await wf.transition(claim_id, payload.target,
                                     actor_type="agent", actor_id=user.id,
                                     reason=payload.reason)
    except InvalidTransitionException as e:
        return fail(ErrorCode.TERMINAL_STATE,
                    f"Transición no permitida: {e.current} → {e.target}.",
                    field="target")
    except ExpedienteIncompleteException as e:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Expediente incompleto.",
                    extra_errors=[{"code": "INCOMPLETE_FILE", "message": ", ".join(e.missing),
                                   "field": "expediente"}])
    if not result.ok:
        return fail(ErrorCode.TERMINAL_STATE, result.reason)
    return ok({"estado": result.estado})


# ────────────────────── Send to carrier (R33) ────────────────────────────
@router.post("/api/reclamos/{claim_id}/enviar-carrier")
async def send_to_carrier(claim_id: str, request: Request, _: object = Depends(_CLAIM_RBAC)):
    user = request.state.user
    repo = ClaimRepository(tenant_id=user.tenant_id)
    claim = await repo.find_one({"id": claim_id})
    if not claim:
        raise ResourceNotFoundException()
    if claim["estado"] != "expediente_en_armado":
        return fail(ErrorCode.TERMINAL_STATE,
                    "El reclamo debe estar en expediente_en_armado.",
                    field="estado")

    # R33 — consult the automation matrix using the damage type as solucion key
    decision = await can_automate(
        tenant_id=user.tenant_id, client_id=claim["client_id"],
        solucion_id=f"reclamo:{claim['tipo_dano']}", channel="api",
    )
    if not decision.can_automate:
        return fail(ErrorCode.RBAC_DENIED,
                    "Automatización no autorizada — esperando revisión del agente.",
                    extra_errors=[{"code": "AWAITING_AGENT_REVIEW",
                                   "message": decision.reason, "field": None}])

    # Mock outbound to carrier — real HTTP call lands in PROMPT 20.
    log.info("claim_sent_to_carrier_mock", extra={"context": {
        "tenant_id": user.tenant_id, "claim_id": claim_id,
        "client_id": claim["client_id"], "tipo_dano": claim["tipo_dano"],
    }})
    wf = ClaimWorkflow(tenant_id=user.tenant_id)
    await wf.transition(claim_id, "enviado_carrier",
                        actor_type="system", actor_id=user.id,
                        reason="enviado vía API (mock)")
    await wf.transition(claim_id, "en_dictamen_carrier",
                        actor_type="carrier",
                        reason="carrier acuse de recibo HTTP 200")
    return ok({
        "claim": await repo.find_one({"id": claim_id}),
        "channel_used": "api", "carrier_received": True,
    })


# ────────────────────── Carrier dictamen webhook (HMAC R18) ─────────────
@router_ingest.post("/api/reclamos/ingest/dictamen")
async def ingest_dictamen(request: Request, client_id: str = Query(..., min_length=36, max_length=36)):
    body = await request.body()
    if not body:
        return fail(ErrorCode.VALIDATION_FAILED, "Cuerpo vacío.")
    db = get_db()
    raw_client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not raw_client:
        return fail(ErrorCode.AUTH_REQUIRED, "Cliente no encontrado.")

    sig = request.headers.get("X-MyE-Signature", "")
    if not hmac_verify(raw_client.get("webhook_token") or "", body, sig):
        log.warning("dictamen_signature_invalid", extra={"context": {"client_id": client_id}})
        return fail(ErrorCode.AUTH_REQUIRED, "Firma HMAC inválida.")
    try:
        payload = CarrierDictamenWebhook(**json.loads(body))
    except Exception as e:  # noqa: BLE001
        return fail(ErrorCode.VALIDATION_FAILED, f"Payload inválido: {e}")
    if payload.decision == "approved" and payload.monto_aprobado is None:
        return fail(ErrorCode.VALIDATION_FAILED, "monto_aprobado es obligatorio cuando decision=approved.",
                    field="monto_aprobado")

    tenant_id = raw_client["tenant_id"]
    # Find active claim by tracking_id → guia → ticket → claim
    guia = await db.guias.find_one({"tenant_id": tenant_id, "tracking_id": payload.tracking_id}, {"_id": 0})
    claim = None
    if guia:
        ticket = await db.tickets.find_one({"tenant_id": tenant_id, "guia_id": guia["id"]}, {"_id": 0})
        if ticket:
            claim = await db.claims.find_one(
                {"tenant_id": tenant_id, "ticket_id": ticket["id"], "is_terminal": False},
                {"_id": 0},
            )
    if not claim or claim["estado"] != "en_dictamen_carrier":
        return fail(ErrorCode.RESOURCE_NOT_FOUND, "No hay reclamo activo en dictamen para ese tracking.")

    wf = ClaimWorkflow(tenant_id=tenant_id)
    target = "aprobado_carrier" if payload.decision == "approved" else "rechazado_carrier"
    try:
        await wf.transition(claim["id"], target, actor_type="carrier",
                            payload={"carrier_referencia": payload.carrier_referencia,
                                     "razon_rechazo": payload.razon_rechazo})
    except (InvalidTransitionException, ExpedienteIncompleteException) as e:
        return fail(ErrorCode.TERMINAL_STATE, str(e))

    # P0.8 — register indemnization on approval
    if payload.decision == "approved":
        await IndemnizationRepository(tenant_id=tenant_id).upsert(
            claim_id=claim["id"], monto_aprobado=payload.monto_aprobado,
            divisa=payload.divisa, carrier_referencia=payload.carrier_referencia,
        )
        await wf.transition(claim["id"], "en_conciliacion",
                            actor_type="system",
                            reason="aprobado_carrier → en_conciliacion automático")
    return ok({"claim_id": claim["id"], "decision": payload.decision}, status_code=202)


# ────────────────────── Conciliate (coordinator) ─────────────────────────
@router.post("/api/reclamos/{claim_id}/conciliar")
async def conciliate(claim_id: str, payload: ConciliateRequest, request: Request,
                     _: object = Depends(_COORD_RBAC)):
    user = request.state.user
    repo = ClaimRepository(tenant_id=user.tenant_id)
    claim = await repo.find_one({"id": claim_id})
    if not claim:
        raise ResourceNotFoundException()
    if claim["estado"] != "en_conciliacion":
        return fail(ErrorCode.TERMINAL_STATE, "El reclamo no está en en_conciliacion.")
    indem = await IndemnizationRepository(tenant_id=user.tenant_id).find_one({"claim_id": claim_id})
    if not indem or indem.get("monto_aprobado") is None:
        return fail(ErrorCode.TERMINAL_STATE,
                    "Falta el monto aprobado del carrier — no se puede conciliar.",
                    field="monto_aprobado")
    await IndemnizationRepository(tenant_id=user.tenant_id).conciliate(
        claim_id, monto=payload.monto_conciliado, divisa=payload.divisa,
        conciliado_por=user.id, notas=payload.notas_conciliacion,
    )
    wf = ClaimWorkflow(tenant_id=user.tenant_id)
    await wf.transition(claim_id, "conciliado", actor_type="coordinator",
                        actor_id=user.id, reason=payload.notas_conciliacion)
    final = await repo.find_one({"id": claim_id})
    # PROMPT 39 — webhook claim.conciliated (R48)
    try:
        from services.webhooks.dispatcher import OutboundWebhookDispatcher
        await OutboundWebhookDispatcher.dispatch(
            tenant_id=user.tenant_id, client_id=final.get("client_id", ""),
            event_type="claim.conciliated", source_id=claim_id,
            data={
                "claim_id": claim_id,
                "ticket_id": final.get("ticket_id"),
                "monto_aprobado": float(payload.monto_conciliado) if payload.monto_conciliado is not None else None,
                "moneda": payload.divisa,
            },
        )
    except Exception:  # noqa: BLE001
        from core.logger import log
        log.exception("webhook_claim_conciliated_failed",
                      extra={"context": {"claim_id": claim_id}})
    return ok(final)


# ────────────────────── Notify CxC client (P0.5 / R32) ──────────────────
@router.post("/api/reclamos/{claim_id}/notificar-cliente")
async def notify_client(claim_id: str, payload: NotifyClientRequest,
                        request: Request, _: object = Depends(_CLAIM_RBAC)):
    """Envía email al cxc_contact_email del cliente y registra el evento.

    R32: la comunicación al CxC NUNCA se dispara sin que un agente la inicie
    explícitamente (de ahí que sea POST manual, no automatizado por el cron).
    """
    user = request.state.user
    repo = ClaimRepository(tenant_id=user.tenant_id)
    claim = await repo.find_one({"id": claim_id})
    if not claim:
        raise ResourceNotFoundException()
    if claim.get("is_terminal"):
        return fail(ErrorCode.TERMINAL_STATE,
                    "Reclamo en estado terminal — no admite notificaciones.")

    client = await ClientRepository(tenant_id=user.tenant_id).find_one({"id": claim["client_id"]})
    if not client:
        return fail(ErrorCode.RESOURCE_NOT_FOUND, "Cliente no encontrado.")
    cxc_email = client.get("cxc_contact_email") or client.get("ops_contact_email")
    cxc_name = client.get("cxc_contact_name") or client.get("ops_contact_name") or "Equipo CxC"
    if not cxc_email:
        return fail(ErrorCode.VALIDATION_FAILED,
                    "Cliente sin cxc_contact_email configurado.",
                    field="cxc_contact_email")

    from services.notification_service import render_incident_notice, send_email
    subject = payload.subject or f"[MyExcellence] Reclamo {claim_id[:8]} — {claim['tipo_dano']}"
    html, text = render_incident_notice(
        recipient_name=cxc_name, ticket_id=claim["ticket_id"],
        tracking_id=f"reclamo:{claim_id[:8]}",
        message=payload.message,
        cta_url=payload.cta_url,
        cta_label="Abrir reclamo",
    )
    result = await send_email(
        to=cxc_email, subject=subject, html=html, text=text,
        tags={"kind": "claim_cxc_notice", "claim_id": claim_id[:8],
              "tenant_id": user.tenant_id[:8]},
    )

    # R30 — append-only en claim_events
    events = ClaimEventRepository(tenant_id=user.tenant_id)
    await events.record(
        claim_id=claim_id, event_type="client_notified", actor_type="agent",
        actor_id=user.id,
        payload={"to": cxc_email, "subject": subject,
                 "ok": result.ok, "email_id": result.id, "mock": result.mock,
                 "reason": result.reason},
    )
    if not result.ok:
        return fail(ErrorCode.VALIDATION_FAILED,
                    f"Error enviando email: {result.reason}",
                    extra_errors=[{"code": "EMAIL_SEND_FAILED",
                                   "message": result.reason or "unknown",
                                   "field": "to"}])
    return ok({
        "claim_id": claim_id, "to": cxc_email, "subject": subject,
        "result": result.to_dict(),
    })
