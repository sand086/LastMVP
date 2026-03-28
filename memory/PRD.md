# LastMile OS - Product Requirements Document

## Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajeria y Estrategias). Full-stack platform with authentication, dashboard, CSV/XLSX uploads, journey tracking, AI-powered quality evaluation, geographic analytics, comprehensive reporting, and AI chatbot assistant.

## Tech Stack
- **Backend:** FastAPI, MongoDB (motor), JWT Auth, APScheduler, Claude Sonnet (AI scoring + reports + chatbot), slowapi, websockets
- **Frontend:** React, TailwindCSS, Shadcn UI, Lucide Icons, embla-carousel-react, Leaflet/react-leaflet
- **Database:** MongoDB (test_database)

## User Roles
- Agent (agente@me.mx) / Coordinator (yael@me.mx) / Executive (karina@me.mx) / Developer (dev@me.mx)
- Password (all): LastMile2026

## Core Architecture
- `/app/backend/server.py` - Slim main app loader
- `/app/backend/routes/` - Modular route files (8 modules)
- `/app/backend/lumi.py` - Lumi AI chatbot endpoint + context builder
- `/app/backend/kosmo_sync.py` - External tracking data scraper
- `/app/backend/ws_manager.py` - WebSocket manager
- `/app/backend/evidence_scoring.py` - AI quality scoring
- `/app/backend/cp_coordinates.py` - CDMX postal code geo dictionary
- `/app/frontend/src/pages/` - Page components
- `/app/frontend/src/components/` - LumiChat, HeatmapSection, ImageUploader, etc.
- `/app/frontend/src/lib/` - API client, hooks, utilities

## Completed Features
- [x] JWT role-based authentication
- [x] 2-step Cosmo layout upload
- [x] Journey management (CRUD, start, close)
- [x] Incident tracking with image uploads
- [x] Dashboard v2 (heatmap, KPIs, WebSocket, sortable tables)
- [x] Kosmo tracking sync + batch re-scrape
- [x] AI evidence quality scoring
- [x] **Reports v2 Redesign** - Period selector, 6 section checkboxes, KPI strip, 6 tabs
- [x] **Attempts Tab** (NEW) - 1st/2nd/3rd attempt distribution + retry causes
- [x] **SLA Tab** (NEW) - SLA vs Target with editable brackets, by provider/driver
- [x] **AI Report Generation** - Claude Sonnet narrative with operational insights
- [x] **Lumi AI Chatbot** - Global floating assistant with operational context

## Key API Endpoints (NEW)
- `GET /api/reports/attempts` - Delivery attempts distribution
- `GET /api/reports/sla` - SLA vs Target data
- `PATCH /api/config/sla-targets` - Persist SLA brackets
- `POST /api/reports/generate-ai` - AI narrative report
- `POST /api/chat/lumi` - Lumi chatbot endpoint
- `GET /api/reports/heatmap` - Geo-enriched CP data

## Design System
- Typography: DM Sans (300-600), DM Mono (400-500)
- Colors: --bg:#F5F4F1, --surface:#FFF, --blue:#2563EB, --green:#16A34A, --amber:#D97706, --coral:#DC2626
