# CrudPanel — Inventario de consumidores

> Bundle C · Parte 1 (Inventario obligatorio antes del refactor).
> Fecha: Mayo 2026.
> Stack adaptado: el prompt original asume Vue 3 + DataTables. En MyExcellence
> usamos **React 18** y `CrudPanel` es un componente local a `AdminHierarchy.jsx`
> (no compartido entre múltiples archivos). Esto reduce significativamente el
> blast-radius del refactor.

## Ubicación canónica

- `CrudPanel` está definido en `/app/frontend/src/pages/AdminHierarchy.jsx`
  (línea 123). NO está exportado.
- NO existe `/app/frontend/src/components/CrudPanel.jsx`.
- Confirmado con: `grep -rn "CrudPanel" /app/frontend/src` (5 referencias,
  todas en el mismo archivo).

## Consumidores actuales

| # | Consumidor (sub-panel)                | Línea | Endpoint                  | ¿Necesita refresh externo? | Notas |
|---|----------------------------------------|-------|----------------------------|----------------------------|-------|
| 1 | `ClientsPanel` (clientes)              | ~367  | `/admin/clients`           | **SÍ** — el modal `CarrierConfigDialog` se monta dentro de la columna "Integraciones" y al guardar carrier modifica `client.carriers[code]`. Hoy NO refresca (workaround documentado L488). | UX-JERARQUIA-002 ↩ |
| 2 | `SubclientsPanel` (subclientes)        | ~509  | `/admin/subclients`        | **SÍ (parcial)** — depende del listado de `clients` que carga al montar. Si el admin crea un cliente en otra pestaña/tab, los subclientes muestran nombres obsoletos. | Caso menor |
| 3 | `ProjectsPanel` (proyectos)            | ~620  | `/admin/projects`          | **NO** crítico — CRUD interno típico, sin modales externos que modifiquen. | Backlog |
| 4 | `UsersPanel` (usuarios)                | ~894  | `/admin/users`             | **NO** crítico — CRUD interno típico. Cambios de rol/status se hacen desde el mismo panel. | Backlog |

`CarriersPanel` (línea ~536) **NO usa CrudPanel** — implementa su propia tabla
+ modal por requisitos especiales. Se queda fuera del scope de este refactor.

## Decisión de migración

- ✅ **Migrar AHORA**: `ClientsPanel` (cierra UX-JERARQUIA-002 S1).
- 🟡 **Migrar AHORA (oportunidad)**: `SubclientsPanel` con suscripción a
  `admin.client.created/updated` para mantener lista de clientes fresca.
- ⏸️ **Diferir a Bundle F**: `ProjectsPanel` y `UsersPanel` — no hay caso
  reportado de "datos obsoletos por fuente externa".

## Backward compatibility

- La nueva API es **aditiva**: prop opcional `refreshSignal`, método imperativo
  `ref.current.refresh()`, callback opcional `onRefreshCompleted`. Los 4
  consumidores actuales siguen funcionando idéntico si NO se les pasa la prop.
- Tests existentes de admin/jerarquia (`test_iter22_routal_multiproject.py`,
  `test_iter25_platform_carriers.py`) NO se modifican.

## Eventos del bus introducidos por este Bundle

Solo aquellos que necesitamos hoy. El catálogo completo se documenta en
`/app/frontend/src/admin/eventCatalog.js` y se extiende ad-hoc por Bundles
futuros (siempre vía constantes, nunca strings literales).

- `admin.carrier.updated` — payload `{ client_id: string, carrier_code: string }`.
  Emitido por `CarrierConfigDialog.onSaved`.
- `admin.client.created` — payload `{ client_id: string }`.
  Emitido por `ClientsPanel` tras crear cliente (futuro consumidor: `SubclientsPanel`).
- `admin.client.updated` — payload `{ client_id: string }`.

## Restricciones aplicadas

- **Sin nuevas deps** (sigue regla de stack mínimo).
- **No migración a TypeScript** (el archivo está en JS).
- **No migración a stores globales** (Pinia/Redux) — bus local al módulo admin.
- **No cross-tab refresh** (BroadcastChannel/WebSocket fuera de alcance).
  Mensaje al usuario: "Los cambios entre pestañas distintas del navegador
  requieren recarga manual."
