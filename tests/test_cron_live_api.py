"""Live API tests against the public REACT_APP_BACKEND_URL — PROMPT 11.5 cron endpoints.

These tests hit the actual running supervisor-managed backend through the
ingress URL. They are kept separate from the unit suite because they depend
on the live scheduler being started (CRON_ENABLED=1).
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend/.env
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")


def _login(email: str, password: str = "Admin123!") -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    token = (body.get("data") or {}).get("access_token") or body.get("access_token")
    assert token, f"no token in login response: {body}"
    return token


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login('admin@myexcellence.local')}"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login('agent@myexcellence.local')}"}


def test_cron_status_running(admin_headers):
    r = requests.get(f"{BASE_URL}/api/admin/cron/status", headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["running"] is True, f"scheduler not running: {data}"
    assert data["enabled_env"] is True
    job_ids = sorted(j["id"] for j in data["jobs"])
    # Core jobs always present; webhook_worker added in iter13, claim_sla_scan
    # in iter12. Use subset assertion so future additions don't flake the test.
    expected_subset = {"daily_summary", "inactivity_scan", "pulling", "sla_scan"}
    assert expected_subset.issubset(set(job_ids)), data
    for j in data["jobs"]:
        assert j["next_run_time"] is not None
        assert j["trigger"]


def test_cron_status_rbac_blocks_agent(agent_headers):
    r = requests.get(f"{BASE_URL}/api/admin/cron/status", headers=agent_headers, timeout=10)
    assert r.status_code == 403, r.text


def test_cron_run_sla(admin_headers):
    r = requests.post(f"{BASE_URL}/api/admin/cron/run/sla", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["job"] == "sla"
    assert "breaches" in body and "notified" in body


def test_cron_run_inactivity(admin_headers):
    r = requests.post(f"{BASE_URL}/api/admin/cron/run/inactivity", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["job"] == "inactivity"
    assert "inactive_agents" in body and "notified" in body


def test_cron_run_pulling(admin_headers):
    r = requests.post(f"{BASE_URL}/api/admin/cron/run/pulling", headers=admin_headers, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["job"] == "pulling"
    assert "clients" in body and "results" in body
    # All client invocations succeeded (stub never throws)
    assert all(rr.get("ok") for rr in body["results"]) or body["clients"] == 0


def test_cron_run_daily_summary(admin_headers):
    r = requests.post(f"{BASE_URL}/api/admin/cron/run/daily_summary",
                      headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["job"] == "daily_summary"
    # Real Resend in testing mode: supervisor email NOT verified → sent=False
    # OR sent=True if mocked. Both acceptable; we just need a clean response shape.
    assert "sent" in body and "metrics" in body
    metrics = body["metrics"]
    for k in ["open_tickets", "resolved_today", "backlog_aged_24h",
              "automations_today", "sla_breaches_today",
              "agents_inactive_today", "claims_dictamen_aging"]:
        assert k in metrics
    if not body["sent"]:
        # Either no supervisor (no_recipient) or Resend rejected the recipient
        assert body.get("reason"), body


def test_cron_run_unknown_job(admin_headers):
    r = requests.post(f"{BASE_URL}/api/admin/cron/run/bogus",
                      headers=admin_headers, timeout=10)
    # Path Literal validation → 422
    assert r.status_code in (404, 422), r.text
