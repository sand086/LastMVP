# LastMile OS - Changelog

## 2026-03-25 (Session 2) - Bug Fix: Kosmo Evidence Detection

### Bug Fix: Paquete NzjTRRrBBjGyduqR no detectó evidencias
- **Causa raíz**: El scraper periódico de Kosmo tuvo un error transitorio al procesar este paquete, resultando en `kosmo_proof_count: 0` y `kosmo_status_raw: "unknown"` a pesar de tener 4 evidencias en la URL de tracking
- **Fix 1**: Mejorada la query del sync scheduler para re-scrape automático de paquetes con `kosmo_status_raw: "unknown"`
- **Fix 2**: Nuevo endpoint `POST /api/packages/{id}/rescrape` para forzar re-sincronización individual
- **Fix 3**: Botón de re-scrape (icono de refresh naranja) visible en tabla de paquetes cuando `proof_count=0` o `status_raw=unknown`
- **Resultado**: 2 paquetes recuperados exitosamente (NzjTRRrBBjGyduqR → 4 evidencias/score 100, zQ7VVz15gewfc5F5 → 10 evidencias)

## 2026-03-25 (Session 1) - Major Refactoring & New Features

### Backend Refactoring (P0)
- Decomposed monolithic `server.py` (3,584 lines) into 8 modular route files in `/app/backend/routes/`
- Created `dependencies.py` for shared auth, DB, limiter, and utility functions
- Created `models.py` with all Pydantic models
- Main `server.py` reduced to 124 lines (app init + router inclusion)

### Sortable Tables (P1)
- Applied `useSortableTable` hook to all data tables: Dashboard, JourneyDetail, Reports, Settings

### Quality Criteria Configuration (P1)
- New page `/quality-criteria` for Coordinator/Developer
- CRUD for delivery type evidence, scoring rules, third-party keywords, AI config

### WebSocket Real-time Dashboard (P1)
- WebSocket at `/ws/dashboard` with auto-reconnect and polling fallback
- Live connection indicator in dashboard header

### API Documentation Update
- 17 endpoints documented in `/api/reports/schema`

## 2026-03-24 - Security & Quality Features
- AI-powered evidence scoring (Claude Sonnet 4.5)
- Security hardening (CORS, rate limiting, file validation, lockout, JWT revocation)
- Bulk package status update
- Heatmap, quality reports, cost tracking
- Dynamic server-side pagination
- Adaptive Kosmo sync scheduler

## Earlier Sessions
- FastAPI + React + MongoDB scaffolding
- 2-step Cosmo layout upload
- Image uploads, journey lifecycle
- Failed packages search, role-based auth
