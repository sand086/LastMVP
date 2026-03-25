# LastMile OS MVP - Product Requirements Document

## Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard polling, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, quality evaluation, and real-time monitoring.

## User Personas
- **Agent (agente)**: Field operations, uploads layouts, manages journeys
- **Coordinator (coordinador)**: Full access, manages users/config, reviews quality
- **Executive (ejecutivo)**: View reports, dashboards, analytics
- **Developer (developer)**: Full admin access, system config, quality criteria

## Core Architecture
- **Backend**: FastAPI (Python) - Modular routes in `/app/backend/routes/`
- **Frontend**: React + TailwindCSS + Shadcn UI
- **Database**: MongoDB (via motor async driver)
- **AI**: Claude Sonnet 4.5 for evidence scoring (Emergent LLM Key)
- **Real-time**: WebSocket at `/ws/dashboard`

## Backend Module Structure (Refactored)
- `server.py` (124 lines) - App init, middleware, router inclusion, WebSocket endpoint
- `dependencies.py` - DB, auth, JWT, limiter, utilities
- `models.py` - All Pydantic models
- `ws_manager.py` - WebSocket connection manager
- `evidence_scoring.py` - AI + rule-based quality evaluation
- `kosmo_sync.py` - Adaptive sync scheduler
- `middleware.py` - Audit + Security headers middleware
- `system_routes.py` - System health/logs endpoints
- `routes/auth_routes.py` - Login, logout, JWT revocation, password reset
- `routes/user_routes.py` - Users, Clients, Providers CRUD
- `routes/journey_routes.py` - Journeys, incidents, cosmo import, bulk update
- `routes/upload_routes.py` - CSV/XLSX uploads, images, messenger mappings
- `routes/dashboard_routes.py` - Stats, incidents breakdown, provider comparison
- `routes/analytics_routes.py` - Heatmap, quality reports, report generation, Power BI, token consumption
- `routes/admin_routes.py` - Seed data, cleanup
- `routes/quality_criteria_routes.py` - Quality evaluation criteria config

## Key Features Implemented
1. JWT auth with role-based access (4 roles) + token revocation + lockout
2. 2-step Cosmo layout upload (history-orders CSV + route-summary XLSX)
3. Journey lifecycle (scheduled → in_progress → closed)
4. Evidence quality scoring (rule-based + AI/Claude Sonnet)
5. Dynamic server-side pagination
6. Interactive evidence carousel
7. Adaptive Kosmo sync scheduler
8. Geographic heatmap with address normalization
9. Sortable tables across all pages (useSortableTable hook)
10. Cost/token consumption tracking
11. Bulk package status update
12. Configurable quality criteria (delivery types, scoring rules, AI config)
13. WebSocket real-time dashboard updates
14. Security: CORS hardening, rate limiting, file validation, security headers

## Credentials
- dev@me.mx / LastMile2026 (Developer)
- agente@me.mx / LastMile2026 (Agent)
- yael@me.mx / LastMile2026 (Coordinator)
- karina@me.mx / LastMile2026 (Executive)

## Key API Endpoints
- POST /api/auth/login, GET /api/auth/me, POST /api/auth/logout
- GET/POST /api/users, GET/POST /api/clients, GET/POST /api/providers
- GET/POST /api/journeys, PUT /api/journeys/{id}/start, PUT /api/journeys/{id}/close
- POST /api/journeys/from-cosmo
- POST /api/journeys/{id}/packages/bulk-status
- POST /api/upload/history-orders, POST /api/upload/route-summary
- GET /api/dashboard/stats, GET /api/dashboard/incidents-breakdown
- GET /api/analytics/heatmap, GET /api/reports/quality
- POST /api/reports/generate, POST /api/reports/generate-excel
- GET/PUT /api/quality/criteria, POST /api/quality/criteria/reset
- GET /api/system/health, GET /api/system/token-consumption
- WS /ws/dashboard
