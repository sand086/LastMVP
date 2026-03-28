# LastMile OS - Changelog

## 2026-03-28 - Dashboard v2 Redesign (Complete)
- **NEW:** Completely redesigned Dashboard page based on approved HTML reference
  - Filters row relocated **above** KPIs (search, dates, client, provider, status, refresh, export)
  - 5 KPI cards with new design tokens (DM Sans typography, accent colors)
  - Routes table with sortable columns and pagination
  - Bottom grid: Metrics + Provider Comparison
- **NEW:** Provider Comparison now includes **Visita%** column (`visit_rate` field)
- **NEW:** Interactive Leaflet heatmap section "Mapa de calor — Densidad de entregas por CP"
  - CartoDB Light tiles (no API key required)
  - Circle markers colored by intensity (yellow→orange→red gradient)
  - Zone selector (Todo México, CDMX, Norte, Centro, Sur)
  - Top 10 CPs sidebar with clickable rows
  - Tooltip on hover: CP, zone, deliveries, failures, effectiveness %
  - Empty state with overlay message
- **NEW:** Backend endpoint `GET /api/reports/heatmap` 
  - Groups packages by postal code, enriches with lat/lng from `cp_coordinates.py`
  - Returns: cp, zone, lat, lng, delivered, failed, total, rate
- **NEW:** `cp_coordinates.py` with 120+ CDMX/ZM postal codes
- **NEW:** Leaflet CSS and DM Sans/DM Mono fonts imported
- **FIX:** CORS origins now read from env var (deployment readiness)
- **FIX:** N+1 query patterns in analytics_routes.py replaced with batch aggregation
- **TESTED:** 100% backend (15/15), 100% frontend (iteration_16)

## 2026-03-25 - Batch Re-scrape Feature
- Created `POST /api/journeys/{journey_id}/batch-rescrape` endpoint
- Fixed batch re-scrape button visibility condition
- Updated frontend to use backend batch endpoint
- Tested: 19/19 backend, 100% frontend (iteration_15)

## 2026-03-24 - Major Refactoring & Feature Delivery
- Backend refactored from monolithic `server.py` (3584 lines) to modular routes (8 files)
- Sortable tables added to all pages
- Quality Criteria configuration page
- WebSocket real-time dashboard updates
- Kosmo scraper bug fix
- Individual package re-scrape

## 2026-03-23 - Core Features
- 2-step Cosmo layout upload
- Image uploads for journey phases
- Failed packages search
- Dynamic client/provider assignment
- AI evidence quality scoring

## 2026-03-21 - MVP Foundation
- FastAPI + React + MongoDB scaffolding
- JWT role-based authentication
- Dashboard with KPIs and date filtering
- Journey CRUD with start/close workflows
- Kosmo tracking sync
