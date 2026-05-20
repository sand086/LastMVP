# Bundle F · Triaje S2/S3 — Inventario y decisiones

**Fecha:** 12 May 2026 (Iter34)
**Origen:** AUDIT_UX_REPORT_v1.md + LATAM_AUDIT_REPORT_v1.md
**Política aplicada:** POL-01 (criterio editorial sobre S2/S3)
**Choices del PO:** 1.b (yo trío, vos validás output) · 2.b (remediar obvios cosméticos chicos, dejar mayores pendientes) · 3.b (si N<8, reportar sin ritual)

---

## Inventario total inicial

| Fuente | S2 | S3 | Total |
|---|---|---|---|
| AUDIT_UX_REPORT_v1 | 30 | 3 | 33 |
| LATAM_AUDIT_REPORT_v1 | 7 | 3 | 10 |
| **TOTAL** | **37** | **6** | **43** |

---

## Tabla de triaje

| ID | Sev | Confianza | Título resumido | Filtro | Decisión |
|---|---|---|---|---|---|
| **AUDIT UX v1** | | | | | |
| UX-AGENTE-003 | S2 | Alta | "Ticket" vs "folio" vs "caso" mezclados | — | **REMEDIAR** · Grupo 3 |
| UX-AGENTE-006 | S2 | Media | text-[10px]/font-mono en metadatos críticos | B | PENDIENTE VALIDACIÓN |
| UX-AGENTE-007 | S2 | Media | Composer sin indicador "guardando…" | — | **REMEDIAR** · Grupo 2 |
| UX-RECLAMOS-003 | S2 | Media | Upload sin progress bar individual | D | DESCARTE (refactor mayor) |
| UX-RECLAMOS-004 | S2 | Alta | Fechas mm/dd en algunos campos legacy | — | **REMEDIAR** · Grupo 6 |
| UX-CATALOGO-003 | S2 | Baja | Iconografía decorativa en algunas filas | B | PENDIENTE VALIDACIÓN |
| UX-CATALOGO-004 | S2 | Media | Modal de edición se corta 1366×768 | D | DESCARTE (refactor modal) |
| UX-CATALOGO-005 | S2 | Media | Cada cambio requiere "Guardar" individual | B | PENDIENTE VALIDACIÓN |
| UX-JERARQUIA-005 | S2 | Alta | Tabs sin contador (ej. "Usuarios · 3") | — | **REMEDIAR** · Grupo 2 |
| UX-JERARQUIA-006 | S2 | Baja | Forms sin tab-order óptimo | A+D | DESCARTE |
| UX-TICKETS-004 | S2 | Alta | Sin breadcrumb en /admin/tickets/:id | — | **REMEDIAR** · Grupo 2 |
| UX-TICKETS-005 | S2 | Alta | Tabla 8 columnas con scroll horizontal 1366 | D | DESCARTE (refactor tabla) |
| UX-TICKETS-006 | S2 | Alta | "Cancelar en Routal" sin disabled state por rol | — | **REMEDIAR** · Grupo 4 (a11y) |
| UX-TORRE-003 | S2 | Media | Sin auto-refresh visible (¿real-time?) | — | **REMEDIAR** · Grupo 1 (microcopy "última actualización") |
| UX-TORRE-004 | S2 | Alta | "Agente inactivo" sin contacto rápido (botón WA) | D | DESCARTE (feature) |
| UX-TORRE-005 | S2 | Alta | Heatmap externo, no embebido | B | PENDIENTE VALIDACIÓN |
| UX-DASHBOARD-002 | S2 | Media | Sin export CSV directo del dashboard | D | DESCARTE (feature) |
| UX-DASHBOARD-003 | S2 | Media | Tarjetas con bordes inconsistentes vs Panel Agente | B | PENDIENTE VALIDACIÓN |
| UX-DASHBOARD-004 | S2 | Alta | Sin filtro por cliente para multi-subcliente | D | DESCARTE (feature) |
| UX-DASHBOARD-005 | S3 | Baja | Tipografía números muy pequeña 1366 | A | DESCARTE |
| UX-WEBHOOKS-003 | S2 | Baja | Lista de entregas sin filtro por estado | D | DESCARTE (feature) |
| UX-WEBHOOKS-004 | S2 | Alta | "Approve" gris sin tooltip | — | **REMEDIAR** · Grupo 1 (tooltip) |
| UX-WEBHOOKS-005 | S2 | Media | Logs timestamps absolutos, no relativos | — | **REMEDIAR** · Grupo 6 (formatFechaMX.fechaRelativa) |
| UX-AI-003 | S2 | Media | Benchmark sin "ejecutado hace X" relativo | — | **REMEDIAR** · Grupo 6 (formatFechaMX.fechaRelativa) |
| UX-PLATFORM-002 | S2 | Baja | Tabla sin filtro | D | DESCARTE (feature) |
| UX-PLATFORM-003 | S2 | Baja | Whitelist usa modal anidado, no slide-over | B+D | DESCARTE (refactor) |
| UX-LOGIN-001 | S2 | Media | Sin "Olvidé mi contraseña" visible | D | DESCARTE (feature backend nueva) |
| UX-LOGIN-002 | S3 | Baja | Password sin toggle de visibilidad | A | DESCARTE |
| UX-DEFAULT-001 | S2 | Baja | Default genérica sin CTAs claros | D | DESCARTE (refactor) |
| UX-MAINTENANCE-001 | S3 | Baja | Sin ETA estimada | A | DESCARTE |
| UX-ONBOARDING-002 | S2 | Media | Sin "no mostrar más" persistente per-tour | — | **REMEDIAR** · Grupo 2 (sessionStorage→localStorage) |
| UX-NOTIF-002 | S2 | Alta | Templates sin preview en vivo | D | DESCARTE (feature) |
| UX-INGEST-001 | S2 | Media | Sin healthcheck visible del último pull por carrier | D | DESCARTE (feature) |
| **LATAM v1** | | | | | |
| UX-LATAM-004 | S2 | Media | Fechas relativas en inglés "2 minutes ago" | — | **REMEDIAR** · Grupo 6 |
| UX-LATAM-008 | S2 | Media | Falta validación RFC clientes corporativos | — | **REMEDIAR** · Grupo 6 (MxInput type="rfc" ya existe) |
| UX-LATAM-009 | S2 | Alta | Anglicismo "tracking" en UI | — | **REMEDIAR** · Grupo 3 |
| UX-LATAM-010 | S2 | Media | users.name único (no apellido pat/mat) | C | DESCARTE (schema change) |
| UX-LATAM-011 | S3 | Baja | Acentos recortados por text-[10px] | A | DESCARTE |
| UX-LATAM-013 | S2 | Media | Zona horaria banners no etiquetada CDMX | — | **REMEDIAR** · Grupo 1 (microcopy "(CDMX)") |
| UX-LATAM-015 | S2 | Media | AdminAI mezcla toLocaleString + ISO | E | DESCARTE (cerrado en Bundle D Parte 3) |
| UX-LATAM-016 | S2 | Media | Mezcla "tú"/"usted" entre componentes | B+C | PENDIENTE VALIDACIÓN |
| UX-LATAM-017 | S3 | Baja | Horario laboral tenant no configurable | A | DESCARTE (parcialmente cubierto Bundle E paso 2) |
| UX-LATAM-018 | S3 | Baja | Falta validación CURP persona física | A | DESCARTE |

---

## Resumen del triaje

| Categoría | Cantidad |
|---|---|
| Total inicial | 43 |
| Descartados por filtro A (baja confianza, sin quejas) | 6 |
| Descartados por filtro B (subjetivo sin validación) | 0 (los muevo todos a `pending/validation_required.md`) |
| Descartados por filtro C (familiaridad / cambio costoso) | 1 |
| Descartados por filtro D (costo alto / beneficio bajo) | 13 |
| Descartados por filtro E (ya cerrado por Bundle A-E) | 1 |
| Pendientes de validación con usuario real | 7 |
| **A remediar en Bundle F** | **15** |

**N = 15** — dentro del rango óptimo 10-20. Procedo a Fase 2.

---

## Hallazgos a remediar (N=15)

### Grupo 1 — Microcopy / tooltips (4)
- **UX-WEBHOOKS-004** · Agregar tooltip explicativo al botón "Approve" gris en `/admin/webhooks`
- **UX-LATAM-013** · Etiquetar zona horaria como "(CDMX)" en banners con timestamps absolutos
- **UX-TORRE-003** · Agregar etiqueta "Última actualización: hace Xs" en /torre para hacer visible el polling
- **UX-LATAM-009** · Reemplazar "tracking" por "rastreo" en labels visibles de UI

### Grupo 2 — Visual polish (3)
- **UX-JERARQUIA-005** · Contadores en tabs ("Proyectos · 4", "Clientes · 2", etc.)
- **UX-TICKETS-004** · Insertar `SaaSHierarchyBreadcrumb` o breadcrumb propio en `/admin/tickets/:id`
- **UX-AGENTE-007** · Indicador "Guardando…" / "Guardado ✓" en el composer de Reclamos/Agent

### Grupo 3 — Consistencia terminológica (2)
- **UX-AGENTE-003** · Definir "caso" como término canónico en UI hacia agente/cliente. APIs y BD mantienen `ticket` (compatibilidad).
- **UX-LATAM-009** · (también aquí) Reemplazo "tracking" → "rastreo" como parte del glosario.

### Grupo 4 — Accesibilidad menor (1)
- **UX-TICKETS-006** · El botón "Cancelar en Routal" debe tener `disabled` + tooltip cuando el rol del user no permite la acción (visual gating, RBAC ya bloquea en backend).

### Grupo 5 — Migración CrudPanel
**0 hallazgos.** Bundle C ya cubrió todos los consumidores con hallazgo específico.

### Grupo 6 — Formatos LATAM restantes (5)
- **UX-RECLAMOS-004** · Reemplazar fechas mm/dd legacy en Reclamos por `fechaCompacta()`
- **UX-WEBHOOKS-005** · Timestamps absolutos en logs → `fechaRelativa()`
- **UX-AI-003** · Benchmark "ejecutado hace X" relativo → `fechaRelativa()`
- **UX-LATAM-004** · Auditar fechas relativas en inglés ("X minutes ago") → `fechaRelativa()` (es-MX)
- **UX-LATAM-008** · Aplicar `MxInput type="rfc"` en formulario de Cliente (AdminHierarchy → CarrierConfigDialog/ClientsPanel)

### Grupo 6.bis — Glosario canónico (transversal)
- Crear `/docs/terminology_canonical.md` con la tabla: caso ← ticket, rastreo ← tracking, etc. Aplicar reemplazo en UI manteniendo APIs estables.

---

## Decisiones del triaje (notas operativas)

1. **No incluyo migración CrudPanel** porque Bundle C ya cubrió a todos los consumidores con hallazgo específico (auditado en `audits/CrudPanel_consumers.md`).
2. **Anglicismo "tracking"** aparece en 2 grupos (1 microcopy y 3 terminología) — lo trato como UN solo cambio en commit "terminología".
3. **15 hallazgos efectivos**, en el rango óptimo 10-20.
4. **POL-01 a aplicar** — política editorial nueva, no regla. Va a PRD.md sección "Políticas operativas".
