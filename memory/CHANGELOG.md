# LastMile OS - CHANGELOG

## 2026-03-31 — Webhooks + Refactoring + API Docs Update
- [x] Webhooks Integration (Plug & Play): Full CRUD, test dispatch, HMAC signatures, delivery log, retry logic
- [x] WebhooksTab UI in Settings page (create, toggle, test, delete, expand deliveries, regenerate secret)
- [x] Fixed Settings TabsList: grid-cols-4 -> grid-cols-5 for 5 tabs
- [x] Backend refactoring: Moved admin.py, lumi.py, system_routes.py (factory), kosmo router to routes/ directory
- [x] server.py simplified from ~218 to 206 lines (all routing via routes/__init__.py)
- [x] API Documentation updated: Added Webhooks API reference (8 endpoints) and Security section
- [x] Testing: iteration_23 — 95% backend, 100% frontend pass rate

## 2026-03-31 — Non-blocking AI + JourneyDetail Refactoring
- [x] evaluate-IA non-blocking: AI runs in separate thread (ThreadPoolExecutor)
- [x] API Documentation updated with security details
- [x] JourneyDetail.jsx refactored: Extracted JourneyStartTab, JourneyIncidentsTab, JourneyCloseTab

## 2026-03-30 — Pre-production Infrastructure Hardening
- [x] CORS wildcard -> specific domains
- [x] HSTS, X-Content-Type-Options, X-Frame-Options headers
- [x] bcrypt async with ThreadPoolExecutor
- [x] JWT_SECRET from .env, auto-logout on 401
- [x] Production MongoDB indexes (15+ compound)
- [x] PUT /close schema fix, evaluate-ia alias endpoint

## 2026-03-28 — Bug Fixes
- [x] Restored Start/Incidents/Close workflow visibility in JourneyDetail
- [x] Developer role permissions for journey operations

## Earlier
- Full MVP build: Auth, Layout Upload, Journey Management, Dashboard, Reports, Lumi, Quality, Admin IA
