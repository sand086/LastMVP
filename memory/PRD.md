# LastMile OS - Product Requirements Document (PRD)

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajeria y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, AI-powered evidence scoring with discrepancy detection, real-time dashboard, advanced reporting, quality criteria configurations, admin AI consumption tracking, webhook integrations, and API documentation.

## Tech Stack
- **Backend**: FastAPI, Motor (MongoDB), Python 3.11
- **Frontend**: React 18, TailwindCSS, Shadcn UI, React-Leaflet, DOMPurify
- **Database**: MongoDB
- **AI**: Claude Sonnet 4.5 via Emergent LLM Key
- **Maps**: Leaflet + CartoDB Positron tiles
- **Webhooks**: httpx async dispatch with HMAC-SHA256 signatures

## User Personas
- **Agent** (`agente@me.mx`): Field delivery agent. Views assigned routes and packages.
- **Coordinator** (`yael@me.mx`): Manages operations, reviews quality, configures settings, admin access. Can edit SLA and Pulse config.
- **Developer** (`dev@me.mx`): Full access, configures system, tests API, admin module, can upload layouts.
- **Executive** (`karina@me.mx`): High-level dashboards, reports, admin read-only.
- **Proveedor** (`proveedor@me.mx`): Read-only restricted view.

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
- [x] Quality Tab V2 in Journey Detail
- [x] Supervised training (correct/incorrect + natural language notes + score override)
- [x] Admin IA Module (Token Consumption, Routes Report, Cost Config)
- [x] API Documentation with sandbox, Webhooks reference, and code examples
- [x] Database indexes + parallel query optimization
- [x] Webhook Integrations (Plug & Play) — CRUD, test, HMAC, delivery log
- [x] Backend refactoring — all routes in /routes/ directory
- [x] Code quality: XSS sanitization (DOMPurify), Python complexity reduction, table-driven middleware
- [x] Resilient data loading: Promise.allSettled in all page fetchers
- [x] Test security: credentials via env vars (conftest.py)
- [x] Dynamic SLA Configuration per Provider
- [x] Pulse: Real-time feasibility monitor
- [x] Discrepancy Detection with Confidence Engine
- [x] AI Evaluation UX: Severity badges (critical/warning) in GuiasTab
- [x] AI Evaluation UX: Quick Review Modal (decoupled from table row)
- [x] AI Evaluation UX: Background execution with polling progress banner

## Architecture
```
/app/backend/
  server.py (206 lines - app setup only)
  dependencies.py (refactored: extracted address helpers)
  middleware.py (refactored: table-driven patterns)
  evidence_scoring.py (refactored: 5 extracted helpers + status tracking)
  kosmo_sync.py, token_logger.py, cp_coordinates.py, ws_manager.py

  routes/ (14 modules via __init__.py)
    auth_routes.py, user_routes.py, journey_routes.py
    upload_routes.py, dashboard_routes.py, analytics_routes.py
    admin_routes.py, admin_module_routes.py (refactored: report helpers)
    quality_criteria_routes.py, quality_tab_routes.py
    webhook_routes.py, system_routes.py (top-level imports)
    lumi_routes.py, kosmo_routes.py

  tests/
    conftest.py (shared fixtures, env-based credentials)
    22+ test files

/app/frontend/src/
  pages/ (AdminPage, Dashboard, Reports, JourneyDetail, QualityCriteria,
          ApiDocumentation, Layout, Settings, Login, Journeys)
  components/ (admin/*, QualityTabV2, WebhooksTab, JourneyStartTab,
               JourneyIncidentsTab, JourneyCloseTab, HeatmapSection,
               LumiChat, EvidenceCarousel, ImageUploader, DashboardLayout,
               GuiasTab, ReviewModal, PulseBanner, PulseCell, PulseStrip)
```

## Credentials
- dev@me.mx / LastMile2026 (Developer)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)
- proveedor@me.mx / LastMile2026 (Proveedor)

## Backlog
- [x] Validate export filters across all report sections (P0) — Done 2026-04-01
- [x] Unified Guias tab replacing Calidad + Paquetes (P0) — Done 2026-04-01
- [x] Proveedor role with read-only access (P0) — Done 2026-04-01
- [x] Liquidacion del Servicio export (Belgos/SOP format, P0) — Done 2026-04-07
- [x] Dynamic SLA Configuration per Provider (P0) — Done 2026-04-07
- [x] SLA/Pulse config edit permissions for Coordinators (P1) — Done 2026-04-07
- [x] Pulse: Real-time feasibility monitor — Done 2026-04-07
- [x] Code Quality: Security fixes, useMemo, refactoring — Done 2026-04-07
- [x] Discrepancy Detection: Confidence engine + GuiasTab UI — Done 2026-04-09
- [x] AI Evaluation UX: Severity badges, ReviewModal, Background polling — Done 2026-04-09
- [x] Bug fix: Confidence score using raw DB fields + auto-recalc after Kosmo rescrape — Done 2026-04-09
- [x] Bug fix: Kosmo batch re-scrape now fetches ALL packages (not just 0-proof) — Done 2026-04-09
- [x] Connected Quality Criteria system_prompt to AI evaluation engine — Done 2026-04-09
- [x] Supervised Training generates training_samples on manual review — Done 2026-04-09
- [x] Reports module redesign: KPI cards, charts, chip filters, PDF export — Done 2026-04-10
- [x] P1: Inline Incident Registration from Guías Tab — Done 2026-04-10
- [x] P2: AI Reports Generation v2.0 with Dynamic Cards — Done 2026-04-10
- [x] P3: Cubbo Standard Evidence Evaluation (ReviewModal) — Done 2026-04-10
- [ ] Split large components: Settings (1066L), JourneyDetail (1237L), Layout (802L) (P1)
- [ ] localStorage -> httpOnly cookies migration (P1, security hardening)
- [ ] Mobile-optimized views for field agents (P2)
- [ ] Export journey details to PDF (P2)
- [ ] Automatic image compression for large uploads (P2)
- [ ] Historical trend charts for delivery rates (P3)
