# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), and dynamic assignment.

## User Personas
- **Agent**: Field delivery operator (upload layouts, manage routes)
- **Coordinator**: Operations manager (full access, user management, assignments, reports)
- **Executive**: Business oversight (dashboard, reports, API docs)

## Tech Stack
- **Frontend**: React + TailwindCSS + Shadcn UI + Lucide Icons
- **Backend**: FastAPI + JWT Auth + Pandas/Openpyxl
- **Database**: MongoDB
- **AI Integration**: Claude Sonnet 4.5 via emergentintegrations (Emergent LLM Key)

## Completed Features

### Core (Phase 1)
- [x] FastAPI Backend & React Frontend scaffolding with Seed Data
- [x] JWT role-based auth (Agent, Coordinator, Executive)
- [x] 2-step Cosmo layout upload (history-orders + route-summary)
- [x] Image uploads in Start, Incidents, Close, and Return Evidence
- [x] Failed packages search filter with magnifying glass
- [x] Global rename: "Jornada" → "Ruta" in all UI

### Phase 2 (March 21, 2026)
- [x] Extended start checklist (9 items: 5 original + 4 CEDIS items)
- [x] Backup driver fields (name, request/arrival time - conditionally visible)
- [x] Conditional return evidence in close route (photos when failed/retry > 0)
- [x] API Documentation page at /api-docs
- [x] Dynamic user assignment (client/provider) in Settings page
- [x] Database cleanup endpoint/script

### Phase 3 (March 21, 2026)
- [x] Dashboard filtering by user assignments (assigned_clients/assigned_providers)
- [x] Imputability field in incidents (ME/Mensajero | Cliente | Por definir) with colored badges
- [x] Route type (CDMX/Zona Metro | Foránea) with conditional city/max_packages fields
- [x] Layout re-upload updates existing packages instead of skipping (X new, Y updated)
- [x] Custom Report page with lego-style section selector + period presets
- [x] Claude AI insights generation for reports
- [x] Excel report download (routes, incidents, provider summary sheets)
- [x] Imputability summary in close route ("Imputables a ME: X | al cliente: Y")

## Upcoming Tasks (P1)
- [ ] Add clickable tracking_url view in package details
- [ ] Add search functionality in main packages table of Journey Detail page

## Future Tasks (P2)
- [ ] Automatic compression for large image uploads
- [ ] Mobile-optimized views for field agents

## Key API Endpoints
- POST /api/auth/login
- POST /api/upload/step1-orders, /api/upload/step2-routes
- POST /api/journeys/from-cosmo (accepts route_type, city, max_packages)
- POST /api/journeys/{id}/start (accepts arrival_time_cedis, backup fields)
- POST /api/journeys/{id}/close
- POST /api/incidents (accepts imputability field)
- POST /api/reports/generate (AI insights)
- POST /api/reports/generate-excel (Excel download)
- GET /api/reports/journeys, /api/reports/packages, /api/reports/schema

## DB Schema
- users: {email, password_hash, role, assigned_clients, assigned_providers}
- journeys: {client_id, provider_id, date, status, route_type, city, max_packages, packages_total, start_data, close_data}
- packages: {tracking_number, order_reference_id, recipient_name, address, status, cosmo_status, tracking_url, journey_id}
- incidents: {journey_id, type, severity, imputability, images}
