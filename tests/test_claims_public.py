"""E2E claims test against the public REACT_APP_BACKEND_URL.

Validates routing through ingress for PROMPT 13 endpoints — tests that
listing/empty queries work end-to-end with real auth.
"""
from __future__ import annotations
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bootstrap-emergent.preview.emergentagent.com").rstrip("/")


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["data"]["access_token"]


def test_health_via_ingress():
    r = requests.get(f"{BASE_URL}/api/system/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["db"] == "ok"


def test_login_agent_seed():
    tok = _login("agent@myexcellence.local", "Admin123!")
    assert isinstance(tok, str) and len(tok) > 20


def test_list_reclamos_agent_via_public():
    tok = _login("agent@myexcellence.local", "Admin123!")
    r = requests.get(f"{BASE_URL}/api/reclamos",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "items" in body["data"]
    assert isinstance(body["data"]["items"], list)


def test_list_reclamos_filtered_by_estado():
    tok = _login("agent@myexcellence.local", "Admin123!")
    r = requests.get(f"{BASE_URL}/api/reclamos?estado=promovido",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    for c in items:
        assert c.get("estado") == "promovido"


def test_reclamos_requires_auth():
    r = requests.get(f"{BASE_URL}/api/reclamos", timeout=10)
    assert r.status_code in (401, 403)


def test_promote_nonexistent_ticket_returns_404():
    tok = _login("agent@myexcellence.local", "Admin123!")
    r = requests.post(
        f"{BASE_URL}/api/tickets/00000000-0000-0000-0000-000000000000/promote-to-claim",
        json={"tipo_dano": "extravio", "monto_reclamado": 100.0},
        headers={"Authorization": f"Bearer {tok}"}, timeout=10,
    )
    assert r.status_code == 404


def test_claim_detail_404_for_unknown_id():
    tok = _login("agent@myexcellence.local", "Admin123!")
    r = requests.get(f"{BASE_URL}/api/reclamos/00000000-0000-0000-0000-000000000000",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    assert r.status_code == 404


def test_dictamen_ingest_is_public_but_rejects_no_body():
    """Endpoint is in PUBLIC_PREFIXES — must not 401, but must validate."""
    r = requests.post(
        f"{BASE_URL}/api/reclamos/ingest/dictamen?client_id=00000000-0000-0000-0000-000000000000",
        data=b"", timeout=10,
    )
    # Must not be 401 (means it's actually public)
    assert r.status_code != 401
    # Empty body validation OR client not found
    assert r.status_code in (400, 404, 422)
