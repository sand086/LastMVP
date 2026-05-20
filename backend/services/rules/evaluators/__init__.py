"""Base contracts para evaluators de reglas — Bundle B · R50."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class AllowedAction:
    """Una acción CTA proyectada para la UI."""
    code: str
    enabled: bool
    reason: Optional[str] = None           # rule_id si está bloqueado
    tooltip: str = ""                      # texto humano
    category: str = "other"                # communication | state_change | automation | escalation | other


@dataclass
class EntityContext:
    """Contexto compartido para evaluators. Inmutable durante una proyección."""
    entity_type: str                       # "ticket" | "reclamo"
    entity: dict                           # documento Mongo (sin _id)
    tenant_id: str
    user_id: str
    user_role: str
    # Optional helpers — varían por entity_type
    motivo: Optional[dict] = None
    automation_rules: Optional[dict] = None
    client: Optional[dict] = None


@dataclass
class RuleResult:
    """Lo que retorna cada evaluator: a qué actions afecta y su veredicto."""
    rule_id: str
    overrides: list[AllowedAction]         # cada elemento sobreescribe el catálogo base


class RuleEvaluatorInterface(Protocol):
    def rule_id(self) -> str: ...
    def applies_to(self) -> set[str]:
        """Lista de entity_types a los que aplica este evaluator
        (ej. {"ticket"} o {"reclamo"})."""
        ...
    def evaluate(self, context: EntityContext) -> RuleResult: ...
