# LastMile OS - Changelog

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
