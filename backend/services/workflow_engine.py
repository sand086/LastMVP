"""WorkflowEngine — sec 5.4-5.7 of MYEXCELLENCE.md (R14 single source).

Triggered by IngestService after a guía is created/updated. Returns the ID of
any ticket created/affected so the caller can attach it to telemetry.

Scope of this module:
  Tree #1 — Carrier event → ticket?     (implemented)
  Tree #2 — New ticket → auto-assign?    (implemented; round-robin deferred)
  Tree #3 — Can we automate?              (implemented as evaluation only —
            execution lives in AutomationService stub; full execution lands
            with the notification adapters in PROMPT_11)
  Tree #4 — SLA evaluation                (deferred → PROMPT_09)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from core.logger import log
from repositories.tickets import TicketRepository, first_available_agent
from services.automation_check import can_automate

# Heuristic mapping until the CAE catalog is fully populated.
# Once PROMPT_06 lands these constants are unused — the normalizer takes over.
_CARRIER_INCIDENT_HINTS = (
    "EXCEPTION", "REJECT", "RETURN", "FAILED", "DAMAGE", "INCIDENT",
    "CUSTOMS", "ADDRESS", "REFUSED", "LOST", "DEVUELTO", "RECHAZADO",
)


def _looks_like_incident(carrier_status: str) -> Optional[str]:
    """Returns an ``incident_type`` for known patterns; None means 'no incident'."""
    cs = (carrier_status or "").upper()
    for kw, kind in (
        ("ADDRESS", "address_issue"), ("REJECT", "refused"), ("REFUSED", "refused"),
        ("RETURN", "returned"), ("DEVUELTO", "returned"),
        ("CUSTOMS", "customs"), ("DAMAGE", "damage"),
        ("LOST", "lost"), ("FAILED", "failed"),
        ("EXCEPTION", "exception"), ("INCIDENT", "exception"),
        ("RECHAZADO", "refused"),
    ):
        if kw in cs:
            return kind
    return None


@dataclass
class WorkflowOutcome:
    ticket_id: Optional[str]
    action: str
    reason: str
    auto_assigned_agent_id: Optional[str] = None
    automation_decision: Optional[str] = None


class WorkflowEngine:
    """The single decision authority for incident routing (R14).

    All ingest events MUST pass through ``process_post_ingest``. Direct ticket
    creation outside this engine is allowed only via the agent panel
    (manual creation by a human).
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.tickets = TicketRepository(tenant_id=tenant_id)

    async def process_post_ingest(
        self,
        *,
        guia: dict,
        ingest_action: str,  # 'created' | 'updated' | 'discarded_terminal' | 'discarded_no_change'
        normalized_canonical: Optional[str] = None,
        normalized_incident_type: Optional[str] = None,
    ) -> WorkflowOutcome:
        if ingest_action in ("discarded_terminal", "discarded_no_change"):
            return WorkflowOutcome(None, "skip", f"ingest_{ingest_action}")

        carrier_status = guia.get("carrier_status", "")
        # Prefer the normalizer's verdict; fall back to (a) heuristic for
        # incident_type, (b) `guia.internal_status` for canonical (pre-CAE
        # already set the right value, ej. CSV "Entregado" → "delivered").
        canonical = normalized_canonical
        if not canonical or canonical == "unknown":
            canonical = guia.get("internal_status")
        incident = normalized_incident_type or _looks_like_incident(carrier_status)
        # Iter60 — Si el catálogo CAE clasifica la guía como incidencia
        # (canonical ∈ {exception, cancelled}), la consideramos incidente aun
        # cuando incident_type esté vacío. Antes el engine sólo creaba ticket
        # ante una keyword en carrier_status, ignorando el veredicto del
        # catálogo y dejando guías canceled/exception sin ticket.
        cae_signals_incident = (canonical or "").lower() in {"exception", "cancelled"}
        if not incident and cae_signals_incident:
            incident = canonical  # usar canonical como incident_type fallback

        if guia.get("is_terminal") and (canonical or "").lower() == "delivered":
            # Tree #1 path A — guía entregada: cierra cualquier ticket abierto.
            existing = await self.tickets.open_for_guia(guia["id"])
            if existing:
                await self.tickets.change_status(
                    existing["id"], "resolved",
                    reason="guía entregada — cierre automático por WorkflowEngine",
                )
                return WorkflowOutcome(existing["id"], "auto_resolved", "delivery_terminal")
            return WorkflowOutcome(None, "skip", "delivered_no_open_ticket")

        if not incident and not (guia.get("is_terminal") and canonical == "returned"):
            # Tree #1 path B — evento normal sin incidente: nada que hacer.
            return WorkflowOutcome(None, "skip", "no_incident_signal")

        # Iter54 P1.2 — Gating por max_attempts del carrier.
        # Algunos carriers permiten N intentos antes de considerar incidencia
        # "real". El documento del cliente dice:
        #   Redpack, FedEx, DHL → 3 intentos (incident a partir del penúltimo, i.e. 2)
        #   Estafeta            → 2 intentos (incident a partir del 1)
        # Si la guía aún no llegó a `max_attempts - 1`, dejamos pasar el evento
        # sin crear ticket (status update sigue pero no se notifica).
        gating = await self._should_gate_by_attempts(guia)
        if gating:
            return gating

        # Tree #1 path C — incidente. Si ya hay ticket abierto, NO duplicar.
        existing = await self.tickets.open_for_guia(guia["id"])
        if existing:
            return WorkflowOutcome(existing["id"], "ticket_exists", "open_ticket_for_guia")

        # Iter61 — Enriquecimiento con report del carrier (Routal trae motivo
        # categorizado + comentarios + fotos en guia.carrier_meta.routal_report).
        rr = (guia.get("carrier_meta") or {}).get("routal_report") or {}
        incident_subtype = rr.get("reason_label") or None
        # Si el catálogo no marcó incident_type pero hay reason_label del
        # carrier, usarlo como tipo de incidencia (más específico que
        # "exception").
        if rr.get("reason_label") and (not incident or incident == canonical):
            incident = rr.get("reason_label")
        carrier_incident_detail = {
            "report_id": rr.get("report_id"),
            "report_type": rr.get("report_type"),
            "comments": rr.get("comments"),
            "reason_label": rr.get("reason_label"),
            "images": rr.get("images"),
            "images_count": rr.get("images_count"),
            "report_at": rr.get("report_at"),
        } if rr else None

        ticket = await self.tickets.create_from_workflow(
            client_id=guia["client_id"],
            subclient_id=guia.get("subclient_id"),
            guia_id=guia["id"],
            motivo_id=None,  # set by agent or via solucion picker once catalog ready
            carrier_id=guia.get("carrier_id"),
            carrier_status_raw=carrier_status,
            incident_type=incident,
            incident_subtype=incident_subtype,
            carrier_incident_detail=carrier_incident_detail,
            canonical_status=canonical,
            source="ingest",
        )
        log.info("workflow_ticket_created", extra={"context": {
            "tenant_id": self.tenant_id, "ticket_id": ticket["id"],
            "guia_id": guia["id"], "incident_type": incident,
        }})

        # Tree #2 — auto-assign al primer agente activo
        agent = await first_available_agent(self.tenant_id)
        assigned_id = None
        if agent:
            await self.tickets.assign(ticket["id"], agent["id"])
            assigned_id = agent["id"]

        # Tree #3 — diagnóstico de automatización (no ejecuta sin solucion_id)
        # Solo se evalúa si el ticket llega con solucion preasignada (no en MVP).
        automation_reason = "no_solucion_yet"
        return WorkflowOutcome(
            ticket_id=ticket["id"],
            action="ticket_created",
            reason=f"incident:{incident}",
            auto_assigned_agent_id=assigned_id,
            automation_decision=automation_reason,
        )

    async def evaluate_automation_for_ticket(self, ticket: dict, channel: str = "email") -> str:
        """Tree #3 helper — exposed so the agent panel can ask:
        "if I select solución X, can I press the magic button?".
        """
        if not ticket.get("solucion_id"):
            return "no_solucion"
        decision = await can_automate(
            tenant_id=self.tenant_id,
            client_id=ticket["client_id"],
            solucion_id=ticket["solucion_id"],
            channel=channel,
        )
        return "ok" if decision.can_automate else decision.reason

    # Iter54 P1.2 — defaults por carrier (3 intentos para mayoría, 2 Estafeta).
    _DEFAULT_MAX_ATTEMPTS = {
        "fedex": 3, "dhl": 3, "redpack": 3, "estafeta": 2,
    }

    async def _resolve_max_attempts(self, *, carrier_code: str | None,
                                    client_id: str | None) -> int:
        """Devuelve max_attempts: prioriza override en `clients.carriers.<code>`,
        luego defaults por carrier, default global 3."""
        if not carrier_code:
            return 3
        code = carrier_code.lower()
        if client_id:
            from core.db import get_db
            cli = await get_db().clients.find_one(
                {"id": client_id, "tenant_id": self.tenant_id},
                {"_id": 0, "carriers": 1},
            )
            ov = (cli or {}).get("carriers", {}).get(code, {}).get("max_attempts")
            if isinstance(ov, int) and ov > 0:
                return ov
        return self._DEFAULT_MAX_ATTEMPTS.get(code, 3)

    async def _should_gate_by_attempts(self, guia: dict) -> Optional[WorkflowOutcome]:
        """Devuelve WorkflowOutcome("skip", ...) si el carrier aún tiene
        intentos restantes y no es la "penúltima" entrega; None si NO debe
        gating (deja pasar al flujo normal).
        """
        attempts = guia.get("delivery_attempts")
        if not isinstance(attempts, int) or attempts <= 0:
            # Sin tracker de attempts → no gating (no rompemos el flow legacy).
            return None
        max_a = await self._resolve_max_attempts(
            carrier_code=guia.get("carrier_code") or guia.get("carrier_id"),
            client_id=guia.get("client_id"),
        )
        # Threshold = penúltimo intento. Ej: max=3 → ticket en 2do intento.
        #              max=2 → ticket en 1er intento (Estafeta).
        threshold = max(1, max_a - 1)
        if attempts < threshold:
            return WorkflowOutcome(
                None, "skip",
                f"attempts_below_threshold:{attempts}/{max_a}",
            )
        return None
