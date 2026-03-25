# LastMile OS - Changelog

## 2026-03-25 - Major Feature Release (5 Features)

### P0: AI-Powered Evidence Scoring
- Rewrote `evidence_scoring.py` to use Claude Sonnet 4.5 (via Emergent LLM Key) for deep photo analysis
- AI evaluates delivery evidence against Cubbo standards (exitosa, terceros, fallida)
- Detects photo types (fachada, paquete, receptor, llamadas), OCR guide numbers, checks timestamps
- Returns structured results: photos_analysis, criteria_met, missing_items, alerts, ai_observations
- New endpoints: `POST /api/journeys/{id}/packages/{guide}/evaluate-evidence` (single) and `POST /api/journeys/{id}/evaluate-evidence-all` (batch, async background task)
- Falls back to rule-based scoring when AI unavailable or images expired
- Revamped QualityTab UI: expandable rows with detailed AI feedback, criteria checklists, new columns (Método, Fotos, Faltante/Alertas)
- "Evaluados IA" counter card in quality summary

### P1: Dynamic Pagination
- Server-side pagination for `GET /api/journeys` endpoint
- Frontend pagination controls: page size selector (25/50/75/100), First/Prev/Next/Last buttons, "Página X de N (Y rutas)" indicator
- Filters reset to page 1 automatically
- Response format: `{data: [...], pagination: {page, page_size, total_count, total_pages}}`

### P1: Interactive Evidence Carousel
- New `EvidenceCarousel.jsx` fullscreen modal component
- Navigation via arrows, keyboard (Left/Right/Esc), and touch swipe
- Thumbnail strip, position indicator ("Foto 2 de 5"), zoom controls
- Displays AI analysis metadata per photo (type, quality, OCR text)
- Integrated in both Packages tab and Quality tab of JourneyDetail

### P2: Adaptive Sync Scheduler
- Dynamic scheduling based on route age: 5min (same day) → 15min (1d) → 30min (2d) → 60min (3d) → 180min (4d) → 360min (5d+)
- Active window: 06:00-23:00 CDMX (UTC-6)
- Persists `last_sync_at` and `next_sync_at` in journeys collection
- New monitoring endpoint: `GET /api/system/sync-schedule`
- Max 10 journeys per sync cycle, 3 concurrent scrapers (prevents server overload)

### P2: Address Normalization & Heatmap
- `_normalize_address()` parses Mexican addresses during CSV upload → extracts address_cp, address_colonia, address_municipio, address_estado
- New endpoints: `GET /api/analytics/heatmap` (group_by: address_cp, municipio, estado, zone) and `POST /api/analytics/heatmap-export` (Excel)
- New "Heatmap Geográfico" section in Reports page with group-by selector, delivery rate bars, and Excel export

### Bug Fixes & Improvements
- Fixed `_next_day()` function body corruption
- Added `asyncio` import for background task creation
- Added `DialogTitle` for accessibility in carousel modal
- Reduced sync concurrency (5→3) and batch size (250→100) to prevent server overload
- Added developer role access to Reports page

## Previous Sessions
- FastAPI + React scaffolding with seed data
- 2-step Cosmo layout upload
- Image uploads for journey lifecycle
- JWT role-based auth
- Kosmo tracking scraper
- Rule-based evidence scoring
- Dashboard KPIs and date filtering
- Reports with AI (Claude) insights
- Dynamic assignments
- Composite key for packages
- Multiple rounds of bug fixes (iterations 1-12)
