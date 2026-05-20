# Terminología canónica · MyExcellence

**Política:** POL-01 (criterio editorial · Bundle F).

UI hacia agente/cliente usa términos en **español MX**. Los modelos, endpoints,
colecciones MongoDB y APIs mantienen sus nombres técnicos para no romper
compatibilidad con consumidores externos (CAE, webhooks, scripts).

## Conceptos principales

| Término canónico (UI) | Variantes a eliminar en UI | Contexto técnico (NO tocar) | Estado |
|---|---|---|---|
| **caso** | `ticket`, `incidencia`, `folio` | endpoint `/api/tickets`, modelo `Ticket`, col `tickets` | **Aplicar** |
| **rastreo** | `tracking`, `tracking number`, `track` | endpoint `/api/tracking`, campo `tracking_id` | **Aplicar** |
| **guía** | `shipment`, `envío` (cuando es paquete) | modelo `Shipment`, col `shipments` | Existente, mantener |
| **destinatario** | `recipient`, `consignee` | campo `recipient_*` | Existente, mantener |
| **carrier** | "transportista", "carrier" (en UI técnica) | modelo `Carrier` | Híbrido OK (técnico es global) |
| **catálogo** | `catalog` | endpoint `/api/admin/catalog` | Existente |
| **motivo** | `motive`, `reason` (en UI técnica) | modelo `Motivo` | Existente |
| **solución** | `solution` | modelo `Solucion` | Existente |
| **reclamo** | `claim` | endpoint `/api/claims` | Existente |
| **conciliación** | `settlement`, `reconciliation` | campo `conciliado_*` | Existente |
| **tenant** | "organización", "cuenta" | modelo `Tenant` | Mantener "tenant" (público, MX entiende SaaS) |
| **cliente** | `account` | modelo `Client` | Existente |
| **subcliente** | `sub-account` | modelo `Subclient` | Existente |

## Notas operativas

- **APIs, endpoints, modelos y colecciones MongoDB**: nombres técnicos estables. Los consumidores externos (webhooks, scripts) y la documentación interna mantienen el lenguaje del schema.
- **UI visible al usuario operativo** (agente, supervisor, admin operativo): español MX según tabla.
- **Microcopy de errores backend**: ya están en español por el envelope `fail()` — no requiere migración.
- **Botones, labels, tooltips, badges, headers de tabla**: aplican el glosario.
- **No cambiar**: nombres de routes (`/admin/tickets`, `/agente`) ni `data-testid` existentes.

## Ámbito Bundle F (Iter34)

Se aplican los reemplazos `ticket` → `caso` y `tracking` → `rastreo` SOLO en strings de UI visible al usuario operativo (es decir labels, titles, placeholders, headings). El resto del glosario ya estaba consolidado o se mantiene.
