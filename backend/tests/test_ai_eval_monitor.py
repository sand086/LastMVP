"""
Tests for AI Evaluation Monitor de Procesos (Iteration 43).
Covers: list/get/create/cancel jobs, role-based auth, SSE stream.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://lastmile-mvp.preview.emergentagent.com"
API = f"{BASE_URL}/api"

DEV = {"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
COORD = {"email": "yael@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
AGENT = {"email": "agente@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
PROV = {"email": "proveedor@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"Login {creds['email']} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def dev_session():
    return _login(DEV)


@pytest.fixture(scope="module")
def coord_session():
    return _login(COORD)


@pytest.fixture(scope="module")
def agent_session():
    return _login(AGENT)


@pytest.fixture(scope="module")
def prov_session():
    return _login(PROV)


# ---------- AUTH ----------
class TestAuth:
    def test_unauth_list_jobs_401(self):
        r = requests.get(f"{API}/ai-evaluation/jobs", timeout=15)
        assert r.status_code == 401

    def test_agent_cannot_create_manual_job_403(self, agent_session):
        r = agent_session.post(f"{API}/ai-evaluation/jobs/manual", json={"route_id": "fake-id"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_agent_can_list_jobs(self, agent_session):
        # list_jobs only requires get_current_user, not role
        r = agent_session.get(f"{API}/ai-evaluation/jobs")
        assert r.status_code == 200

    def test_proveedor_cannot_create_manual_job_403(self, prov_session):
        r = prov_session.post(f"{API}/ai-evaluation/jobs/manual", json={"route_id": "fake-id"})
        assert r.status_code == 403

    def test_agent_cannot_cancel_job_403(self, agent_session):
        r = agent_session.delete(f"{API}/ai-evaluation/jobs/some-fake-id")
        assert r.status_code == 403


# ---------- LIST / GET ----------
class TestListAndGet:
    def test_list_jobs_structure(self, dev_session):
        r = dev_session.get(f"{API}/ai-evaluation/jobs", params={"page": 1, "limit": 25})
        assert r.status_code == 200
        data = r.json()
        assert "data" in data and "total" in data and "page" in data and "pages" in data
        assert isinstance(data["data"], list)
        assert data["page"] == 1

    def test_list_jobs_with_filters(self, dev_session):
        r = dev_session.get(f"{API}/ai-evaluation/jobs", params={"status": "all", "triggered_by": "all"})
        assert r.status_code == 200

    def test_list_jobs_status_filter_specific(self, dev_session):
        r = dev_session.get(f"{API}/ai-evaluation/jobs", params={"status": "Evaluada"})
        assert r.status_code == 200
        for j in r.json()["data"]:
            assert j["status"] == "Evaluada"

    def test_list_jobs_date_filters(self, dev_session):
        r = dev_session.get(
            f"{API}/ai-evaluation/jobs",
            params={"fecha_desde": "2025-01-01", "fecha_hasta": "2030-12-31"},
        )
        assert r.status_code == 200

    def test_get_job_404(self, dev_session):
        r = dev_session.get(f"{API}/ai-evaluation/jobs/non-existent-id-xyz")
        assert r.status_code == 404
        assert "no encontrado" in r.json().get("detail", "").lower()


# ---------- CREATE ----------
class TestCreateManual:
    def test_create_manual_invalid_route_404(self, dev_session):
        r = dev_session.post(
            f"{API}/ai-evaluation/jobs/manual",
            json={"route_id": "definitely-not-a-route-uuid"},
        )
        assert r.status_code == 404
        assert "no encontrada" in r.json().get("detail", "").lower()

    def test_create_manual_with_real_route(self, dev_session):
        # Find a journey
        jr = dev_session.get(f"{API}/journeys", params={"limit": 1})
        if jr.status_code != 200:
            pytest.skip(f"Cannot list journeys: {jr.status_code}")
        body = jr.json()
        items = body.get("data") or body.get("items") or body if isinstance(body, list) else body.get("data", [])
        if not items:
            pytest.skip("No journeys available to enqueue")
        route_id = items[0].get("id")
        if not route_id:
            pytest.skip(f"Journey has no id field: {items[0]}")
        r = dev_session.post(
            f"{API}/ai-evaluation/jobs/manual",
            json={"route_id": route_id, "force_reevaluate": False},
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        # Either job created or "no eligible guides" message
        assert "total" in data
        if data.get("job_id"):
            # Verify job visible via GET
            jid = data["job_id"]
            gr = dev_session.get(f"{API}/ai-evaluation/jobs/{jid}")
            assert gr.status_code == 200
            got = gr.json()
            assert got["job_id"] == jid
            assert got["route_id"] == route_id
            assert "guias_detail" in got

    def test_create_manual_guia_not_found_404(self, dev_session):
        r = dev_session.post(
            f"{API}/ai-evaluation/jobs/manual/guia",
            json={"guia_id": "non-existent-guia-xyz"},
        )
        assert r.status_code == 404
        assert "guia no encontrada" in r.json().get("detail", "").lower()

    def test_create_manual_guia_ineligible_status_400(self, dev_session):
        # Find a package with status != delivered/failed
        pr = dev_session.get(f"{API}/packages/search", params={"q": ""})
        if pr.status_code != 200:
            pytest.skip(f"Cannot search packages: {pr.status_code}")
        pkgs = pr.json()
        pkgs = pkgs if isinstance(pkgs, list) else pkgs.get("data", [])
        ineligible = next(
            (p for p in pkgs if p.get("status") not in ("delivered", "failed") and p.get("id")),
            None,
        )
        if not ineligible:
            pytest.skip("No ineligible package found")
        r = dev_session.post(
            f"{API}/ai-evaluation/jobs/manual/guia",
            json={"guia_id": ineligible["id"]},
        )
        assert r.status_code == 400
        assert "no es elegible" in r.json().get("detail", "").lower()


# ---------- CANCEL ----------
class TestCancel:
    def test_cancel_nonexistent_400(self, dev_session):
        r = dev_session.delete(f"{API}/ai-evaluation/jobs/non-existent-id")
        # Job not found or not En_Cola → 400
        assert r.status_code == 400


# ---------- SSE ----------
class TestSSE:
    def test_sse_content_type(self, dev_session):
        r = dev_session.get(
            f"{API}/ai-evaluation/jobs/fake-id/stream",
            stream=True,
            timeout=5,
        )
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/event-stream" in ct, f"Expected SSE content-type, got {ct}"
        r.close()


# ---------- REGRESSION ----------
class TestRegression:
    def test_login_sets_cookie(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=DEV)
        assert r.status_code == 200
        assert "lm_access_token" in s.cookies, f"Cookies: {list(s.cookies.keys())}"

    def test_logout(self, dev_session):
        s = _login(DEV)
        r = s.post(f"{API}/auth/logout")
        assert r.status_code == 200

    def test_me_endpoint(self, dev_session):
        r = dev_session.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json().get("email") == DEV["email"]

    def test_journeys_accessible(self, dev_session):
        r = dev_session.get(f"{API}/journeys", params={"limit": 5})
        assert r.status_code == 200

    def test_health(self):
        r = requests.get(f"{API}/health")
        assert r.status_code == 200
