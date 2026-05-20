"""R03 — Matriz de permisos de automatización.

Bloquea acciones `execute_solution_automatic` cuando:
  - El motivo del ticket tiene `restricted=True` (hard stop legal — ej. AUTORIDAD),
    o
  - La fila (client_id, solucion_id, channel) en `automation_permissions`
    está ausente o tiene `allowed=False` (default-deny).

Si la solución todavía no fue asignada al ticket (`solucion_id is None`),
no proyectamos nada — R03 se evaluará cuando se elija solución.
"""
from __future__ import annotations
from . import (
    AllowedAction, EntityContext, RuleEvaluatorInterface, RuleResult,
)


class R03Evaluator:
    def rule_id(self) -> str:
        return "R03"

    def applies_to(self) -> set[str]:
        return {"ticket"}

    def evaluate(self, context: EntityContext) -> RuleResult:
        ticket = context.entity
        motivo = context.motivo
        rules = context.automation_rules or {}

        # ─── Hard stop: motivo restricted ─────────────────────────────────
        if motivo and motivo.get("restricted"):
            return RuleResult(rule_id="R03", overrides=[
                AllowedAction(
                    code="execute_solution_automatic",
                    enabled=False, reason="R03",
                    tooltip=("Motivo restringido por política legal. "
                             "Solo gestión manual permitida."),
                    category="automation",
                ),
            ])

        # ─── No solución asignada todavía ─────────────────────────────────
        solucion_id = ticket.get("solucion_id")
        channel = ticket.get("channel")
        if not solucion_id or not channel:
            return RuleResult(rule_id="R03", overrides=[])

        # ─── Matrix lookup (precalculada en context.automation_rules) ────
        # automation_rules es un dict precomputado en projection_service:
        # {(solucion_id, channel): allowed}
        allowed = rules.get((solucion_id, channel), False)
        if allowed:
            return RuleResult(rule_id="R03", overrides=[
                AllowedAction(
                    code="execute_solution_automatic",
                    enabled=True, reason=None,
                    tooltip="Automatización permitida por el administrador.",
                    category="automation",
                ),
            ])

        return RuleResult(rule_id="R03", overrides=[
            AllowedAction(
                code="execute_solution_automatic",
                enabled=False, reason="R03",
                tooltip=("Requiere acción manual. Esta combinación motivo / "
                         "solución / canal no está autorizada para "
                         "automatización por tu administrador."),
                category="automation",
            ),
        ])
