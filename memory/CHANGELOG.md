# LastMile OS - Changelog

## 2026-03-25 - Major Refactoring & New Features

### Backend Refactoring (P0)
- Decomposed monolithic `server.py` (3,584 lines) into 8 modular route files in `/app/backend/routes/`
- Created `dependencies.py` for shared auth, DB, limiter, and utility functions
- Created `models.py` with all Pydantic models
- Main `server.py` reduced to 124 lines (app init + router inclusion)
- Full backward compatibility maintained - all API endpoints work identically

### Sortable Tables (P1)
- Applied `useSortableTable` hook to all data tables across the application
- Dashboard: routes table (already done)
- JourneyDetail: packages table, incidents table
- Reports: MetricTable (provider/driver), QualityProviderTable, QualityTypeTable, HeatmapTable
- Settings: users table, clients table, providers table
- Extracted table components (MetricTable, QualityProviderTable, etc.) as standalone components

### Quality Criteria Configuration (P1)
- New backend: `routes/quality_criteria_routes.py` with GET/PUT/RESET endpoints
- New frontend: `QualityCriteria.jsx` page with full CRUD UI
- Configurable per delivery type (exitosa, terceros, fallida):
  - Required evidence items (add/remove/edit label, key, weight)
  - Scoring rules (min photos, score values, note requirements)
- Third-party detection keywords editor
- AI evaluation config (enable/disable, provider, custom instructions)
- Role-restricted: only Coordinator and Developer can access

### WebSocket Real-time Dashboard (P1)
- New backend: `ws_manager.py` with ConnectionManager class
- WebSocket endpoint at `/ws/dashboard` with ping/pong keepalive
- Broadcasts events: stats_update, journey_update, incident_update, sync_update
- Frontend: `useWebSocket.js` hook with auto-reconnect (5s interval)
- Dashboard shows live connection indicator ("En vivo" / "Reconectando...")
- Graceful fallback to 60s polling when WS unavailable

### API Documentation Update
- Added 3 new endpoints to `/api/reports/schema`: bulk-status, quality/criteria, ws/dashboard
- Total documented endpoints: 17

### Developer Role Enhancement
- Added 'developer' role to all sidebar navigation items (Rutas, Layout, Reportes, etc.)

## 2026-03-24 - Security & Quality Features

### Security Hardened
- CORS: strict origin whitelist (no more wildcard)
- Rate limiting via slowapi on login (5/min), uploads (10/min), reports (30/min)
- File upload validation (type, extension, 10MB max)
- Login lockout after 5 failed attempts (15 min block)
- HTTP security headers middleware
- JWT expiry reduced to 8h with token revocation on logout

### Quality & Evidence
- AI-powered evidence scoring using Claude Sonnet 4.5
- Rule-based scoring with configurable criteria
- Interactive evidence carousel modal
- Failed delivery scoring fixed (no driver comment required)
- Scroll position preserved after individual AI evaluation

### Operations
- Bulk package status update (Pending/Delivered/Failed/Returned)
- Provider names displayed instead of IDs in reports
- Cubbo export button fixed
- Cost/token consumption counter in System Health
- Heatmap Excel export with all geo fields
- Address normalization for Mexican addresses

### Infrastructure
- Dynamic server-side pagination for routes table
- Adaptive Kosmo sync scheduler
- Geographic heatmap analytics

## Earlier Sessions
- FastAPI + React + MongoDB scaffolding with seed data
- 2-step Cosmo layout upload (history-orders + route-summary)
- Image uploads for Start/Incidents/Close journey
- Failed packages search filter
- JWT role-based auth (Agent, Coordinator, Executive, Developer)
- Multiple bug fix iterations (iterations 1-13)
