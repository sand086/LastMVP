"""PROMPT 11 — Notifications endpoints over the public ingress (REACT_APP_BACKEND_URL)."""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bootstrap-emergent.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@myexcellence.local"
AGENT_EMAIL = "agent@myexcellence.local"
PASSWORD = "Admin123!"


def _login(email: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    data = body.get("data") or {}
    tok = data.get("access_token") or data.get("token") or body.get("access_token") or body.get("token")
    assert tok, f"no token in {body}"
    return tok


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL)}"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login(AGENT_EMAIL)}"}


def test_config_returns_resend_state(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/notifications/config", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["resend_configured"] is True
    assert data["sender_email"] == "onboarding@resend.dev"
    assert "email" in data["channels_available"]
    assert "whatsapp" in data["channels_available"]
    # No api_key leak
    assert "api_key" not in str(data).lower()
    assert "re_" not in str(data)  # secret prefix not exposed


def test_config_rbac_blocks_agent(agent_headers):
    r = requests.get(f"{BASE_URL}/api/admin/notifications/config", headers=agent_headers, timeout=20)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


def test_test_endpoint_rbac_blocks_agent(agent_headers):
    r = requests.post(f"{BASE_URL}/api/admin/notifications/test",
                      json={"to": "demo@example.com"}, headers=agent_headers, timeout=20)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


def test_test_endpoint_returns_resend_failure_for_non_owner(admin_headers):
    """In Resend testing mode, sending to non-owner email fails with 502 + clear reason."""
    r = requests.post(f"{BASE_URL}/api/admin/notifications/test",
                      json={"to": "demo@example.com"}, headers=admin_headers, timeout=30)
    # Real Resend in testing mode → ok=false. Endpoint returns 502 in this case.
    assert r.status_code in (200, 502), f"unexpected: {r.status_code} {r.text}"
    body = r.json()["data"]
    assert body["to"] == "demo@example.com"
    res = body["result"]
    if res["ok"]:
        # If Resend account got upgraded after test was authored, just assert id present
        assert res["id"]
    else:
        # Should expose a reason string (Resend's error)
        assert res.get("reason"), f"expected reason, got {res}"


def test_test_endpoint_real_send_to_owner(admin_headers):
    """Sending to the verified Resend owner succeeds with a real id (not mock).

    Bundle A · FIX-A3 (Mayo 2026): el endpoint /test exige ahora
    ``confirmed_external=true`` para destinatarios fuera de la whitelist;
    el owner de Resend (gmail) cae en esa categoría y el flujo simulado del
    front pasa el flag explícitamente. Replicamos eso aquí.
    """
    r = requests.post(f"{BASE_URL}/api/admin/notifications/test",
                      json={"to": "jair.vargas.9108@gmail.com",
                            "confirmed_external": True},
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    res = r.json()["data"]["result"]
    assert res["ok"] is True, f"expected real ok=true, got {res}"
    assert res["id"] and not res["id"].startswith("mock_"), f"expected real id, got {res['id']}"
    assert res["mock"] is False
