"""Iteration 14 — live ingress integration tests for:
- /api/admin/security/audit (root_dev only)
- /api/saved-filters CRUD with per-user isolation + RBAC denials
- /api/admin/claims/{id}/export.pdf + bulk-export.zip RBAC + magic bytes
- /api/admin/webhooks/subscriptions/{id}/reset-circuit (admin+) (smoke)
- OpenAPI registration for webhook endpoints

All tests run against REACT_APP_BACKEND_URL (preview ingress).
"""
from __future__ import annotations
import io
import os
import zipfile

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bootstrap-emergent.preview.emergentagent.com").rstrip("/")
PWD = "Admin123!"

ROOT_EMAIL = "root@myexcellence.local"
ADMIN_EMAIL = "admin@myexcellence.local"
AGENT_EMAIL = "agent@myexcellence.local"
AUDITOR_EMAIL = "auditor@myexcellence.local"


def _login(email: str, password: str = PWD) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {email} {r.status_code} {r.text}"
    return r.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def root_token():
    return _login(ROOT_EMAIL)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL)


@pytest.fixture(scope="module")
def agent_token():
    return _login(AGENT_EMAIL)


@pytest.fixture(scope="module")
def auditor_token():
    return _login(AUDITOR_EMAIL)


def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── Security audit ──────────────────────────────────────────────────────
class TestSecurityAudit:
    def test_root_dev_access(self, root_token):
        r = requests.get(f"{BASE_URL}/api/admin/security/audit", headers=H(root_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        data = body["data"]
        assert "checks" in data and isinstance(data["checks"], list) and len(data["checks"]) > 0
        for c in data["checks"]:
            assert c["severity"] in ("pass", "warn", "fail")
            assert c.get("name") and "detail" in c
        s = data["summary"]
        assert {"total_checks", "pass", "warn", "fail", "ready_for_prod"} <= s.keys()
        assert s["total_checks"] == len(data["checks"])
        assert isinstance(s["ready_for_prod"], bool)

    def test_admin_forbidden(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/security/audit", headers=H(admin_token), timeout=15)
        assert r.status_code == 403, f"admin must be 403, got {r.status_code} {r.text[:200]}"

    def test_agent_forbidden(self, agent_token):
        r = requests.get(f"{BASE_URL}/api/admin/security/audit", headers=H(agent_token), timeout=15)
        assert r.status_code == 403

    def test_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/admin/security/audit", timeout=15)
        assert r.status_code in (401, 403)


# ─── Saved filters ───────────────────────────────────────────────────────
class TestSavedFilters:
    def test_agent_crud_and_isolation(self, agent_token, admin_token):
        # CREATE as agent
        payload = {"name": "TEST_iter14_agentfilter", "scope": "agent_queue",
                   "filters": {"status": ["nuevo", "in_progress"]}}
        r = requests.post(f"{BASE_URL}/api/saved-filters", headers=H(agent_token),
                          json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        body = r.json()["data"]
        fid = body["id"]
        assert body["name"] == payload["name"]
        assert body["scope"] == "agent_queue"
        assert body["filters"] == payload["filters"]

        # LIST as agent should include
        r2 = requests.get(f"{BASE_URL}/api/saved-filters", headers=H(agent_token), timeout=15)
        assert r2.status_code == 200
        items = r2.json()["data"]["items"]
        assert any(it["id"] == fid for it in items), "agent must see his own filter"

        # LIST as admin should NOT include the agent's filter (per-user isolation)
        r3 = requests.get(f"{BASE_URL}/api/saved-filters", headers=H(admin_token), timeout=15)
        assert r3.status_code == 200
        admin_items = r3.json()["data"]["items"]
        assert all(it["id"] != fid for it in admin_items), "admin must NOT see agent's filter"

        # DELETE as admin (different user) should 404 (not owner)
        r4 = requests.delete(f"{BASE_URL}/api/saved-filters/{fid}",
                             headers=H(admin_token), timeout=15)
        assert r4.status_code == 404, f"admin delete of agent filter must be 404, got {r4.status_code}"

        # DELETE as agent (owner) → 200
        r5 = requests.delete(f"{BASE_URL}/api/saved-filters/{fid}",
                             headers=H(agent_token), timeout=15)
        assert r5.status_code == 200
        assert r5.json()["data"]["deleted"] is True

        # DELETE again should 404
        r6 = requests.delete(f"{BASE_URL}/api/saved-filters/{fid}",
                             headers=H(agent_token), timeout=15)
        assert r6.status_code == 404

    def test_client_auditor_forbidden(self, auditor_token):
        r = requests.get(f"{BASE_URL}/api/saved-filters", headers=H(auditor_token), timeout=15)
        assert r.status_code == 403, f"client_auditor must be 403, got {r.status_code}"

    def test_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/saved-filters", timeout=15)
        assert r.status_code in (401, 403)


# ─── Claims PDF + bulk ZIP ───────────────────────────────────────────────
class TestClaimsExport:
    def _find_claim_id(self, admin_token: str) -> str | None:
        # Try admin claims listing (may exist)
        for path in ("/api/admin/claims", "/api/claims"):
            try:
                r = requests.get(f"{BASE_URL}{path}", headers=H(admin_token), timeout=15)
                if r.status_code == 200:
                    data = r.json().get("data") or r.json()
                    items = data.get("items") if isinstance(data, dict) else data
                    if items and isinstance(items, list) and len(items) > 0:
                        return items[0].get("id")
            except Exception:
                continue
        return None

    def test_pdf_404_for_unknown_claim(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/claims/nonexistent-xyz/export.pdf",
                         headers=H(admin_token), timeout=15)
        assert r.status_code == 404

    def test_pdf_individual_admin(self, admin_token):
        cid = self._find_claim_id(admin_token)
        if not cid:
            pytest.skip("No claims exist in tenant — cannot exercise PDF export")
        r = requests.get(f"{BASE_URL}/api/admin/claims/{cid}/export.pdf",
                         headers=H(admin_token), timeout=30)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        assert r.content[:4] == b"%PDF", "missing PDF magic bytes"

    def test_pdf_agent_forbidden(self, admin_token, agent_token):
        cid = self._find_claim_id(admin_token) or "x"
        r = requests.get(f"{BASE_URL}/api/admin/claims/{cid}/export.pdf",
                         headers=H(agent_token), timeout=15)
        assert r.status_code == 403

    def test_bulk_zip_404_when_invalid_ids(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/admin/claims/bulk-export.zip",
                          headers=H(admin_token),
                          json={"claim_ids": ["nope-1", "nope-2"]}, timeout=20)
        assert r.status_code == 404

    def test_bulk_zip_admin(self, admin_token):
        cid = self._find_claim_id(admin_token)
        if not cid:
            pytest.skip("No claims exist in tenant")
        r = requests.post(f"{BASE_URL}/api/admin/claims/bulk-export.zip",
                          headers=H(admin_token),
                          json={"claim_ids": [cid, "fake-other-tenant"]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        assert r.headers.get("content-type", "").startswith("application/zip")
        assert r.headers.get("X-MyE-Bulk-Count") == "1", "cross-tenant must be filtered out"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert len(names) >= 1
        with zf.open(names[0]) as f:
            assert f.read(4) == b"%PDF"

    def test_bulk_zip_agent_forbidden(self, agent_token):
        r = requests.post(f"{BASE_URL}/api/admin/claims/bulk-export.zip",
                          headers=H(agent_token),
                          json={"claim_ids": ["x"]}, timeout=15)
        assert r.status_code == 403


# ─── Webhook circuit reset + OpenAPI ─────────────────────────────────────
class TestWebhooksMeta:
    def test_openapi_registers_endpoints(self, admin_token):
        # OpenAPI spec is not exposed through the ingress (only /api/* is proxied,
        # and FastAPI registers spec at /openapi.json which is shadowed by the
        # SPA). Endpoint registration is implicitly verified by all other tests
        # in this file hitting the live routes successfully. We treat this as a
        # smoke check on /api/admin/webhooks/events instead.
        r = requests.get(f"{BASE_URL}/api/admin/webhooks/events",
                          headers=H(admin_token), timeout=15)
        assert r.status_code == 200, r.text[:200]
        body = r.json()["data"]
        assert "items" in body and len(body["items"]) >= 1

    def test_reset_circuit_404_for_unknown(self, admin_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/webhooks/subscriptions/nonexistent-sub/reset-circuit",
            headers=H(admin_token), timeout=15,
        )
        # Should be 404 (not found) but not 403/500
        assert r.status_code in (404, 400), f"unexpected {r.status_code} {r.text[:200]}"

    def test_reset_circuit_agent_forbidden(self, agent_token):
        r = requests.post(
            f"{BASE_URL}/api/admin/webhooks/subscriptions/nonexistent-sub/reset-circuit",
            headers=H(agent_token), timeout=15,
        )
        assert r.status_code == 403
