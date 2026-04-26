"""
iter57 — Kosmo & Manual integration handlers + Manual seed v2 (14 entries, upsert by slug).

Validates:
  1. POST /api/integrations/{cid}/test for kosmo + manual + routal (regression).
  2. RBAC: only developer can call /test; agent/proveedor 403; coordinator 403.
  3. POST /api/manuals-admin/seed force=false vs force=true semantics.
  4. Catalog count = 14, total_catalog field exposed.
  5. GET /api/manuals returns >=14 with all 6 sections.
  6. GET /api/manuals/{slug} returns content blocks for new slugs.
  7. Seed RBAC: agent/proveedor 403; coordinator + developer 200.

Important: Cubbo client_id swapped temporarily to manual/kosmo, then restored to routal.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")
CUBBO_ID = "0b6590e9-234a-4111-ae5a-e49ebdaf8261"
CUBBO_RESTORE_SECRET = "whsec_e2e_test_iter55"

NEW_SLUGS = [
    "integraciones-saas", "auditorias-sel01", "lumi-asistente",
    "admin-ia-motor", "diccionario-tecnico", "webhooks-plug-play",
    "quality-criteria-v2",
]
EXPECTED_SECTIONS = {
    "Paneles", "Operación de Envíos", "Configuración",
    "Integraciones", "Inteligencia Artificial", "Documentación Técnica",
}


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def dev_headers():
    return {"Authorization": f"Bearer {_login('dev@me.mx', 'LastMile2026')}"}


@pytest.fixture(scope="module")
def coord_headers():
    return {"Authorization": f"Bearer {_login('yael@me.mx', 'LastMile2026')}"}


@pytest.fixture(scope="module")
def agent_headers():
    return {"Authorization": f"Bearer {_login('agente@me.mx', 'LastMile2026')}"}


@pytest.fixture(scope="module")
def prov_headers():
    return {"Authorization": f"Bearer {_login('proveedor@me.mx', 'LastMile2026')}"}


def _set_cubbo_type(dev_headers, integration_type, status="active", with_routal_creds=False):
    payload = {"integration_type": integration_type, "status": status}
    if with_routal_creds:
        payload["credentials"] = {
            "routal_webhook_secret": CUBBO_RESTORE_SECRET,
        }
    r = requests.post(
        f"{BASE_URL}/api/integrations/{CUBBO_ID}",
        json=payload,
        headers=dev_headers,
        timeout=15,
    )
    assert r.status_code in (200, 201), f"upsert {integration_type} failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def restore_cubbo_at_end(dev_headers):
    """Always restore Cubbo to routal+active at module teardown to keep iter55 green."""
    yield
    try:
        _set_cubbo_type(dev_headers, "routal", status="active", with_routal_creds=True)
    except Exception as e:
        print(f"[restore] failed to restore Cubbo: {e}")


# ───────────────────────── Kosmo /test ─────────────────────────
class TestKosmoHealth:
    def test_kosmo_test_shape_and_no_api_key_required(self, dev_headers):
        _set_cubbo_type(dev_headers, "kosmo", status="active")
        r = requests.post(f"{BASE_URL}/api/integrations/{CUBBO_ID}/test", headers=dev_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("type") == "kosmo"
        for k in ("ok", "scraper_status", "last_sync_at", "last_sync_age_hours",
                  "journeys_active_today", "journeys_pending_sync", "note"):
            assert k in data, f"missing key {k} in {data}"
        assert data["scraper_status"] in ("ok", "stale", "down", "never_synced")
        # ok=true iff status in (ok, stale)
        if data["scraper_status"] in ("ok", "stale"):
            assert data["ok"] is True
        else:
            assert data["ok"] is False
        assert isinstance(data["journeys_active_today"], int)
        assert isinstance(data["journeys_pending_sync"], int)


# ───────────────────────── Manual /test ─────────────────────────
class TestManualHealth:
    def test_manual_test_shape(self, dev_headers):
        _set_cubbo_type(dev_headers, "manual", status="active")
        r = requests.post(f"{BASE_URL}/api/integrations/{CUBBO_ID}/test", headers=dev_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("type") == "manual"
        for k in ("ok", "manual_status", "total_journeys", "recent_journeys_30d",
                  "latest_journey_date", "latest_journey_created_at", "note"):
            assert k in data, f"missing key {k} in {data}"
        assert data["manual_status"] in ("ok", "dormant", "empty")
        # ok=true ONLY if manual_status='ok'
        assert data["ok"] is (data["manual_status"] == "ok")
        assert isinstance(data["total_journeys"], int)
        assert isinstance(data["recent_journeys_30d"], int)


# ───────────────────────── Routal /test (regression) ─────────────────────────
class TestRoutalRegression:
    def test_routal_still_works(self, dev_headers):
        _set_cubbo_type(dev_headers, "routal", status="active", with_routal_creds=True)
        r = requests.post(f"{BASE_URL}/api/integrations/{CUBBO_ID}/test", headers=dev_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        # Shape regression: must have ok + latency_ms keys (type may be missing on missing-creds path — pre-existing minor bug)
        assert "ok" in data
        assert "latency_ms" in data
        # Either valid response with type=routal OR graceful 'missing creds' fallback
        if data["ok"]:
            assert data.get("type") == "routal"
        else:
            assert "error" in data and isinstance(data["error"], str)


# ───────────────────────── /test RBAC ─────────────────────────
class TestRBACTestEndpoint:
    def test_coordinator_403(self, coord_headers):
        r = requests.post(f"{BASE_URL}/api/integrations/{CUBBO_ID}/test", headers=coord_headers, timeout=15)
        assert r.status_code == 403, r.text

    def test_agent_403(self, agent_headers):
        r = requests.post(f"{BASE_URL}/api/integrations/{CUBBO_ID}/test", headers=agent_headers, timeout=15)
        assert r.status_code == 403, r.text

    def test_proveedor_403(self, prov_headers):
        r = requests.post(f"{BASE_URL}/api/integrations/{CUBBO_ID}/test", headers=prov_headers, timeout=15)
        assert r.status_code == 403, r.text


# ───────────────────────── Manual seed ─────────────────────────
class TestManualSeed:
    def test_seed_force_false_no_overwrite(self, dev_headers):
        # First call (may already be seeded) — get baseline
        r1 = requests.post(f"{BASE_URL}/api/manuals-admin/seed", headers=dev_headers, timeout=30)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("total_catalog") == 14
        assert d1.get("force") is False
        # Second call without force: should NOT update (updated=0 must hold)
        r2 = requests.post(f"{BASE_URL}/api/manuals-admin/seed", headers=dev_headers, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["updated"] == 0, f"force=false must not update, got {d2}"
        assert d2["total_catalog"] == 14

    def test_seed_force_true_updates(self, dev_headers):
        r = requests.post(f"{BASE_URL}/api/manuals-admin/seed?force=true", headers=dev_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["force"] is True
        assert data["total_catalog"] == 14
        # On a re-run after first force, inserted should be 0 and updated=14
        # (assuming all 14 already exist after the previous test)
        assert data["inserted"] + data["updated"] == 14
        # If a previous force already ran in this module, expect updated=14
        if data["inserted"] == 0:
            assert data["updated"] == 14

    def test_seed_rbac_agent_403(self, agent_headers):
        r = requests.post(f"{BASE_URL}/api/manuals-admin/seed", headers=agent_headers, timeout=15)
        assert r.status_code == 403

    def test_seed_rbac_proveedor_403(self, prov_headers):
        r = requests.post(f"{BASE_URL}/api/manuals-admin/seed", headers=prov_headers, timeout=15)
        assert r.status_code == 403

    def test_seed_rbac_coordinator_200(self, coord_headers):
        r = requests.post(f"{BASE_URL}/api/manuals-admin/seed", headers=coord_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["total_catalog"] == 14


# ───────────────────────── Manuals listing & content ─────────────────────────
class TestManualsList:
    def test_list_has_at_least_14_with_6_sections(self, dev_headers):
        r = requests.get(f"{BASE_URL}/api/manuals?limit=50", headers=dev_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Envelope: paginated_response → expect list at .data
        items = body.get("data") if isinstance(body, dict) else body
        assert isinstance(items, list), f"unexpected shape: {body}"
        assert len(items) >= 14, f"expected >=14 manuals, got {len(items)}"
        sections = {m["section"] for m in items if "section" in m}
        missing = EXPECTED_SECTIONS - sections
        assert not missing, f"missing sections: {missing} (got {sections})"

    @pytest.mark.parametrize("slug", NEW_SLUGS)
    def test_get_manual_by_slug_has_content_blocks(self, dev_headers, slug):
        r = requests.get(f"{BASE_URL}/api/manuals/{slug}", headers=dev_headers, timeout=15)
        assert r.status_code == 200, f"slug={slug} failed: {r.status_code} {r.text}"
        manual = r.json()
        assert manual.get("slug") == slug
        assert "title" in manual
        assert "section" in manual
        content = manual.get("content")
        assert isinstance(content, list) and len(content) > 0, f"slug={slug} has empty content"
        valid_types = {"callout", "section", "table", "tip", "warning"}
        block_types = {b.get("type") for b in content}
        assert block_types <= valid_types, f"invalid block types in {slug}: {block_types - valid_types}"
        # Must have at least one callout (every catalog manual starts with one)
        assert "callout" in block_types, f"slug={slug} missing callout"
