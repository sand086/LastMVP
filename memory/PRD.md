# LastMile OS MVP - Product Requirements Document

## Original Problem Statement
Build "LastMile OS MVP" for managing last-mile delivery operations for ME (Mensajería y Estrategias). Includes authentication, dashboard, CSV/XLSX Cosmo data layout uploads, journey execution tracking (Start/Incidents/Close), dynamic assignment, custom reports with AI, system observability, automated Kosmo tracking sync, and evidence quality scoring based on Cubbo standards.

## Tech Stack
- **Frontend**: React + TailwindCSS + Shadcn UI + Lucide Icons
- **Backend**: FastAPI + JWT Auth + Pandas/Openpyxl + httpx (Kosmo scraper)
- **Database**: MongoDB (indexed: cosmo_route_id + order_reference_id, order_reference_id)
- **AI**: Claude Sonnet 4.5 via emergentintegrations (Emergent LLM Key)

## Completed Features

### Core (Phase 1-3)
- JWT role-based auth (Agent, Coordinator, Executive, Developer)
- 2-step Cosmo layout upload with composite key dedup + CSV auto-filter
- Route management (Start with checklist, Incidents with bulk resolve, Close with auto-calculated metrics)
- Dashboard with date range stats, driver column, sync bar (10 min)
- Custom Reports + AI, API docs, System Observability

### Kosmo Tracking + Evidence Quality (Phase 4-5)
- Async Kosmo scraper (max 250 pkgs) with proof photo URL extraction
- Evidence quality scoring (Cubbo standard: exitosa=3 photos, fallida=photo+note, terceros=note)
- Quality tab + Dashboard KPI + reports

### Operational Adjustments (Phase 7-9)
- Composite unique key (cosmo_route_id + order_reference_id) — same package in multiple routes
- Delivery attempt counting by date order (newest=1, oldest=highest)
- "Creation Date" from route-summary used as journey date
- Auto-calculated close metrics (no manual input), pre-populated return candidates
- "returned" (Devuelto) status, "VISITAS" header, "DEVOLUCIONES" in close
- "Resolver todas" incidents button, package review indicator
- Driver name in dashboard table, journey detail, WhatsApp summaries
- Odometer validation before close, DB cleanup confirmation dialog
- Date filter off-by-one fix (_next_day for timestamps)
- Dashboard stats from actual package counts (not journey summary fields)

## Key DB Schema
- `packages`: {id, journey_id, cosmo_route_id, order_reference_id, tracking_url, delivery_attempt, kosmo_proof_count, kosmo_proof_urls, evidence_score, evidence_type, reviewed_by, reviewed_at, ...}
- `journeys`: {id, cosmo_route_id, date, client_id, provider_id, driver_name, status, ...}

## Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
- Developer: dev@me.mx / LastMile2026

## Future Tasks (P2)
- [ ] Automatic image compression for large uploads
- [ ] Mobile-optimized views for field agents
- [ ] Email/Slack alerts for delivery rate drops
