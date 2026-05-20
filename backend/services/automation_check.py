"""Single source of truth for R03 — may we automate this ticket?

R03: AutomationService ejecuta SOLO si
  automation_permissions(client_id, solucion_id, channel).allowed = TRUE
  AND motivos.restricted = FALSE.

Default of any row in automation_permissions: allowed = FALSE.
This module is the ONLY caller of motivo.restricted + permission.allowed
in the codebase — Controllers and the WorkflowEngine (PROMPT_05) MUST
delegate here. (R14 — Single Source of Truth.)
"""
from __future__ import annotations
from dataclasses import dataclass

from core.db import get_db


@dataclass
class AutomationDecision:
    can_automate: bool
    reason: str  # human-readable English+es-MX label for logs/timeline


async def can_automate(
    *,
    tenant_id: str,
    client_id: str,
    solucion_id: str,
    channel: str,
) -> AutomationDecision:
    db = get_db()

    # PROMPT 13 — synthetic solucion ids for the claims flow ("reclamo:{tipo_dano}")
    # bypass the soluciones/motivos lookup. The CxC flow has its own state machine
    # and tipo_dano enum, so no solucion row exists. R03 still applies on the
    # automation_permissions check below.
    is_claim_flow = isinstance(solucion_id, str) and solucion_id.startswith("reclamo:")

    if not is_claim_flow:
        sol = await db.soluciones.find_one(
            {"tenant_id": tenant_id, "id": solucion_id},
            {"_id": 0},
        )
        if not sol:
            return AutomationDecision(False, "solucion_not_found")
        if not sol.get("automatable", False):
            return AutomationDecision(False, "solucion_no_automatable")

        motivo = await db.motivos.find_one(
            {"tenant_id": tenant_id, "id": sol["motivo_id"]},
            {"_id": 0},
        )
        if not motivo:
            return AutomationDecision(False, "motivo_not_found")
        if motivo.get("restricted", False):
            # R03 hard-stop: motivos restricted (e.g., AUTORIDAD) NEVER automate
            return AutomationDecision(False, "motivo_restricted")
        if not motivo.get("active", True):
            return AutomationDecision(False, "motivo_inactive")

    perm = await db.automation_permissions.find_one(
        {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "solucion_id": solucion_id,
            "channel": channel,
        },
        {"_id": 0},
    )
    if not perm or not perm.get("allowed", False):
        # Default-deny when row missing
        return AutomationDecision(False, "permission_denied")

    return AutomationDecision(True, "ok")
