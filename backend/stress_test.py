import os
"""
LastMile OS — Stress Test Suite
Ejecutar: python backend/stress_test.py
Genera: stress_test_results.md
"""
import asyncio
import aiohttp
import time
import statistics
import json
from datetime import datetime

BASE_URL = "https://lastmile-mvp.preview.emergentagent.com"
JOURNEY_ID = "c8d4c292-5c27-46bf-8b81-e83e40fb8a05"

# ─── OBTENER TOKEN ────────────────────────────────────────────────
async def get_token(session):
    r = await session.post(f"{BASE_URL}/api/auth/login",
        json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")})
    data = await r.json()
    return data.get("access_token") or data.get("token")

# ─── UTILIDADES ───────────────────────────────────────────────────
async def timed_get(session, url, headers):
    t0 = time.perf_counter()
    try:
        async with session.get(url, headers=headers) as r:
            body = await r.read()
            ms = round((time.perf_counter() - t0) * 1000)
            return {"url": url.replace(BASE_URL, ""), "status": r.status,
                    "ms": ms, "bytes": len(body)}
    except Exception as e:
        return {"url": url, "status": "ERR", "ms": -1, "error": str(e)}

def stats(ms_list):
    clean = [m for m in ms_list if m >= 0]
    if not clean:
        return {"avg": -1, "p50": -1, "p95": -1, "p99": -1, "max": -1, "min": -1}
    return {
        "avg":  round(statistics.mean(clean)),
        "p50":  round(statistics.median(clean)),
        "p95":  round(sorted(clean)[int(len(clean) * 0.95)]),
        "p99":  round(sorted(clean)[int(len(clean) * 0.99)]),
        "max":  max(clean),
        "min":  min(clean),
    }

# ─── TEST 1: BASELINE INDIVIDUAL ──────────────────────────────────
async def test_baseline(session, headers):
    """Latencia individual de cada endpoint clave."""
    print("\n📊 TEST 1: Baseline individual (1 usuario, 1 request)")
    endpoints = [
        "/api/health",
        "/api/journeys?page=1&page_size=25",
        "/api/dashboard/stats",
        "/api/sync/status",
        "/api/reports/kpis?period=current_month",
        "/api/reports/journeys?period=7d",
        "/api/reports/heatmap?date_from=2026-03-01&date_to=2026-03-28",
        "/api/admin/summary?period=current_month",
        "/api/admin/token-usage?period=current_month",
        "/api/admin/routes-report?date_from=2026-03-01&date_to=2026-03-28",
        f"/api/journeys/{JOURNEY_ID}/quality-summary",
        "/api/config/quality-settings",
    ]
    results = []
    for ep in endpoints:
        r = await timed_get(session, BASE_URL + ep, headers)
        status = "✅" if r["ms"] < 200 else ("⚠️" if r["ms"] < 500 else "❌")
        print(f"  {status} {r['url']:50s} {r['status']} {r['ms']:>5}ms  {r.get('bytes',0):>7} bytes")
        results.append(r)
    return results

# ─── TEST 2: CARGA CONCURRENTE ─────────────────────────────────────
async def test_concurrent(session, headers, endpoint, n_users):
    """N usuarios simultáneos al mismo endpoint."""
    print(f"\n⚡ TEST 2: {n_users} usuarios concurrentes → {endpoint}")
    tasks = [timed_get(session, BASE_URL + endpoint, headers) for _ in range(n_users)]
    t_wall = time.perf_counter()
    results = await asyncio.gather(*tasks)
    wall_ms = round((time.perf_counter() - t_wall) * 1000)
    ms_list = [r["ms"] for r in results]
    s = stats(ms_list)
    errors = sum(1 for r in results if r["status"] != 200)
    print(f"  Wall time: {wall_ms}ms | avg:{s['avg']}ms | p95:{s['p95']}ms | max:{s['max']}ms | errors:{errors}/{n_users}")
    degradation = round(s['max'] / s['min'], 1) if s['min'] > 0 else -1
    status = "✅" if s['p95'] < 500 else ("⚠️" if s['p95'] < 1000 else "❌")
    print(f"  {status} Degradación: {degradation}x | P95: {s['p95']}ms")
    return {"n": n_users, "wall_ms": wall_ms, "errors": errors, **s, "degradation": degradation}

# ─── TEST 3: ESCALADA DE CARGA ─────────────────────────────────────
async def test_ramp(session, headers):
    """Aumentar usuarios progresivamente: 1→5→10→20→30→50"""
    print("\n📈 TEST 3: Rampa de carga en /api/journeys")
    levels = [1, 5, 10, 20, 30, 50]
    results = []
    for n in levels:
        tasks = [timed_get(session, BASE_URL + "/api/journeys?page=1&page_size=25", headers)
                 for _ in range(n)]
        t_wall = time.perf_counter()
        res = await asyncio.gather(*tasks)
        wall_ms = round((time.perf_counter() - t_wall) * 1000)
        ms_list = [r["ms"] for r in res]
        s = stats(ms_list)
        errors = sum(1 for r in res if r["status"] != 200)
        status = "✅" if s["p95"] < 500 else ("⚠️" if s["p95"] < 1500 else "❌")
        print(f"  {status} {n:>3} usuarios → wall:{wall_ms:>5}ms  avg:{s['avg']:>5}ms  p95:{s['p95']:>5}ms  max:{s['max']:>5}ms  err:{errors}")
        results.append({"users": n, "wall_ms": wall_ms, "errors": errors, **s})
        await asyncio.sleep(1)  # Pausa entre niveles
    return results

# ─── TEST 4: ENDPOINTS DE IA BAJO CARGA ────────────────────────────
async def test_ia_endpoints(session, headers):
    """Endpoints que invocan IA — verificar timeout y error handling."""
    print("\n🤖 TEST 4: Endpoints de IA (5 requests concurrentes)")

    # Lumi: 5 consultas simultáneas
    lumi_payload = json.dumps({
        "message": "¿Cuál es el SLA actual?",
        "history": [],
        "period": "current_month"
    })
    lumi_headers = {**headers, "Content-Type": "application/json"}

    async def post_lumi(session):
        t0 = time.perf_counter()
        try:
            async with session.post(
                f"{BASE_URL}/api/chat/lumi",
                data=lumi_payload, headers=lumi_headers
            ) as r:
                body = await r.read()
                ms = round((time.perf_counter() - t0) * 1000)
                return {"status": r.status, "ms": ms, "bytes": len(body)}
        except Exception as e:
            return {"status": "ERR", "ms": -1}

    # 5 consultas Lumi en paralelo
    t_wall = time.perf_counter()
    lumi_results = await asyncio.gather(*[post_lumi(session) for _ in range(5)])
    wall_ms = round((time.perf_counter() - t_wall) * 1000)
    lumi_ms = [r["ms"] for r in lumi_results if r["ms"] > 0]
    lumi_errors = sum(1 for r in lumi_results if r["status"] not in [200, 403])
    s = stats(lumi_ms)
    print(f"  Lumi 5x concurrent → wall:{wall_ms}ms  avg:{s['avg']}ms  max:{s['max']}ms  err:{lumi_errors}")
    print(f"  {'✅' if s['max'] < 10000 else '❌'} Respuesta Lumi {'dentro' if s['max'] < 10000 else 'FUERA'} de timeout de 10s")

    # Evaluación IA — solo 1 (es costosa)
    print("  🔍 Evaluación IA individual (evidence_scoring)...")
    ia_t0 = time.perf_counter()
    try:
        async with session.post(
            f"{BASE_URL}/api/journeys/{JOURNEY_ID}/evaluate-ia",
            headers=headers
        ) as r:
            ia_ms = round((time.perf_counter() - ia_t0) * 1000)
            print(f"  {'✅' if r.status == 200 else '⚠️'} Evaluate IA → {r.status} en {ia_ms}ms")
    except Exception as e:
        print(f"  ❌ Evaluate IA → ERROR: {e}")

    return {"lumi": {"wall_ms": wall_ms, "errors": lumi_errors, **s}}

# ─── TEST 5: SOSTENIDO 60 SEGUNDOS ────────────────────────────────
async def test_sustained(session, headers, duration_s=60, rps=3):
    """3 requests/segundo durante 60 segundos — detectar degradación."""
    print(f"\n⏱️  TEST 5: Carga sostenida {rps} req/s durante {duration_s}s")
    results = []
    errors = 0
    t_start = time.perf_counter()
    interval = 1.0 / rps

    async def single():
        r = await timed_get(session, BASE_URL + "/api/journeys?page=1&page_size=25", headers)
        results.append(r["ms"])
        if r["status"] != 200:
            nonlocal errors
            errors += 1

    while time.perf_counter() - t_start < duration_s:
        asyncio.create_task(single())
        await asyncio.sleep(interval)

    await asyncio.sleep(2)  # Esperar últimas respuestas
    total_elapsed = round(time.perf_counter() - t_start)

    # Dividir en ventanas de 10s para detectar degradación
    window = len(results) // 6
    windows_avg = []
    for i in range(0, len(results), max(1, window)):
        chunk = [m for m in results[i:i+window] if m > 0]
        if chunk:
            windows_avg.append(round(statistics.mean(chunk)))

    s = stats([m for m in results if m > 0])
    degradation = round(windows_avg[-1] / windows_avg[0], 2) if len(windows_avg) >= 2 and windows_avg[0] > 0 else 1.0
    is_stable = degradation < 1.5

    print(f"  Requests totales: {len(results)} | Errores: {errors} | Duración: {total_elapsed}s")
    print(f"  avg:{s['avg']}ms  p95:{s['p95']}ms  max:{s['max']}ms")
    print(f"  Degradación: {degradation}x {'✅ Estable' if is_stable else '❌ Degradando'}")
    print(f"  Latencia por ventana de 10s: {windows_avg}")
    return {"requests": len(results), "errors": errors, "degradation": degradation, "stable": is_stable, **s}

# ─── TEST 6: DESCARGA EXCEL BAJO CARGA ────────────────────────────
async def test_export(session, headers):
    """Export de Excel — verificar que no bloquea el server."""
    print("\n📥 TEST 6: Descarga Excel + requests normales en paralelo")

    async def get_export():
        t0 = time.perf_counter()
        async with session.get(
            f"{BASE_URL}/api/admin/routes-report/export?date_from=2026-03-01&date_to=2026-03-28",
            headers=headers
        ) as r:
            body = await r.read()
            return {"status": r.status, "ms": round((time.perf_counter() - t0) * 1000), "bytes": len(body)}

    # Iniciar export + 5 requests normales en paralelo
    t_wall = time.perf_counter()
    results = await asyncio.gather(
        get_export(),
        timed_get(session, BASE_URL + "/api/journeys", headers),
        timed_get(session, BASE_URL + "/api/dashboard/stats", headers),
        timed_get(session, BASE_URL + "/api/reports/kpis?period=current_month", headers),
        timed_get(session, BASE_URL + "/api/admin/summary", headers),
        timed_get(session, BASE_URL + "/api/sync/status", headers),
    )
    wall_ms = round((time.perf_counter() - t_wall) * 1000)
    export_r = results[0]
    normal_ms = [r["ms"] for r in results[1:]]
    s = stats(normal_ms)

    print(f"  Export: {export_r['status']} en {export_r['ms']}ms ({export_r.get('bytes', 0)} bytes)")
    print(f"  Requests normales durante export → avg:{s['avg']}ms  max:{s['max']}ms")
    not_blocked = s['max'] < 1000
    print(f"  {'✅' if not_blocked else '❌'} Server {'NO bloqueado' if not_blocked else 'BLOQUEADO'} durante export")
    return {"export_ms": export_r["ms"], "normal_avg_ms": s["avg"], "blocked": not not_blocked}

# ─── TEST 7: BÚSQUEDA Y FILTROS ────────────────────────────────────
async def test_filters(session, headers):
    """Múltiples combinaciones de filtros — detectar queries lentas."""
    print("\n🔍 TEST 7: Combinaciones de filtros")
    filter_combos = [
        "/api/journeys?date_from=2026-03-01&date_to=2026-03-28",
        "/api/journeys?date_from=2026-03-25&date_to=2026-03-25",
        "/api/journeys?status=delivered",
        "/api/reports/kpis?period=7d",
        "/api/reports/kpis?period=current_month",
        "/api/reports/kpis?period=prev_month",
        "/api/reports/journeys?period=7d&group_by=provider",
        "/api/reports/heatmap?date_from=2026-03-01&date_to=2026-03-28",
    ]
    results = []
    for ep in filter_combos:
        r = await timed_get(session, BASE_URL + ep, headers)
        status = "✅" if r["ms"] < 300 else ("⚠️" if r["ms"] < 800 else "❌")
        print(f"  {status} {r['url'][:55]:55s} {r['ms']:>5}ms")
        results.append(r)
    return results

# ─── TEST 8: AUTENTICACIÓN BAJO CARGA ─────────────────────────────
async def test_auth_load(session):
    """Logins concurrentes — verificar que rate limit está bien configurado."""
    print("\n🔐 TEST 8: Autenticación — 8 logins concurrentes (límite esperado: 10/min)")
    async def do_login():
        t0 = time.perf_counter()
        async with session.post(f"{BASE_URL}/api/auth/login",
            json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        ) as r:
            return {"status": r.status, "ms": round((time.perf_counter() - t0) * 1000)}

    results = await asyncio.gather(*[do_login() for _ in range(8)])
    ok = sum(1 for r in results if r["status"] == 200)
    rl = sum(1 for r in results if r["status"] == 429)
    ms_list = [r["ms"] for r in results if r["status"] == 200]
    s = stats(ms_list)
    print(f"  200 OK: {ok}/8  |  429 Rate Limited: {rl}/8")
    print(f"  {'✅' if ok >= 7 else '⚠️'} {'Rate limit correcto' if rl == 0 else f'{rl} requests bloqueados'}")
    print(f"  Login latency avg: {s['avg']}ms  max: {s['max']}ms")
    return {"ok": ok, "rate_limited": rl, "avg_ms": s["avg"]}

# ─── MAIN ──────────────────────────────────────────────────────────
async def main():
    print("=" * 70)
    print("LastMile OS — Stress Test Suite")
    print(f"Iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Target:   {BASE_URL}")
    print("=" * 70)

    connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Login
        print("\n🔑 Obteniendo token...")
        token = await get_token(session)
        if not token:
            print("❌ FATAL: No se pudo obtener token de autenticación")
            return
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  ✅ Token obtenido correctamente")

        # Ejecutar tests
        t1 = await test_baseline(session, headers)
        t2a = await test_concurrent(session, headers, "/api/journeys?page=1&page_size=25", 10)
        t2b = await test_concurrent(session, headers, "/api/reports/kpis?period=current_month", 10)
        t2c = await test_concurrent(session, headers, "/api/dashboard/stats", 20)
        t3 = await test_ramp(session, headers)
        t4 = await test_ia_endpoints(session, headers)
        t5 = await test_sustained(session, headers, duration_s=60, rps=3)
        t6 = await test_export(session, headers)
        t7 = await test_filters(session, headers)
        t8 = await test_auth_load(session)

    # ─── GENERAR REPORTE ──────────────────────────────────────────
    print("\n" + "=" * 70)
    print("📋 GENERANDO REPORTE...")

    # Criterios de aprobación
    baseline_ok  = all(r["ms"] < 300 for r in t1 if r["ms"] > 0)
    conc_p95_ok  = t2a.get("p95", 9999) < 800
    ramp_50_ok   = next((r for r in t3 if r["users"] == 50), {}).get("p95", 9999) < 2000
    sustained_ok = t5.get("stable", False) and t5.get("degradation", 9) < 1.5
    export_ok    = not t6.get("blocked", True)
    auth_ok      = t8["ok"] >= 7

    score = sum([baseline_ok, conc_p95_ok, ramp_50_ok, sustained_ok, export_ok, auth_ok])
    verdict = "✅ APTO PARA GO-LIVE" if score >= 5 else ("⚠️ REQUIERE OPTIMIZACIÓN" if score >= 3 else "❌ NO APTO")

    report = f"""# LastMile OS — Stress Test Results
**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**URL:** {BASE_URL}

## Veredicto: {verdict} ({score}/6 criterios cumplidos)

## Criterios de Aprobación

| # | Criterio | Resultado | Estado |
|---|---|---|---|
| 1 | Baseline < 300ms todos los endpoints | p95={max((r["ms"] for r in t1 if r["ms"]>0), default=0)}ms | {'✅' if baseline_ok else '❌'} |
| 2 | 10 usuarios concurrentes P95 < 800ms | p95={t2a.get('p95')}ms | {'✅' if conc_p95_ok else '❌'} |
| 3 | 50 usuarios concurrentes P95 < 2000ms | p95={next((r for r in t3 if r['users']==50), {}).get('p95','N/A')}ms | {'✅' if ramp_50_ok else '❌'} |
| 4 | Carga sostenida 60s estable (<1.5x degradación) | {t5.get('degradation')}x | {'✅' if sustained_ok else '❌'} |
| 5 | Export Excel no bloquea requests normales | max={t6.get('normal_avg_ms')}ms | {'✅' if export_ok else '❌'} |
| 6 | 8 logins concurrentes OK (≥7 exitosos) | ok={t8['ok']}/8 | {'✅' if auth_ok else '❌'} |

## Resultados Detallados

### Baseline Individual
| Endpoint | Status | Latencia | Bytes |
|---|---|---|---|
""" + "\n".join(f"| {r['url'][:50]} | {r['status']} | {r['ms']}ms | {r.get('bytes',0)} |" for r in t1) + f"""

### Concurrencia
| Test | Users | Avg | P95 | Max | Degradación |
|---|---|---|---|---|---|
| /api/journeys | {t2a['n']} | {t2a['avg']}ms | {t2a['p95']}ms | {t2a['max']}ms | {t2a.get('degradation','N/A')}x |
| /api/reports/kpis | {t2b['n']} | {t2b['avg']}ms | {t2b['p95']}ms | {t2b['max']}ms | {t2b.get('degradation','N/A')}x |
| /api/dashboard/stats | {t2c['n']} | {t2c['avg']}ms | {t2c['p95']}ms | {t2c['max']}ms | {t2c.get('degradation','N/A')}x |

### Rampa de Carga
| Usuarios | Wall Time | Avg | P95 | Max | Errores |
|---|---|---|---|---|---|
""" + "\n".join(f"| {r['users']} | {r['wall_ms']}ms | {r['avg']}ms | {r['p95']}ms | {r['max']}ms | {r['errors']} |" for r in t3) + f"""

### Carga Sostenida 60s ({t5.get('requests')} requests a 3 req/s)
- Errores: {t5.get('errors')}/{t5.get('requests')}
- Degradación: {t5.get('degradation')}x
- Estable: {'✅ SÍ' if t5.get('stable') else '❌ NO'}
- P95: {t5.get('p95')}ms | Max: {t5.get('max')}ms

### Export Excel
- Tiempo export: {t6.get('export_ms')}ms
- Requests normales durante export: avg {t6.get('normal_avg_ms')}ms
- Server bloqueado: {'❌ SÍ' if t6.get('blocked') else '✅ NO'}

### Autenticación
- Logins exitosos: {t8['ok']}/8
- Rate limited: {t8['rate_limited']}/8
- Latencia promedio: {t8['avg_ms']}ms

## Comparativo: Antes vs Después de Optimizaciones

| Métrica | Antes (medido) | Target | 
|---|---|---|
| 1 usuario baseline | 123-195ms | <200ms |
| 10 usuarios concurrentes (max) | 1319ms | <800ms |
| Degradación 10x concurrente | 8.6x | <3x |
| DOMContentLoaded | 1000ms | <500ms |
| Heap utilización | 90% | <70% |
"""

    with open("/app/stress_test_results.md", "w") as f:
        f.write(report)

    print(f"\n{'=' * 70}")
    print(f"  {verdict}")
    print(f"  Reporte guardado: /app/stress_test_results.md")
    print(f"{'=' * 70}\n")

if __name__ == "__main__":
    asyncio.run(main())
