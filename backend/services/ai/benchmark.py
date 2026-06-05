"""Benchmark cost-vs-latency por modelo (P2 · PROMPT 26).

Dos modos:
  dry_run=True (default): estima costos desde MODEL_PRICING + heurísticas de
                          tokens promedio. NO gasta tokens reales.
  dry_run=False:          ejecuta N invocaciones REALES contra cada modelo
                          con un prompt fijo, mide latency_ms y tokens.
                          REQUIERE superadmin Y EMERGENT_LLM_KEY.

Resultado se persiste en `ai_benchmarks` con timestamp para tracking histórico.
"""
from __future__ import annotations
import os
import statistics
from datetime import datetime, timezone

from core.db import get_db
from core.uuid import new_id
from services.ai.gateway import MODEL_PRICING, _call_provider, _GatewayError


_BENCHMARK_PROMPT = (
    "Resume en una sola línea, en español, este evento operativo: "
    "El paquete fue entregado correctamente al destinatario."
)
_BENCHMARK_SYSTEM = "Eres un asistente operativo de logística."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(pct / 100 * (len(s) - 1)))))
    return s[k]


async def _measure_dry_run(model: str, *, samples: int = 1) -> dict:
    """No llama al provider — estima desde tabla y heurísticas."""
    in_rate, out_rate = MODEL_PRICING.get(model, (0.003, 0.015))
    avg_in, avg_out = 250, 80
    cost_usd = (avg_in / 1000.0) * in_rate + (avg_out / 1000.0) * out_rate
    return {
        "model": model,
        "mode": "dry_run",
        "samples": samples,
        "avg_input_tokens": avg_in,
        "avg_output_tokens": avg_out,
        "avg_cost_usd": round(cost_usd, 6),
        "p50_latency_ms": None, "p95_latency_ms": None, "p99_latency_ms": None,
        "errors": 0,
        "input_rate_per_1k": in_rate,
        "output_rate_per_1k": out_rate,
    }


async def _measure_live(model: str, provider: str, api_key: str,
                        *, samples: int = 3) -> dict:
    latencies: list[float] = []
    in_toks: list[int] = []
    out_toks: list[int] = []
    costs: list[float] = []
    errors = 0
    for _ in range(samples):
        try:
            r = await _call_provider(provider, model, _BENCHMARK_SYSTEM,
                                     _BENCHMARK_PROMPT, api_key)
            latencies.append(r["latency_ms"])
            in_toks.append(r["input_tokens"])
            out_toks.append(r["output_tokens"])
            in_rate, out_rate = MODEL_PRICING.get(model, (0.003, 0.015))
            costs.append((r["input_tokens"] / 1000.0) * in_rate +
                         (r["output_tokens"] / 1000.0) * out_rate)
        except _GatewayError:
            errors += 1
        except Exception:  # noqa: BLE001
            errors += 1
    if not latencies:
        return {
            "model": model, "mode": "live", "samples": samples,
            "avg_input_tokens": 0, "avg_output_tokens": 0,
            "avg_cost_usd": 0.0, "p50_latency_ms": 0,
            "p95_latency_ms": 0, "p99_latency_ms": 0, "errors": errors,
        }
    return {
        "model": model, "mode": "live", "samples": samples,
        "avg_input_tokens": int(statistics.mean(in_toks)),
        "avg_output_tokens": int(statistics.mean(out_toks)),
        "avg_cost_usd": round(statistics.mean(costs), 6),
        "p50_latency_ms": int(_percentile(latencies, 50)),
        "p95_latency_ms": int(_percentile(latencies, 95)),
        "p99_latency_ms": int(_percentile(latencies, 99)),
        "errors": errors,
    }


# Modelos a benchmark — sólo los que están en MODEL_PRICING
_BENCHMARK_MODELS = [
    ("anthropic", "claude-haiku-4-5-20251001"),
    ("anthropic", "claude-sonnet-4-5-20250929"),
    ("openai", "gpt-4o-mini"),
    ("openai", "gpt-4.1-mini"),
]


async def run_benchmark(*, dry_run: bool = True, samples: int = 3,
                        triggered_by: str | None = None) -> dict:
    """Ejecuta el benchmark contra todos los modelos del catálogo.

    Persiste el resultado en `ai_benchmarks` (1 doc por corrida, con todos los
    modelos en `results[]`).
    """
    started = datetime.now(timezone.utc)
    api_key = os.environ["EMERGENT_LLM_KEY"]
    results = []
    if dry_run or not api_key:
        for prov, model in _BENCHMARK_MODELS:
            r = await _measure_dry_run(model, samples=samples)
            r["provider"] = prov
            results.append(r)
    else:
        for prov, model in _BENCHMARK_MODELS:
            r = await _measure_live(model, prov, api_key, samples=samples)
            r["provider"] = prov
            results.append(r)

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    doc = {
        "id": new_id(),
        "started_at": started.isoformat(),
        "duration_ms": duration_ms if not dry_run else None,
        "mode": "dry_run" if dry_run else "live",
        "samples_per_model": samples,
        "triggered_by": triggered_by,
        "results": results,
    }
    db = get_db()
    await db.ai_benchmarks.insert_one(doc.copy())
    doc.pop("_id", None)
    return doc


async def list_benchmarks(*, limit: int = 20) -> list[dict]:
    db = get_db()
    cur = db.ai_benchmarks.find({}, {"_id": 0}).sort("started_at", -1).limit(limit)
    return await cur.to_list(length=limit)
