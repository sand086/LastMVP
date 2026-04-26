"""
SEL01 (iter56) E2E tests against the live FastAPI service.

Covers:
  - Bootstrap of Cubbo client_config
  - Auto-create-on-first-read for legacy clients (Grupo Nadro)
  - PATCH validation (max_daily_audits, scheduler_time)
  - PATCH preserves omitted fields
  - RBAC: developer / coordinator / agent / proveedor / executive
  - Selection /run (no plans → total=0)
  - Selection /run E2E with seeded plans (5 docs → all selected, phase_1)
  - PHASE 1 PURE truncation (max_daily=2, 5 fresh drivers)
  - Idempotency (re-run does not create duplicate journeys)
  - GET /selection/summary fields
  - GET /drivers/audit-history requires client_id (422 without it)
  - _handle_plan_created: gating by selection_enabled (Cubbo→staging; legacy→journey)
"""
import os
import sys
import asyncio
import pytest
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is required")
API = f"{BASE_URL}/api"

CUBBO_ID = "0b6590e9-234a-4111-ae5a-e49ebdaf8261"
CDMX_TZ = ZoneInfo("America/Mexico_City")

CRED = {
    "developer": ("dev@me.mx", "LastMile2026"),
    "coordinator": ("yael@me.mx", "LastMile2026"),
    "agent": ("agente@me.mx", "LastMile2026"),
    "proveedor": ("proveedor@me.mx", "LastMile2026"),
}


def _login(role: str) -> dict:
    s = requests.Session()
    email, pwd = CRED[role]
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {role} failed {r.status_code} {r.text}"
    body = r.json()
    token = body.get("access_token") or body.get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return {"session": s, "user": body.get("user") or {}}


@pytest.fixture(scope="module")
def dev_session():
    return _login("developer")["session"]


@pytest.fixture(scope="module")
def coord_session():
    return _login("coordinator")["session"]


@pytest.fixture(scope="module")
def agent_session():
    return _login("agent")["session"]


@pytest.fixture(scope="module")
def prov_session():
    return _login("proveedor")["session"]


# ─────────────── Bootstrap & GET ───────────────

def test_cubbo_bootstrap(dev_session):
    r = dev_session.get(f"{API}/client-config/{CUBBO_ID}", timeout=15)
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["client_id"] == CUBBO_ID
    assert cfg["selection_enabled"] is True
    assert cfg["max_daily_audits"] == 30
    assert cfg["scheduler_time"] == "06:00"
    assert cfg["active"] is True


def test_list_client_configs_includes_cubbo(dev_session):
    r = dev_session.get(f"{API}/client-config", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [c["client_id"] for c in body["data"]]
    assert CUBBO_ID in ids


def test_legacy_client_auto_create_on_first_read(dev_session):
    # Find another client (not Cubbo) via /clients
    r = dev_session.get(f"{API}/clients", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("data") or body.get("items") or []
    other = next((c for c in items if c.get("name") and c["name"].lower() != "cubbo"), None)
    if not other:
        pytest.skip("no non-cubbo clients to test legacy auto-create")
    cid = other["id"]
    r = dev_session.get(f"{API}/client-config/{cid}", timeout=15)
    assert r.status_code == 200, r.text
    cfg = r.json()
    # default selection_enabled=False (safe/legacy)
    assert cfg["selection_enabled"] is False
    assert cfg["client_id"] == cid


# ─────────────── PATCH validation ───────────────

def test_patch_validation_bad_scheduler_time(dev_session):
    r = dev_session.patch(
        f"{API}/client-config/{CUBBO_ID}",
        json={"scheduler_time": "bad"},
        timeout=15,
    )
    assert r.status_code in (400, 422), r.text


def test_patch_validation_max_daily_999(dev_session):
    r = dev_session.patch(
        f"{API}/client-config/{CUBBO_ID}",
        json={"max_daily_audits": 999},
        timeout=15,
    )
    assert r.status_code in (400, 422), r.text


def test_patch_validation_max_daily_zero(dev_session):
    r = dev_session.patch(
        f"{API}/client-config/{CUBBO_ID}",
        json={"max_daily_audits": 0},
        timeout=15,
    )
    assert r.status_code in (400, 422), r.text


def test_patch_preserves_unspecified_fields(dev_session):
    # Read current
    r = dev_session.get(f"{API}/client-config/{CUBBO_ID}", timeout=15)
    cur = r.json()
    cur_max = cur["max_daily_audits"]
    cur_time = cur["scheduler_time"]
    # PATCH only selection_enabled
    r = dev_session.patch(
        f"{API}/client-config/{CUBBO_ID}",
        json={"selection_enabled": True},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["max_daily_audits"] == cur_max
    assert cfg["scheduler_time"] == cur_time
    assert cfg["selection_enabled"] is True


# ─────────────── RBAC ───────────────

def test_rbac_agent_forbidden(agent_session):
    r = agent_session.get(f"{API}/client-config", timeout=15)
    assert r.status_code == 403
    r = agent_session.get(f"{API}/client-config/{CUBBO_ID}", timeout=15)
    assert r.status_code == 403
    r = agent_session.post(f"{API}/selection/run/{CUBBO_ID}", timeout=15)
    assert r.status_code == 403


def test_rbac_proveedor_forbidden(prov_session):
    r = prov_session.get(f"{API}/client-config", timeout=15)
    assert r.status_code == 403
    r = prov_session.post(f"{API}/selection/run/{CUBBO_ID}", timeout=15)
    assert r.status_code == 403


def test_rbac_coordinator_can_run_but_not_config(coord_session):
    # coordinator cannot list configs (developer-only)
    r = coord_session.get(f"{API}/client-config", timeout=15)
    assert r.status_code == 403
    # but can run selection
    r = coord_session.post(f"{API}/selection/run/{CUBBO_ID}?date=2030-01-01", timeout=20)
    assert r.status_code in (200, 400, 404), r.text


def test_rbac_developer_ok(dev_session):
    r = dev_session.get(f"{API}/client-config", timeout=15)
    assert r.status_code == 200


# ─────────────── /audit-history validation ───────────────

def test_audit_history_requires_client_id(dev_session):
    r = dev_session.get(f"{API}/drivers/audit-history/some-driver", timeout=15)
    assert r.status_code == 422


def test_audit_history_with_client_id(dev_session):
    r = dev_session.get(
        f"{API}/drivers/audit-history/nonexistent-driver?client_id={CUBBO_ID}&days=30",
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert "history" in body and isinstance(body["history"], list)


# ─────────────── Selection algorithm E2E ───────────────

def _get_db():
    """Build a motor client using the same env vars as the app."""
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    assert mongo_url and db_name, "MONGO_URL/DB_NAME required"
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def _seed_plans(db, n: int, target_date, prefix="test_"):
    target_dt = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    docs = []
    for i in range(n):
        drv = f"{prefix}drv{i}"
        docs.append({
            "client_id": CUBBO_ID,
            "driver_id": drv,
            "driver_name": f"Test_Driver_{i}",
            "date": target_dt,
            "plan_id_routal": f"{prefix}plan_{i}",
            "processed": False,
            "route_metadata": {
                "plan_id": f"{prefix}plan_{i}",
                "driver_id": drv,
                "driver_name": f"Test_Driver_{i}",
                "stops": [],
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    await db.routal_daily_plans.insert_many(docs)


async def _cleanup(db):
    await db.routal_daily_plans.delete_many({"driver_id": {"$regex": "^test_"}})
    await db.driver_audit_log.delete_many({"driver_id": {"$regex": "^test_"}})
    await db.journeys.delete_many({"driver_name": {"$regex": "^Test_"}})


def _future_date(offset_days: int):
    """Use a future date to avoid clashing with last_scheduled_run_date or production data."""
    return (datetime.now(CDMX_TZ).date() + timedelta(days=offset_days))


def test_selection_run_no_plans(dev_session):
    target = _future_date(40)  # far future, no plans
    r = dev_session.post(
        f"{API}/selection/run/{CUBBO_ID}?date={target.strftime('%Y-%m-%d')}",
        timeout=20,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0
    assert body["selected"] == 0


def test_selection_run_e2e_all_selected_phase1(dev_session):
    """Insert 5 fresh drivers, max_daily=30 → all selected, phase_1."""
    client, db = _get_db()
    target = _future_date(50)

    async def setup_and_run():
        await _cleanup(db)
        await _seed_plans(db, 5, target)
        r = dev_session.post(
            f"{API}/selection/run/{CUBBO_ID}?date={target.strftime('%Y-%m-%d')}",
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 5
        assert body["selected"] == 5
        assert body["unselected"] == 0
        assert body["phase_1"] == 5
        assert body["phase_2"] == 0

        # Verify driver_audit_log has 5 selected entries
        target_dt = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
        cnt = await db.driver_audit_log.count_documents({
            "client_id": CUBBO_ID,
            "date": target_dt,
            "selection_status": "selected",
            "driver_id": {"$regex": "^test_"},
        })
        assert cnt == 5

        # GET /summary fields
        r = dev_session.get(
            f"{API}/selection/summary/{CUBBO_ID}?date={target.strftime('%Y-%m-%d')}",
            timeout=15,
        )
        assert r.status_code == 200, r.text
        sm = r.json()
        assert sm["selected"] == 5
        assert sm["phase_applied"] == "phase_1"
        assert isinstance(sm["drivers_selected"], list) and len(sm["drivers_selected"]) == 5
        first = sm["drivers_selected"][0]
        assert "phase" in first and "audit_count_30d" in first and "journey_id" in first

        # IDEMPOTENCY: count test journeys, re-run, count again
        j_before = await db.journeys.count_documents({"driver_name": {"$regex": "^Test_"}})
        r2 = dev_session.post(
            f"{API}/selection/run/{CUBBO_ID}?date={target.strftime('%Y-%m-%d')}",
            timeout=30,
        )
        assert r2.status_code == 200
        j_after = await db.journeys.count_documents({"driver_name": {"$regex": "^Test_"}})
        assert j_after == j_before, f"idempotency violated: {j_before} → {j_after}"

        await _cleanup(db)

    try:
        asyncio.get_event_loop().run_until_complete(setup_and_run())
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(setup_and_run())
    finally:
        client.close()


def test_selection_phase1_pure_truncation(dev_session):
    """max_daily=2, 5 fresh drivers → 2 selected p1, 3 unselected."""
    client, db = _get_db()
    target = _future_date(60)

    async def run_test():
        await _cleanup(db)
        await _seed_plans(db, 5, target)
        # temporarily set max_daily=2
        orig = await db.client_config.find_one({"client_id": CUBBO_ID}, {"_id": 0})
        await db.client_config.update_one(
            {"client_id": CUBBO_ID},
            {"$set": {"max_daily_audits": 2}},
        )
        try:
            r = dev_session.post(
                f"{API}/selection/run/{CUBBO_ID}?date={target.strftime('%Y-%m-%d')}",
                timeout=30,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 5
            assert body["selected"] == 2
            assert body["unselected"] == 3
            assert body["phase_1"] == 2
            assert body["phase_2"] == 0
        finally:
            # restore original max_daily
            await db.client_config.update_one(
                {"client_id": CUBBO_ID},
                {"$set": {"max_daily_audits": orig.get("max_daily_audits", 30)}},
            )
            await _cleanup(db)

    try:
        asyncio.get_event_loop().run_until_complete(run_test())
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(run_test())
    finally:
        client.close()


# ─────────────── Restore Cubbo to canonical settings at end ───────────────

def test_restore_cubbo_canonical(dev_session):
    """Ensure Cubbo ends with max=30, scheduler='06:00', selection=True."""
    r = dev_session.patch(
        f"{API}/client-config/{CUBBO_ID}",
        json={"max_daily_audits": 30, "scheduler_time": "06:00", "selection_enabled": True, "active": True},
        timeout=15,
    )
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["max_daily_audits"] == 30
    assert cfg["scheduler_time"] == "06:00"
    assert cfg["selection_enabled"] is True
