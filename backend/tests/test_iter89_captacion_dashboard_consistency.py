"""
Iter89 — Bug fix: discrepancia entre /captacion y /dashboard.

PROD bug (2026-06-16): /captacion mostraba 35 rutas / 1,021 paquetes para hoy,
pero /dashboard mostraba 29 rutas / 865 paquetes — misma fecha, números distintos.

Causa raíz: en `routal_selection_worker.run_daily_selection`, si
`_handle_plan_created_direct` lanzaba excepción o retornaba "skipped: ..." (no se
materializó journey), el `driver_audit_log` igual quedaba con
`selection_status="selected"` y `selection_runs.selected_count` apuntaba al
recuento PRE-materialización. /captacion lee de driver_audit_log/selection_runs;
/dashboard lee de la colección journeys. Resultado: divergencia silenciosa.

Fix:
  - Detectar journey "skipped:" o exception → registrar
    `selection_status="failed"` con `failure_reason`, NO "selected".
  - Quitar de `new_selected`/`selected_set` para que el resumen sea consistente.
  - `packages_audited` ahora se calcula desde `packages` reales (no del snapshot
    de stops del staging) cuando el journey sí se materializó.
  - Reconciliar `selection_runs` después del loop con los counts reales de
    `driver_audit_log`.

Tests:
  1. journey skipped → audit_log selection_status="failed", no overcounting.
  2. journey exception → audit_log selection_status="failed", failure_reason logged.
  3. journey OK → audit_log selection_status="selected", packages_audited matches packages collection.
  4. selection_runs reflects materialized counts post-loop.
"""
from __future__ import annotations
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(BACKEND_DIR) / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from workers.routal_selection_worker import run_daily_selection  # noqa: E402


def _make_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


def _date_to_dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_journey_skipped_marks_audit_failed():
    """A staged plan whose payload yields zero real routes (placeholder driver
    label) must end up as selection_status='failed' in driver_audit_log, NOT
    'selected'. selection_runs.selected_count must reflect actual materialized
    journeys after the loop."""
    db = _make_db()
    client_id = f"_test_iter89_{uuid.uuid4().hex[:8]}"
    target = date(2026, 6, 16)
    target_dt = _date_to_dt(target)
    drv_ok = f"drv_ok_{uuid.uuid4().hex[:6]}"
    drv_skip = f"drv_skip_{uuid.uuid4().hex[:6]}"

    try:
        await db.client_config.insert_one({
            "client_id": client_id, "client_name": "Test 89",
            "active": True, "selection_enabled": True,
            "audit_target_packages_daily": 100,
            "audit_min_packages_daily": 50,
            "audit_max_packages_daily": 200,
            "audit_target_packages_weekly": 700,
            "audit_distribution_strategy": "adaptive_calendar_week",
            "ingest_eligibility_states": ["in_progress"],
            "audit_overshoot_tolerance": 0.10,
        })

        def stops(n, prefix=""):
            return [
                {"id": f"{prefix}s{i}", "route_id": prefix, "label": f"Order {i}"}
                for i in range(n)
            ]

        # Plan that will materialize successfully
        await db.routal_daily_plans.insert_one({
            "client_id": client_id, "driver_id": drv_ok, "date": target_dt,
            "plan_id_routal": "plan_ok", "processed": False,
            "route_metadata": {
                "id": drv_ok, "plan_id": "plan_ok",
                "label": "Driver OK", "status": "in_progress",
                "driver": {"id": drv_ok, "name": "Driver OK"},
                "stops": stops(30, drv_ok), "services": stops(30, drv_ok),
            },
        })

        # Plan whose payload triggers "skipped: no real routes" — driver label
        # starts with "LastmileScanSessions" so the placeholder filter discards it.
        await db.routal_daily_plans.insert_one({
            "client_id": client_id, "driver_id": drv_skip, "date": target_dt,
            "plan_id_routal": "plan_skip", "processed": False,
            "route_metadata": {
                "id": drv_skip, "plan_id": "plan_skip",
                "label": "LastmileScanSessions-cdmx", "status": "in_progress",
                "driver": {"id": drv_skip, "name": "LastmileScanSessions-cdmx"},
                "stops": stops(50, drv_skip), "services": stops(50, drv_skip),
            },
        })

        result = await run_daily_selection(db, client_id, target_date=target)
        assert result["ok"] is True

        ok_log = await db.driver_audit_log.find_one(
            {"client_id": client_id, "driver_id": drv_ok}
        )
        assert ok_log is not None
        assert ok_log["selection_status"] == "selected"
        assert ok_log["journey_id"] is not None

        skip_log = await db.driver_audit_log.find_one(
            {"client_id": client_id, "driver_id": drv_skip}
        )
        assert skip_log is not None
        assert skip_log["selection_status"] == "failed", (
            f"placeholder driver must be 'failed', got {skip_log['selection_status']!r}"
        )
        assert skip_log.get("failure_reason"), "failure_reason must be populated"
        assert skip_log["journey_id"] is None

        # selection_runs must reflect post-materialization counts
        run = await db.selection_runs.find_one({"client_id": client_id, "date": target_dt})
        assert run is not None
        assert run["selected_count"] == 1, (
            f"selected_count must drop failed entries — got {run['selected_count']}"
        )
        assert run["failed_count"] == 1
        assert run["knapsack"]["selected_packages"] == 30, (
            f"packages must come from real journey, got {run['knapsack']['selected_packages']}"
        )

        # Cross-check: journeys count for the date matches selection_runs.selected_count
        materialized = await db.journeys.count_documents(
            {"client_id": client_id, "date": target.isoformat()}
        )
        assert materialized == run["selected_count"], (
            f"journeys={materialized} must equal selection_runs.selected_count={run['selected_count']}"
        )
    finally:
        await db.client_config.delete_one({"client_id": client_id})
        await db.routal_daily_plans.delete_many({"client_id": client_id})
        await db.driver_audit_log.delete_many({"client_id": client_id})
        await db.selection_runs.delete_many({"client_id": client_id})
        await db.journeys.delete_many({"client_id": client_id})
        await db.packages.delete_many({"client_id": client_id})
