# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, custom reports with AI, and system observability tools.

## User Personas
- **Agent**: Field delivery operator (upload layouts, manage routes)
- **Coordinator**: Operations manager (full access, user management, assignments, reports, system)
- **Executive**: Business oversight (dashboard, reports, API docs)
- **Developer**: IT/Dev team (system observability, health monitoring, logs, error tracking)

## Tech Stack
- **Frontend**: React + TailwindCSS + Shadcn UI + Lucide Icons
- **Backend**: FastAPI + JWT Auth + Pandas/Openpyxl
- **Database**: MongoDB (collections: users, journeys, packages, incidents, clients, providers, audit_logs, system_errors, request_metrics, integrity_results)
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
- [x] **Health Dashboard** (/system/health): API status, MongoDB status/latency, avg latency, 4xx/5xx error counts, upload space, uptime, error timeline. Polling every 30s.
- [x] **Performance Metrics** (within health): Requests per hour chart, slowest endpoints top 10, most active users, layout file stats
- [x] **Log Viewer** (/system/logs): Audit log table with filters (date, user, action, errors-only), pagination, CSV export. Actions logged: login, route CRUD, incidents, layout uploads, user management
- [x] **Error Tracker** (/system/errors): Grouped errors by type (API/parsing/validation), occurrence count, first/last seen, mark-as-reviewed. Badge in sidebar with unreviewed count.
- [x] **Data Integrity Checker** (/system/integrity): Validates routes without start data, closed routes without close data, inconsistent package counts, open incidents on closed routes, inactive users. Export to CSV.
- [x] **Environment Config** (Settings > System tab): Backend/Python version, MongoDB host, DB size, JWT expiry, CORS, last deploy timestamp, uptime
- [x] Non-blocking audit middleware (async, doesn't affect request latency)
- [x] Developer role with dedicated user (dev@me.mx)

## Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
- Developer: dev@me.mx / LastMile2026

## Upcoming Tasks (P1)
- [ ] Add clickable tracking_url view in package details
- [ ] Add search in main packages table of Journey Detail

## Future Tasks (P2)
- [ ] Automatic image compression for large uploads
- [ ] Mobile-optimized views for field agents
