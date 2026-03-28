# LastMile OS - Changelog

## 2026-03-28 (Session 5 continued)
### Admin IA Module — Complete New Module
- **New page** `/admin` with 3 tabs accessible only for Developer/Executive roles
- **Tab 1: Consumo de tokens** — KPI cards (total tokens, costo USD/MXN, evaluaciones, lumi, reportes), 3 cards por entregable con Input/Output/Prompt + promedios por unidad, tabla de eventos paginada con filtros (período, entregable, modelo)
- **Tab 2: Reporte de rutas (Cubbo ADM)** — Tabla con 25+ columnas del layout Cubbo, filtros (fecha, driver, team, status), totals strip (rutas, días, pkgs, completados, evidencia, costo, km extra), selector de columnas con persistencia en localStorage, **Exportar Excel** funcional (LAYOUT_ADM_Cubbo_{fechas}.xlsx con headers estilizados)
- **Tab 3: Configuración de costos** — TC USD→MXN editable con historial, tabla de costos por modelo IA (input/output per million tokens), vista previa de costo por entrega, alertas de presupuesto (umbral, reporte semanal)
- **Token logging** integrado en `evidence_scoring.py` y `lumi.py` — estimación de tokens basada en longitud de texto, log en `token_usage_log` con costo calculado
- **Backend**: `admin.py` (5 endpoints), `token_logger.py` (helper), seeded config documents
- **Role-based access**: Solo Developer y Executive pueden acceder al módulo admin

### Supervised Training Enhancement
- Training section now always visible for coordinators/developers (removed `supervised_training_enabled` dependency)
- Added natural language text area for human feedback
- Added score override slider + numeric input
- Backend accepts `human_note`, `corrected_score`, stores `evidence_score_override` and `evidence_score_original`

### QA Bug Fix Round — 9/9 Bugs Resolved
- **BUG-001 [BLOQUEANTE]**: JourneyDetail defaults to Calidad tab for scheduled journeys with packages
- **BUG-002 [BLOQUEANTE]**: Coordinator added to ADMIN_ROLES in admin.py + AdminPage.jsx
- **BUG-003 [BLOQUEANTE]**: Reports now include all journey statuses (scheduled, in_progress, closed)
- **BUG-004 [ALTO]**: Training samples endpoint allows coordinator and agent roles
- **BUG-006 [ALTO]**: JourneyStartData model uses `extra = "allow"` for flexible validation
- **BUG-007 [MEDIO]**: Login rate limit increased from 5/min to 20/min
- **BUG-008 [MEDIO]**: `/api-docs` → 301 redirect to `/documentation` (backend level)
- **BUG-009 [MEDIO]**: 401 interceptor confirmed working (already existed)
- **Additional**: AdminPage.jsx role check updated to include coordinator
- **Testing**: Iteration 20 — 15/15 backend tests (100%), all frontend verified
### Quality Tab V2 — Journey Detail Redesign
- **New QualityTabV2 component** (`/app/frontend/src/components/QualityTabV2.jsx`):
  - KPI strip: score promedio, completos, incompletos, evaluados IA con confianza
  - Distribution bar (completos/parciales/incompletos en %)
  - Error summary banner con chips de errores detectados por IA y acción sugerida
  - Package table: Guía, Tipo, Score IA (círculos), Confianza (barra), Errores (chips), Fotos, Intento, Revisión, Acciones
  - Expandable row con detalle IA, fotos con indicadores de calidad
  - **Entrenamiento supervisado** siempre visible para coordinadores/developers:
    - Botones "Sí, es correcta" / "No, corregir"
    - Campo de texto libre en lenguaje natural para explicar la corrección
    - Slider + input numérico para modificar score a N%
    - Checkboxes de errores reales del catálogo
    - Backend guarda `human_note`, `corrected_score`, `evidence_score_override`, `evidence_score_original`
  - Pagination, filtro "solo alertas"
- **New backend routes** (`quality_tab_routes.py`):
  - `GET /api/journeys/{id}/quality-summary` — KPIs y resumen de errores
  - `GET /api/journeys/{id}/packages-quality` — Paquetes con detalle de calidad paginado
  - `POST /api/training/samples` — Guardar muestras de entrenamiento supervisado
  - `PATCH /api/journeys/{id}/packages/{guide}/review` — Aprobar/rechazar evaluación
- **Evidence scoring enhanced**: Structured JSON output with confidence, errors array, severity map, and feedback
- **API Documentation updated**: All v2 endpoints added to schema (quality-summary, packages-quality, training/samples, attempts, SLA, heatmap, lumi chat, quality settings master)
- **Route fix**: `/api-docs` → `/documentation` to avoid ingress prefix conflict

### Performance Optimization
- Added 20+ MongoDB indexes across packages, journeys, incidents, config, training_samples collections
- Parallelized dashboard stats queries with `asyncio.gather` (3x fewer sequential DB calls)
- Deduplicated legacy error key mapping

### Quality Criteria V2 Validation
- Confirmed all 5 tabs working: Evidencias, KPIs, SLA & Penalizaciones, Config IA, Tipos de Error

### Testing
- Iteration 18: 18/18 backend tests passed (100%), all frontend features verified (100%)

---

## 2026-03-27 (Session 4)
### Dashboard V2 Redesign
- KPI cards with live data, provider comparison
- Geographic heatmap with React-Leaflet + CartoDB tiles
- WebSocket real-time updates

### Reports V2 Redesign
- 6-tab reporting: General, Por Proveedor, Por Driver, Calidad, SLA, Intentos
- KPI strip, AI report generation, Excel export

### Lumi AI Chatbot
- Floating FAB chatbot integrated globally
- Context-aware responses using Claude Sonnet

### Batch Re-scrape
- Button and endpoint for batch Kosmo rescrape per journey

---

## 2026-03-26 (Session 3)
- Deployment fixes: CORS, N+1 queries optimized
- Quality Criteria V2 settings page (5 tabs)
- Quality Criteria master backend endpoints

---

## 2026-03-25 (Sessions 1-2)
- Initial MVP: Auth, uploads, journeys, incidents, Kosmo sync, AI scoring
- Failed packages search, image uploads, dynamic assignments
