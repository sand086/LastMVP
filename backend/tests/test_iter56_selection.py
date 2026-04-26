"""
Tests for R00B / SEL01 — Routal selection algorithm + scheduler.
Pure-function tests of the selection algorithm + service-level upsert validation.
"""
import os
import sys
from datetime import date, datetime, timezone
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lastmile_iter56")


# ─────────────── ALGORITHM ───────────────

def test_algorithm_phase_1_pure():
    """All drivers fresh + more than max_daily → phase_1 pure (random sample)."""
    from workers.routal_selection_worker import _select_drivers
    drivers = [f"d{i}" for i in range(20)]
    selected, phases = _select_drivers(
        drivers_today=drivers,
        audited_yesterday=set(),
        audit_counts={},
        max_daily=10,
        target_date=date(2026, 1, 15),
    )
    assert len(selected) == 10
    assert all(phases[d] == "phase_1" for d in selected)
    # Deterministic for the same date
    selected2, _ = _select_drivers(drivers, set(), {}, 10, date(2026, 1, 15))
    assert selected == selected2


def test_algorithm_phase_1_partial_plus_phase_2():
    """3 fresh + 7 yesterday, max 5 → 3 phase_1 + 2 phase_2 (lowest count first)."""
    from workers.routal_selection_worker import _select_drivers
    drivers = ["a", "b", "c", "x", "y", "z", "w", "v", "u", "t"]
    audited_yesterday = {"x", "y", "z", "w", "v", "u", "t"}
    audit_counts = {"x": 5, "y": 5, "z": 1, "w": 2, "v": 0, "u": 3, "t": 4}
    selected, phases = _select_drivers(
        drivers_today=drivers,
        audited_yesterday=audited_yesterday,
        audit_counts=audit_counts,
        max_daily=5,
        target_date=date(2026, 1, 15),
    )
    assert len(selected) == 5
    # All fresh ones must be selected (a, b, c)
    assert {"a", "b", "c"}.issubset(set(selected))
    # The 2 phase_2 picks must be those with the lowest counts → v(0), z(1)
    p2_picks = [d for d in selected if phases[d] == "phase_2"]
    assert set(p2_picks) == {"v", "z"}


def test_algorithm_phase_2_pure():
    """Everyone audited yesterday → fall back to count rotation."""
    from workers.routal_selection_worker import _select_drivers
    drivers = ["a", "b", "c", "d", "e"]
    audited_yesterday = set(drivers)
    audit_counts = {"a": 10, "b": 1, "c": 5, "d": 0, "e": 2}
    selected, phases = _select_drivers(
        drivers_today=drivers,
        audited_yesterday=audited_yesterday,
        audit_counts=audit_counts,
        max_daily=2,
        target_date=date(2026, 1, 15),
    )
    assert len(selected) == 2
    assert set(selected) == {"d", "b"}  # lowest counts: 0 and 1
    assert all(phases[d] == "phase_2" for d in selected)


def test_algorithm_fits_entirely():
    """Drivers ≤ max_daily → all selected, phase based on origin."""
    from workers.routal_selection_worker import _select_drivers
    drivers = ["a", "b", "c"]
    selected, phases = _select_drivers(
        drivers_today=drivers,
        audited_yesterday={"b"},
        audit_counts={"b": 3},
        max_daily=10,
        target_date=date(2026, 1, 15),
    )
    assert set(selected) == {"a", "b", "c"}
    assert phases["a"] == "phase_1"
    assert phases["c"] == "phase_1"
    assert phases["b"] == "phase_2"


def test_algorithm_deterministic_seeded():
    """Same date → same selection. Different date → likely different."""
    from workers.routal_selection_worker import _select_drivers
    drivers = [f"d{i}" for i in range(50)]
    s1, _ = _select_drivers(drivers, set(), {}, 10, date(2026, 1, 15))
    s2, _ = _select_drivers(drivers, set(), {}, 10, date(2026, 1, 15))
    s3, _ = _select_drivers(drivers, set(), {}, 10, date(2026, 1, 16))
    assert s1 == s2
    assert s1 != s3  # extremely high probability


# ─────────────── CLIENT CONFIG SERVICE ───────────────

@pytest_asyncio.fixture
async def fake_db():
    db = MagicMock()
    store = {}

    async def find_one(filt, *a, **k):
        return store.get(filt.get("client_id"))

    async def update_one(filt, update, **k):
        cid = filt.get("client_id")
        doc = store.get(cid, {}).copy()
        doc.update(update.get("$set", {}))
        store[cid] = doc
        m = MagicMock(); m.matched_count = 1; m.upserted_id = None; return m

    db.client_config = MagicMock()
    db.client_config.find_one = AsyncMock(side_effect=find_one)
    db.client_config.update_one = AsyncMock(side_effect=update_one)
    return db


@pytest.mark.asyncio
async def test_client_config_upsert_defaults(fake_db):
    from services.client_config_service import ClientConfigService
    svc = ClientConfigService(fake_db)
    cfg = await svc.upsert(client_id="c1", client_name="Cubbo")
    assert cfg["client_id"] == "c1"
    assert cfg["max_daily_audits"] == 30
    assert cfg["selection_enabled"] is False
    assert cfg["scheduler_time"] == "06:00"
    assert cfg["active"] is True


@pytest.mark.asyncio
async def test_client_config_validates_time(fake_db):
    from services.client_config_service import ClientConfigService
    svc = ClientConfigService(fake_db)
    with pytest.raises(ValueError):
        await svc.upsert(client_id="c1", client_name="Cubbo", scheduler_time="bad")


@pytest.mark.asyncio
async def test_client_config_validates_max_daily(fake_db):
    from services.client_config_service import ClientConfigService
    svc = ClientConfigService(fake_db)
    with pytest.raises(ValueError):
        await svc.upsert(client_id="c1", client_name="Cubbo", max_daily_audits=0)
    with pytest.raises(ValueError):
        await svc.upsert(client_id="c1", client_name="Cubbo", max_daily_audits=600)
    cfg = await svc.upsert(client_id="c1", client_name="Cubbo", max_daily_audits=50)
    assert cfg["max_daily_audits"] == 50


@pytest.mark.asyncio
async def test_client_config_partial_update_preserves_fields(fake_db):
    from services.client_config_service import ClientConfigService
    svc = ClientConfigService(fake_db)
    await svc.upsert(client_id="c1", client_name="Cubbo", max_daily_audits=30, selection_enabled=True)
    # Only flip selection_enabled
    cfg = await svc.upsert(client_id="c1", client_name="Cubbo", selection_enabled=False)
    assert cfg["max_daily_audits"] == 30  # preserved
    assert cfg["selection_enabled"] is False
    assert cfg["scheduler_time"] == "06:00"
