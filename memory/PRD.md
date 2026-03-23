# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, custom reports with AI, system observability, automated Kosmo tracking sync, and evidence quality scoring based on Cubbo standards.

## User Personas
- **Agent**: Field delivery operator (upload layouts, manage routes)
- **Coordinator**: Operations manager (full access, user management, assignments, reports, system)
- **Executive**: Business oversight (dashboard, reports, API docs)
- **Developer**: IT/Dev team (system observability, health monitoring, logs, error tracking)

## Tech Stack
- **Frontend**: React + TailwindCSS + Shadcn UI + Lucide Icons
- **Backend**: FastAPI + JWT Auth + Pandas/Openpyxl + httpx (Kosmo scraper)
- **Database**: MongoDB
- **AI**: Claude Sonnet 4.5 via emergentintegrations (Emergent LLM Key)

## Completed Features

### Phase 1-3: Core, Assignments, Observability
- [x] JWT role-based auth (Agent, Coordinator, Executive, Developer)
- [x] 2-step Cosmo layout upload (history-orders + route-summary) with deduplication
- [x] Route management (Start with checklist, Incidents, Close with conditional evidence)
- [x] Image uploads, failed packages search filter
- [x] Dashboard filtering, imputability, route type, custom Reports + AI, API docs
- [x] System Observability (Health, Metrics, Logs, Errors, Integrity)

### Phase 4-5: Kosmo Tracking Sync + Evidence Quality (March 23, 2026)
- [x] Kosmo scraper with proof photo URL extraction
- [x] Evidence quality scoring (Cubbo standard)
- [x] Quality tab + Dashboard KPI + reports

### Phase 6: Deployment Readiness (March 23, 2026)
- [x] Removed DB_NAME fallback, strengthened JWT secret, optimized N+1 query

### Phase 7: Operational Adjustments (March 23, 2026)
**P0 - Critical:**
- [x] CSV auto-filter: Empty tracking_number, OWN_FLEET, repeated header rows silently ignored with count
- [x] Driver name column in Dashboard journeys table
- [x] Auto-calculated close metrics (Entregados/Fallidos/Devoluciones) — no manual input
- [x] Pre-populated failed packages in close form from Kosmo cancelled/failed status

**P1 - High Priority:**
- [x] Renamed "REINTENTOS" → "VISITAS" (delivered+failed+returned count)
- [x] Renamed "Para reintento" → "DEVOLUCIONES" in close summary
- [x] Driver name in WhatsApp start route summary
- [x] "Resolver todas" bulk button for open incidents with confirmation dialog
- [x] "returned" (Devuelto) status for packages closed as returns, dark gray badge

**P2 - Medium Priority:**
- [x] Polling interval reduced to 10 minutes
- [x] Package review indicator ("Revisado" column) with click-to-review + MongoDB persistence
- [x] Sync max increased to 250 packages per call

### Phase 8: Kosmo Evidence Fix (March 23, 2026)
- [x] Fixed scraper query to include delivered/failed packages that were never scraped or have 0 proofs
- [x] Stored proof-of-delivery photo URLs (kosmo_proof_urls) from Kosmo
- [x] Made sync endpoint async (background task) to avoid HTTP timeout
- [x] Frontend shows clickable camera icons linking to individual proof photos
- [x] Re-evaluated all 567 packages with updated evidence data (490 now have proofs)

## Key API Endpoints
- POST /api/auth/login
- POST /api/upload/step1-orders (history-orders), step2-routes (route-summary)
- POST /api/journeys/{id}/start, /close
- POST /api/sync/tracking (async background task), GET /api/sync/status
- PUT /api/incidents/journey/{id}/resolve-all
- PUT /api/packages/{id}/review
- POST /api/reports/evaluate-journey/{id}
- GET /api/reports/quality, POST /api/reports/quality-export
- POST /api/cleanup/routes-packages

## Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
- Developer: dev@me.mx / LastMile2026

## Future Tasks (P2)
- [ ] Automatic image compression for large uploads
- [ ] Mobile-optimized views for field agents
- [ ] Email/Slack alerts for delivery rate drops
