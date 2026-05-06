"""
Iter85 — Selection auto-backfill (SEL01 resilience fix).

Context: Routal webhooks stopped arriving for Cubbo MX since 2026-04-26 → scheduler
fires but routal_daily_plans is empty → 0 drivers selected. The fix adds a resilience
layer in services/selection_backfill.py that pulls directly from Routal API when
staging is empty for the scheduled cutoff.

Test coverage:
  1. backfill_plans_for_date → routal_inactive (no Routal client)
  2. maybe_backfill_if_empty → skip when pending > 0 (no API call)
  3. maybe_backfill_if_empty → routal_inactive when staging empty & no integration
  4. maybe_backfill_if_empty → staged>0 with mocked Routal client
  5. run_daily_selection path normal with staged plans (not broken by fix)
  6. Scheduler loop smoke: logs show started, no startup errors
  7. Regression iter83 (/api/admin/routes-report) + iter84 (/api/health.checks.routal_sync)
  8. POST /api/selection/run/{client_id} manual endpoint does NOT use auto-backfill
     (contract preserved — empty staging returns total=0 without pulling from API)
"""
import os
import sys
import uuid
import asyncio
import inspect
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import requests

# Make backend modules importable
BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(BACKEND_DIR) / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE_URL = os.environ.get("TEST_API_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")
DEV_EMAIL = os.environ.get("TEST_DEV_EMAIL", "dev@me.mx")
DEV_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


# ─────────────── DB fixtures (direct Mongo access for unit tests) ───────────────

def _make_db():
    """Create a fresh Motor client bound to the current running loop."""
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    return client[db_name]


@pytest.fixture
def db():
    # Fresh per-test to avoid Motor event-loop reuse issues under pytest-asyncio
    return _make_db()


@pytest.fixture
def tst_client_id():
    return f"TEST_iter85_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def target_date_today():
    return date(2026, 5, 6)


@pytest.fixture
def target_dt_today(target_date_today):
    return datetime(target_date_today.year, target_date_today.month, target_date_today.day, tzinfo=timezone.utc)


# ─────────────── UNIT TESTS ───────────────

# Test 1: backfill_plans_for_date returns routal_inactive when no Routal client
@pytest.mark.asyncio
async def test_1_backfill_routal_inactive(db, tst_client_id, target_date_today):
    from services.selection_backfill import backfill_plans_for_date

    with patch("services.integration_service.IntegrationService.get_routal_client", new=AsyncMock(return_value=None)):
        result = await backfill_plans_for_date(db, tst_client_id, target_date_today)

    assert result["ok"] is True
    assert result["staged"] == 0
    assert result["error"] == "routal_inactive"


# Test 2: maybe_backfill_if_empty returns None when plans already staged
@pytest.mark.asyncio
async def test_2_maybe_backfill_skipped_when_pending(db, tst_client_id, target_date_today, target_dt_today):
    from services.selection_backfill import maybe_backfill_if_empty

    await db.routal_daily_plans.insert_one({
        "client_id": tst_client_id,
        "driver_id": "TEST_driver_01",
        "driver_name": "TEST Driver",
        "date": target_dt_today,
        "processed": False,
        "plan_id_routal": "plan_test_001",
        "route_metadata": {"stops": []},
        "source": "test",
    })

    called = {"flag": False}

    async def fake_get_routal_client(*args, **kwargs):
        called["flag"] = True
        return None  # should never be reached

    try:
        with patch("services.integration_service.IntegrationService.get_routal_client", new=AsyncMock(side_effect=fake_get_routal_client)):
            result = await maybe_backfill_if_empty(db, tst_client_id, target_date_today)
        assert result is None, "Expected None when pending plans exist (no API call)"
        assert called["flag"] is False, "Routal client should NOT be invoked when pending > 0"
    finally:
        await db.routal_daily_plans.delete_many({"client_id": tst_client_id})


# Test 3: maybe_backfill_if_empty returns routal_inactive when empty and integration inactive
@pytest.mark.asyncio
async def test_3_maybe_backfill_inactive_integration(db, tst_client_id, target_date_today):
    from services.selection_backfill import maybe_backfill_if_empty

    await db.routal_daily_plans.delete_many({"client_id": tst_client_id})

    with patch("services.integration_service.IntegrationService.get_routal_client", new=AsyncMock(return_value=None)):
        result = await maybe_backfill_if_empty(db, tst_client_id, target_date_today)

    assert result is not None
    assert result["ok"] is True
    assert result["staged"] == 0
    assert result["error"] == "routal_inactive"


# Test 4: maybe_backfill_if_empty stages>0 when Routal client mocked with valid data
@pytest.mark.asyncio
async def test_4_maybe_backfill_with_mocked_routal(db, tst_client_id, target_date_today, target_dt_today):
    from services.selection_backfill import maybe_backfill_if_empty

    await db.routal_daily_plans.delete_many({"client_id": tst_client_id})

    exd = target_dt_today.isoformat().replace("+00:00", "Z")

    plans_page = [{
        "id": "plan_abc",
        "plan_id": "plan_abc",
        "execution_date": exd,
        "label": "Test Plan",
        "project_id": "proj_test",
    }]

    plan_detail = {
        "id": "plan_abc",
        "label": "Test Plan",
        "project_id": "proj_test",
        "execution_date": exd,
        "stops": [
            {"id": "stop_1", "route_id": "drv_001"},
            {"id": "stop_2", "route_id": "drv_001"},
            {"id": "stop_3", "route_id": "drv_002"},
        ],
        "routes": [
            {"id": "drv_001", "label": "Driver One"},
            {"id": "drv_002", "label": "Driver Two"},
        ],
    }

    mock_rc = AsyncMock()
    # _request returns list on first call, empty on second (stops iteration)
    mock_rc._request = AsyncMock(side_effect=[plans_page, []])
    mock_rc.get_plan = AsyncMock(return_value=plan_detail)
    mock_rc.aclose = AsyncMock()

    try:
        with patch("services.integration_service.IntegrationService.get_routal_client", new=AsyncMock(return_value=mock_rc)):
            result = await maybe_backfill_if_empty(db, tst_client_id, target_date_today)

        assert result is not None
        assert result["ok"] is True, f"Expected ok=True, got {result}"
        assert result["staged"] == 2, f"Expected 2 staged (2 routes), got {result['staged']}"

        # Verify persistence
        staged_docs = await db.routal_daily_plans.find({"client_id": tst_client_id}).to_list(length=10)
        assert len(staged_docs) == 2
        drv_ids = {d["driver_id"] for d in staged_docs}
        assert drv_ids == {"drv_001", "drv_002"}
        for d in staged_docs:
            assert d["source"] == "auto_backfill"
            assert d["processed"] is False
            assert d["plan_id_routal"] == "plan_abc"
    finally:
        await db.routal_daily_plans.delete_many({"client_id": tst_client_id})


# Test 5: run_daily_selection still works normally with staged plans (no regression)
@pytest.mark.asyncio
async def test_5_run_daily_selection_with_staged_plans(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    # Seed an active client_config
    cfg_doc = {
        "client_id": tst_client_id,
        "client_name": "TEST Iter85 Client",
        "selection_enabled": True,
        "active": True,
        "max_daily_audits": 2,
        "scheduler_times": ["06:00", "15:01"],
        "last_scheduled_run_dates": {},
    }
    await db.client_config.insert_one(cfg_doc)
    # Seed 3 staged plans
    for i in range(3):
        await db.routal_daily_plans.insert_one({
            "client_id": tst_client_id,
            "driver_id": f"TEST_drv_{i}",
            "driver_name": f"Test Driver {i}",
            "date": target_dt_today,
            "processed": False,
            "plan_id_routal": f"plan_{i}",
            "route_metadata": {
                "id": f"plan_{i}",
                "plan_id": f"plan_{i}",
                "driver": {"id": f"TEST_drv_{i}", "name": f"Test Driver {i}"},
                "driver_id": f"TEST_drv_{i}",
                "driver_name": f"Test Driver {i}",
                "execution_date": target_dt_today.isoformat(),
                "stops": [],
                "services": [],
            },
            "source": "test_seed",
        })

    # Mock _handle_plan_created_direct to avoid side effects (Journey creation)
    try:
        with patch("workers.routal_event_processor._handle_plan_created_direct", new=AsyncMock(return_value="journey_test_id")):
            summary = await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        assert summary["ok"] is True
        assert summary["total"] == 3
        assert summary["selected"] == 2  # max_daily_audits = 2
        assert summary["unselected"] == 1
        assert summary["max_daily_audits"] == 2
    finally:
        await db.client_config.delete_many({"client_id": tst_client_id})
        await db.routal_daily_plans.delete_many({"client_id": tst_client_id})
        await db.driver_audit_log.delete_many({"client_id": tst_client_id})


# Test 6: scheduler loop smoke test (logs must show "started" without errors post-restart)
def test_6_scheduler_loop_started_in_logs():
    import subprocess
    result = subprocess.run(
        ["tail", "-n", "300", "/var/log/supervisor/backend.err.log"],
        capture_output=True, text=True, timeout=10,
    )
    log_output = result.stdout + result.stderr
    # Scheduler must have started at least once
    assert "[selection.scheduler] started" in log_output, \
        "Scheduler did not log 'started' — loop may have failed to boot"
    # Must not have traceback/exception spam related to backfill at import time
    # (ImportError/ModuleNotFoundError would be deadly)
    forbidden_patterns = [
        "ModuleNotFoundError: No module named 'services.selection_backfill'",
        "cannot import name 'maybe_backfill_if_empty'",
        "cannot import name 'backfill_plans_for_date'",
    ]
    for pat in forbidden_patterns:
        assert pat not in log_output, f"Startup error detected: {pat}"


# ─────────────── API REGRESSION TESTS ───────────────

@pytest.fixture(scope="module")
def dev_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": DEV_EMAIL, "password": DEV_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Auth failed: {r.status_code} {r.text[:200]}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(dev_token):
    return {"Authorization": f"Bearer {dev_token}"}


# Test 7a: iter83 regression — /api/admin/routes-report returns counts
def test_7a_routes_report_regression(auth_headers):
    # iter83 endpoint requires date_from/date_to
    today = date.today()
    d_from = (today - timedelta(days=7)).isoformat()
    d_to = today.isoformat()
    r = requests.get(
        f"{BASE_URL}/api/admin/routes-report",
        params={"date_from": d_from, "date_to": d_to},
        headers=auth_headers, timeout=60,
    )
    assert r.status_code == 200, f"routes-report failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert isinstance(data, dict)
    # Should expose some counts/summary/rows — loose shape check
    assert any(k in data for k in ("rows", "summary", "counts", "routes", "total", "items")), \
        f"routes-report has unexpected shape: keys={list(data.keys())[:10]}"


# Test 7b: iter84 regression — /api/health exposes checks.routal_sync block
def test_7b_health_routal_sync_regression():
    r = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert r.status_code == 200, f"/api/health failed: {r.status_code}"
    data = r.json()
    checks = data.get("checks") or {}
    assert "routal_sync" in checks, f"checks.routal_sync missing. checks keys={list(checks.keys())}"


# Test 8: POST /api/selection/run/{client_id} does NOT call maybe_backfill_if_empty
# We assert by grep (static contract check) since calling the live endpoint needs
# a real client_id and could have side-effects.
def test_8_manual_run_endpoint_does_not_auto_backfill():
    src = Path("/app/backend/routes/selection_routes.py").read_text()
    # Locate the run_selection function body (from @router.post("/selection/run/{client_id}") to the next @router.post)
    start_marker = '@router.post("/selection/run/{client_id}")'
    end_marker = '@router.post("/selection/run-range/{client_id}")'
    assert start_marker in src
    assert end_marker in src
    body = src[src.index(start_marker):src.index(end_marker)]
    assert "maybe_backfill_if_empty" not in body, \
        "Manual run endpoint must NOT invoke auto-backfill (contract breach)"
    assert "backfill_plans_for_date" not in body, \
        "Manual run endpoint must NOT invoke auto-backfill helper"
    # And confirm it still calls run_daily_selection
    assert "run_daily_selection" in body

    # Additionally: ensure the live endpoint responds (auth-gated, shape-check)
    # Use an invalid client_id → expect 400 (no config), proving endpoint is alive
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": DEV_EMAIL, "password": DEV_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip("auth failed for live endpoint check")
    tok = r.json().get("access_token") or r.json().get("token")
    r2 = requests.post(
        f"{BASE_URL}/api/selection/run/TEST_nonexistent_client_iter85",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    # 400 (no config) or 404 are acceptable — 500 would be a breakage
    assert r2.status_code in (400, 404), f"Unexpected status: {r2.status_code} {r2.text[:200]}"
