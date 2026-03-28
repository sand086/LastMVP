# LastMile OS - Product Requirements Document (PRD)

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, AI-powered evidence scoring, real-time dashboard, advanced reporting, quality criteria configurations, and API integrations.

## Tech Stack
- **Backend**: FastAPI, Motor (MongoDB), Python 3.11
- **Frontend**: React 18, TailwindCSS, Shadcn UI, React-Leaflet
- **Database**: MongoDB
- **AI**: Claude Sonnet 4.5 via Emergent LLM Key
- **Maps**: Leaflet + CartoDB Positron tiles

## User Personas
- **Agent** (`agente@me.mx`): Field delivery agent. Views assigned routes and packages.
- **Coordinator** (`yael@me.mx`): Manages operations, reviews quality, configures settings.
- **Developer** (`dev@me.mx`): Full access, configures system, tests API.
- **Executive** (`karina@me.mx`): High-level dashboards, reports.

## Core Requirements (Status)
- [x] JWT role-based authentication (Agent, Coordinator, Developer, Executive)
- [x] 2-step Cosmo layout upload (history-orders CSV + route-summary XLSX)
- [x] Journey management (Start, Incidents, Close) with image uploads
- [x] Kosmo tracking sync (automatic + manual)
- [x] AI-powered evidence scoring (Claude Sonnet)
- [x] Real-time WebSocket dashboard with geographic heatmaps
- [x] Advanced reporting with 6 tabs (SLA, Attempts, Quality, etc.)
- [x] Lumi AI Chatbot
- [x] Quality Criteria V2 (5-tab settings: Evidencias, KPIs, SLA, Config IA, Tipos Error)
- [x] Quality Tab V2 in Journey Detail (KPI strip, distribution, error chips, training)
- [x] API Documentation with sandbox and code examples
- [x] Database indexes for performance optimization
- [x] Parallel query execution for dashboard endpoints

## Architecture
```
/app/backend/
  server.py              # Main FastAPI app loader
  dependencies.py        # DB, auth, helpers
  evidence_scoring.py    # AI evidence evaluation (Claude)
  lumi.py               # Lumi chatbot logic
  cp_coordinates.py     # Geographic coordinates
  routes/
    auth_routes.py       # Login, user management
    journey_routes.py    # Journey CRUD, evidence eval
    upload_routes.py     # CSV/XLSX file processing
    dashboard_routes.py  # Stats, search, comparisons
    analytics_routes.py  # Reports, schema, heatmap
    quality_criteria_routes.py  # Settings config
    quality_tab_routes.py      # Quality summary, training
    admin_routes.py      # Admin operations
    user_routes.py       # User management

/app/frontend/
  src/pages/
    Dashboard.jsx        # Real-time dashboard with heatmap
    Reports.jsx          # 6-tab reporting
    JourneyDetail.jsx    # Journey management
    QualityCriteria.jsx  # 5-tab quality settings
    ApiDocumentation.jsx # API docs + sandbox
    Layout.jsx           # File upload
    Settings.jsx         # System settings
  src/components/
    QualityTabV2.jsx     # Quality tab in journey detail
    HeatmapSection.jsx   # Leaflet map wrapper
    LumiChat.jsx         # AI chatbot widget
    EvidenceCarousel.jsx # Photo viewer
    ImageUploader.jsx    # Image upload widget
    DashboardLayout.jsx  # Sidebar navigation
```

## Key API Endpoints
- POST /api/auth/login
- GET /api/dashboard/stats
- GET /api/journeys/{id}/quality-summary (v2)
- GET /api/journeys/{id}/packages-quality (v2)
- POST /api/training/samples (v2)
- PATCH /api/journeys/{id}/packages/{guide}/review (v2)
- GET /api/reports/schema (includes all endpoints)
- POST /api/lumi/chat
- WS /ws/dashboard

## Credentials
- dev@me.mx / LastMile2026 (Developer)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)

## Backlog
- [ ] Mobile-optimized views for field agents
- [ ] Export journey details to PDF
- [ ] Historical trend charts for delivery rates
- [ ] Automatic image compression for large uploads
- [ ] Refactor JourneyDetail.jsx into smaller components
