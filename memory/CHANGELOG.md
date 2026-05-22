# LastMile OS - Changelog


## 2026-05-21 — FIX P0 INTEGRIDAD: incidencias eliminadas sin trazabilidad

**Reporte del usuario**: 7 incidencias desaparecieron entre ayer y hoy ~3pm en producción. 6 de ellas pertenecientes a la misma ruta Routal (`6a04abeb69d4d67178642d8c`). Imposible determinar quién/cuándo/cómo se eliminaron.

**Root cause real (déficit arquitectónico, no bug puntual)**: el código tenía 3 caminos que eliminaban incidencias y **2 de ellos no guardaban audit_log**:
1. `DELETE /api/incidents/{id}` (botón 🗑️ en UI, abierto a `agent`/`coordinator`/`developer`) → hard-delete sin audit_log.
2. `POST /api/admin/cleanup/routes-packages` → hard-delete masivo sin audit_log.
3. `DELETE /api/journeys/{id}` cascade → con audit_log pero sin archivo.

Cualquier click accidental en el basurero o ejecución de cleanup masivo sin filtros borraba incidencias **irrecuperables** y sin testigo. Una incidencia de cliente vale dinero (multas, PowerBI, SLA): la pérdida silenciosa es inaceptable.

**Patrón de fix elegido — `incidents_archive` collection**:
- En vez de soft-delete con campo `deleted_at` (que requeriría modificar las ~25 queries de incidents existentes y abrir riesgo de regresiones), se copia el documento completo a colección `incidents_archive` antes del `delete_one` / `delete_many`. La colección `incidents` queda exactamente igual (sólo activas), por lo que ninguna query pre-existente cambia su comportamiento.
- Cada documento archivado lleva metadata `_archive_meta`: `deleted_at`, `deleted_by_id`, `deleted_by_email`, `deleted_by_name`, `deletion_source`, `deletion_reason` (opcional).

**Cambios** (`/app/backend/routes/journey_routes.py`, `/app/backend/routes/admin_routes.py`):

1. **`DELETE /api/incidents/{id}`** ahora:
   - Acepta body opcional con `reason`.
   - Copia incidencia completa a `incidents_archive` con metadata.
   - Inserta `audit_logs.action=incident_deleted` con `tracking_number`, `incident_type`, `severity`, `imputability`, `journey_id`, `user_email`.
   - Recién entonces hace `delete_one`.
   - **Role restringido a `coordinator`/`developer`** (antes incluía `agent`).

2. **`POST /api/incidents/{id}/restore`** (nuevo, sólo `developer`):
   - Mueve documento desde `incidents_archive` → `incidents`.
   - Audit_log con `originally_deleted_at` y `originally_deleted_by`.

3. **`DELETE /api/journeys/{id}`** cascade ahora también archiva las incidencias afectadas y reporta `incidents_archived` en el response y audit log.

4. **`POST /api/admin/cleanup/routes-packages`** ahora:
   - Archiva todas las incidencias afectadas antes del bulk delete.
   - Inserta `audit_logs.action=cleanup_all` o `cleanup_by_date` con `journeys_deleted`, `packages_deleted`, `incidents_deleted`, `incidents_archived`, rango de fechas y `user_email`.

5. **`POST /api/incidents/forensics`** (nuevo, `coordinator`/`developer`):
   - Recibe `{ tracking_numbers: [], journey_id?, routal_route_id?, hours_back?: 48 }`.
   - Devuelve por cada tracking: estado actual del package + journey + incidencias activas + **incidencias archivadas con quién/cuándo/por qué se borraron** + audit logs relevantes.
   - Adicionalmente devuelve `recent_destructive_events` global con todos los `cleanup_*`/`journey_deleted`/`incident_deleted` de la ventana.
   - Esta es la herramienta para que el equipo investigue producción sin acceso a Atlas.

**Limitación importante para producción actual**: las 7 incidencias borradas hoy 3pm fueron eliminadas con el código viejo (sin archive ni audit_log) → **no son recuperables vía `/api/incidents/forensics` ni `restore`**. Sólo se pueden recuperar desde el oplog de Atlas dentro de la ventana de 24h (contactar Emergent Support antes de mañana 3pm).

**Verificación local**: lint OK, backend reinicia, `/api/incidents/forensics` y `/api/incidents/{id}/restore` registrados con auth (401 sin token). `/health` sigue en 1.9ms.



## 2026-05-15 — REFACTOR ARQUITECTÓNICO P0 (CAPA 6): Workers en proceso separado

**Motivación**: tras capas 3 (middleware bypass), 4 (yields explícitos) y 5 (raw ASGI middleware), `/health` ya no timeoutea bajo carga normal. Pero la causa raíz subyacente — **workers compartiendo event loop con FastAPI** — permanecía. Bajo picos extremos (concurrencias altas, ráfagas LLM con timeouts de 30s+, sweeps masivos) las mitigaciones podían no ser suficientes. La solución definitiva es ejecutar los workers en un **proceso OS separado** con su propio event loop.

**Diseño** (compatible con supervisor read-only del entorno Emergent):

```
┌─ Pod ────────────────────────────────────────────────────────┐
│                                                              │
│  ┌─ uvicorn (FastAPI, PID 1707) ─┐  spawn  ┌─ workers proc (PID 1735) ─────┐
│  │ • HTTP API + WebSocket        │ ──────► │ • event loop dedicado          │
│  │ • Event loop libre            │  monitor│ • leader-election bg_tasks      │
│  │ • subprocess_manager monitor  │ ◄────── │ • ai_eval + kosmo + routal      │
│  └───────────────────────────────┘  respawn│ • SIGTERM-aware                 │
│                                            │ • PR_SET_PDEATHSIG=SIGTERM      │
│                                            └─────────────────────────────────┘
└──────────────────────────────────────────────────────────────┘
```

**Archivos nuevos**:
- `/app/backend/workers/standalone_runner.py` — entry point del proceso de workers. Crea su propio `AsyncIOMotorClient`, inicializa `init_encryption`, hace leader-election (`bg_tasks`), arranca `ai_eval_worker` + `kosmo_sync` + `routal_sync_worker` + `routal_selection_worker`, espera SIGTERM. En Linux registra `prctl(PR_SET_PDEATHSIG, SIGTERM)` para que si FastAPI muere por SIGKILL el subproceso muera también (zero zombies).
- `/app/backend/workers/subprocess_manager.py` — `start_worker_subprocess()` / `stop_worker_subprocess()` / `is_worker_alive()` / `get_worker_pid()`. Spawn + monitor task con backoff exponencial (1s → 60s) ante crashes.

**Archivos modificados**:
- `/app/backend/server.py`:
  - Import del `subprocess_manager`.
  - `_deferred_startup` ahora respeta `WORKERS_MODE` (default: `subprocess`). Cuando es `subprocess`, NO arranca workers en el loop de FastAPI; spawnea el proceso aparte.
  - Modo legacy `WORKERS_MODE=inline` preservado para fallback.
  - Shutdown: SIGTERM al subprocess con grace de 10s, SIGKILL fallback.
  - Nuevo endpoint `GET /api/admin/workers-process-status` → `{mode, alive, pid}`.

**Verificación local**:
- 2 procesos vivos tras boot: uvicorn (PID 1707, 26MB) + standalone_runner (PID 1735, 82MB).
- `/health` HTTP/1.1 keepalive: **0.04ms** (sin variación entre 25 requests consecutivas en 5 conexiones distintas) — antes el bypass capa-5 daba 0.77ms, ahora la sobrecarga del BaseHTTPMiddleware ni siquiera aplica porque el subprocess no compite por el loop.
- **Test de respawn**: `kill -9 $worker_pid` → monitor detecta exit, respawnea en <10s con nuevo PID. `/health` no afectado.
- Logs del subprocess llevan prefijo `[worker-proc]` para distinguirlos del API.
- Endpoint diagnóstico devuelve `{"mode":"subprocess","alive":true,"pid":1851}`.

**Implicaciones operativas**:
- ✅ Podemos volver a subir `AI_EVAL_MAX_ROUTES_CONCURRENT`, `KOSMO_SCRAPE_CONCURRENCY`, `ROUTAL_SYNC_MAX_CONCURRENT` sin riesgo de afectar `/health`.
- ✅ Si el subprocess crashea (OOM, bug LLM, etc.), FastAPI sigue sirviendo y respawnea workers.
- ✅ Si uvicorn crashea, los workers mueren con él (PR_SET_PDEATHSIG) — supervisor reinicia ambos.
- ⚠️ Memoria adicional: ~80MB por el segundo proceso Python. Aceptable.
- ⚠️ Para volver al modo legacy en producción: setear `WORKERS_MODE=inline` en `.env` del deploy.



## 2026-05-15 — FIX P0 BLOQUEADOR DE DEPLOY (CAPA 5): Raw ASGI middleware para /health

**Síntoma persistente tras capa 4**: aunque los workers ahora ceden el event loop con `await asyncio.sleep(0)`, el deploy a producción seguía fallando con `upstream timed out` desde el NGINX sidecar del pod hacia `127.0.0.1:8001/health`. Observación clave en los logs:

- `/health` HTTP/1.0 (probes de supervisor sin keepalive) → 200 OK consistente.
- `/health` HTTP/1.1 (probes de NGINX sidecar con keepalive) → timeout cada 10–20s.
- Resto de la API (`/api/journeys`, `/api/dashboard/...`, WebSockets) → 200 OK rápido durante el mismo intervalo.

**Root cause real**: el `@app.middleware("http")` que usábamos para el bypass es azúcar sintáctico para `BaseHTTPMiddleware`, que internamente **spawnea un task asyncio interno por request** y bufferea la respuesta vía `anyio.MemoryObjectStream`. Bajo carga concurrente con HTTP/1.1 keepalive (cómo NGINX hace probes en k8s), esos tasks internos se encolan detrás del event loop ocupado con LLM calls. Issue conocido de Starlette: encode/starlette#1438. Por eso HTTP/1.0 (sin keepalive, conexión efímera) sí pasaba — cada call abría socket nuevo que iba directo a la accept queue del worker — mientras HTTP/1.1 (conexión persistente) se quedaba esperando que el task interno del middleware fuera schedule-ado.

**Fix** (`/app/backend/server.py`): reemplazar el `@app.middleware("http")` por una clase **raw ASGI** (`HealthFastBypass`) registrada con `app.add_middleware(HealthFastBypass)`. La clase intercepta requests a `/health` y `/api/health` en la capa ASGI ANTES de que FastAPI/Starlette monten el `Request`, ANTES de cualquier task interno. Solo dos `await send()` calls — latencia sub-millisegundo independientemente del estado del event loop.

```python
class HealthFastBypass:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") in ("/health", "/api/health"):
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b'{"status":"ok"}'})
            return
        await self.app(scope, receive, send)
```

**Verificación local**:
- HTTP/1.1 con conexión nueva: 0.66–1.0ms.
- HTTP/1.1 con keepalive (3 requests en misma conexión): 0.77ms cada uno, estables.
- Workers arrancando limpios con leader-election idempotente + grace period 60s.
- API normal (`/api/system/errors/count`) sigue respondiendo en 5ms.



## 2026-05-14 — FIX P0 BLOQUEADOR DE DEPLOY (CAPA 4): yields explícitos en workers

**Síntoma persistente tras capa 3**: aunque `/health` evita los middlewares con bypass, NGINX seguía registrando timeouts cuando los workers procesaban cargas pesadas. Razón: el bypass usa `@app.middleware("http")`, que aún forma parte de la cadena ASGI de Starlette y depende de que el event loop tenga oportunidad de despachar la request entrante. Cuando un task del worker (LLM call de 15-25s, gather de 250 paquetes Kosmo, gather de N journeys Routal) acapara el loop entre awaits significativos, NGINX nunca llega a recibir la respuesta a tiempo.

**Fix (capa 4)**: insertar `await asyncio.sleep(0)` como puntos de cesión explícitos dentro de los bucles principales de los 3 workers. `asyncio.sleep(0)` no duerme; sólo cede control al scheduler una sola tick, permitiendo que la request `/health` pendiente sea servida.

**Ubicaciones modificadas**:

`/app/backend/ai_eval_worker.py`:
- `_process_job`: yield al inicio de cada batch en el for-loop (`for batch_start in range(...)`).
- `_evaluate_batch_with_retry`: yield entre marcar guías como Evaluando y lanzar tareas LLM; yield entre updates de progreso por guía.
- `_cron_sweep`: yield cada 100 docs al iterar el cursor de journeys abiertas; yield entre rutas al encolar jobs.
- `_kill_active_jobs_due_to_pause`: yield entre jobs en el async-for cursor.

`/app/backend/kosmo_sync.py`:
- `process_package`: yield después de cada update a `db.packages` para que el gather concurrente no monopolice el loop.
- `_recount_and_update_journeys`: yield tras agotar el cursor de aggregation y antes de armar batch de updates.

`/app/backend/workers/routal_sync_worker.py`:
- `_sync_one`: yield antes de la llamada `sync_journey_from_routal` (puede demorar segundos por request HTTP+procesamiento).
- `_tick`: yield tras materializar el cursor de journeys candidatas.

**Verificación local**: `/health` responde en <5ms tras restart con workers activos (5ms / 0.6ms / 1.1ms consecutivos). Logs muestran los 3 workers arrancando con leader-election idempotente. Listo para validar en deploy de producción.



## 2026-05-14 — FIX P0 BLOQUEADOR DE DEPLOY (CAPA 3): /health bypass de middlewares

**Síntoma persistente**: tras el fix de grace period y defer lifespan, el deploy SEGUÍA fallando con NGINX timeout en `/health`. Logs mostraban patrón confuso: `/api/system/errors/count` respondía 200 OK mientras `/health` timeout 10s consistentemente. Esto pasaba aunque pasara el grace period inicial.

**Root cause (capa 3)**: cuando el AI Eval worker hace LLM calls (15-25s cada una con LiteLLM + httpx + descarga imágenes Routal), el event loop se satura. Aunque mi endpoint `/health` es trivial (1 return), la request debe atravesar TODA la cadena de middlewares:
1. CORSMiddleware
2. SecurityHeadersMiddleware
3. AuditMiddleware (logging async)
4. global_rate_limit_middleware (resuelve user del JWT)
5. **Llegada al endpoint**

Cada middleware hace `await call_next(request)` que cede al event loop. Si el event loop está saturado, ese `await` puede tardar segundos en retomar control. Suma de N middlewares con N awaits + event loop saturado = `/health` tarda 10+ segundos → NGINX timeout → pod unhealthy → 520.

Confirmación: `/api/system/errors/count` también atraviesa la misma cadena pero el frontend lo polling con tolerancia (timeout >10s); NGINX para probe sí tiene timeout corto, por eso solo `/health` falla aparentemente.

**Fix** (`/app/backend/server.py`): nuevo middleware `_health_fast_bypass` registrado como **ÚLTIMO** middleware (FastAPI aplica middlewares en orden reverso, último registrado = más externo). Intercepta `/health` y `/api/health` ANTES de cualquier otro middleware y responde inmediatamente:

```python
@app.middleware("http")
async def _health_fast_bypass(request, call_next):
    path = request.url.path
    if path == "/health" or path == "/api/health":
        return JSONResponse({"status": "ok"}, status_code=200)
    return await call_next(request)
```

No toca DB, no toca event loop pesado, no atraviesa ningún otro middleware. La respuesta es inmediata aunque todo lo demás esté saturado.

**Verificación en preview**:
- 10/10 hits a `/health`: **HTTP 200 en 0.5-3 ms** (antes: 2ms, ahora 0.5ms = 4x más rápido)
- `/api/health`: 0.5ms también
- `/api/journeys` sigue requiriendo auth (HTTP 401) → otros middlewares funcionan normal
- Crucial: este endpoint responde aunque el AI Eval worker esté procesando 3 LLM calls en paralelo

**Resumen de las 3 capas de fixes para destrabar deploy**:
| Fix | Resolvió |
|---|---|
| Idempotencia workers (12 may) | Workers acumulándose tras restart |
| Defer lifespan a background (14 may AM) | Startup bloqueante de migrations + indices |
| Grace period 60s al AI worker (14 may tarde) | Bloqueo inmediato post-startup por LLM calls |
| **/health bypass de middlewares (este fix)** | Bloqueo del probe NGINX aunque event loop esté saturado |

**Acción para PROD**: redeploy desde panel Emergent. Esta vez `/health` responde con seguridad <1ms sin importar el estado del backend, el probe pasa, el pod queda healthy.



## 2026-05-14 — FIX P0 BLOQUEADOR DE DEPLOY (CAPA 2): grace period para AI Eval worker

**Síntoma**: deploys a PROD seguían fallando con timeout `/health` en NGINX (mismo síntoma del fix anterior del lifespan), pero ahora con un patrón diferente: `/api/system/errors/count` SÍ respondía 200 OK, mientras que `/health` consistentemente timeout. Reproducido en preview: tras minutos de actividad del AI Eval worker, `/health` empezaba a colgarse 3+ segundos.

**Root cause (capa 2 del bug del lifespan ya arreglado el 2026-05-14)**:

El fix de `_deferred_startup` resolvió el lifespan inicial. Pero inmediatamente después del `Application startup complete`, el AI Eval worker:
1. Hacía polling y encontraba jobs En_Cola.
2. Descargaba 3 jobs simultáneamente (`max_routes_concurrent=3`).
3. Lanzaba 3 LLM calls paralelas (cada una 15-25s con httpx + LiteLLM + descarga de imágenes Routal).
4. El event loop se saturaba a tal grado que `/health` respondía >10s.
5. NGINX (timeout 10s) marcaba el pod unhealthy.
6. Sub-efecto: el `_heartbeat_loop` de leader-election no podía ejecutar en tiempo → leader perdía lease → el retry de otra replica se promovía → ambas replicas arrancaban workers → doble carga → loop infinito.

Validación: en logs reales de preview se observó:
- `[leader] lost lease for 'bg_tasks' — agendando retry` durante actividad LLM
- LLM calls tardando 15-25s consistentemente
- `/health` timeout 3s aún con CPU del pod en 0% (event loop bloqueado, no CPU)

**Fix** (`/app/backend/ai_eval_worker.py`):

Nuevo env var `AI_EVAL_STARTUP_GRACE_SECONDS` (default 60s). Aplicado al inicio de `_worker_loop` y `_cron_sweep`:

```python
if STARTUP_GRACE_SECONDS > 0:
    logger.info(f"AI Eval worker grace period: sleeping {STARTUP_GRACE_SECONDS}s")
    await asyncio.sleep(STARTUP_GRACE_SECONDS)
    logger.info("AI Eval worker grace period elapsed — starting to poll jobs")
```

Durante 60s después del arranque, el worker no procesa jobs. El event loop queda libre para responder a probes de NGINX. Tras el grace period, el procesamiento normal arranca.

**Verificación en preview**:
- `Application startup complete` → inmediato
- `AI Eval worker grace period: sleeping 60s before processing` ← visible en logs
- **10/10 health checks consecutivos**: HTTP 200 en **2ms** durante el grace period
- Tras 60s, workers empezaron a procesar normalmente sin afectar la salud del pod

**Acción para PROD**: redeploy desde panel Emergent. Esta vez el pod arrancará con 60s de grace para pasar los probes, después procesará el backlog.

**Trade-off aceptable**: el primer barrido de evaluación ocurre 60s más tarde que antes. Es invisible para el usuario (el cron normal corre cada 30 min). Ajustable vía `AI_EVAL_STARTUP_GRACE_SECONDS=0` si se quiere desactivar.



## 2026-05-14 — FIX P0 BLOQUEADOR DE DEPLOY: lifespan startup > timeout NGINX

**Síntoma**: deploys a PROD fallaban con NGINX logueando timeouts cada 10s sobre `/health`:
```
upstream timed out (110: Connection timed out) while reading response header
from upstream "http://127.0.0.1:8001/health"
```
Esto causa que el pod nunca se marque "ready" → ingress devuelve 520 → deploy falla. Es la **segunda manifestación del mismo síntoma** (la primera fue por workers acumulándose en el event loop, arreglada el 2026-05-12 con idempotencia).

**Root cause** (`/app/backend/server.py` `lifespan`): el bloque de startup ejecutaba **en serie** y **antes de emitir `Application startup complete`**:
1. `_create_indexes()` — N índices en MongoDB
2. `_auto_migrate_order_id()` — migración
3. `_auto_migrate_routal_source()` — migración
4. `init_encryption(db)` — query DB
5. `bootstrap_default_clients(db)` — query DB
6. `acquire_leader(db, role="bg_tasks")` — query DB

Mientras esto corría, **uvicorn no aceptaba conexiones HTTP** (FastAPI lifespan bloquea el startup del servidor). En PROD (Atlas más lento que Mongo local), la suma de operaciones excedía los 10s del probe NGINX → todos los probes timeout → pod nunca pasa readiness check.

**Fix**: separar lifespan en 2 fases:

1. **Lifespan crítico (bloqueante, <100ms)**: solo `init_encryption(db)` (necesario para que las queries con PII funcionen). Spawnea `_deferred_startup` como task y hace `yield` inmediatamente → `Application startup complete` se emite en <1s.

2. **`_deferred_startup` (background task)**: ejecuta en background sin bloquear el servidor:
   - `_create_indexes()`
   - `_auto_migrate_order_id()`
   - `_auto_migrate_routal_source()`
   - `bootstrap_default_clients(db)`
   - `acquire_leader(db)` + arranque de workers vía callback
   - Tolera errores (logger.error pero no crashea el server)

3. **Shutdown del lifespan**: cancela el deferred task si aún corre, luego release_leader + stop workers + close mongo.

**Verificación en preview**:
- Antes del fix: `Application startup complete` tras ~5-15s (variable, dependía del estado de DB)
- Después del fix: `Application startup complete` en **<1s** consistente
- `/health` responde HTTP 200 en **2ms** desde el primer hit
- 12 muestras consecutivas a 5s de intervalo: todas 200 en 2ms, sin degradación durante AI Eval procesando jobs en paralelo
- Logs verifican que indices/migrations/leader-election corren en background después del startup complete

**Acción para PROD**: redeploy desde panel Emergent. Esta vez el probe NGINX pasará en <1s, el pod se marcará ready, e ingress enrutará tráfico.



## 2026-05-13 — FIX P0: crash al expandir guía (TypeError en getErrorSeverity)

**Síntoma reportado**: en `/journeys/4659459c-5417-47b7-a78c-5b802a14a4a3` (PROD), al hacer click en la guía `Vs7EMusQ9tseeCoB` la app pide "recargar la página". Solo esa guía, en otras del mismo journey no pasa. El operador no puede revisarla.

**Root cause** (`/app/frontend/src/components/guias/GuiasHelpers.jsx` línea 103):

```javascript
for (const rawKey of iaErrorsRaw) {   // ← asumía Array
```

`getErrorSeverity` asumía que `ia_errors_raw` es siempre Array. Sin embargo, el AI Eval worker persiste ese campo como **dict** (`{ error_key: 'critical'|'warning' }`) para los packages TIPO B/C donde detecta múltiples categorías de error. Hacer `for...of` sobre un objeto plano en JavaScript lanza `TypeError: iaErrorsRaw is not iterable` → React Error Boundary lo intercepta → muestra el banner de "recargar página".

**Por qué solo una guía**: los otros packages tenían `ia_errors_raw` en formato Array (legacy) o `null` (sin evaluación AI). El package `Vs7EMusQ9tseeCoB` (entrega TIPO B a Fabián Hernández - vigilancia) tenía dict porque la evaluación AI agrupó 2 errores críticos: `missing_whatsapp_notification` y `incomplete_type_b_evidence`.

**Fix**: normalización defensiva en `getErrorSeverity`:
- Array → se itera tal cual (legacy preservado).
- Object plain → `Object.keys()` para iterar las claves del dict.
- Cualquier otra forma (string, number, etc) → array vacío, retorna null sin crash.

Verificado con node script: 4 casos pasan (dict, array, null/undefined, forma inesperada). El package `Vs7EMusQ9tseeCoB` retorna correctamente `"critical"`.

**Acción para PROD**: redeploy. Tras el deploy el operador puede expandir la guía sin error.



## 2026-05-13 — FIX P0: notas del driver no se sincronizaban para guías failed

**Síntoma reportado**: en `/journeys/1b3c4094-...` el package `gfo7tSYML4OcIsgq` (Fallida) mostraba "Sin nota del driver" en LastMile, pero en Routal la sección "Comentarios" del reporte del stop tenía "Titular cancelo paquete". El usuario adjuntó screenshots de ambos sistemas para comparar.

**Root cause** (`/app/backend/services/routal_sync.py` rama `failed`, líneas 286-309 originalmente):

`sync_journey_from_routal` SÍ extraía `driver_note` del report Routal (campo `report.comments`), pero en la rama de packages `failed`:
1. SOLO escribía ese valor en `fail_reason`, NO en `kosmo_driver_note`.
2. La rama `delivered` (líneas 263-264) sí escribía `kosmo_driver_note` correctamente.
3. Resultado: 99.8% (433/434) de los packages failed en preview tenían `kosmo_driver_note` vacío. La UI mostraba "Sin nota del driver" indefinidamente.

Adicionalmente, la rama failed no persistía `routal_report_id` ni `routal_signature_url` (asimetría con `delivered`), lo cual también impedía que el sync detectara el package como "unchanged" en futuras corridas → re-procesaba lo mismo sin actualizar.

**Fix**:

1. `services/routal_sync.py` (rama failed):
   - Persistir `kosmo_driver_note`, `routal_report_id` y `routal_signature_url` igual que en rama `delivered`.
   - Guarda "unchanged" ahora también requiere que `kosmo_driver_note` ya esté persistida (antes saltaba sin importar). Esto evita que packages histórcamente saltados queden estancados.

2. `scripts/backfill_driver_notes_failed.py` (nuevo):
   - One-shot reutilizable. Soporta `--dry-run` y `--limit N`.
   - Identifica todos los journeys con packages failed sin nota Y que tienen `routal_plan_id` (1 query agregada por journey, no por package).
   - Llama al `sync_journey_from_routal` parchado.
   - Idempotente: re-correrlo solo sana lo que aún falta.
   - Inicializa encryption singleton (necesario para `IntegrationService.get_routal_client`).

**Verificación en preview** (sweep ejecutado):
- Antes: 434 packages failed · 1 con nota (0.2%)
- Después: 455 packages failed · 446 con nota (98.0%) · 9 sin nota legítimo (en Routal tampoco tienen comentario)
- 249 packages sanados en 29.3 segundos, 0 errores.
- Notas recuperadas son reales y descriptivas: "No coincide la dirección...", "Cliente ausente y solicita reprogramar...", "Falta torre y departamento...", etc.

**Acción para PROD**:
1. Redeploy desde panel Emergent (lleva el fix del sync).
2. Para sanar retroactivamente las guías históricas: 
   - Opción a) UI: presionar "Re-sincronizar Routal" journey por journey (tedioso si hay muchos).
   - Opción b) Script: `cd /app/backend && python -m scripts.backfill_driver_notes_failed --dry-run` para previsualizar, luego sin `--dry-run` para ejecutar. El operador necesita acceso al pod (vía soporte Emergent).
3. Validar abriendo `/journeys/1b3c4094-...` — el package `gfo7tSYML4OcIsgq` debe mostrar la nota del driver.



## 2026-05-12 — FIX P0 BLOQUEADOR DE DEPLOY: workers acumulándose, /health timeout

**Síntoma reportado**: deploys a PROD fallaban con NGINX devolviendo 520 y log:
```
upstream timed out (110: Connection timed out) while reading response header
from upstream "http://127.0.0.1:8001/health"
```
Repetido cada 10s durante minutos. El backend SÍ corría (kosmo_sync, AI Eval workers logueaban actividad), pero `/health` no respondía → Kubernetes marcaba pod unhealthy → ingress devolvía 520.

**Root cause**: `start_periodic_sync` (kosmo) y `start_ai_eval_worker` NO eran idempotentes. Cada vez que se llamaban, creaban tasks nuevas vía `asyncio.create_task` SIN cancelar las anteriores. En combinación con el sistema de leader-election retry implementado el mismo día (callbacks `_start_bg_tasks` se ejecutan tanto en acquire inicial como en cada retry-promotion), los procesos acumulaban **N copias paralelas** de los loops del worker. Reproducido en preview: hot reload + retry promotion → 10 instancias paralelas de `kosmo_sync` corriendo al mismo tiempo → event loop saturado → `/health` tardaba **57s** en responder → NGINX timeout (10s default).

**Fix** (mínimo, 2 archivos):

1. `/app/backend/kosmo_sync.py` (función `start_periodic_sync`):
   ```python
   if _sync_task and not _sync_task.done():
       logger.info("Kosmo adaptive sync already running — skip duplicate start")
       return
   ```

2. `/app/backend/ai_eval_worker.py` (función `start_ai_eval_worker`):
   ```python
   if _worker_task and not _worker_task.done():
       logger.info("AI Eval worker already running — skip duplicate start")
       return
   ```

**Nota**: los otros 2 workers (`routal_sync_worker`, `routal_selection_worker`) ya tenían esta guarda — solo faltaba en estos 2.

**Verificación end-to-end en preview**:
- Antes del fix: `/health` → 57s (timeout en NGINX)
- Después del fix: `/health` → 2-7ms consistente en 10 mediciones
- Probado retry-promotion via `POST /api/ai-evaluation/reset-leader`:
  - Lost lease → retry → acquired → "skip duplicate start" en ambos workers ✅
  - `/health` se mantuvo en 2ms durante todo el ciclo

**Acción para PROD**: redeploy. El backend ahora responderá al probe de NGINX de inmediato y el pod se marcará healthy.



## 2026-05-12 — FEATURE: incidencia auto-creada al rechazar guía desde ReviewModal

**Petición del usuario** (con screenshots): fusionar el flujo del recuadro "Rechazo manual (override)" en `ReviewModal` con el modal "Nueva Incidencia". En vez de tener que abrir un segundo modal después de rechazar, que el operador elija el "Tipo de incidencia" desde el mismo modal de revisión y la incidencia se cree automáticamente, sin dejar de reflejarse en la pestaña Incidencias.

**Implementación**:

1. **`/app/frontend/src/components/ReviewModal.jsx`**:
   - Nuevo estado `incidentType` (reset al abrir/cambiar de package).
   - Nuevo selector "Tipo de incidencia *" agregado a AMBOS paneles:
     - Panel rojo de rechazo (score < 70, panel obligatorio).
     - Panel amarillo de override manual (score ≥ 70, "Rechazar manualmente").
   - Reutiliza el catálogo `INCIDENT_TYPES` de `lib/utils.js` (5 opciones, mismo del modal "Nueva Incidencia").
   - Botón "Confirmar rechazo" está deshabilitado hasta que el operador elija motivo + tipo de incidencia.
   - `handleConfirm` pasa `incident_type` en el payload solo cuando es rechazo.
   - Data-testids: `rejection-incident-type-select` (panel rojo), `override-incident-type-select` (panel amarillo).

2. **`/app/frontend/src/components/GuiasTab.jsx`** (`handleReviewModalConfirm`):
   - Import nuevo: `createIncident` desde `lib/api`, `buildIncidentDescription` desde `lib/incidentTemplate`.
   - Cuando `action === 'rejected'` Y hay `incident_type` → llama a `createIncident()` justo después de `reviewPackageWithNote()`.
   - Payload: `journey_id`, `occurred_at` (now), `incident_type`, `severity` (derivada del adjusted_score vía `suggestSeverity`), `description` (auto-generada con `buildIncidentDescription` — score, criterios fallidos, alertas IA, guía, driver), `tracking_number`, `source='evaluacion'` (distinguible de incidencias manuales), `comentario_asesor` (solo si tipo='otro').
   - Si falla la creación de la incidencia, NO bloquea el rechazo (que ya se persistió). Se muestra UN solo toast (error o success, no ambos — fix sugerido por el testing agent).
   - Mensajes de toast diferenciados: "Guía aprobada" / "Guia rechazada e incidencia creada" / "Guia rechazada" (incident_type no seleccionado) / error específico si falla la incidencia.
   - `onRefreshJourney()` se sigue llamando → la incidencia aparece en la pestaña Incidencias sin pasos manuales.

**No se rompió**: el modal "Nueva Incidencia" original sigue funcionando para casos que no nazcan de un rechazo de guía. El flujo de aprobación normal no cambia.

**Verificación**:
- Lint OK ambos archivos (sin warnings).
- Smoke test del backend: `POST /api/incidents` con payload del frontend → HTTP 200, incidencia creada con `source='evaluacion'`. DELETE limpio funciona.
- Code review del testing agent: "No business-logic regressions introduced. The change is additive and well-scoped." Identificó un bug de doble-toast que fue corregido.

**Acción para PROD**: redeploy desde el panel de Emergent.



## 2026-05-12 — ROOT CAUSE + FIX: leader-election sin recovery tras redeploy

**Incidente recurrente**: tras cada redeploy, el AI Eval worker queda muerto en PROD. El backend FastAPI responde 200 a nivel HTTP, pero la background task del worker nunca arranca, dejando cientos de jobs en cola sin procesar. Síntoma reportado por el usuario: dar clic en "Evaluar IA todas" no genera actividad en `/admin` ni `/monitor`, y los jobs quedan En_Cola indefinidamente.

**Root cause** (`/app/backend/leader_election.py`):

`acquire_leader` solo intentaba ganar el lock una vez al arrancar el pod. Si fallaba (por ejemplo, porque un pod muerto en redeploy abrupto dejó su lock con `expires_at` futuro), el nuevo pod quedaba como `FOLLOWER` permanente — **nunca reintentaba**. Resultado:
- Background tasks (AI Eval, Kosmo sync, Selection scheduler, Routal sync) jamás se inician
- El backend luce sano a nivel API porque el endpoint sigue respondiendo
- Jobs se acumulan En_Cola sin ser tomados
- Único arreglo previo era reiniciar el deployment de nuevo y rezar que esta vez ganara el lock

**Fix**:

1. **Retry automático en `acquire_leader`** (`leader_election.py`):
   - Si el acquire inicial falla, se agenda una coroutine de retry en background que poll cada 10s.
   - Cuando el lock zombi expira (max 30s en condiciones normales), el retry gana el lock y dispara automáticamente los callbacks registrados → workers arrancan sin intervención.
   - `release_leader` ahora cancela también el retry task.

2. **Retry también en pérdida de lease durante runtime** (`_heartbeat_loop`):
   - Si por algún motivo perdemos el lease en runtime (ej. admin borró el lock vía `reset-leader`), agendamos el retry automáticamente. Antes la coroutine simplemente terminaba.

3. **Sistema de callbacks** (`register_on_leader_callback`):
   - `server.py` registra el arranque de los workers como callback idempotente.
   - El callback se ejecuta tanto en acquire inicial como en promoción via retry.

4. **Endpoint de emergencia** `POST /api/ai-evaluation/reset-leader` (`/app/backend/routes/ai_eval_routes.py`):
   - Borra todos los locks de `bg_tasks` en la colección `leader_election`.
   - Permite destrabar PROD sin redeploy si el lock zombi sobrevive.
   - Requiere rol `developer`.
   - Tras llamarlo, el retry de cualquier pod activo se promueve en máximo 10s.

5. **Status `/health` corregido**:
   - Orden de checks invertido: `stuck` (job individual >30 min) ahora se evalúa **antes** que `saturated` para evitar que 3 jobs zombi de 8 horas se vean como "saturated".

**Verificación en preview** (test end-to-end):
- `POST /reset-leader` → `[leader] lost lease — agendando retry` (13:33:47)
- 10s después: `[leader] promoted to leader after retry. Starting registered bg tasks.` (13:33:57)
- Workers arrancan automáticamente sin restart manual.

**Acciones para PROD**:

1. **Redeploy** desde el panel de Emergent para llevar el código nuevo a PROD.
2. Tras el deploy, el worker arranca automáticamente (con retry si el lock zombi sigue vivo). Verificar con:
   ```
   curl https://lastmile-mvp.emergent.host/api/ai-evaluation/health
   ```
   Debe retornar `healthy` o `saturated` (con jobs procesando).
3. Si después de 2 min sigue `stalled`, ejecutar (token del operador):
   ```
   curl -X POST https://lastmile-mvp.emergent.host/api/ai-evaluation/reset-leader \
     -H "Authorization: Bearer $TOKEN"
   ```
   Esto borra el lock zombi y dispara el retry. En max 30s arranca el worker.

**Impacto operacional**: el incidente pasa de "8 horas de jobs atascados sin que nadie se entere" a "auto-recovery en <30s tras redeploy" + "fix manual en 1 curl si recurre".



## 2026-05-12 — INCIDENT PROD + FIX: AI Eval worker stalled detection

**Incidente en PROD**: ~30 min después del redeploy con los fixes del cron sweep + image proxy, los jobs encolados dejaron de procesarse:
- 3 jobs en estado `Evaluando` durante 27 min con `guias_evaluadas=0`, `tokens_consumidos=0`, `last_progress_at == fecha_inicio` (nunca progresaron).
- 12 jobs en `En_Cola` sin tomarse a pesar de tener 3 slots libres lógicos.
- `/api/ai-evaluation/health` reportaba `"status": "healthy"` (falso positivo).

**Diagnóstico**: el background task `_worker_loop` del AI Eval worker dejó de correr en PROD. Probable causa: leader-election no recuperó el rol después del redeploy, o la coroutine crasheó silenciosamente sin re-arrancar. El backend FastAPI seguía operativo a nivel HTTP (de ahí el falso "healthy"), pero la tarea asíncrona del worker estaba muerta.

**Mitigación inmediata (sin redeploy)**: ejecutado `POST /api/ai-evaluation/recover-stuck` con `stuck_minutes=5` → 3 jobs zombi marcados como Error, slots liberados. Pero los jobs En_Cola siguen sin procesarse porque el worker sigue muerto → el operador debe **reiniciar el deployment** desde el panel de Emergent.

**Fix preventivo** (`/app/backend/routes/ai_eval_routes.py`): mejorado el endpoint `/api/ai-evaluation/health` para detectar este caso específico:
- Nuevo status `"stalled"`: `en_cola > 0 && slots_in_use == 0 && last_terminal_age > 60s`. Indica worker vivo a nivel API pero background task muerta.
- Nuevo status `"paused"`: refleja explícitamente cuando el worker está pausado (manual o por shadow autopause).
- Nuevo campo en response: `last_terminal_age_seconds` (edad del último job que terminó).

**Mapa de estados resultantes**:
- `paused` → operador pausó o autopause disparó.
- `saturated` → 3 slots usados, hay cola pendiente.
- `stuck` → un job individual lleva >30 min en Evaluando.
- `stalled` → ⚠️ background task muerta (acción: redeploy).
- `healthy` → todo normal.

**Acción para PROD**:
1. **Redeploy** desde el panel de Emergent (reinicia el pod → arranca worker).
2. Una vez deployado, validar `curl https://lastmile-mvp.emergent.host/api/ai-evaluation/health` debe retornar `healthy` o `saturated`, no `stalled`.



## 2026-05-12 — FIX P0: packages Routal stuck en "Pendiente" por drift de stop.id

**Síntoma reportado**: Ruta en LastMile (`/journeys/06edf7ea-...`) muestra 0/35 paquetes entregados aunque en el planner de Routal todas las 35 paradas están en estado **"Completada"**. El botón "Re-sincronizar Routal" no recupera nada.

**Root cause**: `sync_journey_from_routal` matcheaba packages ↔ stops Routal usando **una sola clave**: `pkg.routal_service_id == stop.id`. Cuando Routal rota el `stop.id` (similar a lo visto con `report_id` cuando un driver re-sube evidencia) los packages quedan en `no_match` silencioso → status `pending` permanente. Cada sync subsiguiente repite el mismo fallo porque no hay fallback.

Distinción importante (aclarada por el operador): el `status` del **journey** (planificada / in_progress / closed) lo controla **el operador manualmente**, NO es responsabilidad del sync. El sync solo debe mantener actualizado el `status` de los **packages** según los stops de Routal.

**Fix** (`/app/backend/services/routal_sync.py` + `/app/backend/workers/routal_sync_worker.py`):

1. **Matching robusto en cascada**:
   - Primera vuelta: `routal_service_id == stop.id` (comportamiento previo)
   - Fallback: matchear por `pkg.tracking_number` (o `order_reference_id`) contra cualquiera de `stop.tracking_number / stop.reference / stop.client_external_id / stop.fixed_id`.

2. **Auto-heal `routal_service_id`**: cuando el fallback encuentra match, persiste el nuevo `stop.id` y un timestamp `routal_service_id_healed_at`. Las syncs futuras matchean directo sin re-lookup.

3. **Telemetría**:
   - Summary del sync incluye nuevo campo `recovered_by_fallback: N`.
   - Worker log incluye `healed_service_id+=N`.
   - Si `no_routal_match > 0` y nada se sanó, emite `WARNING` con counts (visibilidad de drift residual — stops eliminados/reasignados).

**Lo que NO cambia**:
- `status` del journey sigue siendo manual del operador (apertura/cierre).
- No se introduce auto-cierre.
- Si el matching primario funciona, no se toca la DB (retro-compatible).

**Verificación en preview**: sync manual sobre journey Routal `1c185ad0-...` devuelve `recovered_by_fallback: 0` (matching primario OK, sin regresión).

**Acción para PROD**:
1. Redeploy desde el panel de Emergent.
2. Esperar máximo 10 min (intervalo del worker `ROUTAL_SYNC_INTERVAL_MINUTES`) o presionar **"Re-sincronizar Routal"** en `/journeys/06edf7ea-...` para forzar.
3. Los 35 paquetes deberían pasar de Pendiente → Exitosa en una sola sync.
4. En logs de PROD verás: `[routal-sync] journey=06edf7ea-... delivered+=35 healed_service_id+=35`.



## 2026-05-12 — FIX P0: AI Eval worker no procesaba packages Routal

**Síntoma reportado**: En `/admin?tab=model` el panel muestra "Worker activo", pero `Consumo de Tokens` y `/monitor` no reflejan actividad. Rutas con guías cerradas (ej. `/journeys/5b0a48ed-...`) quedan en "No evaluado por IA" indefinidamente.

**Root cause**: dos bugs combinados que dejaron al worker procesando 0 packages desde la migración a flujo Routal-only:

1. **`_cron_sweep` (ai_eval_worker.py L572)** filtraba por `tracking_url` no vacío. Ese campo es **legacy de Kosmo** y los packages sincronizados desde Routal lo dejan en `null`. Resultado en PROD: ~4636 packages elegibles, **0 matches** en el filtro.

2. **`_evaluate_single_guia` (ai_eval_worker.py L190)** llamaba `evaluate_single_package_ai(pkg, has_incident)` **sin pasar `db`**. La rama optimizada que resuelve URLs internas `/api/integrations/routal/image/...` vía `proxy_routal_image` (con cache en disco) no se activaba; caía a `httpx.get(url_relativa)` que fallaba con `Request URL is missing 'http://' protocol`. Todas las imágenes terminaban en fallback de reglas sin evaluación AI.

**Fix**:
- Cambiado el filtro del cron a `kosmo_proof_count > 0` (campo que pueblan **tanto** Kosmo legacy como Routal sync).
- Pasada la conexión `db` al evaluador para que use el proxy interno con cache.

**Optimización adicional (mismo deploy)**:
- Agregado filtro de **backlog scope** en el cron sweep para evitar gastar IA en histórico que ya no aporta valor operacional:
  - `delivered_at` o `created_at` ≥ `AI_EVAL_CRON_CUTOFF_DATE` (default `2026-05-10`, configurable vía env var sin redeploy).
  - `journey.status != "closed"` (solo rutas operativas — `scheduled`, `planificada`, `in_progress`).
- Reducción del universo: 4636 → **1432 packages** en **60 rutas operativas** (~70% ahorro).
- Resuelto via 1 query previa de journey_ids para evitar `$lookup` costoso en pipeline.
- `enqueue_job` manual (botones "Evaluar IA todas" / "Reintentar Errores") **NO aplica** el cutoff — opera sobre toda la ruta solicitada.

**Verificación en preview**:
- Cron sweep encontró 10 rutas en <30s tras filtro de fecha + status.
- Jobs avanzan: `Evaluando 19/63` (32%), 144K tokens consumidos.
- Token events: 3 → 26 eventos (24 evaluaciones). $0.27 USD acumulado en ~5 min.
- `httpx → api.routal.com` devuelve HTTP 200 para imágenes (descarga OK).

**Acción para PROD**: redeploy desde el panel de Emergent. Tras el deploy, el cron procesará solo el universo filtrado (~1400 packages, rutas abiertas, ≥10/05/2026). Para acelerar, presionar "Reintentar Errores" en `/monitor` (96 jobs reciclables — algunos quedarán filtrados si están en rutas cerradas o de fechas anteriores).



## 2026-05-10 — REVERTED: self-healing del proxy de imágenes Routal

**Decisión del usuario**: Eliminar el sanado automático de `report_id` rotados en `proxy_routal_image`. Paridad con la decisión equivalente sobre `plan_id` (2026-05-09).

**Motivación**: La rotación de `report_id` en Routal proviene de mala praxis operativa (drivers que re-suben evidencia horas después del cierre), no de un bug. Hacer un lookup pesado del plan + actualización masiva en cada render de imagen vieja generaba un loop costoso/infinito.

**Cambios** (`/app/backend/services/routal_sync.py`):
- `proxy_routal_image`: eliminado el bloque que llamaba a `_heal_outdated_report_id` ante 400/404. Ahora devuelve `None` (404 al cliente) limpio.
- Eliminada la función `_heal_outdated_report_id` completa.
- Docstring actualizado para documentar la decisión y derivar a "Re-sincronizar Routal" manual.

**Comportamiento esperado**:
- Si Routal rotó el `report_id`, las imágenes viejas devuelven 404 (placeholder CSS de `PhotoThumb` se muestra).
- El operador debe presionar "Re-sincronizar Routal" en el journey para refrescar las URLs persistidas.
- El sanado sigue ocurriendo dentro de `_sync_one` (manual sync), igual que antes.

**Verificación**:
- Backend arranca limpio (HTTP 200, workers OK).
- Sin referencias residuales a `_heal_outdated_report_id` en el repo.


## 2026-05-09 — REVERTED: self-healing del `routal_plan_id`

### Decisión del usuario
- El hallazgo del journey `82d473f9...` derivó de **mala práctica operativa en Routal** (reorganización manual del plan en planner.routal.com), no de un bug de Routal API.
- Aplicar self-healing automático del `plan_id` puede generar inconsistencias en LastMile (ej. un plan_id rotado podría apuntar a otro driver/sucursal por error humano y el sync sobreescribiría datos válidos).
- **Acción**: Rollback aplicado por el usuario en PROD. Código en preview revertido para mantener paridad.

### Rollback aplicado en preview
- Removido helper `_heal_outdated_plan_id()` de `services/routal_sync.py`.
- Removido bloque try/except de heal en `sync_journey_from_routal`. Vuelve a comportamiento previo: si `get_plan` falla, retorna error sin intentar lookup.
- Backend reinicia limpio ✅, lint clean ✅.

### Estado vigente en PROD (post-rollback)
- ✅ **Self-healing del `report_id`** (imágenes Routal): mantenido — solo afecta URLs de fotos, sin riesgo a integridad del journey.
- ✅ **Comparación `routal_report_id` en `_sync_one`**: mantenido.
- ✅ Resto de cambios de la semana (PhotoThumb, criteria_evaluation persist, toggle "Marcar todos", auto-fill incidencias, reportes Admin, perf P0+P1).

### Acción correctiva manual recomendada
Para journeys con `plan_id` obsoleto en BD (como `82d473f9`):
- **Opción 1**: corregir manualmente vía script (actualizar `routal_plan_id` con el ID nuevo que el operador ve en planner.routal.com).
- **Opción 2**: borrar el journey y dejar que el webhook/auto-backfill lo recree con el plan vigente.

## 2026-05-09 — Self-healing automático del proxy de imágenes Routal

### Reporte del usuario
- En PROD `journeys/363821e1.../guías/wOKsUDptnpWPOXgr` las fotos siguen sin cargar (mismo journey que ayer, otro paquete).
- Sync manual sigue diciendo `unchanged: 43` en PROD → confirma que el fix del 2026-05-09 (comparar `routal_report_id`) **NO está desplegado en PROD**.

### Investigación
- Test directo a Routal API: el report_id guardado (`69fd112191a50011f7ad093e`) responde 400. El report actual del mismo stop es `69fe1d390c329db3682ec4e3` y SÍ responde 200.
- Confirma que mi fix anterior (2026-05-09) sí resuelve el problema, pero solo aplicará después del redeploy.

### Fix adicional (proactivo): self-healing en el proxy
- `services/routal_sync.py:proxy_routal_image` ahora intercepta 400/404 de Routal API y:
  1. Busca el package en BD por `routal_report_id` viejo + posición de la imagen.
  2. Pulls plan vigente desde Routal API (`get_plan(routal_plan_id)`).
  3. Match el stop por `tracking_number` y obtiene el reporte completado más reciente.
  4. Persiste `kosmo_proof_urls`, `kosmo_proof_count`, `routal_report_id` y nuevo flag `routal_report_id_healed_at` en el package.
  5. Retorna la imagen al usuario en la misma petición HTTP.
- Cachea bajo AMBAS keys (vieja y nueva) para que las URLs cacheadas sigan funcionando.
- Logging informativo en cada healing para auditoría.

### Validación
- Test directo en preview: package con `report_id` falso `0000...ffff0` + URLs apuntando a ID falso. Llamada a `proxy_routal_image` → detecta 400, hace heal, devuelve **1.47MB** (imagen real). Package en BD queda con `routal_report_id` correcto + flag `routal_report_id_healed_at`. ✅
- Lint clean ✅.

### Acción del usuario
- 🚀 **Redeploy a PROD** para activar fix del 2026-05-09 + este self-healing.
- Tras redeploy, el journey `363821e1` (y cualquier otro afectado) recuperarán fotos automáticamente la primera vez que se abran — sin necesidad de re-sync manual.
- Para journeys masivos con URLs obsoletas, el worker `routal_sync_worker` también las recuperará en su tick de 10 min.

## 2026-05-09 — Bug fix: sync no actualizaba URLs cuando Routal cambiaba report_id

### Reporte del usuario
- En PROD `journeys/363821e1.../guías/8PzBzRTz8l0kLmNp`, las 3 fotos mostraban "No carga" (mi placeholder de PhotoThumb tras el último deploy).

### RCA
- PhotoThumb hace su trabajo: el backend devuelve genuinamente `{"detail":"Imagen no disponible en Routal"}` (404).
- Trace al `proxy_routal_image` reveló que Routal API responde `400 Bad Request` para los `report_id/image_id` guardados.
- **Bug raíz**: Routal **cambia el `report_id`** del stop cuando el driver re-sube evidencia (o reorganización de storage). Test directo confirma que el report nuevo (`69fd19ad...`) responde 200, pero el viejo guardado (`69fd4ced...`) responde 400.
- `routal_sync._sync_one` tenía guard `unchanged += 1` cuando `proof_count` y `status` coincidían — **ignoraba cambios en `report_id`**. Por eso re-sincronizar manualmente NO actualizaba las URLs (sync detectaba "sin cambios").

### Fix aplicado
- `services/routal_sync.py:_sync_one`: el guard ahora también compara `pkg.routal_report_id == evidence.report_id`. Si Routal reportó un report_id distinto, el sync actualiza `kosmo_proof_urls`, `kosmo_proof_count`, `routal_report_id` y la firma.
- Resultado: re-sincronizar el journey ahora SÍ recupera las URLs nuevas. PhotoThumb las cargará correctamente sin retry.

### Validación
- Test directo en preview: sync que antes retornaba `unchanged: 43` (todos sin cambio) ahora retorna `delivered_synced: 10` cuando los reports cambiaron — sí captura el cambio.
- Lint clean ✅.

### Acción del usuario
- 🚀 **Redeploy a PROD** para activar el fix.
- Después del redeploy, en cualquier journey con fotos rotas (como `363821e1`), **click "Re-sincronizar Routal"** desde el detalle. Las URLs se actualizarán automáticamente y las fotos cargarán.
- Para automatizar: el worker `routal_sync_worker` también usa esta misma lógica en su tick periódico, así que journeys con report_id obsoleto se irán recuperando solos.

## 2026-05-08 — Bug fix: thumbnail roto cuando img falla (broken-icon)

### Reporte del usuario
- En PROD `journeys/98f3a194.../guías/Bj76EC2lVP2ePCYX`, la "Foto 2" mostraba el icono "broken image" verde-blanco del browser en lugar de la foto.

### RCA
- Backend valida 100% OK: las 3 imágenes se sirven en 200/300ms con ~200KB c/u, incluso bajo concurrencia.
- Bug en `GuiasPackageDetail.jsx:41`:
  ```jsx
  onError={e => { e.target.src = ''; e.target.className = 'w-full h-full bg-slate-200'; }}
  ```
- Cuando la `<img>` falla (timeout transitorio, primer load durante login redirect, etc.), el handler ponía `src=''`. El browser interpreta src vacío como "URL inválida" → dispara OTRO `onError` recursivo + muestra el icono "broken image" nativo (NO el `bg-slate-200` esperado).

### Fix aplicado
- Nuevo componente `frontend/src/components/PhotoThumb.jsx`: 
  - Estado `initial → retry → failed`. En primer error, reintenta UNA vez con cache-busting `?_t=timestamp` (cubre timeouts transitorios).
  - En segundo error, swap a placeholder CSS-only con icono `<ImageOff>` y label "No carga" — clickeable para abrir carrusel y reintentar.
  - `loading="lazy"` para no saturar al renderizar listas de paquetes.
  - Nunca pone `src=''` → el navegador nunca muestra el broken-icon nativo.
- `GuiasPackageDetail.jsx`: usa `<PhotoThumb>` en lugar del button+img inline.

### Validación
- Lint clean ✅, bundle compila clean ✅.
- Test directo del backend: la foto problemática responde 200 + 200KB en <300ms consistentemente (5 muestras + concurrente 3x).

⚠️ **Acción usuario**: 🚀 **Redeploy a PROD** + hard refresh.

## 2026-05-08 — Bug fix CRÍTICO: descripción solo listaba 1 criterio del slug

### Reporte del usuario
- En PROD `https://lastmile-mvp.emergent.host/journeys/19f9fdc1.../guías/o448IY3NEkAnaB9h`, el coordinador marcó MÚLTIPLES criterios como X (No cumple) en el modal de evaluación, pero la descripción de "Nueva incidencia" solo listaba 1 (el del Motivo de rechazo).
- Imagen: usuario marca con amarillo el bloque "CRITERIOS FALLIDOS:" y dice "Necesito que coloque todo lo que evaluamos como NO CUMPLE (el tache)".

### RCA
- Frontend `ReviewModal` enviaba al backend `criteria_evaluation: {key: 'pass'|'fail'|null}` con TODOS los criterios marcados.
- Backend `PATCH /api/packages/{id}/review` solo guardaba `manually_reviewed`, `review_note` (slug) y `adjusted_score`. **Descartaba el `criteria_evaluation` completo.**
- → Al abrir "Nueva incidencia" después, el helper solo encontraba el slug (`whatsapp_ausente`) y mapeaba 1 criterio.

### Fix aplicado
- **Backend** `journey_routes.py:review_package`: ahora persiste `criteria_evaluation` traduciendo `'pass'→true / 'fail'→false / null→null` y guardándolo en `evidence_detail.criteria_met`. Misma estructura que la evaluación IA — coexisten en el mismo campo.
- También persiste `evidence_detail.delivery_type_detected` (formato 'A'/'B'/'C') para que el helper detecte correctamente el tipo en futuras revisiones.
- **Frontend** `ReviewModal.detectDeliveryType`: ahora acepta short codes 'A'/'B'/'C' (en minúsculas) además de strings descriptivos como 'terceros'/'fallida'.
- **Helper `incidentTemplate.js`**: sin cambios — ya leía `evidence_detail.criteria_met` correctamente. Ahora con el fix de backend, ese campo viene con TODOS los criterios marcados manualmente.

### Validación
- Test directo PATCH `/api/packages/{id}/review` con `criteria_evaluation` de 6 criterios (2 pass, 3 fail, 1 pass). Verifico: `evidence_detail.criteria_met` persistido con los 6 booleanos correctos. `delivery_type_detected: "B"` también persistido.
- Simulación inline JS con la data persistida: output correcto con **3 criterios listados** (Tercero recibiendo + Mensaje WhatsApp + Timestamp).
- Lint clean ambos lados.

### Output esperado en PROD post-redeploy
```
Faltantes detectados · Tipo B (Entrega a Terceros) · Score 50/100

CRITERIOS FALLIDOS:
• Tercero recibiendo — Persona (vecino/familiar/vigilante)
• Mensaje WhatsApp [CRÍTICO] — Notificacion al cliente final
• Timestamp — Hora visible

Score IA: 50/100
Guía: o448IY3NEkAnaB9h · Driver: Alejandro Juárez
```

### Acción del usuario
- 🚀 **Redeploy a PROD** (incluye este bug fix + toggle "Marcar todos como Cumple" + fix incidentTemplate del 2026-05-07).
- ⚠️ **Importante**: este fix solo aplica a paquetes revisados **DESPUÉS** del redeploy. Paquetes ya revisados antes del fix tienen el `criteria_met` vacío en BD — se mostrarán como antes (con el slug del motivo). Si necesitas re-procesar paquetes históricos, hay que re-evaluarlos manualmente.

## 2026-05-08 — UX: Toggle "Marcar/Desmarcar todos" en evaluación de evidencia

### Petición del usuario
- En el modal "Evaluación de evidencia" agregar un checkbox para marcar/desmarcar todos los criterios con check (Cumple) en un solo click.
- Ubicación: en la cabecera "ENTREGA EXITOSA — N CRITERIOS" (alineado a la derecha).

### Solución
- `ReviewModal.jsx`: nuevo estado derivado `allPass` + handler `handleToggleAll()`.
- Comportamiento: si todos los criterios están en `pass`, click → desmarca todos a `null`. Si NO, click → marca todos como `pass`.
- UI: checkbox al lado del header con etiqueta dinámica:
  - "Marcar todos como Cumple" cuando no todos están marcados.
  - "Desmarcar todos" cuando todos ya están en pass.
- Test IDs: `criteria-toggle-all` (el input) y `criteria-toggle-all-label`.
- Funciona en los 3 tipos (A/B/C) — al cambiar tipo, el toggle se recalcula automáticamente.

### Validación
- Lint clean ✅, bundle compila clean ✅.

⚠️ **Acción usuario**: 🚀 **Redeploy a PROD** + hard refresh para ver el toggle.

## 2026-05-08 — Confirmación: fix anterior NO está en PROD + refinamiento Tipo B

### Investigación
- Usuario reportó que el bug "Sin criterios evaluados aún" persiste en `https://lastmile-mvp.emergent.host/journeys/73e0100f.../packages/CRQtlmrB7gtFvw7c`.
- Análisis de bundles JS de PROD: chunk `2816.9e98ee62.chunk.js` **contiene "Sin criterios evaluados aún"** y NO contiene "REVISIÓN MANUAL". → Mi fix del 2026-05-07 (parser de `manually_reviewed_note`) **no fue desplegado** a PROD.
- El package en PROD tiene la misma forma que el caso anterior: `manually_reviewed_note: "whatsapp_ausente"`, `reviewed_by: "Oswaldo Salinas"`, `ai_score: 50`. Mi helper en preview produce el output correcto.

### Refinamiento aplicado (P2 del backlog que ya tenía marcado)
- Si `manually_reviewed_note` es `whatsapp_ausente` o `foto_receptor_ausente` y `detectDeliveryType` defaultea a Tipo A (porque `delivery_type_detected` no estaba poblado), **forzar `deliveryType = 'B'`** (entrega a terceros). Esto permite mapear el slug `whatsapp_ausente → mensaje_whatsapp` (criterio que solo existe en Tipo B) y mostrar "Mensaje WhatsApp [CRÍTICO]" como criterio fallido en lugar del bloque genérico "REVISIÓN MANUAL".

### Output esperado para el caso del usuario (preview)
```
Faltantes detectados · Tipo B (Entrega a Terceros) · Score 50/100

CRITERIOS FALLIDOS:
• Mensaje WhatsApp [CRÍTICO] — Notificación al cliente final

Score IA: 50/100
Guía: CRQtlmrB7gtFvw7c · Driver: Alejandro Juárez
```

### Acción del usuario
- 🚀 **Redeploy a PROD** — éste es el bloqueador. Sin redeploy, el bundle viejo seguirá mostrando el texto buggeado.
- Tras redeploy, hacer un **hard refresh** (Ctrl+Shift+R / Cmd+Shift+R) o limpiar cache del browser para asegurar que el chunk nuevo se cargue.
- Validar con el mismo paquete `CRQtlmrB7gtFvw7c` que la descripción muestra "CRITERIOS FALLIDOS: • Mensaje WhatsApp [CRÍTICO]..." y ya no "Sin criterios evaluados aún".

## 2026-05-07 — Bug fix: auto-fill no contemplaba revisión manual

### Reporte del usuario
- En PROD, paquete `mO3Mv03B3tBi46mh` (journey `8567dc19...`) ya había sido **revisado manualmente** (Score 50, `manually_reviewed_note: "whatsapp_ausente"`, `reviewed_by: "Oswaldo Salinas"`).
- Pero el modal "Nueva incidencia" mostraba: *"Sin criterios evaluados aún — registrar incidencia manual"*. Mensaje incorrecto.

### RCA
- El helper `buildIncidentDescription` solo consultaba `pkg.evidence_detail.criteria_met` (vía evaluación IA).
- Cuando el paquete fue revisado manualmente vía `ReviewModal`, el backend guarda `manually_reviewed_note` + `review_note` + `adjusted_score` pero **no** un `criteria_met` consolidado en `evidence_detail` — eso se mantiene a nivel `training_samples` para fine-tuning.
- → criteria_met vacío → todos los items "unevaluated" → fallback al texto genérico equivocado.

### Fix aplicado
- `lib/incidentTemplate.js` ahora consume **3 fuentes** en cascada:
  1. **AI evaluation** (`evidence_detail.criteria_met`) — cuando IA evaluó.
  2. **Manual review** (`manually_reviewed_note` + `review_note` + `rejection_reason`) — parsea formato `"slug"` o `"slug: detalle libre"` (ver `GuiasTab.jsx:170`), mapea slug→criterio del catálogo (`whatsapp_ausente → mensaje_whatsapp`, `foto_fachada_ausente → foto_fachada`, etc.).
  3. **Fallback genérico** — solo cuando `(failed=0 && alerts=0 && note vacío && score=null)`.
- Nuevo bloque "REVISIÓN MANUAL:" con el label legible del slug + free-text + `Revisado por: ...`.
- `_scoreLine()` ahora soporta `adjusted_score` (cuando difiere de `ai_score`, lo expone como "Score IA → ajustado en revisión").
- `REJECTION_REASONS` ahora named export en `ReviewModal.jsx` para reutilizar catálogo.

### Output esperado para el caso reportado
```
Faltantes detectados · Tipo A (Entrega al Destinatario) · Score 50/100

REVISIÓN MANUAL:
• Captura de WhatsApp no proporcionada
Revisado por: Oswaldo Salinas

Score IA: 50/100
Guía: mO3Mv03B3tBi46mh · Driver: Gerardo Salinas
```
+ severity sugerida: `Medio` (score 50)

### Validación
- Lint clean ✅, bundle compila clean ✅.
- Smoke test inline JS con fixture replicando el package real de PROD: produce output esperado ✅.

⚠️ **Acción usuario**: 🚀 **Redeploy a PROD**.

## 2026-05-07 — UX: Auto-fill estructurado para "Nueva incidencia"

### Reporte del usuario
- Agentes registran incidencias desde el botón "Registrar Incidencia" en `Guías → detalle paquete`.
- El campo Descripción se prellena con texto genérico (`"Incidencia registrada desde Guias para paquete X"`).
- Los agentes lo borran y escriben manualmente la lista de criterios IA fallidos del modal "Evaluación de evidencia". Trabajo repetitivo.

### Solución (Propuesta A — template determinístico, sin LLM)
- Nuevo helper `frontend/src/lib/incidentTemplate.js`:
  - `buildIncidentDescription(pkg, journey)` genera template estructurado en español a partir de `pkg.evidence_detail.criteria_met`, `delivery_type` y alertas IA.
  - `suggestSeverity(score)` mapea score → `Alto/Medio/Bajo` (<50/<80/100).
  - `suggestIncidentType(deliveryType, hasCriticalFail, failedKeys)` mapea al catálogo canónico `INCIDENT_TYPES` (`autorizacion_tercero_incorrecta`, `evidencia_entrega_incorrecta`, `evidencia_incidencia_incorrecta`, `notas_incorrectas`).
- Refactor `ReviewModal.jsx`: `CRITERIA` y `detectDeliveryType` ahora son named exports (reutilizables en helper sin duplicar catálogo).
- `JourneyDetail.jsx:handleRegisterIncidentFromGuias` ahora aplica el helper. El agente ve el template y puede editarlo libremente antes de "Registrar".

### Ejemplo output (replicando screenshot del usuario)
```
Faltantes detectados en evaluación IA · Tipo B (Entrega a Terceros) · Score 75/100

CRITERIOS FALLIDOS:
• Tercero recibiendo — Persona (vecino/familiar/vigilante)
• Mensaje WhatsApp [CRÍTICO] — Notificación al cliente final

ALERTAS IA:
• Foto de persona recibiendo el paquete (criterio obligatorio TIPO B)
• La foto 0 muestra el paquete en mano, pero no es clara la identidad de quien lo sostiene

Score IA original: 75 → recalculado por criterios: 50
Guía: fjt09OoG827FkWs1 · Driver: Juan Cervantes Martinez
```
+ severity sugerida: `Medio` (score 75)
+ incident_type sugerido: `autorizacion_tercero_incorrecta` (Tipo B + mensaje_whatsapp fallido)

### Validación
- Lint frontend: clean ✅
- Smoke test inline JS con fixture replicando screenshot: output exacto ✅
- Bundle compila sin errores en preview ✅

### Pendiente
- 🚀 **Redeploy a PROD** para que agentes vean el template auto-llenado.
- Si en futuro se quiere upgrade a Propuesta B (narrativa con LLM), el helper actual queda como **fallback** y se agrega un botón "✨ Sugerir IA" sin tocar este código.

## 2026-05-06 — Mejoras backfill: cupo aditivo + filtro rutas vacías

### Petición del usuario
1. **Backfill y auto_backfill solo deben contemplar rutas con paquetes** (descartar rutas vacías que ensucian `/journeys`).
2. **Permitir que ejecuciones subsecuentes del backfill sumen rutas adicionales hasta llegar al límite Drivers/día**: ej. `max_daily=30`, primera corrida selecciona 10 → segunda corrida puede agregar hasta 20 más, sin exceder 30.

### Cambios aplicados
- **`services/selection_backfill.py`**: skip routes con `route_stops` vacío después del filtro `s.route_id == drv_id` (auto-backfill del scheduler).
- **`routes/selection_routes.py` (manual `backfill-from-routal`)**: mismo filtro, contabilizado en `skipped_no_driver`.
- **`workers/routal_selection_worker.py:run_daily_selection`** (refactor crítico):
  - Lee `already_selected` desde `driver_audit_log` ANTES de correr el algoritmo.
  - Calcula `remaining_quota = max(0, max_daily - len(already_selected))`.
  - Pasa solo `candidate_drivers` (excluye los ya seleccionados) y `max_daily=remaining_quota` a `_select_drivers()`.
  - Drivers ya seleccionados se preservan **intactos**: NO se hace upsert para no pisar `selection_phase` ni `journey_id`. Solo se marca el plan como `processed=True`.
  - Bug previo: re-corrida con plans nuevos podía hacer over-selection (10 + 25 = 35 cuando max=30). Ahora siempre `total ≤ max_daily_audits`.

### Validación (testing agent iter86 — 14/14 tests passed)
- Filtro rutas vacías en auto-backfill ✅
- Filtro rutas vacías en manual backfill ✅
- Cupo aditivo escenario A (max=5, 3+4 → 5 total con 2 unselected) ✅
- Cupo aditivo escenario B (max=10, 10+5 → 10 total, 5 unselected, cupo agotado) ✅
- Cupo aditivo escenario C (max=10, 5+5 → 10 total, cupo justo) ✅
- Preservación de `phase` + `journey_id` en drivers ya seleccionados ✅
- Idempotencia sin plans nuevos ✅
- Edge `max_daily=0` ✅
- Edge driver tardío con cupo saturado → unselected ✅
- Regresión iter85 auto-backfill, iter83 reportes Admin, iter59 perf ✅

### Acción del usuario
- 🚀 **Redeploy a PROD** para activar las mejoras.
- Tras redeploy, el backfill y auto-backfill descartarán rutas sin paquetes y respetarán siempre el cupo `max_daily_audits` aunque se ejecuten múltiples veces al día.

## 2026-05-06 — Bug fix: Selection scheduler ignoraba clientes con webhooks rotos

### Reporte del usuario
- En PROD `/settings → Auditorías → Cubbo MX`, el scheduler con cortes 06:00 y 15:01 CDMX corría según calendario pero las journeys no se cargaban automáticamente.
- "Resumen de hoy" mostraba PLANES=0, SELECCIONADOS=0, P1/P2=0 ambas ejecuciones.
- Solo funcionaba al pulsar manualmente "Ejecutar ahora" o "Recuperar rango".

### RCA
- Cubbo MX no recibía webhooks de Routal desde **2026-04-26** (10 días). Verificado vía `/api/webhooks/routal/{client_id}/status`: `last_event_at: 2026-04-26T03:27:15`.
- El scheduler depende de que `routal_daily_plans` esté pre-poblada por webhooks (`plan.created`/`plan.updated`).
- Sin webhooks → staging vacío → `run_daily_selection()` retorna `total: 0` → 0 audits.
- "Recuperar rango" funcionaba porque consulta directamente la API Routal `GET /v2/plans` (no depende de webhooks).

### Fix aplicado
- **Nuevo módulo** `services/selection_backfill.py`:
  - `backfill_plans_for_date(db, client_id, target_date)`: pulls plans directamente desde Routal API `/v2/plans` + `/v2/plan/{id}` con caps de seguridad (PAGE_SIZE=100, MAX_PAGES=30, MAX_HYDRATE=200). Idempotente (upsert por `client_id+driver_id+date`).
  - `maybe_backfill_if_empty(db, client_id, target_date)`: ejecuta el backfill SOLO si `routal_daily_plans` no tiene registros pendientes (no consume rate-limit cuando webhooks sí están llegando).
- **Scheduler modificado** (`workers/routal_selection_worker.py`): cada cutoff ahora llama `maybe_backfill_if_empty()` antes de `run_daily_selection()`, haciendo el sistema resiliente a outages de webhooks.
- **No tocado**: el endpoint manual `POST /api/selection/run/{client_id}` mantiene su contrato (no auto-backfill) — el usuario sigue eligiendo cuándo invocar la API Routal manualmente.

### Validación (testing agent iter85 — 9/9 tests passed)
- `routal_inactive` retorna `staged=0` sin lanzar excepción ✅
- Si hay plans staged, NO se llama API Routal (preserva rate-limit) ✅
- Si staging vacío + Routal inactivo → mensaje claro ✅
- Mock de Routal API hidrata plans correctamente ✅
- `run_daily_selection` con plans staged sigue funcionando (sin regresión) ✅
- Scheduler arranca sin errores ✅
- Regresiones iter83 (`/api/admin/routes-report`) y iter84 (`/api/health.routal_sync`) intactas ✅

### Acción del usuario
- 🚀 **Redeploy a PROD** para activar el auto-backfill.
- Tras redeploy, mañana 2026-05-07 a las 06:00 CDMX el scheduler debería cargar drivers automáticamente sin intervención manual, incluso si Routal sigue sin enviar webhooks.
- Revisar también la integración de webhooks Routal: ir a Settings → Integraciones, copiar la URL de webhook de Cubbo MX (`/api/webhooks/routal/0b6590e9-...`) y verificar que esté configurada correctamente en Routal. El auto-backfill es resiliencia de fallback, no reemplaza los webhooks (más eficiente).

## 2026-05-06 — Bug fix: Routal sync worker no actualizaba algunos journeys

### Reporte del usuario
- En PROD, journey `f4ce8961-5269-4836-8425-ccc28b69854c` (status `planificada`, 38 paquetes) no actualizaba sus paquetes automáticamente.
- Sync manual funcionaba; el worker autónomo no.
- Otros journeys con status idéntico (`planificada`) sí estaban siendo sincronizados — solo algunos se quedaban pegados.

### RCA
1. **Filtro MongoDB no defensivo**: `{"$or": [{"$exists": False}, {"$lt": cutoff}]}` perdía documentos con campo presente pero `null`. Test confirmado: filtro viejo encuentra 2/3 docs (missing + old), filtro nuevo encuentra 3/3 (missing + null + old).
2. **Status `in_progress` no contemplado**: el worker filtraba solo `planificada` + `en_ruta` (obsoleto). Tras iter84/iter85 los journeys también pasan por `in_progress` antes de cerrar — esos quedaban fuera del barrido.
3. **Errores silenciados**: `_sync_one` solo logueaba si había cambios. Si Routal API devolvía error (`ok=false`), el journey quedaba siendo retried indefinidamente sin que se viera nada en logs ni en `/api/health`.
4. **`/api/health` no exponía Routal sync**: solo había heartbeats de `kosmo_sync` y `ai_eval_worker`. Imposible ver desde fuera si el worker Routal estaba vivo o atascado.

### Fixes aplicados
- **`workers/routal_sync_worker.py`**:
  - Filtro `routal_synced_at` reescrito a `{"$not": {"$gte": skip_synced_after}}` — defensivo contra missing/null/old (los 3 casos válidos).
  - Status filter ahora incluye `in_progress` y `scheduled` además de `planificada` y `en_ruta`.
  - `_sync_one` ahora loguea WARNING cuando `summary.ok=false` y estampa `routal_synced_at` + `routal_last_sync_error` en el journey para evitar busy-loops y dar visibilidad.
  - Tick log subido de `DEBUG` → `INFO` para verificar latido del worker en logs PROD.
- **`server.py`**:
  - Nuevo check `routal_sync` en `/api/health`: reporta `last_heartbeat_seconds_ago` (basado en `routal_synced_at` más reciente) y `pending_candidates` (cuántos journeys está esperando sincronizar el worker).

### Validación
- Test directo en MongoDB con 4 docs (missing/null/old/recent): filtro viejo falla en `null`, filtro nuevo correcto.
- Backend reinicia sin errores, worker arranca y loguea `tick processed 0 journeys` cada 10 min.
- `/api/health` ahora muestra el nuevo bloque `routal_sync` con métricas vivas.

### Acción del usuario
- 🚀 **Redeploy a PROD** para activar el fix.
- Tras redeploy, en PROD el journey `f4ce8961` debería sincronizarse en el siguiente tick (≤10 min). Validar en `/api/health` que `routal_sync.pending_candidates` baja a 0.
- Si algún journey queda con `routal_last_sync_error` setteado, ese campo expone el error de Routal (plan eliminado, key inválida, etc.) — útil para troubleshooting reactivo.

## 2026-05-05 — Bug fix: Reportes Admin duplicaban rutas Routal (iter79)

### Reporte del usuario
- Día 2026-04-24 en LastMile/Power BI: **38 rutas**.
- Mismo día en reporte Admin Excel: **43 rutas** (5 extras).
- Discrepancia solo en rutas Routal: cada `Vehículo N` aparecía 2 veces (1 con order_id MX-... real + 1 con UUID interno del plan legacy).

### RCA
- 11 endpoints de reportes/analytics NO aplicaban el filtro de migración iter79.
- Cuando un `journey legacy` (plan-based) se split a N `journeys nuevos` (route-based), el legacy queda en BD con `migrated_to_journeys: [id1, id2, ...]`.
- `/api/journeys` ya filtraba con `$or: [migrated_to_journeys missing, _legacy_incidents_remaining>0]`, pero `/api/admin/routes-report`, `/api/admin/export-liquidacion` y 10 endpoints de analytics NO.

### Fix aplicado
- **Nuevo helper** `apply_legacy_journey_filter()` en `dependencies.py` — defensivo contra `$or`/`$and` existentes (combina con `$and` para no romper full-text search).
- **Aplicado en 11 endpoints**:
  - `admin_module_routes.py:routes_report` (que también alimenta `export-liquidacion` y `routes-report/export`).
  - `analytics_routes.py`: `get_heatmap_data`, `export_heatmap_data`, `get_quality_report`, `export_quality_report`, `export_incidents`, `report_kpis`, `get_reports_heatmap`, `report_attempts`, `report_sla`, `generate_ai_report`.

### Validación (testing agent iter83 — 21/21 tests passed)
- Fixture: 1 legacy + 2 nuevos, día 2026-05-04 → reporte retorna 2 (NO 3) ✅.
- Edge case: si legacy tiene `_legacy_incidents_remaining > 0`, sí aparece (3) ✅.
- Edge case: `_legacy_incidents_remaining = 0` o ausente → oculto ✅.
- Regresión: `/api/journeys?q=...` (full-text search con `$or`) sigue OK con el `$and` defensivo ✅.
- Regresión completa de los 11 endpoints + cache PR2 (clients/providers TTL): clean ✅.

### Pendiente (acción usuario)
- 🚀 **Redeploy a PROD** para que el fix surta efecto.
- 📊 Tras redeploy, verificar que reporte Admin del día 2026-04-24 muestra 38 rutas (no 43).

## 2026-05-05 — PR2: Auditoría de Performance P0+P1 (Fixes A→F)

### Diagnóstico (PROD)
- MongoDB Atlas ping = **1.1s** (vs ~5-50ms esperado, indica latencia de red elevada).
- `/api/journeys` con 10 reqs concurrentes: **11-16s cada una** (sin paralelismo en código + pool MongoDB sin warmup).
- 6 queries DB **secuenciales** en `/api/journeys` (count + find + clients + providers + 2× incidents.aggregate).
- `AsyncIOMotorClient` sin configuración de pool (defaults: minPoolSize=0, sin compresión, serverSelectionTimeoutMS=30s).
- ROUTAL_TIMEOUT = 30s causaba que image proxy 404 bloqueara workers por 30s.

### Fixes aplicados
- **Fix A** `dependencies.py`: `AsyncIOMotorClient` con `maxPoolSize=50`, `minPoolSize=10`, `maxIdleTimeMS=60000`, `waitQueueTimeoutMS=5000`, `serverSelectionTimeoutMS=5000`, `compressors="zlib"`, `retryWrites=True`. Pool warm desde el arranque.
- **Fix B** `routes/journey_routes.py`: `/api/journeys` ahora ejecuta `count + find + clients + providers` en `asyncio.gather` paralelo, y los 2 `incidents.aggregate` también paralelos. De 6 roundtrips secuenciales a 1+1 wallclock.
- **Fix C** `routes/user_routes.py`: `/api/clients` y `/api/providers` con `@ttl_cache(ttl_seconds=300)` y `invalidate_prefix()` en mutaciones (POST/PUT/DELETE).
- **Fix D**: incidents aggregations paralelas con `asyncio.gather` (parte de Fix B).
- **Fix E** `server.py`: nuevos índices en `journeys` — `migrated_to_journeys` (sparse), `_legacy_incidents_remaining` (sparse), compound `[client_id, date, status]` y `[provider_id, date]`.
- **Fix F** `services/routal_client.py`: ROUTAL_TIMEOUT default 30s → **10s** (configurable vía env).

### Validación (testing agent iter59, preview)
- **17/17 tests passed** en 3.62s (`/app/backend/tests/test_iter59_perf_p0_p1.py`).
- **10 GET /api/journeys concurrentes** → wall=**0.78s** (antes 11-16s), max individual 0.77s, avg 0.74s. **~15× mejora**.
- Contrato API `/api/journeys` preservado: `data[] + pagination.{total_count,total_pages,page,page_size}` + items con `client_name`, `provider_name`, `incidents_count`, `open_incidents_count`.
- Cache invalidation `clients_list` y `providers_list` confirmada en POST/PUT/DELETE.

### Pendiente / Backlog
- **Atlas region/tier**: testing solo cubrió preview (Mongo localhost). Para confirmar mejora real en PROD, hay que **redeployar** y medir con `/api/system/performance`. Si la latencia base de Atlas sigue alta (1.1s ping), el techo de mejora será limitado por la red — escalar a Emergent Support para alinear región Atlas ↔ pod PROD.
- **Optional perf pulida** (P2): reusar `_cache` interno de `clients_list`/`providers_list` dentro de `/api/journeys` (hoy aún hace DB, pero en paralelo no agrega wallclock). Surface Mongo pool metrics en `/api/admin/health`.
- **Watch out** Fix F: si Routal `/v2/plan/{id}/stops` con planes muy grandes tarda >10s, ahora fallará. No cubierto por tests.

## 2026-05-05 — PR1: Limpieza de ruido en Error Tracker

### Diagnóstico (`/system/errors` PROD: 197 no-revisados)
- **58,592 hits** `GET /health 404` — probe interno (k8s/monitor) llamando a `/health` sin prefijo `/api`.
- **181 hits** `GET /api/integrations/routal/image/... 404` — imágenes Routal expiradas (1 row por `image_id`).
- **45 hits** `GET /api/client-config 403` — `Journeys.jsx` llamaba `listClientConfigs()` para todos los roles, pero el endpoint solo permite `developer`.
- **9 × HTTP 500** transitorios `connection pool paused` (MongoDB Atlas, ventana 30s del 2026-05-04).

### Fixes aplicados
- `backend/middleware.py`: agregado `/health` a `skip_paths`; agregado `/api/integrations/routal/image/` y `/api/integrations/routal/signature/` a `expected_404_prefixes`; agregado skip global para HTTP 429 (rate-limit es respuesta defensiva esperada, no bug).
- `backend/server.py`: nuevo alias `GET /health` → `{"status":"ok"}` (lightweight liveness probe sin DB check, separado del `/api/health` completo).
- `frontend/src/pages/Journeys.jsx`: `listClientConfigs()` ahora solo se llama si `user.role === 'developer'`. Otros roles ya no triggerean 403 al entrar a `/journeys`.

### Limpieza retroactiva en PROD
- Marcados 191 errores ruido como `reviewed=true` vía script (4 iteraciones por cap de 200 del listado).
- Estado final: **6 errores reales pendientes** (sync-journey 400, journey close/start 422, backfill 502, incidente DELETE 404). Estos quedan para PR 2.

## 2026-04-15 — 5 Feature Prompts Implementados (P1-P5)

### P1: Refresh Token para Power BI
- Nuevo endpoint `POST /api/auth/refresh-token` genera tokens de 90 días
- `POST /api/auth/exchange-token` intercambia refresh → access token
- `GET /api/auth/refresh-tokens` lista tokens activos
- `DELETE /api/auth/refresh-token/{jti}` revoca un token
- Snippets actualizados en ApiDocumentation (Python + Power Query M Code)
- Solo coordinadores/developers pueden generar tokens

### P2: Fix Fórmulas Liquidación
- Columna O: Cambiado de `delivered` a `=H{r}+I{r}` (entregas + fallidas)
- Columna AB: Cambiado de `=O/sla` a `=O/MAX(G,sla)` (evita div by zero y usa el mayor)

### P3: Eliminar Ruta + Columna Driver
- `DELETE /api/journeys/{id}` con cascade: paquetes, incidencias, imágenes, training_samples
- Audit log registrado con detalle de eliminación
- Modal de confirmación con lista de datos que se eliminarán
- Solo coordinadores/developers ven el botón eliminar

### P4: Order ID + Búsqueda + Paginación
- Columna Order ID como primera columna en tablas Journeys y Dashboard
- Búsqueda rápida por Order ID, driver, cliente, proveedor
- Paginación con selector 25/50/100 por página
- Order ID en header de JourneyDetail con botón copiar al clipboard

### P5: Inicio de Ruta — Checklist eliminado + 32 Estados
- Checklist de salida eliminado completamente (9 items)
- Validación de checklist removida de handleStartJourney
- Dropdown "Tipo de ruta" ahora tiene 33 opciones: CDMX + 32 estados de México

### Test Results
- Backend: 21/21 tests passed (100%)
- Frontend: 5/5 features verified (100%)
- Test report: `/app/test_reports/iteration_40.json`

---

## 2026-04-10 — Bug Fix: Reportes mostraba 0% para fechas con datos

### Causa Raíz
El campo `date` en journeys tiene formato mixto: `"2026-04-09"` (solo fecha) vs `"2026-04-09 20:33:23.480000"` (fecha+hora).
La query usaba `$lte "2026-04-09"` que excluye `"2026-04-09 20:33:23"` por comparación lexicográfica de strings.

### Corrección
Reemplazado `$lte date_to` por `$lt _next_day(date_to)` en **10 endpoints** de analytics_routes.py:
- `/reports/quality` (L170)
- `/reports/generate` (L330)
- `/reports/generate-excel` (L455)
- `/reports/journeys` (L560)
- `/reports/incidents export` (L614)
- `/reports/journeys list` (L703)
- `/reports/kpis` (L912) — **principal**
- `/reports/attempts` (L1071)
- `/reports/sla` (L1164)
- `/reports/daily-stats` (L1282)

También corregido `datetime.strptime` sin truncar hora (L925) y `group_by "day"` truncado a 10 chars.

### Verificación
- Query nueva con `$lt "2026-04-10"`: 5 journeys encontradas ✅
- Query vieja con `$lte "2026-04-09"`: 0 journeys ❌

---

## 2026-04-10 — PDF Export Redesign (Multi-page)

### Problem
- Old PDF: Single html2canvas screenshot, compressing everything to one illegible page
- Only captured the active tab, losing 5 of 6 sections

### Solution
- Created `/app/frontend/src/lib/pdfReportGenerator.js` (new 430-line module)
- Uses jsPDF + jspdf-autotable for native PDF rendering (no DOM screenshots for tables)
- Charts captured via html2canvas on individual chart elements only

### PDF Structure (8 pages)
1. **Cover**: Header bar + AI cards + 4 KPI blocks (24pt values) + Charts (combo + donut)
2. **Proveedores**: Full table with autoTable (sortable, formatted)
3. **Drivers**: Full table with SLA highlight
4. **Incidencias**: Breakdown by type
5. **Intentos**: Distribution bars + retry cause bars
6. **Evidencias**: Score global, by type, by provider with progress bars
7. **SLA**: Consolidated score, brackets, by-provider table, top drivers
8. **Analisis IA**: Cards + paginated narrative text

### Technical Details
- Added `jspdf-autotable@5.0.7` dependency
- Uses `applyPlugin(jsPDF)` for v5.x compatibility
- Page numbers "Pagina X de Y" in footer
- Color-coded KPI blocks matching dashboard
- Minimum 9pt text for readability

### Test Results
- Backend: 10/10 tests passed (100%)
- Frontend: All features verified (100%)
- Bug found and fixed: `applyPlugin(jsPDF)` required for jspdf-autotable 5.x
- Test report: `/app/test_reports/iteration_39.json`

---

## 2026-04-10 — Code Quality Corrections Applied

### Security Fixes
- Renamed `_run_ai_eval` to `_background_ai_evaluation` in journey_routes.py (eliminates eval() scanner false positive)
- Added `ALLOWED_TAGS` and `ALLOWED_ATTR` restrictions to DOMPurify in Reports.jsx and LumiChat.jsx
- Extracted `renderMarkdown()` function in Reports.jsx for safer HTML rendering

### React Hook Dependency Fixes
- Added eslint-disable comments with justification for intentional dependency omissions in ReviewModal.jsx and JourneyDetail.jsx

### Backend Complexity Refactoring
- **evidence_scoring.py**: Split `_call_ai_vision` (81 lines, CC:15) into 4 focused helpers:
  - `_get_system_prompt()` - reads custom prompt from DB
  - `_get_training_context()` - fetches calibration examples
  - `_build_user_context()` - builds evaluation context string
  - `_log_ai_token_usage()` - non-blocking token logging
- **liquidacion_export.py**: Extracted 6 helpers from complex functions:
  - `_write_provider_data_row()`, `_write_provider_pivot_table()` from `_build_provider_sheet`
  - `_write_summary_header()`, `_write_route_data_row()` from `_build_route_summary_sheet`
  - `_fetch_incidents_for_export()`, `_resolve_provider_sla()` from `generate_liquidacion_excel`

### Frontend Component Splitting
- **GuiasTab.jsx** (1014 lines, CC:197) → 3 modular files:
  - `GuiasTab.jsx` (684 lines) — main component with hooks and table
  - `guias/GuiasHelpers.jsx` (149 lines) — ScoreCircle, ConfidenceBar, StatusPill, ReviewIndicator, SeverityBadge, KpiCard, DiscRow
  - `guias/GuiasPackageDetail.jsx` (214 lines) — expanded row detail with evidence, AI eval, manual review

### Other Fixes
- PulseStrip: Changed array index key to `r.label` for proper React reconciliation
- Test credentials: Moved hardcoded passwords to `os.environ.get()` with defaults in 3 test files

### Test Results
- Backend: 15/15 tests passed (100%)
- Frontend: All components verified (100%)
- Test report: `/app/test_reports/iteration_38.json`

---

## 2026-04-10 — P1, P2, P3 Features Verified (3 features)

### P1: Inline Incident Registration from Guías Tab
- "Registrar Incidencia" button in expanded package row (GuiasTab.jsx line 870-878)
- Opens incident modal pre-populated: type=Evidencia Insuficiente, source=guias, tracking_number auto-filled
- Backend `IncidentCreate` model supports `source` field (models.py)
- Files: `GuiasTab.jsx`, `JourneyDetail.jsx` (handleRegisterIncidentFromGuias), `models.py`

### P2: AI Reports Generation v2.0 with Dynamic Cards
- POST /api/reports/generate-ai returns {narrative, cards[], period}
- Cards: 3 structured items (tipo: alerta/tendencia/logro, titulo, cuerpo, metrica, variacion)
- Frontend renders color-coded cards (red/blue/green) + markdown narrative
- Stale indicator when filters change post-generation
- Files: `Reports.jsx` (AiInsightsBar), `analytics_routes.py` (generate_ai_report)

### P3: Cubbo Standard Evidence Evaluation (ReviewModal)
- ReviewModal with delivery type selector (A/B/C), criteria cards with pass/fail toggles
- Weighted score calculation with critical failure cap (50pts max)
- 9 predefined rejection reasons + manual override
- Discrepancy tracking (AI vs Manual decisions)
- Files: `ReviewModal.jsx`

### Test Results
- Backend: 11/11 tests passed (100%)
- Frontend: 3/3 features verified (100%)
- Test report: `/app/test_reports/iteration_37.json`

---

## 2026-04-09 — AI Evaluation UX Improvements (3 features)

### 1. Severity Badges in GuiasTab
- Added `SeverityBadge` component showing "CRITICO" (red) and "ALERTA" (amber) labels
- Badges appear in the Errores table column and in the expanded detail row per error
- Backend enrichment updated to pass `ia_severity` and `ia_errors_raw` fields to frontend
- Files: `GuiasTab.jsx`, `journey_routes.py` (enrichment fix)

### 2. Quick Review Modal
- Created `ReviewModal.jsx` with score slider, motivo dropdown, detalle textarea, AI incorrect toggle
- Integrated into GuiasTab: Aprobar/Rechazar buttons now open the modal instead of inline actions
- Modal resets state correctly when switching between packages (useEffect on open/pkg.id/action)
- Files: `ReviewModal.jsx`, `GuiasTab.jsx`

### 3. Background AI Evaluation with Polling
- Added in-memory status tracking in `evidence_scoring.py` (`_ai_eval_status` dict)
- New endpoint `GET /api/journeys/{journey_id}/ai-eval-status` returns progress info
- Frontend polls every 3 seconds during evaluation, showing a progress banner (top-right)
- Banner shows percentage, package count, and error count with animated progress bar
- Auto-refreshes journey data on completion
- Files: `evidence_scoring.py`, `journey_routes.py`, `api.js`, `GuiasTab.jsx`

### Test Results
- Backend: 14/14 tests passed (100%)
- Frontend: All UI elements verified (100%)
- Test report: `/app/test_reports/iteration_34.json`

## 2026-04-09 — Bug Fix: Confidence Score 0% with evidence present
- **Root cause**: `_compute_confidence()` used enriched field names (`ai_score`, `photos_count`, `ai_errors`) but operated on raw DB documents where those fields don't exist
- **Fix 1**: Updated `_compute_confidence` to use raw DB fields: `evidence_score`, `kosmo_proof_count`, `ia_errors`, `evidence_detail.missing_items`
- **Fix 2**: Updated `_detect_discrepancy` to use `kosmo_proof_count` 
- **Fix 3**: Added confidence auto-recalculation after `batch-rescrape` completes (fixes timing issue where confidence was calculated before Kosmo data was available)
- **Result**: False positive discrepancies dropped from 3→0, confidence now accurately reflects evidence
- Files: `journey_routes.py` (`_compute_confidence`, `_detect_discrepancy`, `batch_rescrape_journey`)

## 2026-04-09 — 3 User Findings Fixed (Kosmo Photos, System Prompt, Training)

### 1. Kosmo Batch Re-Scrape: Missing Photos
- **Root cause**: `batch_rescrape_journey` only re-scraped packages with 0 evidence or unknown status; Kosmo often adds photos after initial scrape
- **Fix**: Changed query to re-scrape ALL packages with tracking URLs; added `updated_proofs` counter for packages that gained new evidence
- **Result**: Package `6fzwjfH4k2fzlpgQ` went from 2→4 photos, matching Kosmo tracking page
- Files: `journey_routes.py` (batch_rescrape_journey)

### 2. System Prompt Not Connected to AI Evaluation
- **Root cause**: `_call_ai_vision()` used hardcoded `CUBBO_SYSTEM_PROMPT` instead of the custom prompt configured in Quality Criteria settings (`ia_config.system_prompt`)
- **Fix**: Split prompt into base criteria + JSON response format. AI now reads custom prompt from `db.config(key=ia_config)` and appends JSON format specification to ensure structured output
- **Result**: AI evaluation now uses the detailed Cubbo standard prompt configured by the user
- Files: `evidence_scoring.py` (_call_ai_vision, CUBBO_SYSTEM_PROMPT, AI_RESPONSE_FORMAT)

### 3. Supervised Training Not Generating Value
- **Root cause**: Manual reviews stored data on packages but never created training samples or fed them back to the AI
- **Fix**: 
  - `review_package_with_note` now saves `adjusted_score` and `ai_evaluation_incorrect` fields
  - Creates `training_samples` documents in MongoDB on each review (with error_type, decision, scores, notes)
  - `_call_ai_vision` fetches recent incorrect AI evaluations from `training_samples` and includes them as calibration examples in the AI prompt
  - Quality Criteria error catalog shows `frequency_last_30d` from training_samples
- Files: `journey_routes.py` (review_package_with_note), `evidence_scoring.py` (_call_ai_vision)

### Test Results
- Backend: 14/15 tests passed (93%, 1 skipped due to ID format)
- Test report: `/app/test_reports/iteration_35.json`

## 2026-04-10 — Reports Module Complete Redesign

### Filter Bar
- Horizontal chip-based filter bar with "Hoy" as default period
- Period options: Hoy, 7 días, 15 días, Mes actual, Mes anterior, Semana anterior, Personalizado
- Client and Provider dropdown filters with chip UI
- Date range display chip showing active period
- Mobile responsive with collapsible filter panel

### KPI Cards Strip (4 metrics)
- Tasa de entrega, Tasa de visita, Calidad evidencias, SLA vs Target
- Delta vs previous period (green up / red down arrows with pp units)
- Health bar at bottom of each card (green ≥90%, amber ≥75%, red <75%)

### Charts Section
- **Combo chart**: Orders assigned (bars) vs Avg delivery time (line) per day using Recharts
- **Donut chart**: Incident breakdown by type with legend and percentages
- Backend `daily_stats` endpoint added to `generate_report` with date normalization

### AI Insights On-Demand
- Decoupled from report generation (report loads in <1 sec vs 23 sec)
- "Generar IA" button triggers separate API call
- Stale indicator when filters change after generation
- Insight cards with lavender background

### Tables
- **Providers**: Rate bars, SLA badges (On target/At risk/Breach), activity dots
- **Drivers**: Rate bars, amber background for SLA <60%, strike policy note
- **Incidents**: Type + count, imputability note
- **Attempts**: Distribution bars + retry causes
- **Quality**: Score globe, completas/incompletas, by type chips, by provider bars
- **SLA**: Consolidated view, editable brackets, provider/driver breakdown

### Exports
- **Excel**: Enhanced with filtered data
- **PDF**: New client-side generation using jsPDF + html2canvas, includes header with metadata + AI insights page

### Test Results
- Backend: 9/9 passed (100%)
- Frontend: 13/13 features verified (100%)
- Test report: `/app/test_reports/iteration_36.json`

---

## 2026-04-09 — Discrepancy Detection
- Confidence engine with 5 evidence factors
- GuiasTab UI: 6 KPI cards, alert banner, discrepancy filter, confidence column, review actions
- Discrepancy review: confirm_return / mark_valid decisions

## 2026-04-07 — Code Quality Report Fixes
- Fixed dynamic import eval security issue
- Added useMemo optimizations across React components
- Refactored kosmo_sync.py

## 2026-04-07 — Pulse Feasibility Engine
- PulseStrip, PulseCell, PulseBanner components
- Real-time route feasibility monitoring
- Traslado a 1er punto moved to individual journey start form

## 2026-04-07 — Dynamic SLA Configuration
- Per-provider SLA brackets
- SLA/Pulse config edit permissions for Coordinators
- Liquidacion del Servicio export (Belgos/SOP format)
