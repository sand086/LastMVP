# LastMile OS — Stress Test Results
**Fecha:** 2026-03-30 19:43
**URL:** https://lastmile-mvp.preview.emergentagent.com

## Veredicto: ✅ APTO PARA GO-LIVE (6/6 criterios cumplidos)

## Criterios de Aprobación

| # | Criterio | Resultado | Estado |
|---|---|---|---|
| 1 | Baseline < 300ms todos los endpoints | p95=83ms | ✅ |
| 2 | 10 usuarios concurrentes P95 < 800ms | p95=221ms | ✅ |
| 3 | 50 usuarios concurrentes P95 < 2000ms | p95=344ms | ✅ |
| 4 | Carga sostenida 60s estable (<1.5x degradación) | 0.97x | ✅ |
| 5 | Export Excel no bloquea requests normales | max=239ms | ✅ |
| 6 | 8 logins concurrentes OK (≥7 exitosos) | ok=8/8 | ✅ |

## Resultados Detallados

### Baseline Individual
| Endpoint | Status | Latencia | Bytes |
|---|---|---|---|
| /api/health | 200 | 51ms | 67 |
| /api/journeys?page=1&page_size=25 | 200 | 66ms | 22694 |
| /api/dashboard/stats | 200 | 55ms | 224 |
| /api/sync/status | 200 | 50ms | 90 |
| /api/reports/kpis?period=current_month | 200 | 61ms | 5673 |
| /api/reports/journeys?period=7d | 200 | 63ms | 19577 |
| /api/reports/heatmap?date_from=2026-03-01&date_to= | 200 | 58ms | 5646 |
| /api/admin/summary?period=current_month | 200 | 57ms | 842 |
| /api/admin/token-usage?period=current_month | 200 | 54ms | 5826 |
| /api/admin/routes-report?date_from=2026-03-01&date | 200 | 83ms | 18320 |
| /api/journeys/c8d4c292-5c27-46bf-8b81-e83e40fb8a05 | 200 | 55ms | 251 |
| /api/config/quality-settings | 200 | 65ms | 2627 |

### Concurrencia
| Test | Users | Avg | P95 | Max | Degradación |
|---|---|---|---|---|---|
| /api/journeys | 10 | 137ms | 221ms | 221ms | 3.3x |
| /api/reports/kpis | 10 | 74ms | 108ms | 108ms | 2.2x |
| /api/dashboard/stats | 20 | 137ms | 254ms | 254ms | 4.5x |

### Rampa de Carga
| Usuarios | Wall Time | Avg | P95 | Max | Errores |
|---|---|---|---|---|---|
| 1 | 67ms | 67ms | 67ms | 67ms | 0 |
| 5 | 110ms | 95ms | 110ms | 110ms | 0 |
| 10 | 114ms | 94ms | 113ms | 113ms | 0 |
| 20 | 190ms | 152ms | 188ms | 188ms | 0 |
| 30 | 209ms | 158ms | 207ms | 207ms | 0 |
| 50 | 351ms | 271ms | 344ms | 346ms | 0 |

### Carga Sostenida 60s (180 requests a 3 req/s)
- Errores: 0/180
- Degradación: 0.97x
- Estable: ✅ SÍ
- P95: 81ms | Max: 97ms

### Export Excel
- Tiempo export: 343ms
- Requests normales durante export: avg 239ms
- Server bloqueado: ✅ NO

### Autenticación
- Logins exitosos: 8/8
- Rate limited: 0/8
- Latencia promedio: 1479ms

## Comparativo: Antes vs Después de Optimizaciones

| Métrica | Antes (medido) | Target | 
|---|---|---|
| 1 usuario baseline | 123-195ms | <200ms |
| 10 usuarios concurrentes (max) | 1319ms | <800ms |
| Degradación 10x concurrente | 8.6x | <3x |
| DOMContentLoaded | 1000ms | <500ms |
| Heap utilización | 90% | <70% |
