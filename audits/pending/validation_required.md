# Hallazgos pendientes de validación con usuario real

**Origen:** Bundle F triaje (Filtros B y C de POL-01)
**Validan:** Sandra Pérez (admin) y Ana Rivera (agente) — sesiones de 30 min

Estos hallazgos NO se remedian en Bundle F porque su cambio puede romper familiaridad
acumulada o requiere confirmación de usuario real antes de actuar.

| ID | Eje | Sev | Hallazgo | Necesita validar | Pregunta específica | Acción posterior |
|---|---|---|---|---|---|---|
| UX-AGENTE-006 | Panel Agente | S2 | `text-[10px]` + `font-mono` en metadatos críticos | Ana | "¿La tipografía actual de metadatos te dificulta lectura o te resulta cómoda por la densidad?" | Si dice "cambiar" → bundle dedicado de typography pass. Si dice "mantener" → cerrar como "decisión del usuario". |
| UX-CATALOGO-003 | Admin Catálogo | S2 | Iconografía decorativa en algunas filas | Sandra | "¿Estos iconos te confunden o son útiles para identificar tipos de motivos?" | Si "cambiar" → bundle de icon refresh. Si "mantener" → cerrar. |
| UX-CATALOGO-005 | Admin Catálogo | S2 | Cada cambio requiere "Guardar" individual (no bulk save) | Sandra | "¿Preferirías editar varios motivos y guardar todos juntos al final, o el guardado individual te da más seguridad?" | Si "bulk" → bundle bulk-edit. Si "individual" → cerrar. |
| UX-DASHBOARD-003 | Dashboard | S2 | Tarjetas con bordes inconsistentes vs Panel Agente | Jair/PO | Decisión de design system: ¿unificar bordes con Panel Agente o mantener variación intencional? | PR opcional si Jair decide unificar. |
| UX-TORRE-005 | Torre de Control | S2 | Heatmap externo, no embebido | Supervisor real | "¿Preferirías ver el heatmap embebido en /torre o el link a /heatmap te funciona?" | Si "embeber" → bundle dedicado UI. Si "link" → cerrar. |
| UX-LATAM-016 | Sub-eje 8.8 | S2 | Mezcla "tú" y "usted" entre componentes | Sandra/Ana | "¿Te molesta que algunos textos usen 'tú' y otros 'usted'?" | Si "sí" → bundle de tono unificado. Si "no le di importancia" → cerrar. |
| UX-LATAM-017 | Sub-eje 8.6 | S3 | Horario laboral tenant no configurable visible | Sandra | "¿Necesitás controlar el horario laboral desde UI, o el default 9-18 te alcanza?" | Si "necesito" → endpoint nuevo + UI. Si "alcanza" → cerrar. (Parcialmente cubierto por Bundle E paso 2 step_data.) |

**Total: 7 hallazgos pendientes de validación.**

Una vez validados, cada hallazgo se cierra (descarta) o se convierte en bundle dedicado con scope específico. Bundle F **NO ejecuta** la validación — solo documenta los hallazgos que la requieren.
