# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias).

## Core Features
- JWT Role-based Authentication (Agent, Coordinator, Executive, Developer)
- Dashboard with real-time KPIs, polling, and date-range filtering
- 2-step Cosmo data layout upload (CSV orders + XLSX routes)
- Journey lifecycle management (Start/Incidents/Close)
- Image upload for evidence (Start, Incidents, Close)
- Kosmo public tracking scraper with evidence collection
- Rule-based and AI-powered evidence quality scoring
- Reports module with AI-generated insights
- Dynamic user/client/provider assignments
- Full CRUD for users, clients, providers

## Architecture
- **Backend**: FastAPI, MongoDB (motor), Pandas, emergentintegrations
- **Frontend**: React, TailwindCSS, Shadcn UI, Lucide Icons
- **AI**: Claude Sonnet 4.5 (via Emergent LLM Key) for reports and evidence scoring
- **Database**: MongoDB with collections: users, journeys, packages, incidents, clients, providers, system_config

## Key Technical Details
- Composite key: `cosmo_route_id` + `order_reference_id` for package uniqueness
- Address normalization during CSV upload (CP, colonia, municipio, estado)
- Adaptive sync scheduler (frequency based on route age, active window 06:00-23:00 CDMX)
- Server-side pagination for journeys endpoint

## Credentials
- dev@me.mx / LastMile2026 (Developer)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)
- karina@me.mx / LastMile2026 (Executive)

## API Endpoints
### Auth
- POST /api/auth/login
### Journeys
- GET /api/journeys (paginated: page, page_size)
- GET /api/journeys/{id}
- POST /api/journeys/from-cosmo (upload)
- POST /api/journeys/{id}/start
- POST /api/journeys/{id}/close
### Evidence
- POST /api/journeys/{id}/packages/{guide}/evaluate-evidence (AI single)
- POST /api/journeys/{id}/evaluate-evidence-all (AI batch, async)
- POST /api/reports/evaluate-journey/{id} (rules-based)
### Analytics
- GET /api/analytics/heatmap (group_by: address_cp, address_municipio, address_estado, zone)
- POST /api/analytics/heatmap-export
### System
- GET /api/system/sync-schedule
- POST /api/sync/tracking
- GET /api/sync/status
### Dashboard
- GET /api/dashboard/stats
- GET /api/dashboard/incidents-breakdown
- GET /api/dashboard/provider-comparison
