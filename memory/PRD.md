# LastMile OS - Product Requirements Document (PRD)

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajeria y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, AI-powered evidence scoring with discrepancy detection, real-time dashboard, advanced reporting, quality criteria configurations, admin AI consumption tracking, webhook integrations, and API documentation.

## Tech Stack
- **Backend**: FastAPI, Motor (MongoDB), Python 3.11
- **Frontend**: React 18, TailwindCSS, Shadcn UI, Recharts, DOMPurify
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
- [x] httpOnly cookie auth (secure, SameSite=lax) with Bearer header backward compat
- [x] 2-step Cosmo layout upload (history-orders CSV + route-summary XLSX)
- [x] Journey management (Start, Incidents, Close) with image uploads
- [x] Kosmo tracking sync (automatic + manual) with optimized performance
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
- [x] Webhook Integrations (Plug & Play) - CRUD, test, HMAC, delivery log
- [x] Backend refactoring - all routes in /routes/ directory
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
  server.py (210 lines - app setup only)
  dependencies.py (refactored: extracted address helpers, httpOnly cookie config)
  middleware.py (refactored: table-driven patterns)
  evidence_scoring.py (refactored: 5 extracted helpers + status tracking)
  kosmo_sync.py (optimized: 10x concurrency, connection pooling, 429 handling)
  token_logger.py, cp_coordinates.py, ws_manager.py

  routes/ (14 modules via __init__.py)
    auth_routes.py (httpOnly cookies on login/logout)
    user_routes.py, journey_routes.py
    upload_routes.py, dashboard_routes.py, analytics_routes.py
    admin_routes.py, admin_module_routes.py
    quality_criteria_routes.py, quality_tab_routes.py
    webhook_routes.py, system_routes.py
    lumi_routes.py, kosmo_routes.py

  tests/
    conftest.py (shared fixtures, env-based credentials)
    22+ test files

/app/frontend/src/
  pages/ (AdminPage, Dashboard, Reports, JourneyDetail, QualityCriteria,
          ApiDocumentation, Layout, Settings(416L), Login, Journeys)
  components/ (admin/*, QualityTabV2, WebhooksTab, JourneyStartTab,
               JourneyIncidentsTab, JourneyCloseTab, HeatmapSection,
               LumiChat, EvidenceCarousel, ImageUploader, DashboardLayout,
               GuiasTab, ReviewModal, PulseBanner, PulseCell, PulseStrip)
  components/settings/ (SettingsUsersTab, SettingsClientsTab,
                        SettingsProvidersTab, SettingsSystemTab)
```

## Credentials
- dev@me.mx / LastMile2026 (Developer)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)
- proveedor@me.mx / LastMile2026 (Proveedor)

## Backlog
- [x] Validate export filters across all report sections (P0) - Done 2026-04-01
- [x] Unified Guias tab replacing Calidad + Paquetes (P0) - Done 2026-04-01
- [x] Proveedor role with read-only access (P0) - Done 2026-04-01
- [x] Liquidacion del Servicio export (Belgos/SOP format, P0) - Done 2026-04-07
- [x] Dynamic SLA Configuration per Provider (P0) - Done 2026-04-07
- [x] SLA/Pulse config edit permissions for Coordinators (P1) - Done 2026-04-07
- [x] Pulse: Real-time feasibility monitor - Done 2026-04-07
- [x] Code Quality: Security fixes, useMemo, refactoring - Done 2026-04-07
- [x] Discrepancy Detection: Confidence engine + GuiasTab UI - Done 2026-04-09
- [x] AI Evaluation UX: Severity badges, ReviewModal, Background polling - Done 2026-04-09
- [x] Bug fix: Confidence score using raw DB fields + auto-recalc after Kosmo rescrape - Done 2026-04-09
- [x] Bug fix: Kosmo batch re-scrape now fetches ALL packages (not just 0-proof) - Done 2026-04-09
- [x] Connected Quality Criteria system_prompt to AI evaluation engine - Done 2026-04-09
- [x] Supervised Training generates training_samples on manual review - Done 2026-04-09
- [x] Reports module redesign: KPI cards, charts, chip filters, PDF export - Done 2026-04-10
- [x] P1: Inline Incident Registration from Guias Tab - Done 2026-04-10
- [x] P2: AI Reports Generation v2.0 with Dynamic Cards - Done 2026-04-10
- [x] P3: Cubbo Standard Evidence Evaluation (ReviewModal) - Done 2026-04-10
- [x] Code Quality Review: Security fixes, backend refactoring, GuiasTab split, hook deps, PulseStrip key - Done 2026-04-10
- [x] PDF Export Redesign: Multi-page, legible, all 6 tabs + cover + AI analysis - Done 2026-04-10
- [x] P1: Refresh Token for Power BI (generate, exchange, revoke, list) - Done 2026-04-15
- [x] P2: Liquidacion formulas fix (Col O = H+I, Col AB = O/MAX(G,sla)) - Done 2026-04-15
- [x] P3: Delete Journey + Driver column in tables - Done 2026-04-15
- [x] P4: Order ID in tables + search + pagination 25/50/100 - Done 2026-04-15
- [x] P5: Remove checklist + 32 Mexico states in route type - Done 2026-04-15
- [x] Kosmo Sync Performance Optimization (P0) - Done 2026-04-15
- [x] httpOnly cookie migration (P1, security hardening) - Done 2026-04-15
- [x] Split Settings.jsx (1147->416L), JourneyDetail.jsx (1447->1055L) - Done 2026-04-15
- [x] P0 Driver Management: Drivers tab in Settings + Blocking modal for new providers in Layout upload - Done 2026-04-16
- [x] P1 Driver Management: Route-level provider editing + audit log (route_edits) - Done 2026-04-16
- [x] Lumi Fix: Active journey context injection (P0+P1+P2 combined) - Done 2026-04-16
- [x] Auto-Audit Report: Generated /app/memory/AUDIT_REPORT.md + Applied P0 fixes (TTL indexes, audit_log cleanup) - Done 2026-04-16
- [x] Code Quality Review: Empty catches (30+ fixed), XSS verified (DOMPurify already in place), hook deps, test credentials centralized, webpack 0 warnings - Done 2026-04-16
- [x] Platform Manuals (Knowledge Hub) Fase 1: Index + Viewer + CRUD API + 6 seed manuals - Done 2026-04-17
- [x] Sidebar colapsable (solo iconos) con persistencia en localStorage - Done 2026-04-17
- [x] P1 Split componentes >500L: Dashboard(-95L), QualityTabV2(-65L), Reports(-57L), Settings(-726L) - Done 2026-04-17
- [x] P3 Split Layout.jsx (1062->991L): WizardSteps + UpdateNotesSection extraidos - Done 2026-04-17
- [x] Vistas movil: Sidebar drawer, responsive tables, KPI cards adaptados, hamburger menu - Done 2026-04-17
- [ ] Split Layout.jsx (1062L) — wizard steps a sub-componentes (P3)
- [x] Liquidacion fixes: +Proveedor en Incidencias, Completados=delivered+failed, evidencia incluye failed - Done 2026-04-17
- [x] Update delivery notes: POST /upload/update-notes + note_from_driver in GuiasPackageDetail - Done 2026-04-17
- [x] AI Eval Worker & Monitor de Procesos: MongoDB-backed queue, background worker + cron sweep, /api/ai-evaluation/* routes, /monitor page with access control (coordinator/developer), Progress indicatorClassName support - Done 2026-04-21
- [x] Catalogo estandarizado de Tipos de incidencia (5 enum values) + campo condicional comentario_asesor (requerido con 'otro', max 500 chars) + manual actualizado - Done 2026-04-21
- [x] Code Quality P2+P3: React.lazy() en rutas no críticas (Suspense + PageLoader), refactor ai_eval_worker._process_job (95L→28L + 3 helpers), split ApiDocumentation.jsx (711→270L + DocsTab/SandboxTab/ExamplesTab), orphan job recovery al startup, clipboard API robustness, .quality-ignore.md - Done 2026-04-22
- [x] Code Quality P2+P3 batch 2: lifespan context manager (reemplaza @app.on_event), SSE json.dumps, cancel_job 404/400 clarity, GET /api/ai-evaluation/health para monitoreo externo, Dashboard.css extracted (541→505L), nuevo manual "Monitor de Procesos" + actualizado "API & Integraciones" con sección de worker monitoring - Done 2026-04-22
- [x] Code Quality P2+P3 batch 3: Split GuiasTab (654→585L + useGuiasMetrics hook + GuiasKpisRow component), Split JourneyDetail (1246→1208L + ProviderEditDialogs), Split Layout (992→931L + RoutesPreviewCard + UploadHistoryCard), Harmonizar envelope paginación via pagination_utils.paginated_response() helper con dual-shape (flat + nested) para backwards compat, Fix React duplicate key warning en PulseStrip - Done 2026-04-22
- [ ] Split Layout.jsx (923L) into sub-components (P3)
- [ ] Mobile-optimized views for field agents (P2)
- [ ] Export journey details to PDF (P2)
- [ ] Automatic image compression for large uploads (P2)
- [ ] Historical trend charts for delivery rates (P3)
- [ ] Fix React console warnings: indicatorClassName prop, duplicate keys (P3)
