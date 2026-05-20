"""R02 — Estados terminales de tickets (delivered, returned, cancelled, closed, resolved).

Cuando un ticket llegó a un estado terminal, todas las acciones de cambio
de estado / comunicación se ocultan. Sólo queda visible el botón
'Solicitar reapertura (supervisor)'.
"""
from __future__ import annotations
from . import (
    AllowedAction, EntityContext, RuleEvaluatorInterface, RuleResult,
)

TERMINAL_TICKET_STATUSES = {
    "delivered", "returned", "cancelled", "closed", "resolved",
}

TICKET_TERMINAL_TOOLTIPS = {
    "delivered": "Entregado. El ticket está cerrado.",
    "returned":  "Devuelto al origen. El ticket está cerrado.",
    "cancelled": "Cancelado. El ticket está cerrado.",
    "closed":    "Cerrado.",
    "resolved":  "Resuelto.",
}


class R02Evaluator:
    def rule_id(self) -> str:
        return "R02"

    def applies_to(self) -> set[str]:
        return {"ticket"}

    def evaluate(self, context: EntityContext) -> RuleResult:
        ticket = context.entity
        status = (ticket.get("status") or "").lower()
        is_terminal = bool(ticket.get("is_terminal")) or status in TERMINAL_TICKET_STATUSES
        overrides: list[AllowedAction] = []
        if not is_terminal:
            return RuleResult(rule_id="R02", overrides=[])

        tooltip = TICKET_TERMINAL_TOOLTIPS.get(status, "El ticket está en un estado terminal.")
        # Bloquear comunicación y cambios de estado. Habilitar reapertura.
        blocked_actions = [
            ("send_validation_cta",       "communication"),
            ("send_whatsapp",             "communication"),
            ("send_email_notification",   "communication"),
            ("change_status",             "state_change"),
            ("execute_solution_automatic", "automation"),
            ("execute_solution_manual",   "automation"),
            ("add_internal_note",         "communication"),
        ]
        for code, category in blocked_actions:
            overrides.append(AllowedAction(
                code=code, enabled=False, reason="R02",
                tooltip=tooltip, category=category,
            ))
        # Reapertura disponible (requiere supervisor).
        overrides.append(AllowedAction(
            code="request_reopen", enabled=True, reason=None,
            tooltip="Solicitar reapertura del caso. Requiere aprobación del supervisor.",
            category="escalation",
        ))
        return RuleResult(rule_id="R02", overrides=overrides)
