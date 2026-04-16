# LastMile OS — Auto-Auditoria Tecnica
**Fecha**: 2026-04-16 | **Agente**: Emergent E1 | **Version**: MVP Pilot Cubbo

---

## Resumen Ejecutivo (< 300 palabras)

**Veredicto: AMARILLO** — La plataforma esta operativa y estable para el piloto con Cubbo (1 cliente, ~1,500 paquetes, 39 rutas), pero presenta deuda tecnica acumulada que debe resolverse ANTES de escalar a 10 clientes. Los puntos criticos son: componentes frontend monoliticos (8 archivos >500 lineas), ausencia de aislamiento multi-tenant, y `request_metrics` creciendo sin TTL (49K docs). La arquitectura FastAPI + MongoDB + React es adecuada para el volumen actual, pero los endpoints de analytics (1,850 lineas) y journey management (1,430 lineas) necesitan descomposicion para mantenibilidad. La integracion con Claude Sonnet para evaluacion de evidencia funciona correctamente con logging de tokens. El sync con Kosmo fue recientemente optimizado (10x concurrencia) y es estable. Auth migrada a httpOnly cookies con backward compatibility Bearer.

---

## D1 — Arquitectura y Calidad de Codigo

### AUDIT-D1-001: Componentes Frontend Monoliticos (P1)
- **Archivos**: `JourneyDetail.jsx` (1,169L), `Reports.jsx` (1,033L), `Layout.jsx` (980L), `QualityTabV2.jsx` (708L), `ApiDocumentation.jsx` (691L), `GuiasTab.jsx` (685L), `Dashboard.jsx` (634L)
- **Impacto**: Dificultad de mantenimiento, hot reload lento, riesgo de regresion al editar
- **Remediacion**: Extraer sub-componentes (<200L cada uno). Settings.jsx ya fue refactorizado exitosamente de 1,147→416L como modelo
- **Esfuerzo**: 2-3 dias

### AUDIT-D1-002: Backend Routes Monoliticas (P1)
- **Archivos**: `analytics_routes.py` (1,850L), `journey_routes.py` (1,430L)
- **Impacto**: Acoplamiento alto, dificil testing unitario
- **Remediacion**: Separar en sub-modulos (ej: `journey_crud.py`, `journey_cosmo.py`, `journey_packages.py`)
- **Esfuerzo**: 1-2 dias

### AUDIT-D1-003: Coleccion Duplicada `audit_log` vs `audit_logs` (P2)
- **Evidencia**: `audit_log: 16 docs` y `audit_logs: 2,910 docs` — dos colecciones para el mismo proposito
- **Remediacion**: Migrar datos de `audit_log` a `audit_logs`, eliminar la coleccion legacy
- **Esfuerzo**: 30 min

---

## D2 — Performance y Escalabilidad

### AUDIT-D2-001: `request_metrics` Sin TTL — 49K Docs y Creciendo (P0)
- **Evidencia**: Coleccion `request_metrics` con 49,238 documentos, sin indice TTL
- **Impacto**: A 10 clientes (~500 req/min), esta coleccion crecera a ~720K docs/dia. Sin TTL, MongoDB degradara en queries de auditoria
- **Remediacion**: `db.request_metrics.createIndex({"timestamp": 1}, {expireAfterSeconds: 2592000})` (30 dias TTL)
- **Esfuerzo**: 5 min (1 linea en startup)

### AUDIT-D2-002: Dashboard Queries Sin Cache (P1)
- **Evidencia**: `dashboard_routes.py` ejecuta 5+ queries paralelos en cada request (count_documents x3, find x1, aggregate x1)
- **Impacto**: ~200-400ms por request a volumen actual; a 10x volumen podria llegar a 1-2s
- **Remediacion**: Cache en memoria (dict con TTL de 60s) para stats agregados que no cambian frecuentemente
- **Esfuerzo**: 2-3 horas

### AUDIT-D2-003: Evaluacion IA Batch Sin Limite de Concurrencia por Tenant (P1)
- **Evidencia**: `evidence_scoring.py` procesa paquetes en paralelo sin limitar por cliente
- **Impacto**: Un cliente con 500 paquetes puede monopolizar el rate limit de Claude
- **Remediacion**: Semaforo por tenant en evaluaciones batch
- **Esfuerzo**: 2 horas

### AUDIT-D2-004: Frontend Bundle Sin Code Splitting (P2)
- **Evidencia**: React app carga todo el bundle en initial load (Reports, ApiDocs, AdminPage)
- **Remediacion**: `React.lazy()` + `Suspense` para rutas no-criticas
- **Esfuerzo**: 2 horas

---

## D3 — Seguridad y Datos

### AUDIT-D3-001: PII Sin Cifrado At Rest (P1)
- **Evidencia**: `packages` almacena `recipient_name`, `address`, `recipient_phone` en texto plano
- **Impacto**: ~1,577 registros con datos personales de destinatarios. Con 10 clientes, ~15K+
- **Remediacion**: Cifrado a nivel campo (AES-256) o MongoDB Client-Side Field Level Encryption
- **Esfuerzo**: 1-2 dias

### AUDIT-D3-002: `system_errors` Expone Detalles Internos (P2)
- **Evidencia**: 268 errores almacenados con stack traces y paths internos
- **Remediacion**: Sanitizar `detail` y `last_detail` antes de almacenar; no exponer al frontend
- **Esfuerzo**: 1 hora

### AUDIT-D3-003: Tokens Revocados Sin TTL (P2)
- **Evidencia**: `revoked_tokens: 86 docs` — crece indefinidamente
- **Remediacion**: TTL index basado en `expires_at`
- **Esfuerzo**: 5 min

---

## D4 — Observabilidad y Monitoreo

### AUDIT-D4-001: Sin Metricas de Latencia por Endpoint (P1)
- **Evidencia**: `request_metrics` almacena `duration_ms` pero no hay dashboard de P95/P99
- **Remediacion**: Agregar endpoint `GET /api/system/latency-stats` con aggregation pipeline
- **Esfuerzo**: 2 horas

### AUDIT-D4-002: Kosmo Sync Sin Alertas de Fallo Sostenido (P1)
- **Evidencia**: Si Kosmo esta caido 1h, el sistema solo loguea warnings — no alerta al coordinador
- **Remediacion**: Contador de errores consecutivos → notificacion WebSocket si >10 fallos seguidos
- **Esfuerzo**: 1-2 horas

### AUDIT-D4-003: Token Usage Log Sin Agregacion de Costos (P2)
- **Evidencia**: `token_usage_log: 78 docs` registra tokens pero no agrega costo mensual automaticamente
- **Remediacion**: Cron job o pipeline de agregacion para costos mensuales
- **Esfuerzo**: 1 hora

---

## D5 — Multi-Tenancy y Escalabilidad de Negocio

### AUDIT-D5-001: Sin Aislamiento de Datos por Cliente (P0)
- **Evidencia**: Todas las colecciones comparten datos de todos los clientes. `apply_assignment_filter` filtra por `client_id` pero no es enforcement a nivel DB
- **Impacto**: Al escalar a 10 clientes, un error en filtro expone datos cruzados
- **Remediacion Fase 1**: Middleware que inyecte `client_id` en TODAS las queries automaticamente
- **Remediacion Fase 2**: Indices compuestos con `client_id` como primer campo en colecciones criticas
- **Esfuerzo**: 1-2 dias (Fase 1)

### AUDIT-D5-002: Configuracion SLA Global en Vez de por Cliente (P1)
- **Evidencia**: `config` collection tiene 8 docs globales. SLA targets son compartidos
- **Impacto**: Cada cliente puede tener SLAs diferentes
- **Remediacion**: Agregar `client_id` a docs de config, fallback a config global si no existe
- **Esfuerzo**: 3-4 horas

### AUDIT-D5-003: Proveedores Compartidos Entre Clientes (P2)
- **Evidencia**: `providers: 13 docs` sin campo `client_id`
- **Remediacion**: Agregar scoping por cliente o crear coleccion de relacion client_provider
- **Esfuerzo**: 4 horas

---

## Roadmap Priorizado

### Sprint 1 (P0 — Esta semana)
| ID | Tarea | Esfuerzo |
|---|---|---|
| D2-001 | TTL en `request_metrics` | 5 min |
| D3-003 | TTL en `revoked_tokens` | 5 min |
| D5-001 | Middleware client_id enforcement | 1-2 dias |

### Sprint 2 (P1 — Proxima semana)
| ID | Tarea | Esfuerzo |
|---|---|---|
| D1-001 | Split componentes frontend >500L | 2-3 dias |
| D1-002 | Split routes backend >1000L | 1-2 dias |
| D2-002 | Cache dashboard stats | 2-3 horas |
| D3-001 | PII encryption at rest | 1-2 dias |
| D4-001 | Endpoint latency stats | 2 horas |
| D4-002 | Alertas Kosmo sync | 1-2 horas |
| D5-002 | SLA config por cliente | 3-4 horas |

### Backlog (P2)
- D1-003: Limpieza coleccion `audit_log` duplicada
- D2-004: Code splitting frontend
- D3-002: Sanitizar system_errors
- D4-003: Agregacion costos tokens
- D5-003: Scoping proveedores por cliente

---

## Preguntas Abiertas

1. **Driver App**: Hay planes de app movil para drivers? Esto impactaria la estrategia de API (idempotencia, offline-first, versionamiento)
2. **Retencion de datos**: Cual es la politica de retencion deseada? (30/60/90 dias para metricas, indefinido para rutas?)
3. **Volumen esperado por cliente**: Cubbo maneja ~1,500 paquetes/periodo. Los otros 9 clientes tendran volumen similar?
4. **SLAs diferenciados**: Cada cliente nuevo tendra SLAs propios o comparten el bracket actual?
5. **Carrier integrations**: Chamede y Octavio tendran APIs propias o seguiran con Kosmo scraping?
