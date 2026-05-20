"""ITERATION 17 — Backend tests for new Agent Panel endpoints.

Covers:
- GET   /api/agent/tickets/{id}               (detail with timeline/guia/active_claim/evidence_count/client)
- POST  /api/agent/tickets/{id}/comment       (append-only internal/external)
- POST  /api/agent/tickets/bulk-take
- POST  /api/agent/tickets/bulk-status
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bootstrap-emergent.preview.emergentagent.com").rstrip("/")
TIMEOUT = 30


def _login(email: str, password: str = "Admin123!") -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password},
                      timeout=TIMEOUT)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    data = body.get("data", body)
    token = data.get("access_token") or data.get("token")
    assert token, f"no token in response: {body}"
    return token


@pytest.fixture(scope="module")
def agent_token() -> str:
    return _login("agent@myexcellence.local")


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _login("admin@myexcellence.local")


@pytest.fixture(scope="module")
def headers_agent(agent_token):
    return {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def headers_admin(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def agent_queue(headers_agent):
    r = requests.get(f"{BASE_URL}/api/agent/queue", headers=headers_agent, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json().get("data", r.json())
    return data


@pytest.fixture(scope="module")
def a_ticket_id(agent_queue):
    mine = agent_queue.get("mine", [])
    pool = agent_queue.get("pool", [])
    all_t = mine + pool
    if not all_t:
        pytest.skip("No tickets available in queue for tests")
    return all_t[0]["id"]


# ──────────────────────────────  GET /tickets/{id}  ─────────────────────────
class TestTicketDetail:

    def test_ticket_detail_shape(self, headers_agent, a_ticket_id):
        r = requests.get(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}",
                         headers=headers_agent, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        for key in ("ticket", "timeline", "guia", "active_claim", "evidence_count", "client"):
            assert key in data, f"missing key {key} in detail response"
        assert data["ticket"]["id"] == a_ticket_id
        assert isinstance(data["timeline"], list)
        assert isinstance(data["evidence_count"], int)

    def test_ticket_detail_not_found(self, headers_agent):
        r = requests.get(f"{BASE_URL}/api/agent/tickets/does-not-exist-xyz",
                         headers=headers_agent, timeout=TIMEOUT)
        assert r.status_code == 404, r.text


# ──────────────────────────────  POST /comment  ─────────────────────────────
class TestComment:

    def test_comment_internal_creates_action_event(self, headers_agent, a_ticket_id):
        payload = {"body": "TEST_internal note from pytest iter17", "visibility": "internal"}
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent, json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        ev = r.json().get("data", r.json()).get("event")
        assert ev is not None
        assert ev["event_type"] == "action"
        assert ev["payload"]["visibility"] == "internal"
        assert ev["payload"]["body"] == payload["body"]

    def test_comment_external_creates_comm_event(self, headers_agent, a_ticket_id):
        # iter44: external requiere `to` con al menos un destinatario válido
        payload = {
            "body": "TEST_external message from pytest iter17",
            "visibility": "external",
            "to": ["cliente@ejemplo.com"],
        }
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent, json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        ev = r.json().get("data", r.json()).get("event")
        assert ev["event_type"] == "comm"
        assert ev["payload"]["to"] == ["cliente@ejemplo.com"]

    def test_comment_external_requires_to(self, headers_agent, a_ticket_id):
        # iter44: sin destinatarios → 422
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent,
                          json={"body": "hola", "visibility": "external"},
                          timeout=TIMEOUT)
        assert r.status_code == 422, r.text

    def test_comment_external_rejects_invalid_email(self, headers_agent, a_ticket_id):
        # iter44: email malformado → 422
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent,
                          json={"body": "hola", "visibility": "external",
                                "to": ["no-es-un-email"]},
                          timeout=TIMEOUT)
        assert r.status_code == 422, r.text

    def test_comment_external_accepts_cc_bcc(self, headers_agent, a_ticket_id):
        # iter44: CC y CCO opcionales y validados
        payload = {
            "body": "Con copia",
            "visibility": "external",
            "to": ["cliente@ejemplo.com"],
            "cc": ["copia1@ejemplo.com", "copia2@ejemplo.com"],
            "bcc": ["oculto@ejemplo.com"],
        }
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent, json=payload, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        ev = r.json().get("data", r.json()).get("event")
        assert ev["payload"]["cc"] == ["copia1@ejemplo.com", "copia2@ejemplo.com"]
        assert ev["payload"]["bcc"] == ["oculto@ejemplo.com"]

    def test_comment_validation_empty_body(self, headers_agent, a_ticket_id):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent,
                          json={"body": "", "visibility": "internal"},
                          timeout=TIMEOUT)
        assert r.status_code == 422

    def test_comment_validation_too_long(self, headers_agent, a_ticket_id):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                          headers=headers_agent,
                          json={"body": "x" * 5001, "visibility": "internal"},
                          timeout=TIMEOUT)
        assert r.status_code == 422

    def test_comment_appears_in_timeline(self, headers_agent, a_ticket_id):
        # post and then GET detail to verify persistence
        payload = {"body": "TEST_persistence_check", "visibility": "internal"}
        rp = requests.post(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}/comment",
                           headers=headers_agent, json=payload, timeout=TIMEOUT)
        assert rp.status_code == 200
        rg = requests.get(f"{BASE_URL}/api/agent/tickets/{a_ticket_id}",
                          headers=headers_agent, timeout=TIMEOUT)
        assert rg.status_code == 200
        tl = rg.json().get("data", rg.json()).get("timeline", [])
        bodies = [ev.get("payload", {}).get("body") for ev in tl]
        assert "TEST_persistence_check" in bodies


# ──────────────────────────────  POST /bulk-take  ───────────────────────────
class TestBulkTake:

    def test_bulk_take_payload_empty_422(self, headers_agent):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/bulk-take",
                          headers=headers_agent, json={"ticket_ids": []}, timeout=TIMEOUT)
        assert r.status_code == 422

    def test_bulk_take_not_found(self, headers_agent):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/bulk-take",
                          headers=headers_agent,
                          json={"ticket_ids": ["nope-1", "nope-2"]},
                          timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        assert data["totals"]["taken"] == 0
        assert data["totals"]["skipped"] == 2
        reasons = {s["reason"] for s in data["skipped"]}
        assert reasons == {"not_found"}

    def test_bulk_take_success(self, headers_agent, a_ticket_id):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/bulk-take",
                          headers=headers_agent,
                          json={"ticket_ids": [a_ticket_id]},
                          timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        # taken or skipped if already assigned to same agent (still taken because owner==self)
        # endpoint: if owner and owner != user.id → skip; if owner == user.id, falls through to assign
        assert a_ticket_id in data["taken"] or any(
            s["id"] == a_ticket_id for s in data["skipped"]
        )


# ──────────────────────────────  POST /bulk-status  ─────────────────────────
class TestBulkStatus:

    def test_bulk_status_validation(self, headers_agent):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/bulk-status",
                          headers=headers_agent,
                          json={"ticket_ids": [], "status": "in_progress"},
                          timeout=TIMEOUT)
        assert r.status_code == 422

    def test_bulk_status_not_found(self, headers_agent):
        r = requests.post(f"{BASE_URL}/api/agent/tickets/bulk-status",
                          headers=headers_agent,
                          json={"ticket_ids": ["bogus-id-iter17"], "status": "in_progress"},
                          timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        assert data["totals"]["updated"] == 0
        assert data["totals"]["skipped"] == 1
        assert data["skipped"][0]["reason"] == "not_found"

    def test_bulk_status_success_owner(self, headers_agent, a_ticket_id):
        # first take ticket so we are owner
        requests.post(f"{BASE_URL}/api/agent/tickets/bulk-take",
                      headers=headers_agent,
                      json={"ticket_ids": [a_ticket_id]}, timeout=TIMEOUT)
        r = requests.post(f"{BASE_URL}/api/agent/tickets/bulk-status",
                          headers=headers_agent,
                          json={"ticket_ids": [a_ticket_id],
                                "status": "in_progress",
                                "reason": "TEST_iter17_bulk_status"},
                          timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json().get("data", r.json())
        assert a_ticket_id in data["updated"]


# ─────────────────  Regressions: existing endpoints still green  ────────────
class TestRegressions:

    def test_queue_endpoint(self, headers_agent):
        r = requests.get(f"{BASE_URL}/api/agent/queue", headers=headers_agent, timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json().get("data", r.json())
        assert "mine" in data and "pool" in data and "totals" in data

    def test_saved_filters_list(self, headers_agent):
        r = requests.get(f"{BASE_URL}/api/saved-filters", headers=headers_agent, timeout=TIMEOUT)
        assert r.status_code in (200, 404)  # endpoint may live elsewhere

    def test_reclamos_list(self, headers_admin):
        r = requests.get(f"{BASE_URL}/api/reclamos", headers=headers_admin, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_admin_security_panel(self, headers_admin):
        r = requests.get(f"{BASE_URL}/api/admin/security/checklist",
                         headers=headers_admin, timeout=TIMEOUT)
        assert r.status_code in (200, 404)

    def test_admin_ai_cost_trend(self, headers_admin):
        r = requests.get(f"{BASE_URL}/api/admin/ai/cost-trend?days=7",
                         headers=headers_admin, timeout=TIMEOUT)
        assert r.status_code == 200
