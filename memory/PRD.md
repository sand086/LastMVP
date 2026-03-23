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
- **Database**: MongoDB (indexed: cosmo_route_id + order_reference_id composite, order_reference_id)
- **AI**: Claude Sonnet 4.5 via emergentintegrations (Emergent LLM Key)

## Completed Features

### Phase 1-3: Core, Assignments, Observability
- [x] JWT role-based auth (Agent, Coordinator, Executive, Developer)
- [x] 2-step Cosmo layout upload with deduplication (composite key)
- [x] Route management (Start with checklist, Incidents, Close)
- [x] Image uploads, failed packages search filter
- [x] Dashboard filtering, imputability, route type, Reports + AI, API docs
- [x] System Observability

### Phase 4-5: Kosmo Tracking + Evidence Quality
- [x] Kosmo scraper with proof photo URL extraction and async sync
- [x] Evidence quality scoring (Cubbo standard) with post-sync auto-evaluation

### Phase 6: Deployment Readiness
- [x] Removed hardcoded fallbacks, strengthened JWT, optimized N+1 query

### Phase 7: 12 Operational Adjustments (March 23, 2026)
- [x] CSV auto-filter (empty tracking, OWN_FLEET, repeated headers)
- [x] Driver name column in Dashboard + WhatsApp start summary
- [x] Auto-calculated close metrics (no manual input)
- [x] Pre-populated failed packages from Kosmo
- [x] "VISITAS" renamed from "REINTENTOS"
- [x] "DEVOLUCIONES" renamed from "Para reintento"
- [x] "Resolver todas" bulk incidents button
- [x] "returned" (Devuelto) package status
- [x] 10-min polling, package review indicator, 250 max sync

### Phase 8: Kosmo Evidence Fix (March 23, 2026)
- [x] Fixed scraper to re-scrape delivered/failed packages without proofs
- [x] Stored proof-of-delivery photo URLs (kosmo_proof_urls)
- [x] Async sync endpoint (background task)

### Phase 9: 7 User Findings (March 23, 2026)
- [x] Fix #1: Sync button no longer shows "undefined" — shows correct toast + polls status
- [x] Fix #2: Evidence quality re-evaluated for ALL scraped packages (not just changed)
- [x] Fix #3: DB cleanup button now requires confirmation dialog
- [x] Fix #4: Close form text: "Fallido(s) marcado(s) para devolución"
- [x] Fix #5: Composite unique key (cosmo_route_id + order_reference_id) — same package in multiple routes creates separate records
- [x] Fix #6: "Intentos" column showing delivery attempt count per package
- [x] Fix #7: "Creation Date" from route-summary used as journey date

## Key DB Schema
- `packages`: {id, journey_id, cosmo_route_id, order_reference_id, tracking_url, delivery_attempt, kosmo_proof_count, kosmo_proof_urls, evidence_score, evidence_type, reviewed_by, reviewed_at, ...}
- `journeys`: {id, cosmo_route_id, date, client_id, provider_id, driver_name, status, ...}

## Key API Endpoints
- POST /api/sync/tracking (async background), GET /api/sync/status
- PUT /api/incidents/journey/{id}/resolve-all
- PUT /api/packages/{id}/review
- POST /api/cleanup/routes-packages (with frontend confirmation)

## Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
- Developer: dev@me.mx / LastMile2026

## Future Tasks (P2)
- [ ] Automatic image compression for large uploads
- [ ] Mobile-optimized views for field agents
- [ ] Email/Slack alerts for delivery rate drops
