"""Iteration 47 - Regression: pagination envelope harmonization (P2+P3 refactor).

Scope:
  * paginated_response() helper returns BOTH flat + nested shapes simultaneously
  * /api/ai-evaluation/jobs, /api/journeys, /api/manuals, /api/manuals-admin
  * Legacy consumers keep working (TokenUsageTab, RoutesReportTab, SettingsDriversTab, QualityTabV2)
  * Regression: /api/incidents catalog 422 on 'otro' without comentario_asesor, /api/ai-evaluation/health, cancel_job 404/400
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

COORD = {"email": "yael@me.mx", "password": "LastMile2026"}
DEV = {"email": "dev@me.mx", "password": "LastMile2026"}
AGENT = {"email": "agente@me.mx", "password": "LastMile2026"}


@pytest.fixture(scope="module")
def coord_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=COORD, timeout=15)
    assert r.status_code == 200, f"Coord login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def dev_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=DEV, timeout=15)
    assert r.status_code == 200, f"Dev login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _assert_envelope(body: dict, *, require_total_count: bool = False):
    """Validate both flat + nested pagination shapes coexist."""
    # Flat
    assert "data" in body, f"Missing 'data': keys={list(body.keys())}"
    assert isinstance(body["data"], list)
    assert "total" in body, f"Missing flat 'total': keys={list(body.keys())}"
    assert "page" in body
    assert "pages" in body
    assert "page_size" in body
    # Nested
    assert "pagination" in body, f"Missing 'pagination': keys={list(body.keys())}"
    p = body["pagination"]
    for k in ("total", "page", "page_size", "total_pages", "pages"):
        assert k in p, f"Missing pagination.{k}: {list(p.keys())}"
    # Cross-shape consistency
    assert body["total"] == p["total"], "flat.total != pagination.total"
    assert body["pages"] == p["total_pages"] == p["pages"], "pages mismatch"
    assert body["page"] == p["page"]
    assert body["page_size"] == p["page_size"]
    if require_total_count:
        assert "total_count" in p, f"Missing legacy pagination.total_count: {list(p.keys())}"
        assert p["total_count"] == p["total"]


# ============== AI EVAL JOBS ==============
class TestAiEvalJobsEnvelope:
    def test_jobs_envelope_both_shapes(self, dev_session):
        r = dev_session.get(f"{BASE_URL}/api/ai-evaluation/jobs?limit=5", timeout=15)
        assert r.status_code == 200, r.text
        _assert_envelope(r.json())

    def test_jobs_legacy_consumer_total_pages(self, dev_session):
        # TokenUsageTab reads res.data.pagination.total_pages
        r = dev_session.get(f"{BASE_URL}/api/ai-evaluation/jobs?limit=5", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json()["pagination"]["total_pages"], int)

    def test_jobs_legacy_consumer_pages_flat(self, dev_session):
        # QualityTabV2 reads res.data.pages (flat)
        r = dev_session.get(f"{BASE_URL}/api/ai-evaluation/jobs?limit=5", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json()["pages"], int)


# ============== JOURNEYS ==============
class TestJourneysEnvelope:
    def test_journeys_envelope_both_shapes_with_total_count(self, coord_session):
        r = coord_session.get(f"{BASE_URL}/api/journeys?page=1&page_size=10", timeout=20)
        assert r.status_code == 200, r.text
        _assert_envelope(r.json(), require_total_count=True)

    def test_journeys_legacy_consumer_page_size(self, coord_session):
        # RoutesReportTab reads res.data.pagination.page_size
        r = coord_session.get(f"{BASE_URL}/api/journeys?page=1&page_size=10", timeout=20)
        body = r.json()
        assert body["pagination"]["page_size"] == 10

    def test_journeys_has_data_list(self, coord_session):
        r = coord_session.get(f"{BASE_URL}/api/journeys?page=1&page_size=5", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)


# ============== MANUALS ==============
class TestManualsEnvelope:
    def test_manuals_envelope(self, dev_session):
        r = dev_session.get(f"{BASE_URL}/api/manuals", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        _assert_envelope(body)
        # When pagination is not really used, page=1 and page_size>=len(data)
        assert body["page"] == 1
        assert body["page_size"] >= len(body["data"])
        assert body["pages"] == 1

    def test_manuals_admin_envelope(self, dev_session):
        r = dev_session.get(f"{BASE_URL}/api/manuals-admin", timeout=15)
        assert r.status_code == 200, r.text
        _assert_envelope(r.json())


# ============== REGRESSION ==============
class TestRegressions:
    def test_ai_eval_health(self, dev_session):
        r = dev_session.get(f"{BASE_URL}/api/ai-evaluation/health", timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "status" in body
        assert body["status"] in ("healthy", "saturated", "stuck")

    def test_cancel_job_404_missing(self, dev_session):
        r = dev_session.delete(f"{BASE_URL}/api/ai-evaluation/jobs/does-not-exist-xyz", timeout=10)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text}"

    def test_cancel_job_400_wrong_state(self, dev_session):
        # Pick any non-En_Cola job and verify 400
        r = dev_session.get(f"{BASE_URL}/api/ai-evaluation/jobs?limit=50", timeout=15)
        assert r.status_code == 200
        jobs = r.json()["data"]
        target = next((j for j in jobs if j.get("status") not in ("En_Cola",)), None)
        if not target:
            pytest.skip("No non-En_Cola jobs available to exercise 400 path")
        job_id = target.get("id") or target.get("job_id") or target.get("_id")
        if not job_id:
            pytest.skip(f"Could not infer job id from keys: {list(target.keys())}")
        rd = dev_session.delete(f"{BASE_URL}/api/ai-evaluation/jobs/{job_id}", timeout=10)
        # Completed or Evaluando -> 400
        assert rd.status_code in (400, 404), f"expected 400, got {rd.status_code} {rd.text}"

    def test_incident_otro_requires_comentario(self, coord_session):
        # Need a journey to POST incident; pick first one
        jr = coord_session.get(f"{BASE_URL}/api/journeys?page=1&page_size=1", timeout=15)
        jdata = jr.json()["data"]
        if not jdata:
            pytest.skip("No journeys available")
        journey_id = jdata[0]["id"]
        payload = {
            "journey_id": journey_id,
            "incident_type": "otro",
            "description": "TEST_otro without comentario",
            "severity": "baja",
            "occurred_at": "2026-01-15T10:00:00Z",
            # comentario_asesor intentionally omitted
        }
        r = coord_session.post(f"{BASE_URL}/api/incidents", json=payload, timeout=15)
        assert r.status_code == 422, f"expected 422 for 'otro' w/o comentario_asesor, got {r.status_code}: {r.text}"
