"""
E2E backend tests for Iteration 55 Routal Integrations.
Tests against live preview backend with real auth.
"""
import os
import hmac
import hashlib
import json
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEV = {"email": "dev@me.mx", "password": "LastMile2026"}
COORD = {"email": "yael@me.mx", "password": "LastMile2026"}
AGENT = {"email": "agente@me.mx", "password": "LastMile2026"}


def login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    return token, r.cookies


@pytest.fixture(scope="module")
def dev_token():
    t, _ = login(DEV)
    return t


@pytest.fixture(scope="module")
def coord_token():
    t, _ = login(COORD)
    return t


@pytest.fixture(scope="module")
def agent_token():
    t, _ = login(AGENT)
    return t


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def test_client_id(dev_token):
    """Pick an existing client. Use Cubbo if available."""
    r = requests.get(f"{API}/clients", headers=auth_headers(dev_token), timeout=15)
    assert r.status_code == 200, f"GET /api/clients failed: {r.status_code} {r.text}"
    data = r.json()
    clients = data.get("data") if isinstance(data, dict) else data
    assert clients and len(clients) > 0
    # prefer cubbo
    for c in clients:
        if "cubbo" in (c.get("name") or "").lower():
            return c["id"]
    return clients[0]["id"]


# -----------------------
# RBAC tests
# -----------------------
def test_health():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200


def test_rbac_agent_forbidden(agent_token):
    r = requests.get(f"{API}/integrations", headers=auth_headers(agent_token), timeout=15)
    assert r.status_code == 403


def test_rbac_coordinator_forbidden(coord_token):
    r = requests.get(f"{API}/integrations", headers=auth_headers(coord_token), timeout=15)
    assert r.status_code == 403


def test_rbac_developer_allowed(dev_token):
    r = requests.get(f"{API}/integrations", headers=auth_headers(dev_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    # Ensure no encrypted blob exposed
    for it in data["data"]:
        assert "credentials_encrypted" not in it
        assert "credentials" not in it  # raw creds never exposed in list


# -----------------------
# CRUD lifecycle
# -----------------------
WEBHOOK_SECRET = "whsec_e2e_test_iter55"
FAKE_API_KEY = "sk_fake_e2e_iter55_xxxxxxxxxxxx"
PROJECT_ID = "proj_e2e_iter55"


def test_upsert_and_persistence(dev_token, test_client_id):
    payload = {
        "integration_type": "routal",
        "credentials": {
            "routal_api_key": FAKE_API_KEY,
            "routal_project_id": PROJECT_ID,
            "routal_webhook_secret": WEBHOOK_SECRET,
        },
        "config": {"auto_create_journeys": True, "sync_drivers": True},
        "status": "inactive",
    }
    r = requests.post(
        f"{API}/integrations/{test_client_id}",
        headers=auth_headers(dev_token),
        json=payload,
        timeout=15,
    )
    assert r.status_code in (200, 201), f"upsert failed: {r.status_code} {r.text}"
    body = r.json()
    # Never expose raw API key
    serialized = json.dumps(body)
    assert FAKE_API_KEY not in serialized
    assert WEBHOOK_SECRET not in serialized
    assert "credentials_encrypted" not in body
    # Verify summary marks key
    summary = body.get("credentials_summary") or {}
    assert summary.get("has_api_key") is True
    assert summary.get("has_webhook_secret") is True
    assert summary.get("routal_project_id") == PROJECT_ID

    # GET to verify persistence
    g = requests.get(f"{API}/integrations/{test_client_id}", headers=auth_headers(dev_token), timeout=15)
    assert g.status_code == 200
    gdoc = g.json()
    gser = json.dumps(gdoc)
    assert FAKE_API_KEY not in gser
    assert WEBHOOK_SECRET not in gser
    s2 = gdoc.get("credentials_summary") or {}
    assert s2.get("has_api_key") is True
    assert s2.get("routal_project_id") == PROJECT_ID


def test_test_endpoint_graceful(dev_token, test_client_id):
    """Routal test must return ok=false gracefully with fake key."""
    r = requests.post(
        f"{API}/integrations/{test_client_id}/test",
        headers=auth_headers(dev_token),
        timeout=30,
    )
    assert r.status_code == 200, f"test endpoint crashed: {r.status_code} {r.text}"
    body = r.json()
    assert "ok" in body
    assert body["ok"] is False
    assert "error" in body
    # Should be auth/connection error - not a crash
    assert "latency_ms" in body


def test_status_patch_active(dev_token, test_client_id):
    r = requests.patch(
        f"{API}/integrations/{test_client_id}/status",
        headers=auth_headers(dev_token),
        json={"status": "active"},
        timeout=15,
    )
    assert r.status_code == 200, f"status patch failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("status") == "active"


# -----------------------
# Webhook tests
# -----------------------
def test_webhook_status_endpoint(dev_token, test_client_id):
    r = requests.get(
        f"{API}/webhooks/routal/{test_client_id}/status",
        headers=auth_headers(dev_token),
        timeout=15,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    for k in ("pending", "failed", "last_event_at", "webhook_url"):
        assert k in body, f"missing key {k}"
    assert isinstance(body["pending"], int)
    assert isinstance(body["failed"], int)
    assert "/api/webhooks/routal/" in body["webhook_url"]


def test_webhook_invalid_hmac_rejected(test_client_id):
    """Invalid HMAC signature must be rejected (401)."""
    body = json.dumps({"event": "plan.created", "id": "evt_invalid_e2e"}).encode("utf-8")
    r = requests.post(
        f"{API}/webhooks/routal/{test_client_id}",
        data=body,
        headers={"X-Routal-Signature": "deadbeef" * 8, "Content-Type": "application/json"},
        timeout=15,
    )
    # Must be unauthorized (no auth required, but HMAC must be valid)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code} {r.text}"


def test_webhook_valid_hmac_accepted(test_client_id):
    """Valid HMAC signature with our configured secret must be accepted."""
    event_id = f"evt_e2e_{int(time.time())}"
    payload = {"event": "plan.created", "id": event_id, "data": {"foo": "bar"}}
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = requests.post(
        f"{API}/webhooks/routal/{test_client_id}",
        data=body,
        headers={
            "X-Routal-Signature": sig,
            "X-Routal-Event-Id": event_id,
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    assert r.status_code in (200, 202), f"expected 200/202, got {r.status_code} {r.text}"
    body_resp = r.json()
    assert body_resp.get("ok") is True


def test_webhook_idempotency(test_client_id):
    """Resubmitting same event must dedup."""
    event_id = f"evt_idem_{int(time.time())}"
    payload = {"event": "plan.created", "id": event_id}
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "X-Routal-Signature": sig,
        "X-Routal-Event-Id": event_id,
        "Content-Type": "application/json",
    }
    r1 = requests.post(f"{API}/webhooks/routal/{test_client_id}", data=body, headers=headers, timeout=15)
    assert r1.status_code in (200, 202)
    r2 = requests.post(f"{API}/webhooks/routal/{test_client_id}", data=body, headers=headers, timeout=15)
    assert r2.status_code in (200, 202)
    assert r2.json().get("duplicate") is True


# -----------------------
# Cleanup
# -----------------------
def test_zz_delete_integration(dev_token, test_client_id):
    r = requests.delete(
        f"{API}/integrations/{test_client_id}",
        headers=auth_headers(dev_token),
        timeout=15,
    )
    assert r.status_code == 200, f"delete failed: {r.status_code} {r.text}"
    # Soft delete: status -> inactive, credentials cleared. Doc may still exist.
    g = requests.get(f"{API}/integrations/{test_client_id}", headers=auth_headers(dev_token), timeout=15)
    if g.status_code == 200:
        gdoc = g.json()
        s = gdoc.get("credentials_summary") or {}
        assert s.get("has_api_key") in (False, None), "Soft delete should clear api_key"
        assert s.get("has_webhook_secret") in (False, None), "Soft delete should clear webhook_secret"
        assert gdoc.get("status") == "inactive"
    else:
        assert g.status_code == 404
