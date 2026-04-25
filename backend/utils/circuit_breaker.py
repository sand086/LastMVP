"""
Circuit Breaker simple (sin deps externas) para integraciones inestables.
Estados: CLOSED → OPEN → HALF_OPEN → CLOSED.

Uso típico:
    cb = get_circuit_breaker("llm")
    if cb.is_open():
        raise CircuitOpenError("LLM circuit open, skipping")
    try:
        result = await call_llm()
        cb.record_success()
    except Exception:
        cb.record_failure()
        raise
"""
import time
import threading
from typing import Dict


class CircuitOpenError(Exception):
    """El circuito está abierto — no se debe ejecutar la operación."""
    pass


class CircuitBreaker:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        open_timeout_seconds: int = 60,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.open_timeout_seconds = open_timeout_seconds

        self._state = self.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def _now(self) -> float:
        return time.monotonic()

    def is_open(self) -> bool:
        """Returns True si la operación NO debe ejecutarse."""
        with self._lock:
            if self._state == self.CLOSED:
                return False
            if self._state == self.OPEN:
                # Timeout cumplido → pasar a HALF_OPEN (permite 1 intento de prueba)
                if self._now() - self._opened_at >= self.open_timeout_seconds:
                    self._state = self.HALF_OPEN
                    return False
                return True
            # HALF_OPEN: permite 1 intento de prueba
            return False

    def record_success(self):
        with self._lock:
            self._failure_count = 0
            if self._state in (self.OPEN, self.HALF_OPEN):
                self._state = self.CLOSED

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            if self._state == self.HALF_OPEN:
                # Falla en prueba → re-OPEN
                self._state = self.OPEN
                self._opened_at = self._now()
            elif self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                self._opened_at = self._now()

    def status(self) -> dict:
        with self._lock:
            seconds_open = max(0, self._now() - self._opened_at) if self._state != self.CLOSED else 0
            seconds_until_retry = max(0, self.open_timeout_seconds - seconds_open) if self._state == self.OPEN else 0
            return {
                "name": self.name,
                "state": self._state,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "open_timeout_seconds": self.open_timeout_seconds,
                "seconds_until_retry": round(seconds_until_retry),
            }


# ─── Registry: cada nombre tiene una instancia única (process-local) ───
_BREAKERS: Dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    open_timeout_seconds: int = 60,
) -> CircuitBreaker:
    with _REGISTRY_LOCK:
        cb = _BREAKERS.get(name)
        if cb is None:
            cb = CircuitBreaker(name, failure_threshold, open_timeout_seconds)
            _BREAKERS[name] = cb
        return cb


def all_breaker_status() -> dict:
    """Snapshot de todos los breakers para el endpoint de health."""
    with _REGISTRY_LOCK:
        return {name: cb.status() for name, cb in _BREAKERS.items()}
