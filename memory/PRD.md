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
- **Database**: MongoDB (collections: users, journeys, packages, incidents, clients, providers, audit_logs, system_errors, request_metrics, integrity_results, system_config)
- **AI**: Claude Sonnet 4.5 via emergentintegrations (Emergent LLM Key)

## Completed Features

### Phase 1 - Core
- [x] JWT role-based auth (Agent, Coordinator, Executive, Developer)
- [x] 2-step Cosmo layout upload (history-orders + route-summary)
- [x] Route management (Start with 9-item checklist + backup fields, Incidents, Close with conditional return evidence)
- [x] Image uploads for all sections
- [x] Failed packages search filter
- [x] Global rename "Jornada" → "Ruta"

### Phase 2 - Assignments & Reports
- [x] Dashboard filtering by user assignments (assigned_clients/assigned_providers)
- [x] Imputability in incidents (ME/Mensajero | Cliente | Por definir) with colored badges
- [x] Route type (CDMX/Foránea) with conditional city/max_packages
- [x] Layout re-upload updates existing packages (X new, Y updated)
- [x] Custom Reports page with lego-style sections + Claude AI insights + Excel download
- [x] Dynamic user assignment (client/provider) in Settings
- [x] API Documentation page at /api-docs

### Phase 3 - System Observability (March 21, 2026)
- [x] Health Dashboard, Performance Metrics, Log Viewer, Error Tracker, Data Integrity Checker
- [x] Environment Config viewer
- [x] Non-blocking audit middleware
- [x] Developer role (dev@me.mx)

### Phase 4 - Kosmo Tracking Sync (March 23, 2026)
- [x] Scraper: Extracts order data from public Kosmo tracking pages (Next.js SSR __NEXT_DATA__)
- [x] Package fields: kosmo_order_id, kosmo_status_raw, kosmo_updated_at, kosmo_finished_at, kosmo_driver_note, kosmo_proof_count, kosmo_scraped_at
- [x] Status mapping: delivered→delivered, cancelled→failed, picked_up/in_transit/assigned→pending
- [x] Sync endpoint: POST /api/sync/tracking (max 50 pkgs, Semaphore(5))
- [x] Status endpoint: GET /api/sync/status
- [x] Auto scheduler: Background task every 30 min
- [x] Dashboard sync bar with manual sync button

### Phase 5 - Evidence Quality Scoring (March 23, 2026)
- [x] Scoring function based on Cubbo 3-photo standard
- [x] Evidence types: exitosa, terceros (with driver note keywords), fallida
- [x] Auto-evaluation after sync and route close
- [x] Dashboard 5th KPI: "Calidad de soporte" with color coding
- [x] Package table: Soporte column (Completo/Parcial/Incompleto badges) + Evidencias column
- [x] New "Calidad" tab: Score summary, distribution bar, scored packages table, filter, re-evaluate
- [x] Quality Reports section: by provider, by type, worst packages, Cubbo Excel export
- [x] WhatsApp close summary includes quality block with attention items
- [x] Odometer photo marked optional in Start/Close forms with help text
- [x] Checklist reordered to chronological operation order
- [x] Items 7-8 (odometer photo, CEDIS screenshot) marked as "(opcional)"

## Architecture
- `/app/backend/server.py`: Core API (~2700 lines)
- `/app/backend/kosmo_sync.py`: Kosmo scraper, sync logic, scheduler, router
- `/app/backend/evidence_scoring.py`: Evidence quality scoring functions
- `/app/backend/middleware.py`: Audit/error middleware
- `/app/backend/system_routes.py`: System observability endpoints
- `/app/frontend/src/pages/`: Dashboard, JourneyDetail, Layout, Reports, Settings, System*, etc.

## Key API Endpoints
- POST /api/auth/login
- POST /api/upload/step1-orders, step2-routes
- POST /api/journeys/{id}/start, /close
- POST /api/sync/tracking, GET /api/sync/status
- GET /api/reports/quality, POST /api/reports/quality-export
- POST /api/reports/evaluate-journey/{id}
- POST /api/reports/generate, /generate-excel
- GET /api/system/health, /logs, /errors, /integrity

## Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
- Developer: dev@me.mx / LastMile2026

## Future Tasks (P2)
- [ ] Automatic image compression for large uploads
- [ ] Mobile-optimized views for field agents
- [ ] Email/Slack alerts for delivery rate drops
