# LastMile OS - Product Requirements Document (PRD)

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, AI-powered evidence scoring, real-time dashboard, advanced reporting, quality criteria configurations, admin AI consumption tracking, and API integrations.

## Tech Stack
- **Backend**: FastAPI, Motor (MongoDB), Python 3.11
- **Frontend**: React 18, TailwindCSS, Shadcn UI, React-Leaflet
- **Database**: MongoDB
- **AI**: Claude Sonnet 4.5 via Emergent LLM Key
- **Maps**: Leaflet + CartoDB Positron tiles

## User Personas
- **Agent** (`agente@me.mx`): Field delivery agent. Views assigned routes and packages.
- **Coordinator** (`yael@me.mx`): Manages operations, reviews quality, configures settings.
- **Developer** (`dev@me.mx`): Full access, configures system, tests API, admin module.
- **Executive** (`karina@me.mx`): High-level dashboards, reports, admin read-only.

## Core Requirements (Status)
- [x] JWT role-based authentication (Agent, Coordinator, Developer, Executive)
- [x] 2-step Cosmo layout upload (history-orders CSV + route-summary XLSX)
- [x] Journey management (Start, Incidents, Close) with image uploads
- [x] Kosmo tracking sync (automatic + manual)
- [x] AI-powered evidence scoring (Claude Sonnet) with structured JSON output
- [x] Real-time WebSocket dashboard with geographic heatmaps
- [x] Advanced reporting with 6 tabs (SLA, Attempts, Quality, etc.)
- [x] Lumi AI Chatbot
- [x] Quality Criteria V2 (5-tab settings)
- [x] Quality Tab V2 in Journey Detail (KPI strip, distribution, error chips, training)
- [x] Supervised training (correct/incorrect + natural language notes + score override)
- [x] Admin IA Module (3 tabs: Token Consumption, Routes Report Cubbo ADM, Cost Config)
- [x] Token usage logging for all AI calls (evaluations, Lumi, reports)
- [x] Routes Report with Excel export in Cubbo ADM format
- [x] Cost configuration (exchange rate, model pricing, budget alerts)
- [x] API Documentation with sandbox and code examples
- [x] Database indexes for performance optimization
- [x] Parallel query execution for dashboard endpoints

## Architecture
```
/app/backend/
  server.py              # Main FastAPI app loader
  dependencies.py        # DB, auth, helpers
  evidence_scoring.py    # AI evidence evaluation (Claude) + token logging
  lumi.py               # Lumi chatbot logic + token logging
  admin.py              # Admin module (token usage, routes report, config)
  token_logger.py       # Token usage estimation and logging helper
  cp_coordinates.py     # Geographic coordinates
  routes/
    auth_routes.py, journey_routes.py, upload_routes.py, dashboard_routes.py,
    analytics_routes.py, quality_criteria_routes.py, quality_tab_routes.py,
    admin_routes.py, user_routes.py

/app/frontend/
  src/pages/
    AdminPage.jsx        # Admin IA module (3 tabs)
    Dashboard.jsx, Reports.jsx, JourneyDetail.jsx, QualityCriteria.jsx,
    ApiDocumentation.jsx, Layout.jsx, Settings.jsx
  src/components/
    admin/TokenUsageTab.jsx, admin/RoutesReportTab.jsx, admin/CostConfigTab.jsx
    QualityTabV2.jsx, HeatmapSection.jsx, LumiChat.jsx, EvidenceCarousel.jsx,
    ImageUploader.jsx, DashboardLayout.jsx
```

## Key API Endpoints
- POST /api/auth/login
- GET /api/dashboard/stats
- GET /api/admin/summary, /api/admin/token-usage, /api/admin/routes-report
- GET /api/admin/routes-report/export, /api/admin/config, PATCH /api/admin/config
- GET /api/journeys/{id}/quality-summary, /api/journeys/{id}/packages-quality
- POST /api/training/samples
- GET /api/reports/schema
- POST /api/lumi/chat
- WS /ws/dashboard

## Credentials
- dev@me.mx / LastMile2026 (Developer - full admin)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)

## Backlog
- [ ] Mobile-optimized views for field agents
- [ ] Export journey details to PDF
- [ ] Historical trend charts for delivery rates
- [ ] Automatic image compression for large uploads
- [ ] Refactor JourneyDetail.jsx into smaller components
