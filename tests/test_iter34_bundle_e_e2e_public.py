"""Iter34 — Bundle E · E2E pública via REACT_APP_BACKEND_URL.

Complementa test_iter33_bundle_e_onboarding.py (ASGI directo) ejerciendo
los mismos endpoints contra el ingress externo + auth real.

Cobertura:
  * Login admin/superadmin/root_dev → 200, agent → endpoint /state 403
  * /api/admin/onboarding/state shape completo + claves esperadas
  * /start idempotente
  * /seed-mx-catalog → 12 motivos, ≥18 soluciones, segunda llamada skipped
  * /advance + /skip-step + /complete (idempotente)
  * Skip rechazado para step_1_welcome y step_5_catalog (422 → 200+errors)
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

CREDS = {
    "admin":      ("admin@myexcellence.local",      "Admin123!"),
    "superadmin": ("superadmin@myexcellence.local", "Admin123!"),
    "root":       ("root@myexcellence.local",       "Admin123!"),
    "agent":      ("agent@myexcellence.local",      "Admin123!"),
}


def _login(role_key: str) -> dict:
    email, pwd = CREDS[role_key]
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {role_key}: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("success") is True
    return body["data"]


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin")["access_token"]


@pytest.fixture(scope="module")
def super_token():
    return _login("superadmin")["access_token"]


@pytest.fixture(scope="module")
def root_token():
    return _login("root")["access_token"]


@pytest.fixture(scope="module")
def agent_token():
    return _login("agent")["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ─── RBAC ──────────────────────────────────────────────────────────────
def test_state_admin_200(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=_h(admin_token), timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    d = body["data"]
    for k in ("in_progress", "current_step", "steps_completed", "step_data",
              "started_at", "last_activity", "completed_at",
              "should_auto_open", "is_completed",
              "pre_completed_by_tenant", "tenant_age_days"):
        assert k in d, f"missing key {k}"
    assert isinstance(d["pre_completed_by_tenant"], list)
    assert isinstance(d["tenant_age_days"], int)


def test_state_superadmin_200(super_token):
    r = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=_h(super_token), timeout=10)
    assert r.status_code == 200


def test_state_root_dev_200(root_token):
    r = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=_h(root_token), timeout=10)
    assert r.status_code == 200


def test_state_agent_forbidden(agent_token):
    r = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=_h(agent_token), timeout=10)
    assert r.status_code == 403


def test_state_no_auth_unauthorized():
    r = requests.get(f"{BASE_URL}/api/admin/onboarding/state", timeout=10)
    assert r.status_code in (401, 403)


# ─── Start idempotente ────────────────────────────────────────────────
def test_start_idempotent(admin_token):
    r1 = requests.post(f"{BASE_URL}/api/admin/onboarding/start",
                       headers=_h(admin_token), timeout=10)
    assert r1.status_code == 200
    r2 = requests.post(f"{BASE_URL}/api/admin/onboarding/start",
                       headers=_h(admin_token), timeout=10)
    assert r2.status_code == 200
    # current_step debe ser consistente
    assert r2.json()["data"]["current_step"] in (
        "step_1_welcome", "step_2_tenant_info", "step_3_project_client",
        "step_4_carriers", "step_5_catalog", "step_6_automation_matrix",
    )


# ─── seed-mx-catalog ──────────────────────────────────────────────────
def test_seed_mx_catalog_counts_and_idempotent(root_token):
    """Usamos root_dev para no contaminar el doc del admin."""
    r1 = requests.post(f"{BASE_URL}/api/admin/onboarding/seed-mx-catalog",
                       headers=_h(root_token), timeout=20)
    assert r1.status_code == 200
    d1 = r1.json()["data"]
    # En primer corrida puede insertar 12 o 0 (si ya estaba sembrado de antes).
    assert d1["motivos_inserted"] + d1["motivos_skipped"] == 12
    # 2da llamada: todo skipped, 0 inserted
    r2 = requests.post(f"{BASE_URL}/api/admin/onboarding/seed-mx-catalog",
                       headers=_h(root_token), timeout=20)
    d2 = r2.json()["data"]
    assert d2["motivos_inserted"] == 0
    assert d2["motivos_skipped"] == 12
    assert d2["soluciones_inserted"] == 0
    # soluciones_skipped debería ser ≥18
    assert d2["soluciones_skipped"] >= 18


# ─── Skip mandatorios rechazados ──────────────────────────────────────
def test_skip_mandatory_step_welcome_rejected(super_token):
    r = requests.post(f"{BASE_URL}/api/admin/onboarding/skip-step",
                      headers=_h(super_token),
                      json={"current_step": "step_1_welcome"}, timeout=10)
    # API wrapper devuelve 200 con success:false según core.response.fail
    # o 422 según implementación. Aceptamos ambos pero validamos error.
    if r.status_code == 200:
        body = r.json()
        assert body.get("success") is False
        assert body.get("errors")
    else:
        assert r.status_code == 422


def test_skip_mandatory_step_catalog_rejected(super_token):
    r = requests.post(f"{BASE_URL}/api/admin/onboarding/skip-step",
                      headers=_h(super_token),
                      json={"current_step": "step_5_catalog"}, timeout=10)
    if r.status_code == 200:
        body = r.json()
        assert body.get("success") is False
    else:
        assert r.status_code == 422


# ─── Advance + complete idempotente (uso root_dev para no contaminar) ─
def test_advance_and_complete_flow(root_token):
    headers = _h(root_token)
    # Avanzar welcome
    r = requests.post(f"{BASE_URL}/api/admin/onboarding/advance",
                      headers=headers,
                      json={"current_step": "step_1_welcome",
                            "step_data": {}}, timeout=10)
    assert r.status_code == 200
    assert r.json()["data"]["current_step"] in (
        "step_2_tenant_info", "step_3_project_client", "step_4_carriers",
        "step_5_catalog", "step_6_automation_matrix", None,
    )
    # Complete idempotente
    c1 = requests.post(f"{BASE_URL}/api/admin/onboarding/complete",
                       headers=headers, timeout=10)
    assert c1.status_code == 200
    c2 = requests.post(f"{BASE_URL}/api/admin/onboarding/complete",
                       headers=headers, timeout=10)
    assert c2.status_code == 200
    # state ahora: is_completed=true, should_auto_open=false
    s = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=headers, timeout=10).json()["data"]
    assert s["is_completed"] is True
    assert s["should_auto_open"] is False


# ─── Multi-tenant isolation: admin de tenant A no ve datos de tenant B ─
def test_tenant_isolation_state(admin_token, super_token):
    """admin y superadmin viven en mismo tenant (myexcellence), pero el doc
    de progreso es per-user; verificar que la respuesta no expone tenant_id
    foráneo. (No hay otro tenant seeded, así que validamos shape mínimo.)
    """
    a = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=_h(admin_token), timeout=10).json()["data"]
    s = requests.get(f"{BASE_URL}/api/admin/onboarding/state",
                     headers=_h(super_token), timeout=10).json()["data"]
    # Ambos en mismo tenant → mismo tenant_age_days y pre_completed_by_tenant
    assert a["tenant_age_days"] == s["tenant_age_days"]
    assert sorted(a["pre_completed_by_tenant"]) == sorted(s["pre_completed_by_tenant"])
    # Pero los pasos completados son independientes por user.
    # (No assert estricto; solo verificamos que es una lista)
    assert isinstance(a["steps_completed"], list)
    assert isinstance(s["steps_completed"], list)
