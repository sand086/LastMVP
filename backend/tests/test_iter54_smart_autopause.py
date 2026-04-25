"""Tests for P09 Smart Autopause (iter54)."""
import os
import sys
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lastmile_iter54")


@pytest.fixture
def mock_db():
    """Mock db with token_usage_log.aggregate and config.update_one + find_one."""
    db = MagicMock()
    # aggregate returns an object with .to_list()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    db.token_usage_log = MagicMock()
    db.token_usage_log.aggregate = MagicMock(return_value=cursor)

    db.config = MagicMock()
    db.config.find_one = AsyncMock(return_value=None)
    db.config.update_one = AsyncMock(return_value=MagicMock(matched_count=1))

    db._cursor = cursor
    return db


@pytest.fixture(autouse=True)
def clear_config_cache():
    from ai_eval_config import invalidate_cache
    invalidate_cache()
    yield
    invalidate_cache()


@pytest.mark.asyncio
async def test_autopause_disabled_does_not_trigger(mock_db):
    from ai_eval_worker import _check_shadow_autopause
    cfg = {"shadow_autopause_enabled": False, "shadow_threshold_pct": 1}
    triggered = await _check_shadow_autopause(mock_db, cfg)
    assert triggered is False
    # No DB call when disabled
    mock_db.token_usage_log.aggregate.assert_not_called()


@pytest.mark.asyncio
async def test_autopause_below_threshold_does_not_trigger(mock_db):
    from ai_eval_worker import _check_shadow_autopause
    # 5 shadow / 50 total = 10% which is exactly at threshold of 10
    # but cost-based: 0.05 / 1.00 = 5% → below
    mock_db._cursor.to_list = AsyncMock(return_value=[{
        "total_events": 50, "shadow_events": 5,
        "total_cost": 1.00, "shadow_cost": 0.05,
    }])
    cfg = {
        "shadow_autopause_enabled": True,
        "shadow_threshold_pct": 10,
        "shadow_window_minutes": 15,
        "shadow_min_events": 10,
        "shadow_autopause_minutes": 20,
    }
    triggered = await _check_shadow_autopause(mock_db, cfg)
    assert triggered is False
    mock_db.config.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_autopause_above_threshold_triggers(mock_db):
    from ai_eval_worker import _check_shadow_autopause
    # 0.30 / 1.00 = 30% >> 10% threshold
    mock_db._cursor.to_list = AsyncMock(return_value=[{
        "total_events": 50, "shadow_events": 18,
        "total_cost": 1.00, "shadow_cost": 0.30,
    }])
    cfg = {
        "shadow_autopause_enabled": True,
        "shadow_threshold_pct": 10,
        "shadow_window_minutes": 15,
        "shadow_min_events": 10,
        "shadow_autopause_minutes": 20,
    }
    triggered = await _check_shadow_autopause(mock_db, cfg)
    assert triggered is True
    # Pause was persisted
    mock_db.config.update_one.assert_called_once()
    args, kwargs = mock_db.config.update_one.call_args
    persisted = kwargs.get("upsert") or args[1] if len(args) > 1 else None
    # Inspect the $set payload
    update = args[1] if len(args) > 1 else kwargs.get("update", {})
    set_payload = update.get("$set", {})
    value = set_payload.get("value", {})
    assert value.get("paused_until") is not None
    reason = value.get("pause_reason", "")
    assert "30.0%" in reason or "30%" in reason
    assert "shadow" in reason.lower()


@pytest.mark.asyncio
async def test_autopause_below_min_events_does_not_trigger(mock_db):
    from ai_eval_worker import _check_shadow_autopause
    # Even if 100% shadow, only 5 events → below baseline of 10
    mock_db._cursor.to_list = AsyncMock(return_value=[{
        "total_events": 5, "shadow_events": 5,
        "total_cost": 0.05, "shadow_cost": 0.05,
    }])
    cfg = {
        "shadow_autopause_enabled": True,
        "shadow_threshold_pct": 10,
        "shadow_window_minutes": 15,
        "shadow_min_events": 10,
        "shadow_autopause_minutes": 20,
    }
    triggered = await _check_shadow_autopause(mock_db, cfg)
    assert triggered is False
    mock_db.config.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_autopause_count_fallback_when_no_cost(mock_db):
    from ai_eval_worker import _check_shadow_autopause
    # Costs zero (no pricing config) → fallback to event count: 25/50 = 50%
    mock_db._cursor.to_list = AsyncMock(return_value=[{
        "total_events": 50, "shadow_events": 25,
        "total_cost": 0, "shadow_cost": 0,
    }])
    cfg = {
        "shadow_autopause_enabled": True,
        "shadow_threshold_pct": 10,
        "shadow_window_minutes": 15,
        "shadow_min_events": 10,
        "shadow_autopause_minutes": 20,
    }
    triggered = await _check_shadow_autopause(mock_db, cfg)
    assert triggered is True
    mock_db.config.update_one.assert_called_once()
