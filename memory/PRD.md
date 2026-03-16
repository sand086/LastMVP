# LastMile OS - Product Requirements Document

## Original Problem Statement
Build a SaaS web application called "LastMile OS MVP" for managing last-mile delivery operations. The platform is used internally by ME (Mensajería y Estrategias), a Mexican logistics company, to manage their daily courier operations with multiple transport providers for B2B clients.

## User Choices
- **Database**: MongoDB (pre-configured)
- **File Storage**: Local filesystem
- **Password Reset**: Admin module with internal notifications
- **Design**: AI-chosen (Industrial Swiss design system)
- **Language**: Spanish UI

## User Personas
1. **Agente (Agent)**: Full access to operational modules - creates journeys, manages incidents, starts/closes routes
2. **Coordinador (Coordinator)**: Full access + user management + settings configuration
3. **Ejecutivo (Executive)**: Read-only access to dashboard and reports

## Core Requirements (Static)
- JWT Authentication with 8hr expiry
- Three roles: Agent, Coordinator, Executive
- Module 1: Layout Upload (CSV/XLSX parsing)
- Module 2: Journey Start (checklist, photo upload)
- Module 3: Incidents management (CRUD, severity levels)
- Module 4: Journey Close (metrics calculation, retry packages)
- Module 5: Dashboard (KPIs, polling every 60s, filters)
- Color system: green=#1A7A4A, amber=#C07000, red=#8B0000, blue=#2E6096
- Mobile-responsive, desktop-first (1280px optimized)

## What's Been Implemented (2026-03-16)

### Backend (FastAPI + MongoDB)
- ✅ JWT Authentication with login/logout/me endpoints
- ✅ User management (CRUD, password change by admin)
- ✅ Password reset requests system
- ✅ Clients and Providers CRUD
- ✅ Journeys CRUD with start/close operations
- ✅ Packages management
- ✅ Incidents CRUD with resolve functionality
- ✅ File upload (CSV/XLSX parsing, photo upload)
- ✅ Dashboard stats endpoint
- ✅ Export to Excel/CSV
- ✅ Seed data with 2 clients, 2 providers, 3 users, 2 journeys

### Frontend (React + Tailwind CSS)
- ✅ Login page with forgot password flow
- ✅ Dashboard with 4 KPI cards (polling enabled)
- ✅ Journey table with progress bars and status badges
- ✅ Filters (date range, client, provider, status)
- ✅ Journeys list page
- ✅ Journey detail with 3 tabs (Inicio/Incidencias/Fin)
- ✅ Journey start form with checklist
- ✅ Incidents management with add/edit/resolve/delete
- ✅ Journey close form with metrics calculation
- ✅ Layout upload with drag & drop
- ✅ Settings page with user/client/provider management
- ✅ Role-based navigation and access control
- ✅ WhatsApp-friendly summaries with copy button
- ✅ Export functionality
- ✅ Spanish language UI throughout

### Design System (Industrial Swiss)
- ✅ Barlow Condensed headings, IBM Plex Sans body
- ✅ Light mode with slate neutrals
- ✅ Status badges and progress bar colors
- ✅ Clean data tables with uppercase headers
- ✅ Card-based layout with subtle shadows

## Prioritized Backlog

### P0 - Critical (Not blocking but important)
- None currently

### P1 - High Priority Enhancements
- File upload for odometer photos (endpoint exists, UI not connected)
- Real-time incident count in sidebar notification bell
- More detailed package tracking within journey

### P2 - Medium Priority
- Password reset email integration (currently admin-only)
- Audit log for all actions
- Mobile-optimized layout for field agents
- Advanced reporting with date range charts

### P3 - Nice to Have
- Dark mode toggle
- Multi-language support (English)
- Bulk journey operations
- API rate limiting
- PDF export for reports

## Next Tasks List
1. Connect photo upload UI to backend endpoint
2. Add notification bell with real-time count
3. Implement package-level tracking and status updates
4. Add more detailed analytics charts on dashboard
5. Consider mobile-first redesign for field agents

## Technical Architecture
```
Frontend (React 19)
├── /src
│   ├── /components (DashboardLayout, UI components)
│   ├── /pages (Login, Dashboard, Journeys, Layout, Settings)
│   ├── /contexts (AuthContext)
│   └── /lib (api.js, utils.js)

Backend (FastAPI)
├── server.py (all routes and models)
├── /uploads (file storage)
└── .env (MONGO_URL, JWT_SECRET)

Database (MongoDB)
├── users
├── clients
├── providers
├── journeys
├── packages
├── incidents
├── password_reset_requests
└── upload_history
```

## Test Credentials
- Agent: agente@me.mx / LastMile2026
- Coordinator: yael@me.mx / LastMile2026
- Executive: karina@me.mx / LastMile2026
