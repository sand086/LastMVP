"""
Iter87 — Bug fix: package-cohort selector ignored Routal `status`.

PROD bug (2026-06-11): /captacion runs at 16:00 CDMX but selects 0 services even
though Routal has 20+ plans for the day. Root cause: staged `route_metadata` never
persisted `status` field from Routal payload. Selector reads
`classify_plan_operational_state(plan["route_metadata"])` which falls back to
"created" when status is missing → eligibility filter `["in_progress"]`
discards every plan.

Fix:
  - services/selection_backfill.py: persist `status` in staged payload.
  - workers/routal_event_processor._handle_plan_created: persist `status`.
  - routes/selection_routes.backfill_from_routal: persist `status`.
  - services/selection_backfill.maybe_backfill_if_empty: accept `force_refresh=True`.
  - workers/routal_selection_worker._scheduler_loop: pass force_refresh=True at cutoff.

Tests in this file:
  1. classify_plan_operational_state honors Routal 'planning' / 'in_progress'.
  2. Package-cohort selector drops planning plans, keeps in_progress.
  3. Webhook handler (`_handle_plan_created`) stages status into route_metadata.
  4. maybe_backfill_if_empty(force_refresh=True) bypasses pending>0 short-circuit.
"""
from __future__ import annotations
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(BACKEND_DIR) / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from workers.routal_selection_worker import (  # noqa: E402
    classify_plan_operational_state,
    run_daily_selection,
)
from workers.routal_event_processor import _handle_plan_created  # noqa: E402
from services.selection_backfill import maybe_backfill_if_empty  # noqa: E402


def _make_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


def _date_to_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def test_1_classify_plan_operational_state_routal_payload():
    """Routal returns 'planning' for not-yet-started, 'in_progress' for active.
    Selector must classify them accordingly."""
    assert classify_plan_operational_state({"status": "in_progress"}, ["in_progress"]) == "in_progress"
    assert classify_plan_operational_state({"status": "started"}, ["in_progress"]) == "in_progress"
    assert classify_plan_operational_state({"status": "planning"}, ["in_progress"]) == "created"
    assert classify_plan_operational_state({"status": "completed"}, ["in_progress"]) == "completed"
    # Missing status (the PROD bug): falls back to 'created' → filtered out, NOT in_progress
    assert classify_plan_operational_state({}, ["in_progress"]) == "created"


@pytest.mark.asyncio
async def test_2_package_cohort_filters_by_status():
    """run_daily_selection in package_mode must drop plans whose status is not in
    the eligibility list, even when stops > 0."""
    db = _make_db()
    client_id = f"_test_iter87_{uuid.uuid4().hex[:8]}"
    target = date(2026, 6, 11)
    target_dt = _date_to_dt(target)

    try:
        await db.client_config.insert_one({
            "client_id": client_id,
            "client_name": "Test 87",
            "active": True,
            "selection_enabled": True,
            "audit_target_packages_daily": 100,
            "audit_min_packages_daily": 50,
            "audit_max_packages_daily": 200,
            "audit_target_packages_weekly": 700,
            "audit_distribution_strategy": "adaptive_calendar_week",
            "ingest_eligibility_states": ["in_progress"],
            "audit_overshoot_tolerance": 0.10,
        })

        def _stops(n):
            return [{"id": f"s{i}", "label": f"Order {i}"} for i in range(n)]

        await db.routal_daily_plans.insert_many([
            {
                "client_id": client_id, "driver_id": "drv_inprog", "date": target_dt,
                "plan_id_routal": "p1", "processed": False,
                "route_metadata": {"status": "in_progress", "stops": _stops(30)},
            },
            {
                "client_id": client_id, "driver_id": "drv_planning", "date": target_dt,
                "plan_id_routal": "p2", "processed": False,
                "route_metadata": {"status": "planning", "stops": _stops(50)},
            },
            {
                "client_id": client_id, "driver_id": "drv_no_status", "date": target_dt,
                "plan_id_routal": "p3", "processed": False,
                "route_metadata": {"stops": _stops(40)},
            },
        ])

        result = await run_daily_selection(db, client_id, target_date=target)
        assert result["ok"] is True
        assert result["selected"] == 1, f"expected exactly the in_progress plan, got {result}"

        run = await db.selection_runs.find_one({"client_id": client_id, "date": target_dt})
        assert run is not None
        assert run["mode"] == "package"
        assert run["eligible_count"] == 1
        assert run["knapsack"]["selected_packages"] == 30

        sel = await db.driver_audit_log.find_one(
            {"client_id": client_id, "selection_status": "selected"}
        )
        assert sel and sel["driver_id"] == "drv_inprog"
    finally:
        await db.client_config.delete_one({"client_id": client_id})
        await db.routal_daily_plans.delete_many({"client_id": client_id})
        await db.driver_audit_log.delete_many({"client_id": client_id})
        await db.selection_runs.delete_many({"client_id": client_id})
        await db.journeys.delete_many({"client_id": client_id})
        await db.packages.delete_many({"client_id": client_id})


@pytest.mark.asyncio
async def test_3_webhook_handler_persists_status():
    """_handle_plan_created must include payload['status'] in staged route_metadata
    so the cohort selector can read it later."""
    db = _make_db()
    client_id = f"_test_iter87wh_{uuid.uuid4().hex[:8]}"
    plan_id = f"plan_{uuid.uuid4().hex[:10]}"

    try:
        await db.client_config.insert_one({
            "client_id": client_id, "active": True, "selection_enabled": True,
        })
        payload = {
            "id": plan_id,
            "plan_id": plan_id,
            "label": "Test plan",
            "execution_date": "2026-06-11T18:00:00.000Z",
            "status": "planning",  # Routal sends this on plan.created
            "driver": {"id": "drv_x", "name": "Driver X"},
            "stops": [{"id": "s1", "route_id": "drv_x", "label": "Order 1"}],
        }
        await _handle_plan_created(db, payload, client_id)

        staged = await db.routal_daily_plans.find_one(
            {"client_id": client_id, "driver_id": "drv_x"}
        )
        assert staged is not None
        assert staged["route_metadata"].get("status") == "planning"
    finally:
        await db.client_config.delete_one({"client_id": client_id})
        await db.routal_daily_plans.delete_many({"client_id": client_id})


@pytest.mark.asyncio
async def test_4_maybe_backfill_force_refresh_bypasses_pending_check():
    """force_refresh=True must call the Routal API even when pending>0 already."""
    db = _make_db()
    client_id = f"_test_iter87fr_{uuid.uuid4().hex[:8]}"
    target = date(2026, 6, 11)
    target_dt = _date_to_dt(target)

    try:
        # Pre-populate one pending plan → without force_refresh, backfill should skip.
        await db.routal_daily_plans.insert_one({
            "client_id": client_id, "driver_id": "drv_old", "date": target_dt,
            "processed": False, "route_metadata": {"status": "planning"},
        })

        with patch(
            "services.selection_backfill.backfill_plans_for_date",
            new_callable=AsyncMock,
        ) as bf_mock:
            bf_mock.return_value = {"ok": True, "staged": 0}

            r1 = await maybe_backfill_if_empty(db, client_id, target, force_refresh=False)
            assert r1 is None, "should skip when pending>0 and force_refresh=False"
            bf_mock.assert_not_called()

            r2 = await maybe_backfill_if_empty(db, client_id, target, force_refresh=True)
            assert r2 is not None, "should run when force_refresh=True even with pending>0"
            bf_mock.assert_called_once()
    finally:
        await db.routal_daily_plans.delete_many({"client_id": client_id})
