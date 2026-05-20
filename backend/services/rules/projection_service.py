"""RuleProjectionService — orquesta evaluators y produce projection final.

Bundle B · R50 · contrato:
    GET /api/agent/tickets/{id} → response.data.projection = {
        allowed_actions: [...],
        applied_rules:   ["R02", "R03", ...],
        computed_at:     ISO,
        ttl_seconds:     int,
    }
"""
from __future__ import annotations
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.db import get_db
from . import cache as projection_cache
from .evaluators import AllowedAction, EntityContext
from .evaluators.r02 import R02Evaluator, TERMINAL_TICKET_STATUSES
from .evaluators.r03 import R03Evaluator
from .evaluators.r28 import R28Evaluator, TERMINAL_CLAIM_STATUSES

logger = logging.getLogger("rules.projection")


@dataclass
class Projection:
    """Proyección base. Sub-clases (ticket / reclamo) podrían extender pero
    no es necesario por ahora."""
    allowed_actions: list[dict] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)
    computed_at: str = ""
    ttl_seconds: int = 60

    def as_dict(self) -> dict:
        return {
            "allowed_actions": self.allowed_actions,
            "applied_rules": self.applied_rules,
            "computed_at": self.computed_at,
            "ttl_seconds": self.ttl_seconds,
        }


# ─── Catálogo base de actions por entidad ────────────────────────────────
# Es el "default" antes de que los evaluators apliquen overrides.
_BASE_TICKET_ACTIONS = [
    AllowedAction(code="send_validation_cta",       enabled=True,  tooltip="Enviar CTA de validación de dirección.", category="communication"),
    AllowedAction(code="send_whatsapp",             enabled=True,  tooltip="Enviar mensaje por WhatsApp.",             category="communication"),
    AllowedAction(code="send_email_notification",   enabled=True,  tooltip="Enviar email al cliente.",                 category="communication"),
    AllowedAction(code="change_status",             enabled=True,  tooltip="Cambiar estado del ticket.",               category="state_change"),
    AllowedAction(code="execute_solution_automatic", enabled=True, tooltip="Ejecutar solución automática (carrier).",  category="automation"),
    AllowedAction(code="execute_solution_manual",   enabled=True,  tooltip="Ejecutar solución de forma manual.",       category="automation"),
    AllowedAction(code="add_internal_note",         enabled=True,  tooltip="Agregar nota interna.",                    category="communication"),
    AllowedAction(code="request_reopen",            enabled=False, tooltip="No aplica — el ticket está abierto.",     category="escalation"),
]

_BASE_RECLAMO_ACTIONS = [
    AllowedAction(code="edit_expediente",        enabled=True,  tooltip="Editar campos del expediente.",            category="state_change"),
    AllowedAction(code="submit_to_carrier",      enabled=True,  tooltip="Enviar reclamo al carrier.",               category="state_change"),
    AllowedAction(code="upload_evidence",        enabled=True,  tooltip="Subir evidencia.",                         category="state_change"),
    AllowedAction(code="change_state",           enabled=True,  tooltip="Cambiar estado del reclamo.",              category="state_change"),
    AllowedAction(code="send_followup_message",  enabled=True,  tooltip="Enviar mensaje de seguimiento.",           category="communication"),
    AllowedAction(code="delete_evidence",        enabled=True,  tooltip="Eliminar evidencia subida.",               category="state_change"),
    AllowedAction(code="request_reopen",         enabled=False, tooltip="No aplica — el reclamo está abierto.",    category="escalation"),
]


class RuleProjectionService:
    """Único orquestador de evaluators. Cachea resultado en Mongo TTL."""

    def __init__(self) -> None:
        self._ticket_evaluators = [R02Evaluator(), R03Evaluator()]
        self._reclamo_evaluators = [R28Evaluator()]

    # ─── Public API ──────────────────────────────────────────────────────
    async def project_for_ticket(
        self, *, tenant_id: str, ticket_id: str,
        user_id: str, user_role: str,
        explain: bool = False,
    ) -> dict:
        cached = None
        if not explain:
            cached = await projection_cache.get(
                tenant_id=tenant_id, scope="ticket",
                entity_id=ticket_id, user_role=user_role,
            )
            if cached:
                return cached["payload"]

        t0 = time.perf_counter()
        ticket = await get_db().tickets.find_one(
            {"id": ticket_id, "tenant_id": tenant_id}, {"_id": 0},
        )
        if not ticket:
            # Sin entidad no podemos proyectar; devolvemos vacío.
            return Projection(computed_at=_iso_now(), ttl_seconds=10).as_dict()

        motivo = None
        if ticket.get("motivo_id"):
            motivo = await get_db().motivos.find_one(
                {"id": ticket["motivo_id"], "tenant_id": tenant_id}, {"_id": 0},
            )

        # Pre-compute automation matrix para el client+solucion+channel del ticket.
        automation_rules: dict[tuple, bool] = {}
        if ticket.get("client_id") and ticket.get("solucion_id") and ticket.get("channel"):
            perm = await get_db().automation_permissions.find_one(
                {
                    "tenant_id": tenant_id,
                    "client_id": ticket["client_id"],
                    "solucion_id": ticket["solucion_id"],
                    "channel": ticket["channel"],
                },
                {"_id": 0, "allowed": 1},
            )
            automation_rules[(ticket["solucion_id"], ticket["channel"])] = bool(
                perm and perm.get("allowed", False),
            )

        ctx = EntityContext(
            entity_type="ticket", entity=ticket, tenant_id=tenant_id,
            user_id=user_id, user_role=user_role,
            motivo=motivo, automation_rules=automation_rules,
        )
        projection = self._compose(ctx, _BASE_TICKET_ACTIONS, self._ticket_evaluators)

        # TTL adaptativo: tickets terminales casi no cambian → cache largo.
        status = (ticket.get("status") or "").lower()
        is_terminal = bool(ticket.get("is_terminal")) or status in TERMINAL_TICKET_STATUSES
        ttl_seconds = 3600 if is_terminal else 60
        projection["ttl_seconds"] = ttl_seconds

        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > 500:
            logger.error("rules.projection slow: ticket=%s ms=%.1f", ticket_id, elapsed_ms)
        elif elapsed_ms > 200:
            logger.warning("rules.projection warn: ticket=%s ms=%.1f", ticket_id, elapsed_ms)

        await projection_cache.put(
            tenant_id=tenant_id, scope="ticket", entity_id=ticket_id,
            user_role=user_role, payload=projection, ttl_seconds=ttl_seconds,
        )
        return projection

    async def project_for_reclamo(
        self, *, tenant_id: str, claim_id: str,
        user_id: str, user_role: str,
    ) -> dict:
        cached = await projection_cache.get(
            tenant_id=tenant_id, scope="reclamo",
            entity_id=claim_id, user_role=user_role,
        )
        if cached:
            return cached["payload"]

        claim = await get_db().claims.find_one(
            {"id": claim_id, "tenant_id": tenant_id}, {"_id": 0},
        )
        if not claim:
            return Projection(computed_at=_iso_now(), ttl_seconds=10).as_dict()

        ctx = EntityContext(
            entity_type="reclamo", entity=claim, tenant_id=tenant_id,
            user_id=user_id, user_role=user_role,
        )
        projection = self._compose(ctx, _BASE_RECLAMO_ACTIONS, self._reclamo_evaluators)

        estado = (claim.get("estado") or "").lower()
        ttl_seconds = 3600 if estado in TERMINAL_CLAIM_STATUSES else 60
        projection["ttl_seconds"] = ttl_seconds

        await projection_cache.put(
            tenant_id=tenant_id, scope="reclamo", entity_id=claim_id,
            user_role=user_role, payload=projection, ttl_seconds=ttl_seconds,
        )
        return projection

    async def explain_for_ticket(
        self, *, tenant_id: str, ticket_id: str,
        user_id: str, user_role: str,
    ) -> dict:
        """Bypass de cache + traza por evaluator. Solo root_dev (B1.2.7)."""
        ticket = await get_db().tickets.find_one(
            {"id": ticket_id, "tenant_id": tenant_id}, {"_id": 0},
        )
        if not ticket:
            return {"ticket_id": ticket_id, "found": False, "trace": []}

        motivo = None
        if ticket.get("motivo_id"):
            motivo = await get_db().motivos.find_one(
                {"id": ticket["motivo_id"], "tenant_id": tenant_id}, {"_id": 0},
            )
        automation_rules = {}
        if ticket.get("solucion_id") and ticket.get("channel"):
            perm = await get_db().automation_permissions.find_one(
                {
                    "tenant_id": tenant_id,
                    "client_id": ticket.get("client_id"),
                    "solucion_id": ticket["solucion_id"],
                    "channel": ticket["channel"],
                },
                {"_id": 0, "allowed": 1},
            )
            automation_rules[(ticket["solucion_id"], ticket["channel"])] = bool(
                perm and perm.get("allowed", False),
            )

        ctx = EntityContext(
            entity_type="ticket", entity=ticket, tenant_id=tenant_id,
            user_id=user_id, user_role=user_role,
            motivo=motivo, automation_rules=automation_rules,
        )
        trace = []
        for ev in self._ticket_evaluators:
            t0 = time.perf_counter()
            result = ev.evaluate(ctx)
            ms = (time.perf_counter() - t0) * 1000
            trace.append({
                "rule_id": result.rule_id,
                "evaluator": type(ev).__name__,
                "elapsed_ms": round(ms, 3),
                "overrides_count": len(result.overrides),
                "overrides_codes": [o.code for o in result.overrides],
            })
        projection = self._compose(ctx, _BASE_TICKET_ACTIONS, self._ticket_evaluators)
        return {"ticket_id": ticket_id, "found": True,
                "projection": projection, "trace": trace}

    # ─── Internal ────────────────────────────────────────────────────────
    def _compose(
        self, ctx: EntityContext, base: list[AllowedAction],
        evaluators: list,
    ) -> dict:
        actions = {a.code: AllowedAction(**asdict(a)) for a in base}
        applied = []
        for ev in evaluators:
            result = ev.evaluate(ctx)
            if not result.overrides:
                continue
            applied.append(result.rule_id)
            for override in result.overrides:
                # Ganadores: rule_id más restrictivo (disabled > enabled).
                # Como evaluamos en orden y R02 va antes de R03, el primer
                # disabled "gana" — eso es lo deseado: ticket terminal silencia
                # la matriz de automatización.
                current = actions.get(override.code)
                if current is None or not current.enabled or override.enabled:
                    actions[override.code] = override
                else:
                    # current.enabled=True AND override.enabled=False → aplicar
                    actions[override.code] = override

        return {
            "allowed_actions": [asdict(a) for a in actions.values()],
            "applied_rules": applied,
            "computed_at": _iso_now(),
            "ttl_seconds": 60,
        }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Instancia singleton — barata, sin estado mutable.
projection_service = RuleProjectionService()
