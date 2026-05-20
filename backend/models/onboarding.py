"""Pydantic models — Bundle E · Onboarding Admin Wizard (Iter33).

Modelos de wire-contract para los endpoints `/api/admin/onboarding/*`.
La persistencia (colección `admin_onboarding_progress`) la maneja
`AdminOnboardingRepository`.
"""
from __future__ import annotations
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---- Pasos del wizard (orden deliberado, 6 efectivos según choice del PO) ----
# Step 7 (invitar equipo) fue saltado por decisión del PO en Bundle E. El
# wizard finaliza directo tras `automation_matrix` → pantalla de completion.
STEP_WELCOME = "step_1_welcome"
STEP_TENANT_INFO = "step_2_tenant_info"
STEP_PROJECT_CLIENT = "step_3_project_client"
STEP_CARRIERS = "step_4_carriers"
STEP_CATALOG = "step_5_catalog"
STEP_AUTOMATION_MATRIX = "step_6_automation_matrix"

# Orden canónico. Si reordenás, también ajustá `next_step()` en el repo.
STEP_ORDER: list[str] = [
    STEP_WELCOME,
    STEP_TENANT_INFO,
    STEP_PROJECT_CLIENT,
    STEP_CARRIERS,
    STEP_CATALOG,
    STEP_AUTOMATION_MATRIX,
]

# Pasos que NO pueden saltarse (R51 — onboarding asistido no bloqueante, pero
# pasos críticos para operar el producto se marcan como mandatorios).
# - welcome: da contexto crítico, no captura nada.
# - catalog: sin catálogo los agentes no operan.
MANDATORY_STEPS: set[str] = {STEP_WELCOME, STEP_CATALOG}

StepName = Literal[
    "step_1_welcome",
    "step_2_tenant_info",
    "step_3_project_client",
    "step_4_carriers",
    "step_5_catalog",
    "step_6_automation_matrix",
]


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_step: StepName
    step_data: dict[str, Any] = Field(default_factory=dict)


class SkipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_step: StepName


class OnboardingState(BaseModel):
    """Wire shape devuelto por GET /api/admin/onboarding/state.

    `should_auto_open` es la decisión del backend según E1.1:
        - usuario rol admin/superadmin
        - tenant <= 30 días de antigüedad
        - sin completed_at registrado para este (tenant, user)
    """
    in_progress: bool
    current_step: Optional[StepName]
    steps_completed: list[str]
    step_data: dict[str, Any]
    started_at: Optional[str]
    last_activity: Optional[str]
    completed_at: Optional[str]
    should_auto_open: bool
    is_completed: bool
    # Auxiliar — UI muestra estos como pasos "pre-completados a nivel tenant"
    # (case del 2do admin del mismo tenant: tenant_info ya está, catalog ya
    # está, etc.). Calculado dinámicamente por el backend.
    pre_completed_by_tenant: list[str] = Field(default_factory=list)
