"""
Iter86 — Cupo aditivo + filtro rutas vacías en backfill manual/auto.

Test coverage (review_request iter86):
  1. Filtro rutas vacías auto-backfill (services/selection_backfill.py)
  2. Filtro rutas vacías manual backfill (routes/selection_routes.py)
  3. Cupo aditivo escenario A (max=5, primera 3, segunda 4 → total 5)
  4. Cupo aditivo escenario B (max=10, primera 10, segunda 5 → total 10)
  5. Cupo aditivo escenario C (max=10, primera 5, segunda 5 → total 10)
  6. Preservar phase/journey_id en re-ejecución
  7. Idempotencia sin nuevos plans
  8. Edge max_daily=0
  9. Edge max_daily saturado, 1 driver adicional → unselected
 10. Regresión iter85 (auto-backfill routal_inactive, skip when pending>0)
 11. Smoke: /api/health.checks.routal_sync + scheduler started
"""
import os
import sys
import uuid
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import requests

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(BACKEND_DIR) / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE_URL = os.environ.get("TEST_API_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")
DEV_EMAIL = os.environ.get("TEST_DEV_EMAIL", "dev@me.mx")
DEV_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


def _make_db():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    return client[db_name]


@pytest.fixture
def db():
    return _make_db()


@pytest.fixture
def tst_client_id():
    return f"TEST_iter86_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def target_date_today():
    return date(2026, 5, 7)


@pytest.fixture
def target_dt_today(target_date_today):
    return datetime(target_date_today.year, target_date_today.month, target_date_today.day, tzinfo=timezone.utc)


async def _cleanup(db, client_id):
    await db.client_config.delete_many({"client_id": client_id})
    await db.routal_daily_plans.delete_many({"client_id": client_id})
    await db.driver_audit_log.delete_many({"client_id": client_id})


async def _seed_cfg(db, client_id, max_daily):
    await db.client_config.insert_one({
        "client_id": client_id,
        "client_name": "TEST iter86",
        "selection_enabled": True,
        "active": True,
        "max_daily_audits": max_daily,
        "scheduler_times": ["06:00"],
        "last_scheduled_run_dates": {},
    })


async def _stage_driver(db, client_id, drv_id, target_dt):
    await db.routal_daily_plans.insert_one({
        "client_id": client_id,
        "driver_id": drv_id,
        "driver_name": f"Driver {drv_id}",
        "date": target_dt,
        "processed": False,
        "plan_id_routal": f"plan_{drv_id}",
        "route_metadata": {
            "id": f"plan_{drv_id}",
            "plan_id": f"plan_{drv_id}",
            "driver": {"id": drv_id, "name": f"Driver {drv_id}"},
            "driver_id": drv_id,
            "driver_name": f"Driver {drv_id}",
            "execution_date": target_dt.isoformat(),
            "stops": [{"id": f"s_{drv_id}", "route_id": drv_id}],
            "services": [],
        },
        "source": "test_seed",
    })


# ────────── Test 1: Filtro rutas vacías en auto-backfill ──────────
@pytest.mark.asyncio
async def test_1_auto_backfill_skips_empty_routes(db, tst_client_id, target_date_today, target_dt_today):
    from services.selection_backfill import maybe_backfill_if_empty

    await _cleanup(db, tst_client_id)
    exd = target_dt_today.isoformat().replace("+00:00", "Z")

    plans_page = [{"id": "plan_A", "plan_id": "plan_A", "execution_date": exd, "label": "L"}]
    plan_detail = {
        "id": "plan_A", "label": "L", "execution_date": exd,
        "stops": [
            {"id": "s1", "route_id": "drvA"},
            {"id": "s2", "route_id": "drvA"},
        ],
        "routes": [
            {"id": "drvA", "label": "Driver A"},
            {"id": "drvB", "label": "Driver B"},  # NO stops for drvB
        ],
    }
    mock_rc = AsyncMock()
    mock_rc._request = AsyncMock(side_effect=[plans_page, []])
    mock_rc.get_plan = AsyncMock(return_value=plan_detail)
    mock_rc.aclose = AsyncMock()

    try:
        with patch("services.integration_service.IntegrationService.get_routal_client",
                   new=AsyncMock(return_value=mock_rc)):
            result = await maybe_backfill_if_empty(db, tst_client_id, target_date_today)
        assert result["ok"] is True
        assert result["staged"] == 1, f"Only drvA should be staged (drvB empty). Got: {result}"
        staged_docs = await db.routal_daily_plans.find({"client_id": tst_client_id}).to_list(10)
        assert len(staged_docs) == 1
        assert staged_docs[0]["driver_id"] == "drvA"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 2: Filtro rutas vacías en manual backfill endpoint ──────────
@pytest.mark.asyncio
async def test_2_manual_backfill_skips_empty_routes():
    """Static contract: endpoint code must contain the route_stops empty filter."""
    src = Path("/app/backend/routes/selection_routes.py").read_text()
    # Locate function body
    start = src.index('@router.post("/selection/backfill-from-routal/{client_id}")')
    end = src.index('@router.post("/selection/reconcile-dates/{client_id}")')
    body = src[start:end]
    assert "route_stops = [s for s in stops if s.get(\"route_id\") == drv_id]" in body
    assert "if not route_stops:" in body
    # And must count as skipped_no_driver (not staged)
    assert "skipped_no_driver += 1" in body


# ────────── Test 3: Cupo aditivo escenario A (5 / 3+4 → 5) ──────────
@pytest.mark.asyncio
async def test_3_additive_quota_scenario_A(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    await _seed_cfg(db, tst_client_id, max_daily=5)

    try:
        # First run: 3 drivers
        for i in range(3):
            await _stage_driver(db, tst_client_id, f"drv_A{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="journey_first")):
            s1 = await run_daily_selection(db, tst_client_id, target_date=target_date_today)
        assert s1["ok"] and s1["selected"] == 3, f"First run should select 3, got {s1}"

        # Second run: 4 new drivers
        for i in range(4):
            await _stage_driver(db, tst_client_id, f"drv_B{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="journey_second")):
            s2 = await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        # Should select only 2 more (5 - 3 already = 2)
        # Total selected in log == 5
        total_selected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "selected"}
        )
        total_unselected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "unselected"}
        )
        assert total_selected == 5, f"Total selected should be 5 (cap), got {total_selected}. Summary: {s2}"
        assert total_unselected == 2, f"Total unselected should be 2, got {total_unselected}"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 4: Cupo aditivo escenario B (10 full, +5 → 10) ──────────
@pytest.mark.asyncio
async def test_4_additive_quota_scenario_B(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    await _seed_cfg(db, tst_client_id, max_daily=10)

    try:
        for i in range(10):
            await _stage_driver(db, tst_client_id, f"drv_full{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j")):
            s1 = await run_daily_selection(db, tst_client_id, target_date=target_date_today)
        assert s1["selected"] == 10

        for i in range(5):
            await _stage_driver(db, tst_client_id, f"drv_extra{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j2")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        selected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "selected"}
        )
        unselected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "unselected"}
        )
        assert selected == 10, f"Cap saturated: expected 10 selected, got {selected}"
        assert unselected == 5, f"All 5 new must be unselected, got {unselected}"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 5: Cupo aditivo escenario C (5+5 exactly → 10) ──────────
@pytest.mark.asyncio
async def test_5_additive_quota_scenario_C(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    await _seed_cfg(db, tst_client_id, max_daily=10)

    try:
        for i in range(5):
            await _stage_driver(db, tst_client_id, f"drv_p1_{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        for i in range(5):
            await _stage_driver(db, tst_client_id, f"drv_p2_{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j2")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        selected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "selected"}
        )
        assert selected == 10, f"Expected 10 selected (perfect fit), got {selected}"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 6: Preservar phase + journey_id de primeros drivers ──────────
@pytest.mark.asyncio
async def test_6_preserve_phase_and_journey_id(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    await _seed_cfg(db, tst_client_id, max_daily=5)

    try:
        await _stage_driver(db, tst_client_id, "drv_original", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="journey_ORIGINAL_id")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        original_doc = await db.driver_audit_log.find_one(
            {"client_id": tst_client_id, "driver_id": "drv_original", "date": target_dt_today}
        )
        assert original_doc is not None
        original_phase = original_doc.get("selection_phase")
        original_journey = original_doc.get("journey_id")
        assert original_phase == "phase_1"
        assert original_journey == "journey_ORIGINAL_id"

        # Second run with new drivers
        for i in range(3):
            await _stage_driver(db, tst_client_id, f"drv_new_{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="journey_SECOND_id")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        preserved_doc = await db.driver_audit_log.find_one(
            {"client_id": tst_client_id, "driver_id": "drv_original", "date": target_dt_today}
        )
        assert preserved_doc["selection_phase"] == original_phase, "phase overwritten!"
        assert preserved_doc["journey_id"] == original_journey, \
            f"journey_id overwritten! expected {original_journey} got {preserved_doc['journey_id']}"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 7: Idempotencia sin nuevos plans ──────────
@pytest.mark.asyncio
async def test_7_idempotent_rerun_no_new_plans(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    await _seed_cfg(db, tst_client_id, max_daily=5)

    try:
        for i in range(3):
            await _stage_driver(db, tst_client_id, f"drv_idem_{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j")):
            s1 = await run_daily_selection(db, tst_client_id, target_date=target_date_today)
            s2 = await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        assert s1["selected"] == 3
        # Second call: no unprocessed plans left → early return total=0
        assert s2["ok"] is True
        assert s2.get("total", 0) == 0, f"Expected total=0 on idempotent re-run, got {s2}"

        selected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "selected"}
        )
        assert selected == 3
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 8: max_daily=0 edge ──────────
@pytest.mark.asyncio
async def test_8_max_daily_zero(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    # max_daily_audits requires > 0 in Pydantic model for PATCH endpoint, but
    # the worker itself should handle 0 safely. Insert directly.
    await db.client_config.insert_one({
        "client_id": tst_client_id,
        "client_name": "TEST zero",
        "selection_enabled": True,
        "active": True,
        "max_daily_audits": 0,
        "scheduler_times": ["06:00"],
        "last_scheduled_run_dates": {},
    })

    try:
        for i in range(3):
            await _stage_driver(db, tst_client_id, f"drv_zero_{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j")):
            s = await run_daily_selection(db, tst_client_id, target_date=target_date_today)
        assert s["selected"] == 0
        selected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "selected"}
        )
        unselected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "unselected"}
        )
        assert selected == 0
        assert unselected == 3
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 9: Saturado + 1 extra vía backfill ──────────
@pytest.mark.asyncio
async def test_9_saturated_extra_driver_unselected(db, tst_client_id, target_date_today, target_dt_today):
    from workers.routal_selection_worker import run_daily_selection

    await _cleanup(db, tst_client_id)
    await _seed_cfg(db, tst_client_id, max_daily=3)

    try:
        for i in range(3):
            await _stage_driver(db, tst_client_id, f"drv_sat_{i}", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        # backfill adds 1 more
        await _stage_driver(db, tst_client_id, "drv_late", target_dt_today)
        with patch("workers.routal_event_processor._handle_plan_created_direct",
                   new=AsyncMock(return_value="j2")):
            await run_daily_selection(db, tst_client_id, target_date=target_date_today)

        selected = await db.driver_audit_log.count_documents(
            {"client_id": tst_client_id, "date": target_dt_today, "selection_status": "selected"}
        )
        late = await db.driver_audit_log.find_one(
            {"client_id": tst_client_id, "driver_id": "drv_late"}
        )
        assert selected == 3, f"Must not exceed cap of 3, got {selected}"
        assert late["selection_status"] == "unselected"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 10: Regresión iter85 auto-backfill contracts ──────────
@pytest.mark.asyncio
async def test_10a_regression_routal_inactive(db, tst_client_id, target_date_today):
    from services.selection_backfill import backfill_plans_for_date

    with patch("services.integration_service.IntegrationService.get_routal_client",
               new=AsyncMock(return_value=None)):
        r = await backfill_plans_for_date(db, tst_client_id, target_date_today)
    assert r == {"ok": True, "staged": 0, "error": "routal_inactive"}


@pytest.mark.asyncio
async def test_10b_regression_maybe_backfill_skip_when_pending(db, tst_client_id, target_date_today, target_dt_today):
    from services.selection_backfill import maybe_backfill_if_empty

    await _cleanup(db, tst_client_id)
    await _stage_driver(db, tst_client_id, "drv_pending", target_dt_today)
    try:
        called = {"v": False}

        async def side(*a, **k):
            called["v"] = True
            return None

        with patch("services.integration_service.IntegrationService.get_routal_client",
                   new=AsyncMock(side_effect=side)):
            r = await maybe_backfill_if_empty(db, tst_client_id, target_date_today)
        assert r is None
        assert called["v"] is False, "Routal client must NOT be invoked when plans already pending"
    finally:
        await _cleanup(db, tst_client_id)


# ────────── Test 11: Smoke - /api/health + routes-report + scheduler ──────────
def test_11a_health_routal_sync():
    r = requests.get(f"{BASE_URL}/api/health", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "routal_sync" in (data.get("checks") or {})


def test_11b_scheduler_started_no_import_errors():
    import subprocess
    r = subprocess.run(
        ["tail", "-n", "400", "/var/log/supervisor/backend.err.log"],
        capture_output=True, text=True, timeout=10,
    )
    out = r.stdout + r.stderr
    assert "[selection.scheduler] started" in out
    forbidden = [
        "ModuleNotFoundError: No module named 'services.selection_backfill'",
        "cannot import name 'run_daily_selection'",
    ]
    for p in forbidden:
        assert p not in out


def test_11c_admin_routes_report_regression():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": DEV_EMAIL, "password": DEV_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.skip("auth failed")
    tok = r.json().get("access_token") or r.json().get("token")
    today = date.today()
    rr = requests.get(
        f"{BASE_URL}/api/admin/routes-report",
        params={"date_from": (today - timedelta(days=7)).isoformat(), "date_to": today.isoformat()},
        headers={"Authorization": f"Bearer {tok}"}, timeout=60,
    )
    assert rr.status_code == 200, f"routes-report broken: {rr.status_code} {rr.text[:200]}"
