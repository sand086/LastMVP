"""Load test del AIGateway — 1000 invocaciones concurrentes (P2 · PROMPT 26).

Objetivo: validar correctness bajo concurrencia (sin race conditions en cache,
consumo y log) + medir p50/p95/p99 latencia local del gateway.

Provider mockeado para no gastar tokens. Mide:
  - throughput total
  - p50/p95/p99 latencia
  - integridad: invocaciones exitosas == requests esperados
  - cache: hits + misses == requests
  - consumo: total cost == sum(individual costs no-cache)
  - log: append-only, sin duplicados
"""
from __future__ import annotations
import asyncio
import time
import statistics

import pytest

from core.uuid import new_id
from repositories.ai import (
    AIBracketRepository, AIClientConfigRepository,
    AIConsumptionRepository, AIInvocationLogRepository,
)
from seeds.ai_catalog import run as seed_ai
from services.ai import gateway as ai_gateway
from services.ai.prompt_cache import cache as prompt_cache


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(pct / 100 * (len(s) - 1)))))
    return s[k]


@pytest.fixture
async def load_setup(db):
    await seed_ai()
    tid = new_id()
    uid = new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "load", "name": "Load",
                                 "status": "active"})
    await db.users.insert_one({"id": uid, "tenant_id": tid, "email": "l@l",
                               "role": "agent", "status": "active"})
    await db.clients.insert_one({"id": cl_id, "tenant_id": tid, "name": "ClLoad"})
    bracket = await AIBracketRepository().by_name("enterprise")  # cap alto
    await AIClientConfigRepository(tenant_id=tid).upsert({
        "client_id": cl_id, "bracket_id": bracket["id"],
        "enabled_features": ["classify_motivo", "summarize_timeline"],
        "is_active": True, "opt_in_signature": "Load test",
    })
    return {"tenant_id": tid, "user_id": uid, "client_id": cl_id}


class TestAILoad:
    """Load tests del AIGateway con provider mockeado."""

    async def test_1k_concurrent_invocations_no_race_conditions(
        self, load_setup, monkeypatch, db,
    ):
        """1000 invocaciones concurrentes — diferentes prompts (sin cache hits)."""
        N = 1000
        await prompt_cache.clear()

        # Provider mock: latencia simulada 5ms uniforme
        async def fake_call(provider, model, system, prompt, api_key, **kw):
            await asyncio.sleep(0.005)
            return {"text": "EXTRAVIO", "input_tokens": 100,
                    "output_tokens": 5, "latency_ms": 5}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test")

        latencies: list[float] = []
        results: list = []

        async def one_invoke(i: int):
            start = time.monotonic()
            r = await ai_gateway.invoke(
                tenant_id=load_setup["tenant_id"],
                client_id=load_setup["client_id"],
                user_id=load_setup["user_id"],
                feature_code="summarize_timeline",
                # Único por invocación — fuerza miss en cache
                raw_input={"events": [f"evento-{i}"]},
            )
            latencies.append((time.monotonic() - start) * 1000)
            results.append(r)
            return r

        started = time.monotonic()
        # Limitar fan-out con semaphore para no asfixiar el event loop ni mongo
        sem = asyncio.Semaphore(64)

        async def guarded(i):
            async with sem:
                return await one_invoke(i)

        await asyncio.gather(*[guarded(i) for i in range(N)])
        total_ms = (time.monotonic() - started) * 1000

        # Correctness
        successes = sum(1 for r in results if r.ok)
        assert successes == N, f"Esperados {N} ok, obtenidos {successes}"

        # Log: exactamente N entradas (append-only sin duplicados)
        log_count = await db.ai_invocation_log.count_documents({
            "tenant_id": load_setup["tenant_id"], "status": "success",
        })
        assert log_count == N, f"Log esperaba {N}, tiene {log_count}"

        # Consumo: total_cost_usd debe ser positivo y consistente
        cons_repo = AIConsumptionRepository(tenant_id=load_setup["tenant_id"])
        cons = await cons_repo.get_or_init(load_setup["client_id"])
        assert cons["invocations_count"] == N
        # Cada invocación gastó misma cantidad → total = N * unit_cost
        sum_individual = sum(r.data["cost_estimate_usd"] for r in results)
        assert abs(cons["total_cost_usd"] - sum_individual) < 1e-4, (
            f"Race condition en consumo: cons={cons['total_cost_usd']} "
            f"vs sum={sum_individual}"
        )

        # Métricas de latencia
        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        p99 = _percentile(latencies, 99)
        throughput = N / (total_ms / 1000)
        print(f"\n[LOAD] N={N} duration={total_ms:.0f}ms throughput={throughput:.1f} req/s")
        print(f"[LOAD] p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms")
        # Sanity bounds (con provider mockeado a 5ms y semaphore 64,
        # la latencia individual debería ser < 500ms en p99 incluso bajo presión).
        assert p99 < 2000, f"p99={p99}ms es demasiado alto"

    async def test_1k_concurrent_with_cache_hits(self, load_setup, monkeypatch, db):
        """1000 invocaciones concurrentes con MISMO prompt → solo el primero
        gasta API, los 999 restantes deben ser cache hits."""
        N = 1000
        await prompt_cache.clear()

        call_count = {"n": 0}
        async def fake_call(provider, model, system, prompt, api_key, **kw):
            call_count["n"] += 1
            await asyncio.sleep(0.005)
            return {"text": "DAÑO_PAQUETE", "input_tokens": 100,
                    "output_tokens": 5, "latency_ms": 5}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test")

        # Pre-warm cache con una invocación primero (clasifyMotivo tiene cache_enabled=true)
        first = await ai_gateway.invoke(
            tenant_id=load_setup["tenant_id"],
            client_id=load_setup["client_id"],
            user_id=load_setup["user_id"],
            feature_code="classify_motivo",
            raw_input={"description": "Caja rota"},
        )
        assert first.ok
        assert call_count["n"] == 1, "Primera llamada debe gastar provider"

        # 1000 con MISMO input — todas cache hits
        sem = asyncio.Semaphore(64)
        results = []
        async def guarded():
            async with sem:
                r = await ai_gateway.invoke(
                    tenant_id=load_setup["tenant_id"],
                    client_id=load_setup["client_id"],
                    user_id=load_setup["user_id"],
                    feature_code="classify_motivo",
                    raw_input={"description": "Caja rota"},
                )
                results.append(r)
        await asyncio.gather(*[guarded() for _ in range(N)])

        # Provider llamado SÓLO 1 vez (la pre-warm) — ningún hit más
        assert call_count["n"] == 1, (
            f"Esperaba 1 call al provider, hubo {call_count['n']}. "
            "Race condition en cache."
        )

        # Todos succesful y from_cache=true
        from_cache_count = sum(1 for r in results if r.ok and r.data.get("from_cache"))
        assert from_cache_count == N

        # Costo: solo la primera contó. cons_repo.invocations_count == 1.
        cons = await AIConsumptionRepository(
            tenant_id=load_setup["tenant_id"]
        ).get_or_init(load_setup["client_id"])
        assert cons["invocations_count"] == 1, (
            f"Cache hits NO deben contar al consumo. invocations={cons['invocations_count']}"
        )

    async def test_concurrent_invocations_log_append_only(self, load_setup, monkeypatch, db):
        """Verifica que NO hay duplicate keys en el log bajo presión concurrente."""
        N = 200
        await prompt_cache.clear()
        async def fake_call(provider, model, system, prompt, api_key, **kw):
            await asyncio.sleep(0.001)
            return {"text": "OK", "input_tokens": 50, "output_tokens": 3, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test")

        await asyncio.gather(*[
            ai_gateway.invoke(
                tenant_id=load_setup["tenant_id"],
                client_id=load_setup["client_id"],
                user_id=load_setup["user_id"],
                feature_code="summarize_timeline",
                raw_input={"events": [f"e-{i}-{j}" for j in range(3)]},
            ) for i in range(N)
        ])

        # Verificar uniqueness de id
        log_repo = AIInvocationLogRepository(tenant_id=load_setup["tenant_id"])
        logs = await log_repo.query({}, limit=N + 50)
        ids = [l["id"] for l in logs]
        assert len(ids) == len(set(ids)), "Log tiene IDs duplicados (race en uuid?)"
        assert len(ids) >= N
