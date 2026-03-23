# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, custom reports with AI, system observability tools, and automated Kosmo tracking sync.

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
- [x] **Scraper**: Extracts order data from public Kosmo tracking pages (Next.js SSR __NEXT_DATA__)
- [x] **New Package Fields**: kosmo_order_id, kosmo_status_raw, kosmo_updated_at, kosmo_finished_at, kosmo_driver_note, kosmo_proof_count, kosmo_scraped_at
- [x] **Status Mapping**: delivered→delivered, cancelled→failed, picked_up/in_transit/assigned→pending
- [x] **Sync Endpoint**: POST /api/sync/tracking (max 50 pkgs, Semaphore(5) concurrency)
- [x] **Status Endpoint**: GET /api/sync/status (last_sync, total_checked, updated, errors)
- [x] **Auto Scheduler**: Background task runs every 30 min
- [x] **Dashboard Sync Bar**: Shows last sync time, stats, errors (amber), manual sync button
- [x] **Package Table**: Clickable tracking links, delivery time, camera icon + proof count, driver note tooltip, sync clock
- [x] **Evidence Panel**: Driver notes, delivery time, photo count, external Kosmo link

## Architecture
- `/app/backend/server.py`: Core API (~2490 lines)
- `/app/backend/kosmo_sync.py`: Kosmo scraper, sync logic, scheduler, router
- `/app/backend/middleware.py`: Audit/error middleware
- `/app/backend/system_routes.py`: System observability endpoints
- `/app/frontend/src/pages/`: Dashboard, JourneyDetail, Layout, Reports, Settings, System*, etc.

## Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
- Developer: dev@me.mx / LastMile2026

## Future Tasks (P2)
- [ ] Automatic image compression for large uploads
- [ ] Mobile-optimized views for field agents
- [ ] Email/Slack alerts for delivery rate drops
