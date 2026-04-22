# LastMile OS — Arquitectura Viva (Auto-documentación)

**Audiencia**: DevOps, Arquitectos de Soluciones, líder técnico
**Actualización**: autogenerado cada vez que se regenera el snapshot
**URL en app**: `/arquitectura` (roles `developer`, `executive`)

---

## 1. Propósito

`/arquitectura` es la **fuente de verdad viva** del estado técnico de LastMile OS.
Se genera **leyendo el codebase real** mediante AST parsing — **nunca se escribe a mano**.
Esto elimina el drift clásico entre documentación y código.

Cada snapshot incluye:
- **Capa 1 — Sistema**: diagrama de flujo cliente → ingress → frontend/backend → Mongo → integraciones externas.
- **Capa 2 — Datos**: ER de las top 15 colecciones con ownership de escritura.
- **Capa 3 — Flujos**: diagrama de secuencia del pipeline IA end-to-end.
- **Módulos funcionales**: líneas de código y endpoints por dominio.
- **Antipatrones**: violaciones detectadas (multi-layer writes, rutas sin protección).
- **Changelog**: diff estructural vs snapshot anterior.

## 2. Arquitectura (a la fecha)

```
Internet (HTTPS)
    │
    ▼
Emergent Kubernetes ingress-nginx  ← TLS, HTTP/2, gzip, CORS dinámico, WebSocket upgrade
    │
    ├── /api/*  :8001  FastAPI (uvicorn, supervisor-managed)
    │              ├── 169 endpoints across 16 routers
    │              ├── asyncio workers: kosmo_sync.py + ai_eval_worker.py
    │              └── MongoDB (Motor async driver, 33 colecciones)
    │
    └── /*      :3000  React SPA (17 páginas, ~85 componentes)
                   └── httpOnly JWT cookies (lm_access_token, Secure, SameSite=lax)
```

### Integraciones externas detectadas
| Paquete | Uso | Fuente |
|---------|-----|--------|
| `emergentintegrations` | Emergent LLM (Claude Sonnet/Haiku, GPT, Gemini) | Multiple rutas IA |
| `litellm` | Proxy interno de Emergent LLM | `evidence_scoring.py` |
| `httpx` | Scraper Kosmo tracking | `kosmo_sync.py` |
| `slowapi` | Rate limiting (10 req/min login) | `auth_routes.py` |
| `motor` | MongoDB async driver | `dependencies.py` |

### Colecciones MongoDB (top 10 por operaciones)
Consultar `/arquitectura → Datos` para el listado completo con ownership. Claves:
- `journeys`, `packages`, `incidents`, `users`, `drivers`, `manuals`
- `ai_evaluation_jobs` (cola del worker de evaluación IA)
- `token_usage_log`, `audit_logs`, `webhooks`, `webhook_deliveries`
- `architecture_snapshots`, `architecture_changelog` (self-referential ✨)

## 3. Flujo crítico — Evaluación IA por ruta

```
Coordinador → click "Evaluar IA todas" (GuiasTab)
    ↓
POST /api/journeys/{id}/evaluate-evidence-all
    ↓ enqueue_job() inserta en ai_evaluation_jobs (status=En_Cola)
    ↓
AI Eval Worker (asyncio, max 3 concurrent)
    ↓ cada 10s: picks batch → marks Evaluando
    ↓ batch de 5 guías concurrentes
    ↓   → evaluate_single_package_ai(pkg, has_incident)
    ↓   → _call_ai_vision (Claude Sonnet 4.5, 6 imgs base64)
    ↓   → persiste resultado en packages
    ↓ actualiza progress_percent
    ↓
status final: Evaluada / Parcial / Error
    ↓
Monitor IA (/monitor) muestra estado en tiempo real
```

**Safeguards**:
- Timeout por guía: 90s (configurable vía `AI_EVAL_TIMEOUT_PER_GUIA`).
- Retry con backoff exponencial (max 2 reintentos).
- Orphan job recovery: jobs `Evaluando` > 30min se regresan a `En_Cola` al startup.
- Cron sweep cada 30min vuelve a intentar jobs pendientes.

## 4. Mecanismo de auto-sincronización

### 4.1 Componentes

| Componente | Archivo | Responsabilidad |
|------------|---------|-----------------|
| **Scanner** | `/app/backend/architecture_scanner.py` | Parse AST del codebase → genera snapshot dict |
| **API** | `/app/backend/routes/architecture_routes.py` | 6 endpoints CRUD + diff + changelog |
| **Persistencia** | `architecture_snapshots`, `architecture_changelog` | Versionado con content-hash (sha256) |
| **Página** | `/app/frontend/src/pages/Architecture.jsx` | Renderizado Mermaid en 5 tabs |

### 4.2 Triggers de regeneración
1. **Automático primera vez**: al abrir `/arquitectura` si no hay snapshots previos.
2. **Manual**: botón "Regenerar" (solo `developer` / `executive`).
3. **Programado (recomendado CI/CD)**: hook en post-deploy que haga `curl -X POST /api/architecture/regenerate`.

### 4.3 Detección de cambios (idempotente)
```
1. generate_snapshot() → dict con content_hash (sha256 de payload sin timestamp)
2. Si content_hash == último snapshot: status="unchanged", no persiste.
3. Si difiere: diff_snapshots(prev, curr) detecta:
     - collections_added / collections_removed
     - endpoints_added / endpoints_removed
     - frontend_routes_added / frontend_routes_removed
     - integrations_added / integrations_removed
     - new_antipatterns
4. Inserta snapshot nuevo + registro en architecture_changelog.
5. Housekeeping: mantiene solo los últimos 20 snapshots (GC automático).
```

### 4.4 Endpoints API

| Método | Path | Auth | Descripción |
|--------|------|------|-------------|
| GET    | `/api/architecture/snapshot` | cualquier user | Último snapshot (autogenera si 1ª vez) |
| POST   | `/api/architecture/regenerate` | developer, executive | Fuerza regen + detecta diff |
| GET    | `/api/architecture/history?limit=20` | cualquier user | Lista timestamps/hashes |
| GET    | `/api/architecture/snapshot/{id}` | cualquier user | Snapshot por ID |
| GET    | `/api/architecture/diff?from_id=X&to_id=Y` | cualquier user | Diff entre 2 snapshots |
| GET    | `/api/architecture/changelog?limit=50` | cualquier user | Historial de cambios |

### 4.5 Integración con CI/CD (roadmap opcional)

Para mantener la arquitectura 100% al día sin acción manual, agregar a `post-deploy`:

```bash
# GitHub Actions (ejemplo)
- name: Regenerate architecture snapshot
  run: |
    curl -X POST "${{ secrets.APP_URL }}/api/architecture/regenerate" \
      -H "Cookie: lm_access_token=${{ secrets.DEV_TOKEN }}" \
      --fail
```

Si el response contiene `diff.is_significant: true`, enviar notificación a Slack con el listado de `changes`.

## 5. Detección de antipatrones actuales

El scanner detecta automáticamente **7 antipatrones** en el estado actual:

| Tipo | Severidad | Descripción |
|------|-----------|-------------|
| `multi_layer_write` | high | Colección escrita desde `/routes` + worker/middleware |
| `unprotected_route` | medium | Ruta frontend sin `ProtectedRoute` wrapper |

Los `multi_layer_write` actuales (`config`, `packages`, `incidents`) son **legítimos** por diseño — los workers actualizan estado en paralelo con las APIs. Se documentan pero no bloquean.

## 6. Métricas clave del codebase (a la fecha)

- **Backend**: 16 módulos funcionales, 169 endpoints, 33 colecciones, 4 integraciones externas.
- **Frontend**: 17 páginas, ~85 componentes (sin contar shadcn/ui), 19 rutas.
- **Coverage**: `/app/backend/tests/` contiene ~45 archivos de tests (incluyendo iter20→iter47).
- **Background workers**: 2 (Kosmo Sync cada 45s, AI Eval Worker cada 10s + cron 30min).

## 7. Runbook — "¿Cómo lo uso?"

### Para DevOps
1. Post-deploy: `curl -X POST /api/architecture/regenerate`.
2. Monitorear `/api/architecture/changelog` para detectar cambios no documentados en PRs.
3. Alertar si `new_antipatterns` aparecen.

### Para Arquitecto de Soluciones
1. Visitar `/arquitectura` directamente.
2. Tabs Sistema → Datos → Flujos → Módulos para vista top-down.
3. Tab Changelog para ver evolución de la arquitectura en el tiempo.
4. Exportar snapshot con `GET /api/architecture/snapshot` (JSON) para presentaciones.

### Para Debugging
1. `GET /api/architecture/snapshot/{id}` de un snapshot previo antes del incidente.
2. `GET /api/architecture/diff?from_id=...&to_id=...` para aislar cambios entre despliegues.
3. Revisar `architecture_changelog` para trazabilidad de cambios estructurales.

## 8. Límites conocidos del scanner

- No detecta llamadas Mongo indirectas (via helpers) — solo patrón `db.X.operation`.
- No detecta endpoints declarados sin decorador `@router.*` (todos los endpoints reales lo usan).
- Las rutas frontend solo se parsean desde `App.js` (otros routers no estándar quedarían fuera).
- El ER del modelo de datos usa relaciones heurísticas (journey → packages, etc.) — no es una introspección real de schema (Mongo es sin schema).

Estos límites son aceptables porque la convención del proyecto es uniforme.

---

*Última actualización estructural: consultar `/arquitectura → Changelog` en la app.*
