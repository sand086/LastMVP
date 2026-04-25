"""Tests for P04 Circuit Breaker (iter52)."""
import os
import sys
import time
import pytest

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lastmile_iter52")


def test_breaker_starts_closed():
    from utils.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("test1", failure_threshold=3, open_timeout_seconds=1)
    assert cb.is_open() is False
    assert cb.status()["state"] == "CLOSED"


def test_breaker_opens_after_threshold():
    from utils.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("test2", failure_threshold=3, open_timeout_seconds=1)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is False  # 2 failures, no open yet
    cb.record_failure()
    assert cb.is_open() is True
    assert cb.status()["state"] == "OPEN"


def test_breaker_recovers_after_timeout():
    from utils.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("test3", failure_threshold=2, open_timeout_seconds=1)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is True
    time.sleep(1.1)
    # Después del timeout, primer is_open() debe pasar a HALF_OPEN
    assert cb.is_open() is False
    assert cb.status()["state"] == "HALF_OPEN"
    # Si la siguiente operación tiene éxito → CLOSED
    cb.record_success()
    assert cb.status()["state"] == "CLOSED"
    assert cb.status()["failure_count"] == 0


def test_breaker_half_open_failure_reopens():
    from utils.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker("test4", failure_threshold=2, open_timeout_seconds=1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(1.1)
    cb.is_open()  # transition CLOSED → HALF_OPEN
    cb.record_failure()  # HALF_OPEN failure → re-OPEN
    assert cb.is_open() is True
    assert cb.status()["state"] == "OPEN"


def test_breaker_registry_singleton():
    from utils.circuit_breaker import get_circuit_breaker
    cb1 = get_circuit_breaker("shared", failure_threshold=10)
    cb2 = get_circuit_breaker("shared", failure_threshold=99)  # threshold ignored on 2nd call
    assert cb1 is cb2
    assert cb1.failure_threshold == 10  # original wins


def test_all_breaker_status_returns_snapshot():
    from utils.circuit_breaker import get_circuit_breaker, all_breaker_status
    get_circuit_breaker("snap_a", failure_threshold=5)
    get_circuit_breaker("snap_b", failure_threshold=5)
    snap = all_breaker_status()
    assert "snap_a" in snap
    assert "snap_b" in snap
    assert snap["snap_a"]["state"] == "CLOSED"
