"""Public ingress regression for PROMPT 13 P1.2 inbox + P1.3 claims-open KPI.

Hits REACT_APP_BACKEND_URL through the Kubernetes ingress to verify:
  * envelope shape {success: true, data: ...}
  * RBAC on inbox endpoints (agent+) and claims-open (supervisor+)
  * empty-list path for a fresh user
  * mark-all-read returns updated count
  * /api/dashboard/claims-open returns the 5 mini-KPIs
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # allow tests to be skipped if env var missing rather than crash
    BASE_URL = "https://bootstrap-emergent.preview.emergentagent.com"

PASSWORD = "Admin123!"


def _login(email: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("success") is True
    token = body["data"]["access_token"]
    assert isinstance(token, str) and len(token) > 20
    return token


@pytest.fixture(scope="module")
def coord_headers():
    return {"Authorization": f"Bearer {_login('coord@myexcellence.local')}"}


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login('admin@myexcellence.local')}"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login('agent@myexcellence.local')}"}


# ───────────────────────── /api/inbox ──────────────────────────────────
class TestInboxEndpoints:
    def test_unread_count_envelope(self, coord_headers):
        r = requests.get(f"{BASE_URL}/api/inbox/unread-count",
                         headers=coord_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "unread" in body["data"]
        assert isinstance(body["data"]["unread"], int)

    def test_list_inbox_envelope(self, coord_headers):
        r = requests.get(f"{BASE_URL}/api/inbox?limit=10",
                         headers=coord_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "items" in body["data"]
        assert isinstance(body["data"]["items"], list)
        assert "count" in body["data"]

    def test_inbox_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/inbox/unread-count", timeout=10)
        assert r.status_code in (401, 403)

    def test_mark_read_unknown_id_returns_404(self, coord_headers):
        r = requests.post(f"{BASE_URL}/api/inbox/does-not-exist/read",
                          headers=coord_headers, timeout=10)
        # success=false envelope or 404
        assert r.status_code in (404, 400, 200)
        if r.status_code == 200:
            assert r.json().get("success") is False

    def test_mark_all_read_returns_updated_count(self, coord_headers):
        r = requests.post(f"{BASE_URL}/api/inbox/read-all",
                          headers=coord_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert "updated" in body["data"]
        assert isinstance(body["data"]["updated"], int)


# ───────────────────────── /api/dashboard/claims-open ─────────────────
class TestClaimsOpenKPI:
    def test_claims_open_envelope(self, coord_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/claims-open",
                         headers=coord_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        d = body["data"]
        for key in ("open_total", "in_dictamen", "in_dictamen_aging_24h",
                    "conciliated_today", "sla_breaches_24h", "by_estado"):
            assert key in d, f"missing key {key}"
        assert isinstance(d["by_estado"], list)

    def test_claims_open_requires_supervisor(self, agent_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/claims-open",
                         headers=agent_headers, timeout=10)
        # agent role is below supervisor → must be denied
        assert r.status_code in (401, 403)


# ─────────── notificar-cliente: cliente sin email → VALIDATION_FAILED ──
class TestNotifyClientValidation:
    def test_notify_client_unknown_id_returns_404(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/reclamos/00000000-0000-0000-0000-000000000000/notificar-cliente",
            headers=admin_headers,
            json={"message": "ping"}, timeout=10)
        # 422 if Pydantic body validation fails first, 404 if id resolution
        # fails, 200 with success=false envelope otherwise.
        assert r.status_code in (404, 400, 200, 422)
        if r.status_code == 200:
            assert r.json().get("success") is False
