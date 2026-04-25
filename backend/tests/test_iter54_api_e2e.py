"""E2E tests for iter54 (P09 Smart Autopause) via REACT_APP_BACKEND_URL.
Validates:
  - GET /api/ai-evaluation/config returns 5 new keys with defaults
  - PUT persists changes
  - PUT clamps out-of-bounds values
  - PUT can disable shadow_autopause_enabled
"""
import os
import requests
import pytest

# Read REACT_APP_BACKEND_URL from frontend/.env
def _load_backend_url():
    env_path = "/app/frontend/.env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not in frontend/.env")

BASE_URL = _load_backend_url()
LOGIN_EMAIL = "dev@me.mx"
LOGIN_PASSWORD = "LastMile2026"


@pytest.fixture(scope="module")
def auth_token():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Login failed {r.status_code}: {r.text[:200]}")
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if not token:
        # Maybe stored in cookie only — return session
        return {"_session": s}
    return {"Authorization": f"Bearer {token}", "_session": s}


def _client(auth_token):
    s = auth_token.get("_session") or requests.Session()
    headers = {k: v for k, v in auth_token.items() if k != "_session"}
    return s, headers


@pytest.fixture(scope="module")
def original_cfg(auth_token):
    """Snapshot original config; restore after tests run."""
    s, h = _client(auth_token)
    r = s.get(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    yield r.json()["config"]
    # Teardown — restore defaults for the 5 new keys
    s.put(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15, json={
        "shadow_autopause_enabled": True,
        "shadow_threshold_pct": 10,
        "shadow_window_minutes": 15,
        "shadow_min_events": 10,
        "shadow_autopause_minutes": 20,
    })


def test_get_config_includes_new_keys(auth_token, original_cfg):
    s, h = _client(auth_token)
    r = s.get(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15)
    assert r.status_code == 200
    body = r.json()
    cfg = body["config"]
    bounds = body["bounds"]
    # 5 new keys present
    for k in ["shadow_autopause_enabled", "shadow_threshold_pct",
              "shadow_window_minutes", "shadow_min_events",
              "shadow_autopause_minutes"]:
        assert k in cfg, f"missing key {k} in config"
    # Bounds present for the 4 numeric keys
    for k in ["shadow_threshold_pct", "shadow_window_minutes",
              "shadow_min_events", "shadow_autopause_minutes"]:
        assert k in bounds, f"missing bounds for {k}"
    # Defaults type checks
    assert isinstance(cfg["shadow_autopause_enabled"], bool)
    assert isinstance(cfg["shadow_threshold_pct"], int)


def test_put_persists_changes(auth_token):
    s, h = _client(auth_token)
    r = s.put(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15,
              json={"shadow_threshold_pct": 25, "shadow_min_events": 30})
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert cfg["shadow_threshold_pct"] == 25
    assert cfg["shadow_min_events"] == 30
    # Verify persistence via GET
    g = s.get(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15)
    cfg2 = g.json()["config"]
    assert cfg2["shadow_threshold_pct"] == 25
    assert cfg2["shadow_min_events"] == 30


def test_put_clamps_out_of_bounds(auth_token):
    s, h = _client(auth_token)
    # Above max → clamped to 100
    r = s.put(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15,
              json={"shadow_threshold_pct": 200, "shadow_window_minutes": 999})
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert cfg["shadow_threshold_pct"] == 100
    assert cfg["shadow_window_minutes"] == 60
    # Below min — Pydantic Optional[int] accepts negative; clamped to lower bound 1
    r2 = s.put(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15,
               json={"shadow_threshold_pct": -5})
    assert r2.status_code == 200, r2.text
    assert r2.json()["config"]["shadow_threshold_pct"] == 1


def test_put_can_disable_autopause(auth_token):
    s, h = _client(auth_token)
    r = s.put(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15,
              json={"shadow_autopause_enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["config"]["shadow_autopause_enabled"] is False
    # Re-enable
    r2 = s.put(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=15,
               json={"shadow_autopause_enabled": True})
    assert r2.json()["config"]["shadow_autopause_enabled"] is True


def test_health_still_ok():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("healthy", "degraded")
