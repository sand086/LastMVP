# LastMile OS - Changelog

## 2026-03-28 - Reports v2 + Lumi AI Chatbot (Complete)
### Reports Module Redesign
- **NEW:** Period selector card with 6 presets (7d, 15d, mes actual, mes anterior, semana anterior, custom)
- **NEW:** 6 report section checkboxes: Proveedores, Drivers, Incidencias, Intentos (nuevo), Calidad, SLA (nuevo)
- **NEW:** KPI strip: Tasa de entrega, Tasa de visita, Calidad evidencias, SLA vs target
- **NEW:** 6 tabs with sortable tables: Proveedores, Drivers, Incidencias, Intentos, Evidencias, SLA
- **NEW:** Attempts tab - 1st/2nd/3rd attempt distribution bars + retry causes (driver management, client absent, wrong address, zone no access)
- **NEW:** SLA tab - Consolidated SLA vs target with editable brackets, by-provider and by-driver breakdowns
- **NEW:** AI Report Generation button (Claude Sonnet) - Generates executive narrative
- **NEW:** Excel export button
- **NEW:** Backend endpoints: `GET /api/reports/attempts`, `GET /api/reports/sla`, `PATCH /api/config/sla-targets`, `POST /api/reports/generate-ai`

### Lumi AI Chatbot
- **NEW:** `LumiChat.jsx` - Global floating chatbot mounted in App.js
- **NEW:** `backend/lumi.py` - `POST /api/chat/lumi` with full operational context
- **NEW:** Truck SVG avatar, quick action buttons, message history
- **NEW:** Context-aware responses using Claude Sonnet with period/client/provider data
- **TESTED:** 100% backend (13/13), 100% frontend (iteration_17)

## 2026-03-28 - Dashboard v2 Redesign
- Filters above KPIs, Leaflet heatmap, Provider Visita%, CartoDB tiles
- `GET /api/reports/heatmap`, `cp_coordinates.py` with 120+ CDMX CPs
- CORS fix, N+1 query optimizations
- TESTED: 100% (iteration_16)

## 2026-03-25 - Batch Re-scrape Feature
- `POST /api/journeys/{journey_id}/batch-rescrape`, button visibility fix
- TESTED: 19/19 backend (iteration_15)

## 2026-03-24 - Backend Refactoring + Features
- Monolithic server.py → 8 modular routes
- Sortable tables, Quality Criteria UI, WebSocket dashboard
- Kosmo scraper bug fix, individual re-scrape

## 2026-03-21-23 - MVP Foundation + Core Features
- Auth, uploads, journeys, incidents, Kosmo sync, AI scoring
