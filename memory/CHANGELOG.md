# LastMile OS - Changelog

## 2026-03-25 - Batch Re-scrape Feature & Regression Testing
- **NEW:** Created `POST /api/journeys/{journey_id}/batch-rescrape` backend endpoint
  - Finds all packages with tracking_url but 0 proofs or unknown status
  - Scrapes them in parallel (concurrency 3)
  - Re-evaluates evidence scores after scraping
  - Returns `{total, recovered, errors, message}`
- **FIX:** Fixed batch re-scrape button visibility condition in `JourneyDetail.jsx`
  - Changed from strict `=== 0` to falsy check (`!p.kosmo_proof_count`)
  - Now correctly handles undefined, null, and 0 values
- **FIX:** Updated frontend to use backend batch endpoint instead of frontend loop
- **TESTED:** Full regression pass - 19/19 backend tests, 100% frontend verification

## 2026-03-24 - Major Refactoring & Feature Delivery
- Backend refactored from monolithic `server.py` (3584 lines) to modular routes (8 files)
- Sortable tables added to Dashboard, JourneyDetail, Reports, Settings
- Quality Criteria configuration page created
- WebSocket real-time dashboard updates implemented
- Kosmo scraper bug fixed (silent failures on some packages)
- Individual package re-scrape feature added
- Data correction batch run for 11 affected packages

## 2026-03-23 - Core Features
- 2-step Cosmo layout upload
- Image uploads for Start/Incidents/Close journey
- Failed packages search filter
- Dynamic client/provider assignment
- API documentation (Power BI sandbox)
- Evidence carousel with photo analysis
- AI evidence quality scoring (Claude Sonnet)

## 2026-03-21 - MVP Foundation
- FastAPI + React + MongoDB scaffolding
- JWT role-based authentication
- Dashboard with KPIs and date filtering
- Journey CRUD with start/close workflows
- Incident management
- Kosmo tracking sync with adaptive scheduler
