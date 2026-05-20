"""Iter25 live smoke — verifica RBAC + listado de /api/platform/carriers en preview."""
from __future__ import annotations
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    "https://bootstrap-emergent.preview.emergentagent.com"


def _login(email: str, password: str = "Admin123!") -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    return body.get("data", {}).get("access_token") or body.get("access_token")


def test_no_auth_returns_401():
    r = requests.get(f"{BASE_URL}/api/platform/carriers", timeout=15)
    assert r.status_code == 401, f"expected 401 got {r.status_code}"


def test_admin_role_forbidden():
    tok = _login("admin@myexcellence.local")
    r = requests.get(f"{BASE_URL}/api/platform/carriers",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 403, f"admin should be 403, got {r.status_code}: {r.text[:200]}"


def test_root_dev_can_list():
    tok = _login("root@myexcellence.local")
    r = requests.get(f"{BASE_URL}/api/platform/carriers",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    data = r.json().get("data", {})
    assert "items" in data and "total" in data
    print(f"Platform carriers found: {data['total']} -> codes={[c.get('code') for c in data['items']]}")


def test_root_dev_get_single_returns_secret_set_bool():
    tok = _login("root@myexcellence.local")
    h = {"Authorization": f"Bearer {tok}"}
    # Try routal which the smoke test seeded
    r = requests.get(f"{BASE_URL}/api/platform/carriers/routal", headers=h, timeout=15)
    assert r.status_code == 200
    d = r.json()["data"]
    if d.get("configured"):
        assert "api_key" not in d, "raw secret leaked!"
        assert "api_key_ref" not in d
        assert "api_key_set" in d
        print(f"routal cfg: api_key_set={d.get('api_key_set')} base_url={d.get('base_url')} billing={d.get('billing_mode')}")


def test_root_dev_extra_forbid_rejects_project_ids():
    """Pydantic extra=forbid must reject project_ids at platform level."""
    tok = _login("root@myexcellence.local")
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    r = requests.put(f"{BASE_URL}/api/platform/carriers/routal",
                     headers=h,
                     json={"project_ids": ["x"]}, timeout=15)
    # FastAPI/Pydantic returns 422 when extra=forbid triggers
    assert r.status_code in (400, 422), f"expected 4xx, got {r.status_code}: {r.text[:200]}"
    print(f"extra=forbid blocked correctly with {r.status_code}")


def test_grant_404_on_missing_carrier():
    tok = _login("root@myexcellence.local")
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    fake_tenant = "00000000-0000-0000-0000-000000000000"
    r = requests.put(
        f"{BASE_URL}/api/platform/carriers/zzz_unknown_xyz/access/{fake_tenant}",
        headers=h, json={}, timeout=15)
    assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"
