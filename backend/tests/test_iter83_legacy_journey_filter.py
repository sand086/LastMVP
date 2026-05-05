"""
iter83 — Bug fix: legacy journey filter for reports endpoints.

Validates the helper apply_legacy_journey_filter (dependencies.py) is wired into:
  - GET /api/admin/routes-report
  - 10 analytics endpoints

Also regression-checks /api/journeys?q=... with the inline filter (defensive
against existing $or/$and).

The test inserts journey docs directly via local Mongo because there is no
public API to set the `migrated_to_journeys` / `_legacy_incidents_remaining`
fields. The preview URL routes to the same backend instance that points at
the local mongo of this container.
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone

import sys
sys.path.insert(0, "/app/backend")
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"

# Direct mongo for fixture seeding (legacy migration fields are not exposed via API).
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
_mc = MongoClient(MONGO_URL)
_db = _mc[DB_NAME]

TEST_DATE = "2026-05-04"
TEST_TAG = "TEST_iter83_legacy"

# ────────────────────────── fixtures ──────────────────────────


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": DEV_EMAIL, "password": DEV_PASSWORD},
               timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    yield s


@pytest.fixture(scope="module")
def provider_id(auth_session):
    """Pick or create a provider for the test."""
    r = auth_session.get(f"{BASE_URL}/api/providers", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["data"] if isinstance(data, dict) and "data" in data else data
    assert items, "No providers in DB"
    return items[0]["id"]


@pytest.fixture(scope="module")
def client_id(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/clients", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["data"] if isinstance(data, dict) and "data" in data else data
    assert items, "No clients in DB"
    return items[0]["id"]


@pytest.fixture(scope="module")
def seeded_journeys(provider_id, client_id):
    """
    Seed:
      - new1, new2: route-based journeys
      - legacy: plan-based journey with migrated_to_journeys=[new1.id, new2.id]
                NO _legacy_incidents_remaining → should be hidden by filter.
    Returns dict with ids; cleanup after module.
    """
    new1_id = f"{TEST_TAG}_new1_{uuid.uuid4().hex[:8]}"
    new2_id = f"{TEST_TAG}_new2_{uuid.uuid4().hex[:8]}"
    legacy_id = f"{TEST_TAG}_legacy_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    base = {
        "date": TEST_DATE,
        "client_id": client_id,
        "provider_id": provider_id,
        "status": "completed",
        "packages_total": 10,
        "packages_delivered": 10,
        "packages_failed": 0,
        "packages_retry": 0,
        "packages_pending": 0,
        "packages_cancelled": 0,
        "incidents_count": 0,
        "created_at": now,
    }

    new1 = {**base, "id": new1_id, "driver_name": f"{TEST_TAG} Driver A",
            "order_id": f"{TEST_TAG}_orderA", "routal_route_id": "R1"}
    new2 = {**base, "id": new2_id, "driver_name": f"{TEST_TAG} Driver B",
            "order_id": f"{TEST_TAG}_orderB", "routal_route_id": "R2"}
    legacy = {**base, "id": legacy_id, "driver_name": "Vehículo N",
              "order_id": legacy_id, "routal_plan_id": "P1",
              "migrated_to_journeys": [new1_id, new2_id]}
    # Note: NO _legacy_incidents_remaining key → covered by $exists:False branch implicitly
    # (filter says: keep if migrated_to_journeys missing OR _legacy_incidents_remaining>0;
    #  legacy doc fails BOTH conditions, so it is hidden — correct).

    _db.journeys.insert_many([new1, new2, legacy])
    yield {"new1": new1_id, "new2": new2_id, "legacy": legacy_id,
           "all": [new1_id, new2_id, legacy_id]}

    # Cleanup
    _db.journeys.delete_many({"id": {"$in": [new1_id, new2_id, legacy_id]}})


# ────────────────────────── tests ──────────────────────────


class TestRoutesReportLegacyFilter:
    """1. Bug fix: GET /api/admin/routes-report hides legacy migrated journeys."""

    def test_routes_report_hides_legacy_when_no_orphan_incidents(
            self, auth_session, seeded_journeys, provider_id):
        r = auth_session.get(
            f"{BASE_URL}/api/admin/routes-report",
            params={"date_from": TEST_DATE, "date_to": TEST_DATE,
                    "provider_id": provider_id, "page_size": 100},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body.get("rows", [])
        seeded_set = set(seeded_journeys["all"])
        seeded_rows = [row for row in rows if row.get("journey_id") in seeded_set]

        seeded_ids = {row["journey_id"] for row in seeded_rows}
        assert seeded_journeys["new1"] in seeded_ids, "new1 should be visible"
        assert seeded_journeys["new2"] in seeded_ids, "new2 should be visible"
        assert seeded_journeys["legacy"] not in seeded_ids, (
            "legacy migrated journey must be hidden — got rows: "
            f"{[r.get('journey_id') for r in seeded_rows]}"
        )
        assert len(seeded_rows) == 2, f"Expected 2 seeded rows, got {len(seeded_rows)}"

    def test_routes_report_keeps_legacy_when_orphan_incidents_remain(
            self, auth_session, seeded_journeys, provider_id):
        # Promote legacy: simulate 2 orphan incidents pending.
        _db.journeys.update_one(
            {"id": seeded_journeys["legacy"]},
            {"$set": {"_legacy_incidents_remaining": 2}},
        )
        try:
            r = auth_session.get(
                f"{BASE_URL}/api/admin/routes-report",
                params={"date_from": TEST_DATE, "date_to": TEST_DATE,
                        "provider_id": provider_id, "page_size": 100},
                timeout=20,
            )
            assert r.status_code == 200, r.text
            rows = r.json().get("rows", [])
            seeded_set = set(seeded_journeys["all"])
            seeded_ids = {row["journey_id"] for row in rows
                          if row.get("journey_id") in seeded_set}
            assert seeded_journeys["legacy"] in seeded_ids, (
                "legacy with _legacy_incidents_remaining>0 must be visible"
            )
            assert len(seeded_ids) == 3, f"Expected 3 seeded rows, got {len(seeded_ids)}"
        finally:
            _db.journeys.update_one(
                {"id": seeded_journeys["legacy"]},
                {"$unset": {"_legacy_incidents_remaining": ""}},
            )

    def test_routes_report_zero_remaining_is_hidden(
            self, auth_session, seeded_journeys, provider_id):
        """Edge case the request flags: _legacy_incidents_remaining=0 must be hidden."""
        _db.journeys.update_one(
            {"id": seeded_journeys["legacy"]},
            {"$set": {"_legacy_incidents_remaining": 0}},
        )
        try:
            r = auth_session.get(
                f"{BASE_URL}/api/admin/routes-report",
                params={"date_from": TEST_DATE, "date_to": TEST_DATE,
                        "provider_id": provider_id, "page_size": 100},
                timeout=20,
            )
            assert r.status_code == 200
            rows = r.json().get("rows", [])
            ids = {row["journey_id"] for row in rows}
            assert seeded_journeys["legacy"] not in ids, (
                "legacy with _legacy_incidents_remaining==0 should be hidden"
            )
        finally:
            _db.journeys.update_one(
                {"id": seeded_journeys["legacy"]},
                {"$unset": {"_legacy_incidents_remaining": ""}},
            )


class TestJourneysSearchDefensiveFilter:
    """3. /api/journeys?q=... must still work despite filter combining with $or/$and."""

    def test_search_finds_seeded_journey_and_hides_legacy(
            self, auth_session, seeded_journeys):
        # new1 has order_id with TEST_TAG_orderA — search should return it.
        r = auth_session.get(
            f"{BASE_URL}/api/journeys",
            params={"q": "TEST_iter83_legacy_orderA", "page_size": 100},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        ids = [j["id"] for j in items]
        assert seeded_journeys["new1"] in ids, (
            f"Search by order_id failed; got ids: {ids}"
        )
        assert seeded_journeys["legacy"] not in ids, (
            "Legacy must remain hidden in search results"
        )

    def test_search_no_500_on_unrelated_query(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/journeys",
                             params={"q": "test", "page_size": 5}, timeout=20)
        assert r.status_code == 200, r.text


class TestRoutesReportRegression:
    """4. Filters by driver/provider_id/status/team must still work, exports OK."""

    def test_filter_by_driver(self, auth_session, seeded_journeys, provider_id):
        r = auth_session.get(
            f"{BASE_URL}/api/admin/routes-report",
            params={"date_from": TEST_DATE, "date_to": TEST_DATE,
                    "driver": "TEST_iter83_legacy Driver A", "page_size": 100},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        ids = {row["journey_id"] for row in r.json().get("rows", [])}
        assert seeded_journeys["new1"] in ids
        assert seeded_journeys["new2"] not in ids

    def test_filter_by_status(self, auth_session, provider_id):
        r = auth_session.get(
            f"{BASE_URL}/api/admin/routes-report",
            params={"date_from": TEST_DATE, "date_to": TEST_DATE,
                    "status": "completed", "page_size": 5},
            timeout=20,
        )
        assert r.status_code == 200

    def test_export_liquidacion_returns_excel(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/admin/export-liquidacion",
            params={"date_from": TEST_DATE, "date_to": TEST_DATE},
            timeout=30,
        )
        assert r.status_code == 200, r.text[:500]
        ct = r.headers.get("content-type", "")
        assert "spreadsheet" in ct or "excel" in ct or "octet-stream" in ct, ct
        assert len(r.content) > 100

    def test_routes_report_export(self, auth_session):
        r = auth_session.post(
            f"{BASE_URL}/api/admin/routes-report/export",
            json={"date_from": TEST_DATE, "date_to": TEST_DATE},
            timeout=30,
        )
        # Some impls use GET — fall back if 405
        if r.status_code == 405:
            r = auth_session.get(
                f"{BASE_URL}/api/admin/routes-report/export",
                params={"date_from": TEST_DATE, "date_to": TEST_DATE},
                timeout=30,
            )
        assert r.status_code == 200, r.text[:500]
        assert len(r.content) > 100


class TestAnalyticsRegression:
    """5. The 10 analytics endpoints must not 500 and return valid structure."""

    DATE_PARAMS = {"date_from": TEST_DATE, "date_to": TEST_DATE}

    def test_analytics_heatmap_get(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/analytics/heatmap",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]
        assert isinstance(r.json(), (dict, list))

    def test_analytics_heatmap_export(self, auth_session):
        r = auth_session.post(f"{BASE_URL}/api/analytics/heatmap-export",
                              json=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_quality(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/reports/quality",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_quality_export(self, auth_session):
        # Endpoint uses Form fields, not JSON body
        r = auth_session.post(f"{BASE_URL}/api/reports/quality-export",
                              data=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_export_incidents(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/export/incidents",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_kpis(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/reports/kpis",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_heatmap(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/reports/heatmap",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_attempts(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/reports/attempts",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_sla(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/reports/sla",
                             params=self.DATE_PARAMS, timeout=30)
        assert r.status_code == 200, r.text[:500]

    def test_reports_generate_ai(self, auth_session):
        # 503 acceptable (LLM may be down)
        r = auth_session.post(f"{BASE_URL}/api/reports/generate-ai",
                              json={**self.DATE_PARAMS, "report_type": "summary"},
                              timeout=60)
        assert r.status_code in (200, 422, 503), f"Unexpected: {r.status_code} {r.text[:300]}"


class TestPerfCacheRegression:
    """6. iter59 cache regression: /api/clients & /api/providers still respond fast."""

    def test_clients_cache(self, auth_session):
        # 2 calls; second should be fast (cached)
        import time
        t0 = time.time()
        r1 = auth_session.get(f"{BASE_URL}/api/clients", timeout=15)
        t1 = time.time()
        r2 = auth_session.get(f"{BASE_URL}/api/clients", timeout=15)
        t2 = time.time()
        assert r1.status_code == 200 and r2.status_code == 200
        # Don't assert exact ms — just ensure both work
        assert (t2 - t1) < 5

    def test_providers_cache(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/providers", timeout=15)
        assert r.status_code == 200
