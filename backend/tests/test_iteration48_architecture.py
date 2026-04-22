"""Iteration 48: Arquitectura Viva feature tests.

Covers:
- GET /api/architecture/snapshot (any authenticated user)
- POST /api/architecture/regenerate (RBAC + unchanged/regenerated paths)
- GET /api/architecture/history (paginated envelope)
- GET /api/architecture/snapshot/{id} (404 on missing)
- GET /api/architecture/diff (404 on missing ids)
- GET /api/architecture/changelog (paginated envelope)
- Stats contract thresholds
- Antipatterns contract
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("TEST_API_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")


# ── auth helpers ──────────────────────────────────────────────────
def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Login failed for {email}: {r.status_code} {r.text}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def dev_token():
    return _login("dev@me.mx", "LastMile2026")


@pytest.fixture(scope="module")
def coord_token():
    return _login("yael@me.mx", "LastMile2026")


@pytest.fixture(scope="module")
def agent_token():
    return _login("agente@me.mx", "LastMile2026")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ── SNAPSHOT ──────────────────────────────────────────────────────
class TestSnapshot:
    def test_snapshot_structure_as_dev(self, dev_token):
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot", headers=_h(dev_token), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        required = {"id", "generated_at", "content_hash", "stats", "collections",
                    "endpoints", "frontend_routes", "modules", "integrations", "antipatterns"}
        missing = required - set(data.keys())
        assert not missing, f"Missing keys: {missing}"
        # These may be dicts (keyed by name) or lists — scanner uses dicts for collections/endpoints/modules
        for k in ("collections", "endpoints", "frontend_routes", "modules", "integrations"):
            assert isinstance(data[k], (list, dict)), f"{k} type={type(data[k])}"
            assert len(data[k]) > 0, f"{k} is empty"
        assert isinstance(data["antipatterns"], list)  # always present
        assert isinstance(data["content_hash"], str) and len(data["content_hash"]) >= 8

    def test_snapshot_accessible_to_coordinator(self, coord_token):
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot", headers=_h(coord_token), timeout=30)
        assert r.status_code == 200

    def test_snapshot_accessible_to_agent(self, agent_token):
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot", headers=_h(agent_token), timeout=30)
        assert r.status_code == 200

    def test_stats_contract(self, dev_token):
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot", headers=_h(dev_token), timeout=30)
        assert r.status_code == 200
        stats = r.json().get("stats", {})
        # Contract thresholds per review request
        assert stats.get("collections", 0) >= 30, f"collections={stats.get('collections')}"
        assert stats.get("endpoints", 0) >= 150, f"endpoints={stats.get('endpoints')}"
        assert stats.get("frontend_routes", 0) >= 15, f"frontend_routes={stats.get('frontend_routes')}"
        assert stats.get("pages", 0) > 0
        assert stats.get("components", 0) > 0
        assert stats.get("modules", 0) >= 10, f"modules={stats.get('modules')}"
        assert stats.get("integrations", 0) >= 3

    def test_antipatterns_structure(self, dev_token):
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot", headers=_h(dev_token), timeout=30)
        anti = r.json().get("antipatterns", [])
        assert isinstance(anti, list)
        for entry in anti:
            assert "severity" in entry
            assert "type" in entry
            assert "description" in entry
            # must have either collection or path
            assert "collection" in entry or "path" in entry


# ── REGENERATE RBAC ───────────────────────────────────────────────
class TestRegenerateRBAC:
    def test_coordinator_forbidden(self, coord_token):
        r = requests.post(f"{BASE_URL}/api/architecture/regenerate", headers=_h(coord_token), timeout=60)
        assert r.status_code == 403, f"Expected 403 for coordinator, got {r.status_code}: {r.text}"

    def test_agent_forbidden(self, agent_token):
        r = requests.post(f"{BASE_URL}/api/architecture/regenerate", headers=_h(agent_token), timeout=60)
        assert r.status_code == 403, f"Expected 403 for agent, got {r.status_code}: {r.text}"

    def test_developer_allowed(self, dev_token):
        r = requests.post(f"{BASE_URL}/api/architecture/regenerate", headers=_h(dev_token), timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") in ("unchanged", "regenerated")
        assert "content_hash" in body
        if body["status"] == "regenerated":
            assert "snapshot_id" in body
            assert "diff" in body
            if body["diff"] is not None:
                assert "total_changes" in body["diff"]
                assert "is_significant" in body["diff"]
                assert "changes" in body["diff"]

    def test_regenerate_twice_unchanged(self, dev_token):
        # First regen
        r1 = requests.post(f"{BASE_URL}/api/architecture/regenerate", headers=_h(dev_token), timeout=60)
        assert r1.status_code == 200
        # Second immediate regen => code unchanged => status='unchanged'
        r2 = requests.post(f"{BASE_URL}/api/architecture/regenerate", headers=_h(dev_token), timeout=60)
        assert r2.status_code == 200
        assert r2.json().get("status") == "unchanged"


# ── HISTORY + CHANGELOG ───────────────────────────────────────────
class TestHistory:
    def test_history_envelope(self, dev_token):
        r = requests.get(f"{BASE_URL}/api/architecture/history", headers=_h(dev_token), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        # Standard pagination envelope
        for k in ("data", "total", "page", "pages"):
            assert k in body, f"Missing {k} in envelope: {list(body.keys())}"
        assert isinstance(body["data"], list)
        assert body["total"] >= 1  # at least 1 snapshot should exist by now

    def test_changelog_envelope(self, dev_token):
        r = requests.get(f"{BASE_URL}/api/architecture/changelog", headers=_h(dev_token), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("data", "total", "page", "pages"):
            assert k in body
        assert isinstance(body["data"], list)


# ── SNAPSHOT BY ID + DIFF ─────────────────────────────────────────
class TestSnapshotById:
    def test_get_existing_snapshot(self, dev_token):
        hist = requests.get(f"{BASE_URL}/api/architecture/history", headers=_h(dev_token), timeout=30).json()
        assert len(hist["data"]) >= 1
        sid = hist["data"][0]["id"]
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot/{sid}", headers=_h(dev_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == sid

    def test_get_missing_snapshot_404(self, dev_token):
        r = requests.get(f"{BASE_URL}/api/architecture/snapshot/nonexistent-id-xyz", headers=_h(dev_token), timeout=30)
        assert r.status_code == 404

    def test_diff_missing_ids_404(self, dev_token):
        r = requests.get(
            f"{BASE_URL}/api/architecture/diff?from_id=nope1&to_id=nope2",
            headers=_h(dev_token),
            timeout=30,
        )
        assert r.status_code == 404

    def test_diff_valid_ids(self, dev_token):
        hist = requests.get(f"{BASE_URL}/api/architecture/history", headers=_h(dev_token), timeout=30).json()
        if len(hist["data"]) < 2:
            pytest.skip("Need at least 2 snapshots for diff test")
        to_id = hist["data"][0]["id"]
        from_id = hist["data"][1]["id"]
        r = requests.get(
            f"{BASE_URL}/api/architecture/diff?from_id={from_id}&to_id={to_id}",
            headers=_h(dev_token),
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert "from" in body and "to" in body
        assert "total_changes" in body
        assert "is_significant" in body
        assert "changes" in body
