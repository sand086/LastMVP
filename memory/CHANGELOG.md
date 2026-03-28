# LastMile OS - Changelog

## 2026-03-28 (Session 5)
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
