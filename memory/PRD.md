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
- **Coordinator** (`yael@me.mx`): Manages operations, reviews quality, configures settings, admin access.
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
- [x] Token usage logging for all AI calls
- [x] Routes Report with Excel export in Cubbo ADM format
- [x] Cost configuration (exchange rate, model pricing, budget alerts)
- [x] API Documentation with sandbox and code examples
- [x] Database indexes + parallel query optimization
- [x] QA Bug Fixes (9/9 bugs resolved — iteration 20)

## Architecture
```
/app/backend/
  server.py, dependencies.py, models.py, evidence_scoring.py, lumi.py,
  admin.py, token_logger.py, cp_coordinates.py, middleware.py
  routes/ (auth, journey, upload, dashboard, analytics, quality_criteria,
           quality_tab, admin, user)

/app/frontend/src/
  pages/ (AdminPage, Dashboard, Reports, JourneyDetail, QualityCriteria,
          ApiDocumentation, Layout, Settings, Login)
  components/ (admin/{TokenUsageTab,RoutesReportTab,CostConfigTab},
               QualityTabV2, HeatmapSection, LumiChat, EvidenceCarousel,
               ImageUploader, DashboardLayout)
```

## Key API Endpoints
- POST /api/auth/login (20/min rate limit)
- GET /api/dashboard/stats
- GET /api/admin/summary, /token-usage, /routes-report, /routes-report/export, /config
- PATCH /api/admin/config
- GET /api/journeys/{id}/quality-summary, /packages-quality
- POST /api/training/samples (coordinator, developer, agent)
- GET /api/reports/journeys (includes all journey statuses)
- GET /api-docs → 301 redirect to /documentation

## Credentials
- dev@me.mx / LastMile2026 (Developer)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)

## Recent Fixes (2026-03-28)
- [x] P0 Bug: Restored "Inicio", "Incidencias", "Fin" workflow visibility in JourneyDetail
  - Added 'developer' role to canEdit() in AuthContext.jsx
  - Fixed default tab logic: scheduled journeys now default to 'inicio' (was 'calidad')
  - Added 'developer' role to Layout page access in App.js
- [x] Verified: Dynamic Assignments in Settings already functional
- [x] Verified: API Documentation page already routed and linked in sidebar

## Backlog
- [ ] Mobile-optimized views for field agents
- [ ] Export journey details to PDF
- [ ] Historical trend charts for delivery rates
- [ ] Automatic image compression for large uploads
- [ ] Refactor JourneyDetail.jsx into smaller components
- [ ] Webhook integrations for external systems
