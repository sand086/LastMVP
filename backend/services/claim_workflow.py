"""ClaimWorkflow — R31 single source of truth for claim transitions.

NO controller and NO repository may mutate ``claims.estado`` directly.
Every state change funnels through ``ClaimWorkflow.transition()`` which:
  - Validates the transition against the matrix (R31)
  - Checks expediente completeness on enviado_carrier (R35)
  - Records the change in claim_events (R30 append-only)
  - Honours R28 (terminal protection) via ClaimRepository.update_state
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from core.logger import log
from models.claim import ALLOWED_TRANSITIONS
from repositories.claims import ClaimEventRepository, ClaimRepository


class InvalidTransitionException(Exception):
    def __init__(self, current: str, target: str):
        super().__init__(f"Transition not allowed: {current} → {target}")
        self.current = current
        self.target = target


class ExpedienteIncompleteException(Exception):
    def __init__(self, missing: list[str]):
        super().__init__(f"Expediente incompleto: faltan {', '.join(missing)}")
        self.missing = missing


REQUIRED_EXPEDIENTE_FIELDS = ("monto_reclamado", "tipo_dano", "declaracion_cliente")
MIN_EVIDENCES = 2


@dataclass
class TransitionResult:
    ok: bool
    estado: str
    reason: str


class ClaimWorkflow:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.claims = ClaimRepository(tenant_id=tenant_id)
        self.events = ClaimEventRepository(tenant_id=tenant_id)

    @staticmethod
    def is_allowed(current: str, target: str) -> bool:
        return target in ALLOWED_TRANSITIONS.get(current, set())

    @staticmethod
    def can_transition_with_expediente(claim: dict, target: str) -> tuple[bool, list[str]]:
        """R35 — pasar a enviado_carrier exige expediente completo."""
        if target != "enviado_carrier":
            return True, []
        exp = claim.get("expediente", {}) or {}
        missing: list[str] = []
        if not claim.get("monto_reclamado"):
            missing.append("monto_reclamado")
        if not claim.get("tipo_dano"):
            missing.append("tipo_dano")
        if not exp.get("declaracion_cliente"):
            missing.append("declaracion_cliente")
        evidence_count = len(exp.get("evidencia_ids") or [])
        if evidence_count < MIN_EVIDENCES:
            missing.append(f"evidencias (>= {MIN_EVIDENCES})")
        return (len(missing) == 0), missing

    async def transition(
        self,
        claim_id: str,
        target: str,
        *,
        actor_type: str = "agent",
        actor_id: Optional[str] = None,
        reason: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> TransitionResult:
        claim = await self.claims.find_one({"id": claim_id})
        if not claim:
            raise ValueError("Reclamo no encontrado.")

        if claim.get("is_terminal"):
            # R28 — silent discard
            log.warning("CLAIM_TERMINAL_PROTECTION", extra={"context": {
                "claim_id": claim_id, "current": claim["estado"], "attempted": target,
            }})
            return TransitionResult(False, claim["estado"], "claim_terminal")

        current = claim["estado"]
        if not self.is_allowed(current, target):
            raise InvalidTransitionException(current, target)

        ok, missing = self.can_transition_with_expediente(claim, target)
        if not ok:
            raise ExpedienteIncompleteException(missing)

        modified = await self.claims.update_state(claim_id, target)
        if not modified:
            return TransitionResult(False, current, "no_change")

        await self.events.record(
            claim_id=claim_id,
            event_type=_event_for_target(target),
            actor_type=actor_type,
            actor_id=actor_id,
            estado_anterior=current,
            estado_nuevo=target,
            payload={**(payload or {}), "reason": reason} if reason or payload else None,
        )
        log.info("claim_transition", extra={"context": {
            "tenant_id": self.tenant_id, "claim_id": claim_id,
            "from": current, "to": target, "actor_id": actor_id,
        }})
        return TransitionResult(True, target, "ok")


def _event_for_target(target: str) -> str:
    return {
        "expediente_en_armado": "expediente_completed",
        "enviado_carrier":      "sent_to_carrier",
        "en_dictamen_carrier":  "dictamen_received",
        "aprobado_carrier":     "approved",
        "rechazado_carrier":    "rejected",
        "en_conciliacion":      "conciliation_started",
        "conciliado":           "conciliated",
        "desistido":            "withdrawn",
    }.get(target, "comment")
