"""Cache LRU+TTL de respuestas LLM (P1 · PROMPT 26).

Reduce gasto en prompts repetidos dentro de una ventana de tiempo. La cache
se ENTRADA por (tenant_id, feature_code, model, prompt_hash) y NUNCA cruza
tenants.

Una feature puede oponerse al cache si tiene `cache_enabled=False`. Default
también es False (opt-in explícito por feature) — sólo features deterministas
como classify_motivo deberían activarlo.

CACHE_TTL_S env: default 300 (5 min)
CACHE_MAX_ENTRIES env: default 1024 (LRU)
"""
from __future__ import annotations
import asyncio
import os
import time
from collections import OrderedDict
from dataclasses import dataclass

_TTL_S = float(os.environ.get("AI_CACHE_TTL_S", "300"))
_MAX = int(os.environ.get("AI_CACHE_MAX_ENTRIES", "1024"))


@dataclass
class _Entry:
    value: dict          # {text, input_tokens, output_tokens, latency_ms}
    expires_at: float
    hits: int = 0


class _PromptCache:
    def __init__(self) -> None:
        self._od: "OrderedDict[str, _Entry]" = OrderedDict()
        self._lock = asyncio.Lock()
        self.metrics = {"hits": 0, "misses": 0, "stores": 0, "evictions": 0}

    @staticmethod
    def _key(tenant_id: str, feature_code: str, model: str, prompt_hash: str) -> str:
        return f"{tenant_id}|{feature_code}|{model}|{prompt_hash}"

    async def get(self, tenant_id: str, feature_code: str, model: str, prompt_hash: str) -> dict | None:
        async with self._lock:
            k = self._key(tenant_id, feature_code, model, prompt_hash)
            e = self._od.get(k)
            now = time.monotonic()
            if not e:
                self.metrics["misses"] += 1
                return None
            if e.expires_at <= now:
                self._od.pop(k, None)
                self.metrics["misses"] += 1
                return None
            # LRU: mover al final
            self._od.move_to_end(k)
            e.hits += 1
            self.metrics["hits"] += 1
            return dict(e.value)

    async def put(self, tenant_id: str, feature_code: str, model: str, prompt_hash: str, value: dict) -> None:
        async with self._lock:
            k = self._key(tenant_id, feature_code, model, prompt_hash)
            self._od[k] = _Entry(value=dict(value), expires_at=time.monotonic() + _TTL_S)
            self._od.move_to_end(k)
            self.metrics["stores"] += 1
            while len(self._od) > _MAX:
                self._od.popitem(last=False)
                self.metrics["evictions"] += 1

    async def clear(self) -> None:
        async with self._lock:
            self._od.clear()


cache = _PromptCache()
