# LastMile OS - Product Requirements Document

## Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajeria y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, and AI-powered quality evaluation.

## Tech Stack
- **Backend:** FastAPI, MongoDB (motor), JWT Auth, APScheduler, Claude Sonnet (AI scoring), slowapi, websockets
- **Frontend:** React, TailwindCSS, Shadcn UI, Lucide Icons, embla-carousel-react
- **Database:** MongoDB (test_database)

## User Roles
- Agent (agente@me.mx)
- Coordinator (yael@me.mx)
- Executive (karina@me.mx)
- Developer (dev@me.mx)
- Password (all): LastMile2026

## Core Architecture
- `/app/backend/server.py` - Slim main app loader (145 lines)
- `/app/backend/routes/` - Modular route files (8 modules)
- `/app/backend/kosmo_sync.py` - External tracking data scraper
- `/app/backend/ws_manager.py` - WebSocket connection manager
- `/app/backend/evidence_scoring.py` - AI + rules-based quality scoring
- `/app/frontend/src/pages/` - Page components
- `/app/frontend/src/lib/` - API client, hooks, utilities

## Completed Features
- [x] JWT role-based authentication (Agent, Coordinator, Executive, Developer)
- [x] 2-step Cosmo layout upload (history-orders + route-summary)
- [x] Journey management (create, start, close with checklists)
- [x] Incident tracking with image uploads
- [x] Failed packages search with magnifying glass
- [x] Image upload for Start/Incidents/Close journey
- [x] Dynamic client/provider assignment in Settings
- [x] Dashboard with real-time stats and WebSocket support
- [x] Kosmo tracking data sync (adaptive scheduler)
- [x] AI evidence quality scoring (Claude Sonnet)
- [x] Evidence carousel with photo analysis
- [x] Sortable tables across all pages
- [x] Quality criteria configuration page
- [x] Bulk package status update
- [x] Individual package re-scrape
- [x] **Batch re-scrape** (Re-sincronizar todos) - NEW
- [x] Backend refactoring from monolithic to modular routes
- [x] Geographic heatmap
- [x] Server-side pagination
- [x] API documentation page (Power BI sandbox)

## Key API Endpoints
- `POST /api/auth/login`
- `GET /api/journeys` (paginated)
- `GET /api/journeys/{journey_id}`
- `PUT /api/journeys/{journey_id}/start`
- `PUT /api/journeys/{journey_id}/close`
- `POST /api/journeys/{journey_id}/batch-rescrape` (NEW)
- `POST /api/packages/{package_id}/rescrape`
- `POST /api/upload/step1-orders`
- `POST /api/upload/step2-routes`
- `GET /api/quality-criteria`
- `PUT /api/quality-criteria`
- `GET /api/dashboard/stats`
- `WS /ws/dashboard`

## DB Collections
- users, journeys, packages, incidents, clients, providers
- messenger_mappings, quality_criteria, system_config, audit_log
