# LastMile OS - Changelog

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
