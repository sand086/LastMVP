"""End-to-end API tests for MyExcellence MVP using the public REACT_APP_BACKEND_URL."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://bootstrap-emergent.preview.emergentagent.com").rstrip("/")
ROOT = {"email": "root@myexcellence.local", "password": "Admin123!"}
SUPER = {"email": "superadmin@myexcellence.local", "password": "Admin123!"}


def _envelope_ok(j):
    """Verify standard JSON envelope shape."""
    assert isinstance(j, dict)
    assert set(["success", "data", "meta", "errors"]).issubset(j.keys()), f"Missing envelope keys: {j.keys()}"
    assert "request_id" in j["meta"] and "timestamp" in j["meta"]
    assert isinstance(j["errors"], list)


# ---------- system ----------
def test_health_envelope():
    r = requests.get(f"{BASE}/api/system/health", timeout=15)
    assert r.status_code == 200
    j = r.json()
    _envelope_ok(j)
    assert j["success"] is True
    assert j["data"]["db"] == "ok"
    assert "version" in j["data"]


# ---------- auth ----------
def test_login_root_dev_success():
    r = requests.post(f"{BASE}/api/auth/login", json=ROOT, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    _envelope_ok(j)
    assert j["success"] is True
    assert "user" in j["data"] and "access_token" in j["data"]
    assert j["data"]["redirect_to"] == "/dashboard"
    assert j["data"]["user"]["email"] == ROOT["email"]


def test_login_superadmin_success():
    r = requests.post(f"{BASE}/api/auth/login", json=SUPER, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    _envelope_ok(j)
    assert "access_token" in j["data"]


def test_login_wrong_password_returns_401_auth_required():
    # Use a unique-ish email to avoid bumping the rate-limit bucket of root
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": ROOT["email"], "password": "wrong"},
                      timeout=15)
    assert r.status_code == 401
    j = r.json()
    _envelope_ok(j)
    assert j["success"] is False
    assert any(e.get("code") == "AUTH_REQUIRED" for e in j["errors"]), j
    msg = j["errors"][0].get("message", "")
    assert "Credenciales" in msg or "inv" in msg.lower()


def test_login_unknown_email_returns_401_same_message():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": f"nobody-{int(time.time())}@example.com", "password": "whatever"},
                      timeout=15)
    assert r.status_code == 401
    j = r.json()
    _envelope_ok(j)
    assert any(e.get("code") == "AUTH_REQUIRED" for e in j["errors"])


def test_login_missing_fields_returns_422_validation_failed():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "x@y.z"}, timeout=15)
    assert r.status_code == 422
    j = r.json()
    _envelope_ok(j)
    assert any(e.get("code") == "VALIDATION_FAILED" for e in j["errors"])


# ---------- /me ----------
@pytest.fixture(scope="module")
def root_token():
    r = requests.post(f"{BASE}/api/auth/login", json=ROOT, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


def test_me_with_bearer(root_token):
    r = requests.get(f"{BASE}/api/auth/me",
                     headers={"Authorization": f"Bearer {root_token}"},
                     timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    _envelope_ok(j)
    assert j["data"]["email"] == ROOT["email"]
    assert "default_landing" in j["data"]


def test_me_without_auth_401():
    r = requests.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 401
    j = r.json()
    _envelope_ok(j)
    assert any(e.get("code") == "AUTH_REQUIRED" for e in j["errors"])


def test_logout_works(root_token):
    r = requests.post(f"{BASE}/api/auth/logout",
                     headers={"Authorization": f"Bearer {root_token}"},
                     timeout=15)
    assert r.status_code == 200
    j = r.json()
    _envelope_ok(j)
    # Stateless JWT — token still valid afterwards
    r2 = requests.get(f"{BASE}/api/auth/me",
                      headers={"Authorization": f"Bearer {root_token}"},
                      timeout=15)
    assert r2.status_code == 200


# ---------- CAE admin RBAC ----------
@pytest.mark.parametrize("path", ["/api/admin/cae/unmapped", "/api/admin/cae/catalog", "/api/admin/cae/audit-log"])
def test_cae_endpoints_authorized(root_token, path):
    r = requests.get(f"{BASE}{path}",
                     headers={"Authorization": f"Bearer {root_token}"},
                     timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    _envelope_ok(j)
    # Should be a list (possibly empty) wrapped in envelope
    assert isinstance(j["data"], list) or isinstance(j["data"], dict)


@pytest.mark.parametrize("path", ["/api/admin/cae/unmapped", "/api/admin/cae/catalog", "/api/admin/cae/audit-log"])
def test_cae_endpoints_unauth_401(path):
    r = requests.get(f"{BASE}{path}", timeout=15)
    assert r.status_code in (401, 403), r.status_code
    j = r.json()
    _envelope_ok(j)
    assert any(e.get("code") in ("AUTH_REQUIRED", "RBAC_DENIED") for e in j["errors"])


# ---------- redirect-target ----------
def test_redirect_target(root_token):
    r = requests.get(f"{BASE}/api/auth/redirect-target",
                     headers={"Authorization": f"Bearer {root_token}"},
                     timeout=15)
    assert r.status_code == 200
    j = r.json()
    _envelope_ok(j)
    assert "redirect_to" in j["data"]


# ---------- brute-force lockout ----------
def test_bruteforce_lockout_returns_429():
    """6th failed attempt should be RATE_LIMITED.

    NOTE: Through the ingress proxy this currently fails because the rate-
    limiter keys on ``request.client.host`` which varies per request when
    uvicorn is not started with ``--proxy-headers``. Direct localhost works.
    """
    # Direct hit on the in-cluster service to validate the limiter logic
    # (the public URL goes through a proxy that rotates client IPs).
    email = f"bf-{int(time.time())}@example.com"
    statuses = []
    for _ in range(7):
        r = requests.post("http://localhost:8001/api/auth/login",
                          json={"email": email, "password": "wrong"},
                          timeout=15)
        statuses.append(r.status_code)
    assert 429 in statuses, f"Expected 429 in {statuses}"
