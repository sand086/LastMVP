"""Circuit Breaker para proveedores LLM (P1 · PROMPT 26).

Estados:
  CLOSED      → todo OK, las llamadas pasan
  OPEN        → último N de N falló, todas las llamadas se rechazan inmediatamente
  HALF_OPEN   → tras un timeout, se permite 1 sonda; si OK → CLOSED, si falla → OPEN

Memory-only, por proveedor (anthropic/openai/gemini/...).

Default thresholds (configurables vía env):
  AI_BREAKER_FAILURES   (default 5)
  AI_BREAKER_WINDOW_S   (default 60)
  AI_BREAKER_COOLDOWN_S (default 30)
"""
from __future__ import annotations
import asyncio
import os
import time
from dataclasses import dataclass, field

_FAILURES = int(os.environ.get("AI_BREAKER_FAILURES", "5"))
_WINDOW_S = float(os.environ.get("AI_BREAKER_WINDOW_S", "60"))
_COOLDOWN_S = float(os.environ.get("AI_BREAKER_COOLDOWN_S", "30"))


@dataclass
class _BreakerState:
    failures: list[float] = field(default_factory=list)
    state: str = "closed"          # closed · open · half_open
    opened_at: float = 0.0


class CircuitBreaker:
    def __init__(self) -> None:
        self._states: dict[str, _BreakerState] = {}
        self._lock = asyncio.Lock()

    def _prune(self, st: _BreakerState, now: float) -> None:
        cutoff = now - _WINDOW_S
        st.failures = [t for t in st.failures if t >= cutoff]

    async def allow(self, provider: str) -> tuple[bool, str | None]:
        """Devuelve (allowed, reason). reason está poblado cuando allowed=False."""
        async with self._lock:
            now = time.monotonic()
            st = self._states.setdefault(provider, _BreakerState())
            self._prune(st, now)

            if st.state == "closed":
                return True, None

            if st.state == "open":
                if (now - st.opened_at) >= _COOLDOWN_S:
                    st.state = "half_open"
                    return True, None  # sonda
                return False, f"breaker_open_{int(_COOLDOWN_S - (now - st.opened_at))}s_left"

            # half_open → permitir 1 sonda; el estado se resuelve en record_*
            return True, None

    async def record_success(self, provider: str) -> None:
        async with self._lock:
            st = self._states.setdefault(provider, _BreakerState())
            st.failures.clear()
            st.state = "closed"
            st.opened_at = 0.0

    async def record_failure(self, provider: str) -> None:
        async with self._lock:
            now = time.monotonic()
            st = self._states.setdefault(provider, _BreakerState())
            self._prune(st, now)
            st.failures.append(now)
            if st.state == "half_open" or len(st.failures) >= _FAILURES:
                st.state = "open"
                st.opened_at = now

    def status_snapshot(self) -> dict[str, dict]:
        out = {}
        now = time.monotonic()
        for k, st in self._states.items():
            out[k] = {
                "state": st.state,
                "failures_in_window": len(st.failures),
                "cooldown_remaining_s": max(0, int(_COOLDOWN_S - (now - st.opened_at)))
                    if st.state == "open" else 0,
            }
        return out


breaker = CircuitBreaker()
