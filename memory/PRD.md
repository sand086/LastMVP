# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), and dynamic assignment.

## User Personas
- **Agent**: Field delivery operator (upload layouts, manage routes)
- **Coordinator**: Operations manager (full access, user management, assignments)
- **Executive**: Business oversight (dashboard, reports, API docs)

## Tech Stack
- **Frontend**: React + TailwindCSS + Shadcn UI + Lucide Icons
- **Backend**: FastAPI + JWT Auth + Pandas/Openpyxl
- **Database**: MongoDB

## Core Requirements

### Authentication
- JWT role-based auth (Agent, Coordinator, Executive)
- Credentials: agente@me.mx, yael@me.mx, karina@me.mx / LastMile2026

### Dashboard
- KPIs: Active routes, packages delivered, open incidents, closed routes
- Date range + client/provider/status filters
- Route table with quick access
- Provider comparison metrics
- Export to XLSX

### Layout Upload (2-Step)
- Step 1: Upload history-orders.csv from Cosmo
- Step 2: Upload route-summary.xlsx from Cosmo
- Auto-creates routes and packages from uploaded data

### Route Management (formerly "Jornada" - renamed to "Ruta" in UI)
- **Start Route**: 9-item checklist, vehicle info, backup driver fields
- **Incidents**: Register incidents with severity, images
- **Close Route**: Metrics, 4-item checklist + conditional return evidence
- Image uploads for all sections (start, close, incidents, return_evidence)
- WhatsApp summary generation

### Settings (Coordinator only)
- User CRUD management
- Client/Provider management
- Dynamic user-to-client/provider assignment with modal

### API Documentation
- Power BI integration sandbox at /api-docs
- Available endpoints documentation
- Code examples

## Completed Features (as of March 21, 2026)
- [x] FastAPI Backend & React Frontend scaffolding with Seed Data
- [x] 2-step Cosmo layout upload (history-orders + route-summary)
- [x] Image uploads in Start, Incidents, Close, and Return Evidence
- [x] Failed packages search filter with magnifying glass
- [x] JWT role-based auth (Agent, Coordinator, Executive)
- [x] Global rename: "Jornada" → "Ruta" in all UI (MongoDB keeps "journeys" internally)
- [x] Extended start checklist (9 items including CEDIS arrival, pass, Cosmo confirmation, screenshot)
- [x] Backup driver fields (name, request time, arrival time - conditionally visible)
- [x] Conditional return evidence in close route (photo upload for package returns)
- [x] API Documentation page connected to routing and sidebar
- [x] Dynamic user assignment (client/provider) in Settings page
- [x] Database cleanup for fresh testing

## Upcoming Tasks (P1)
- [ ] Add clickable tracking_url view in package details
- [ ] Add search functionality in main packages table of Journey Detail page

## Future Tasks (P2)
- [ ] Automatic compression for large image uploads
- [ ] Mobile-optimized views for field agents

## Key API Endpoints
- POST /api/auth/login
- POST /api/upload/step1-orders
- POST /api/upload/step2-routes
- POST /api/journeys/{journey_id}/start (accepts arrival_time_cedis, backup_driver_name, backup_request_time, backup_arrival_time)
- POST /api/journeys/{journey_id}/close
- GET /api/reports/journeys, /api/reports/packages, /api/reports/schema

## DB Schema
- users: {email, password_hash, role, assigned_clients, assigned_providers}
- journeys: {client_id, provider_id, date, status, packages_total, start_data, close_data, images}
- packages: {tracking_number, recipient_name, address, status, journey_id}
- incidents: {journey_id, type, severity, images}
