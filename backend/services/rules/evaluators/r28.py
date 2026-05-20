"""R28 — Estados terminales de reclamos (conciliado, desistido).

Cuando un reclamo está en estado terminal, el formulario completo pasa a
solo lectura. La UI muestra un banner verde con la información del cierre.
"""
from __future__ import annotations
from . import (
    AllowedAction, EntityContext, RuleEvaluatorInterface, RuleResult,
)

TERMINAL_CLAIM_STATUSES = {"conciliado", "desistido"}

CLAIM_TERMINAL_TOOLTIPS = {
    "conciliado": "Reclamo conciliado. Solo lectura.",
    "desistido":  "Reclamo desistido. Solo lectura.",
}


class R28Evaluator:
    def rule_id(self) -> str:
        return "R28"

    def applies_to(self) -> set[str]:
        return {"reclamo"}

    def evaluate(self, context: EntityContext) -> RuleResult:
        claim = context.entity
        estado = (claim.get("estado") or "").lower()
        if estado not in TERMINAL_CLAIM_STATUSES:
            return RuleResult(rule_id="R28", overrides=[])

        tooltip = CLAIM_TERMINAL_TOOLTIPS.get(estado, "Reclamo cerrado.")
        blocked_codes = [
            ("edit_expediente",          "state_change"),
            ("submit_to_carrier",        "state_change"),
            ("upload_evidence",          "state_change"),
            ("change_state",             "state_change"),
            ("send_followup_message",    "communication"),
            ("delete_evidence",          "state_change"),
        ]
        overrides = [
            AllowedAction(code=code, enabled=False, reason="R28",
                          tooltip=tooltip, category=category)
            for code, category in blocked_codes
        ]
        # Sólo queda visible la solicitud de reapertura.
        overrides.append(AllowedAction(
            code="request_reopen", enabled=True, reason=None,
            tooltip="Solicitar reapertura del reclamo. Requiere supervisor.",
            category="escalation",
        ))
        return RuleResult(rule_id="R28", overrides=overrides)
