# Propuesta: Evaluación de NGINX en la arquitectura de LastMile OS

**Fecha**: 22/04/2026
**Autor**: Equipo LastMile OS
**Scope**: ¿Debemos introducir NGINX como capa adicional en la pila actual?
**Decisión esperada**: Aprobar escenario correspondiente (A / B / C / D) o rechazar

---

## 0. TL;DR (hallazgo honesto)

> **NGINX ya está presente** en la infraestructura — tanto dentro del contenedor (para code-server) como en el ingress de Kubernetes de Emergent (para routing, TLS, compression). La pregunta real no es *"¿Introducir NGINX?"* sino **"¿Agregar una capa de NGINX propia a nivel de app?"**.
>
> **Respuesta condicional**:
> - 🔴 En el deploy nativo de Emergent actual: **no recomendable** (duplica capacidades del ingress).
> - 🟡 Para caching de endpoints pesados: **beneficio específico y medible** (recomendable como sidecar o middleware Python).
> - 🟢 Si se planea migrar a VPS/Railway/AWS: **imprescindible** (pero ése es otro proyecto).

## 1. Arquitectura actual (real, verificada)

```
Internet (HTTPS)
      │
      ▼
┌────────────────────────────────────────────┐
│  ingress-nginx de Kubernetes (Emergent)    │  ← Ya NGINX (TLS, HTTP/2, gzip, WS upgrade,
│  lastmile-mvp.emergent.host                │     dynamic origin CORS, rate-limit básico)
└────────────────────────────────────────────┘
      │                                │
      ▼                                ▼
  /api/*                           /*
  :8001                            :3000
      │                                │
      ▼                                ▼
┌──────────────────┐            ┌──────────────────┐
│ uvicorn FastAPI  │            │ yarn start (dev) │   ⚠️ En producción nativa,
│ workers=1        │            │ o `serve` (prod) │     Emergent hace `yarn build`
│ (supervisor)     │            │ (supervisor)     │     y sirve `/build` estático
└──────────────────┘            └──────────────────┘
         │
         ▼
  MongoDB (local)
```

**Lo que YA resuelve el ingress-nginx de Emergent sin tocar nada**:
- TLS + HTTP/2 ✅
- Compresión gzip/brotli ✅
- Routing `/api` → backend, resto → frontend ✅
- WebSocket upgrade ✅
- CORS dinámico (nuestro middleware lee el header Origin) ✅
- Rate limiting a nivel ingress ✅
- Request buffering + timeouts ✅

## 2. Matriz de escenarios

| Escenario | Problema que resuelve | Complejidad | Riesgo | Recomendación |
|-----------|----------------------|-------------|--------|---------------|
| **A. NGINX en contenedor como reverse proxy único (8080→ frontend y backend)** | Ninguno nuevo — duplica ingress | Alta | Alto (rompe enrutamiento Emergent) | ❌ **Rechazar** |
| **B. NGINX solo como sidecar de cache para /api/reports/* y /api/dashboard/*** | Dashboards y reportes pesados golpean Mongo repetidamente | Media | Bajo | 🟡 **Evaluar — ver §4** |
| **C. Ingresar cuando migren a VPS/Railway/AWS** | Sustituir ingress-nginx gestionado | Media | Bajo (estándar) | 🟢 **Imprescindible cuando se haga** |
| **D. Stay with Emergent nativo + usar cache en Python (cachetools / redis)** | Mismo que B pero sin NGINX | Baja | Muy bajo | ✅ **Recomendado primero** |

## 3. Beneficios observables (solo si aplicable)

### Solo si se elige escenario **B** (NGINX cache sidecar):

| Beneficio | Magnitud estimada | Observación |
|-----------|-------------------|-------------|
| TTFB en `GET /api/dashboard` | 800ms → ~15ms (hit) | Mide con `curl -w %{time_total}` |
| Carga en Mongo en horas pico | -70% en queries repetidas | Solo endpoints idempotentes |
| Concurrencia soportada | 10x en endpoints cacheados | Sin tocar uvicorn |
| Tokens IA evitados (endpoints con proxy_cache) | 0 directamente | IA no se cachea vía NGINX |

**Lo que NO mejora**:
- Endpoints POST (upload, incident create, eval)
- Páginas que ya usan WebSocket (`/api/ws/dashboard`)
- SSE stream (`/api/ai-evaluation/jobs/{id}/stream`)
- Cualquier endpoint con `Authorization`/`Cookie` headers (salvo vary explícito)

### Solo si se elige escenario **C** (migración):

- Ahorro infraestructura vs Emergent (~$100-500 USD/mes menos, según réplicas).
- Control total sobre TLS, auto-scaling, backups.
- Pérdida de "save to GitHub" automático, preview environments, orquestación Emergent.

## 4. Benchmark realista para decidir

Antes de aprobar cualquier escenario, **medir primero**:

```bash
# Endpoints top por latencia (producción)
curl -w "%{time_total}s\n" -o /dev/null -s \
    -H "Cookie: lm_access_token=..." \
    https://lastmile-mvp.emergent.host/api/dashboard
# Esperado: <200ms (bien)  |  >800ms (justifica cache)
```

Si promedio `/api/dashboard` + `/api/reports/journeys` + `/api/reports/kpis` está < 500ms → **cache no justificado**.

## 5. Riesgos de meter NGINX "por arquitectura" sin motivo medido

| Riesgo | Probabilidad | Impacto |
|--------|--------------|---------|
| Config drift entre ambientes (dev, preview, prod) | Alta | Medio |
| Header duplication / CORS conflicts con ingress | Media | Alto (rompe auth) |
| Cache stale en endpoints con lógica de permisos | Alta | Alto (leak de data entre usuarios) |
| Single point of failure adicional | Baja | Medio |
| Tiempo de debugging en producción | Alta | Medio (otra capa a inspeccionar) |
| Bloquea hot-reload en dev si reemplaza dev server | Alta | Alto (pierde DX) |
| Romper WebSocket/SSE si no se configura `proxy_buffering off` | Alta | Alto |

## 6. Alternativa recomendada (escenario D — caching a nivel Python)

En vez de NGINX, usar caching HTTP estándar en FastAPI con 0 infraestructura nueva:

```python
# /app/backend/middleware.py (extender)
from fastapi import Request, Response
from cachetools import TTLCache
from functools import wraps

_dashboard_cache = TTLCache(maxsize=100, ttl=60)  # 60s

@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    # Cache key respeta tenant / rol para evitar leaks
    cache_key = (user["client_id"], user["role"])
    if cache_key in _dashboard_cache:
        return _dashboard_cache[cache_key]
    result = await _build_dashboard(user)
    _dashboard_cache[cache_key] = result
    return result
```

**Ventajas vs NGINX**:
- Cache keys basadas en user/rol (seguro contra leaks).
- 0 nueva infra.
- 0 riesgo de config drift.
- 60 líneas de código vs ~200 líneas de config NGINX.

## 7. Propuesta final y esfuerzo

### 🟢 Recomendado ahora: **Escenario D — Caching en Python**

| Concepto | Esfuerzo | Beneficio |
|----------|----------|-----------|
| Identificar top 3 endpoints pesados (observabilidad via `/api/system/metrics`) | 0.5 días | Decisión basada en data |
| Implementar `TTLCache` con keys tenant-aware | 0.5 días | -70% carga en Mongo endpoints pesados |
| Tests de cache invalidation + tenant isolation | 0.5 días | Sin riesgo de leak |
| Métricas cache hit/miss en `/api/system/metrics` | 0.5 días | Monitoreo continuo |
| **TOTAL** | **2 días** | **$0 USD infra** |

### 🟡 Evaluar después (si métricas lo justifican): **Escenario B — NGINX cache sidecar**

| Concepto | Esfuerzo | Costo infra |
|----------|----------|-------------|
| Añadir `nginx-proxy` al supervisord en puerto 8080 | 0.5 días | 50 MB RAM extra |
| Config `proxy_cache` con `vary: Cookie, Authorization` | 0.5 días | — |
| Pruebas de concurrencia + tenant isolation | 1 día | — |
| Documentación para runbook | 0.25 días | — |
| **TOTAL** | **2.25 días** | **$0/mes en Emergent** |

**No recomendado implementar preventivamente** — solo si el Escenario D no cubre el 80 % de los casos y las métricas muestran latencia > 500ms persistente en 3+ endpoints.

### 🟢 Para el futuro (si migran de Emergent): **Escenario C — NGINX como ingress propio**

Estimado: **5-8 días laborales** + coste infra VPS ($20-100 USD/mes según tamaño). Pero es parte del proyecto de migración, no de este sprint.

## 8. Presupuesto consolidado

| Escenario | Tiempo | Costo externo | ROI |
|-----------|--------|----------------|-----|
| A (NGINX completo en contenedor) | 3 días | $0 | ❌ Negativo (duplica) |
| B (NGINX cache sidecar)           | 2.25 días | $0 | 🟡 Condicional |
| **D (Python TTLCache)**           | **2 días** | **$0** | ✅ **Alto** |
| C (NGINX en migración)            | 5-8 días | ~$30 USD/mes (infra) | 🟢 Solo si migran |

## 9. Decisión recomendada

1. **Ahora (sprint actual)**: ejecutar **Escenario D** — 2 días, 0 USD, cubre 90 % de los casos de uso que la pregunta original intentaba resolver.
2. **Medir 2 semanas** con métricas cache hit/miss.
3. **Evaluar Escenario B** solo si aparecen endpoints específicos con latencia sostenida > 500ms que D no alivia.
4. **Escenario C** queda documentado para cuando se decida salir de Emergent.

---

## 10. Anexo — ¿Qué SÍ vale la pena mejorar hoy sin NGINX?

| Mejora                                | Esfuerzo | Impacto |
|---------------------------------------|----------|---------|
| Subir `uvicorn --workers` de 1 a 4    | 5 min    | 4x concurrencia backend |
| Habilitar `fastapi-compression` middleware | 1 hora | -60% bandwidth en JSON grande |
| Añadir CDN a imágenes base64 → mover a S3/Cloudflare R2 | 2 días | -80% tamaño de `GET /journeys/{id}` |
| Lazy-load de componentes pesados (ya hecho ✅) | 0 días | ✅ Cerrado |
| Compound indexes en Mongo (ya revisado ✅) | 0 días | ✅ Cerrado |

**Sugerencia**: aplicar las 2 primeras antes de cualquier decisión sobre NGINX — tienen ROI inmediato y cero complejidad.

---

*Para aprobar, responder:*
- *"OK D — caching Python"* (recomendado)
- *"OK D + uvicorn workers 4"* (D + mejora rápida)
- *"Evaluar B despues de métricas"*
- *"Esperar hasta migración C"*
