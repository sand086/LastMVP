# Changelog: Deployment 48 → 50

> **Propósito:** Documentar exhaustivamente los cambios entre los deployments 48-50 para reimplementarlos de forma segura tras el rollback, garantizando el resguardo de las incidencias asociadas a journeys Routal.

> **Lecciones aprendidas:** El bug crítico de pérdida visual de incidencias se debió a (a) usar `package_id` cuando el schema de `incidents` usa `tracking_number`, y (b) un filtro global `migrated_to_journeys: {$exists: false}` que oculta journeys legacy donde quedaron las incidencias huérfanas. Cualquier reimplementación debe incluir el fix antes de aplicar la migración.

---

## ⚠️ ANTES DE REIMPLEMENTAR — CHECKLIST DE RESGUARDO

Antes de correr **cualquier** parte de iter79, ejecuta estos pasos:

### 1. Backup de la colección `incidents` y `journeys`
```bash
# Conectado al pod o al cliente Mongo de producción
mongodump --uri="$MONGO_URL" --db="$DB_NAME" \
  --collection=incidents \
  --out=/backup/pre_iter79_$(date +%Y%m%d_%H%M)/

mongodump --uri="$MONGO_URL" --db="$DB_NAME" \
  --collection=journeys \
  --out=/backup/pre_iter79_$(date +%Y%m%d_%H%M)/

# Verificar
mongorestore --dryRun --uri="$MONGO_URL" \
  /backup/pre_iter79_$(date +%Y%m%d_%H%M)/
```

### 2. Validar el schema de `incidents`
**CRÍTICO:** Verifica si el campo se llama `tracking_number` o `package_id`. La migración debe usar la clave correcta.

```bash
# Conectado a la DB
db.incidents.findOne({}, {_id:0})
# Debe mostrar: tracking_number, journey_id, incident_type, severity, ...
# NO debe haber package_id en este schema (LastMile no lo guarda)
```

### 3. Conteo previo (snapshot)
```javascript
db.incidents.countDocuments({})         // Total
db.incidents.countDocuments({journey_id: {$ne: null}})  // Con journey
// Guarda estos números para validar post-migración
```

---

## Cambios incluidos por iteración

### iter77 — UI Desglose por sucursal en "Resumen de hoy" (P2, sin riesgo)
**Backend:** `routes/selection_routes.py`
- `GET /api/selection/summary/{client_id}` agrega `branch_breakdown: {CDMX: {total, selected, branch_id, name}, GDL: {...}}` desde `driver_audit_log` filtrado por fecha.
- Lookup adicional a `db.branches` para resolver código humano.

**Frontend:** `components/settings/SettingsAuditTab.jsx`
- Nueva sección "Desglose por sucursal" debajo de los 4 KPIs.
- Date picker integrado al header del resumen para navegar fechas históricas.
- Chips coloreados (verde ≥50%, azul >0, gris 0%) formato `QRO · 1/1`.

**Archivos modificados:**
- `backend/routes/selection_routes.py` — agregar agregación `branch_breakdown` en summary endpoint
- `frontend/src/components/settings/SettingsAuditTab.jsx` — sección visual + estado `summaryDate`

**Riesgo de reimplementación:** Bajo. Sólo lectura.

---

### iter78 — Sparkline tendencia 14 días por sucursal (P3, sin riesgo)
**Backend:** `routes/selection_routes.py`
- Nuevo endpoint `GET /api/selection/branch-history/{client_id}?days=14` (1-90, RBAC dev/coord/exec).
- Aggregation de `driver_audit_log` por (date, branch_id) con `$group`.
- Lookup adicional a `branches` para resolver códigos.
- Retorna `branches:[{code, branch_id, name, points:[{date, total, selected}], total_sum, selected_sum}]` con días materializados (incluso ceros).

**Frontend:** `components/settings/SettingsAuditTab.jsx`
- Componente inline `BranchSparkline` SVG 88×22 sin dependencias.
- Sección "Tendencia · últimos 14 días" debajo del desglose.

**API helper:** `lib/api.js`
```js
export const getBranchHistory = (clientId, days = 14) =>
    api.get(`/selection/branch-history/${clientId}?days=${days}`);
```

**Riesgo de reimplementación:** Bajo. Sólo lectura.

---

### iter79 — REFACTOR Routal model: route→journey ⚠️ **CONTIENE EL BUG**

**Bug de origen:** `_handle_plan_created_direct` en `workers/routal_event_processor.py` interpretaba 1 plan Routal como 1 journey LastMile, ignorando que `plan.routes[]` tiene N rutas con sus drivers reales.

#### Cambios funcionales (re-aplicar, son correctos):

**Schema:**
- `journeys`: agregar `routal_route_id` (índice compuesto con `client_id`, sparse).
- `packages`: agregar `routal_route_id`.

```javascript
db.journeys.createIndex(
    { client_id: 1, routal_route_id: 1 },
    { background: true, sparse: true, name: "client_routal_route_idx" }
)
```

**Helpers nuevos (`workers/routal_event_processor.py`):**
- `_normalize_routes_from_payload(payload)` — itera `plan.routes[]` y filtra stops por `route_id`.
- `_is_scanner_placeholder(label)` — detecta "LastmileScanSessions*" para skip.

**Comportamiento:**
- 1 route real = 1 journey (NO 1 plan = 1 journey).
- Routes vacías en planes multi-route → skip.
- Placeholder routes ("LastmileScanSessions*") → skip.
- Idempotente por `(client_id, routal_route_id)`.

**Backfill (`routes/selection_routes.py`):** filtrar stops por `route.id == stop.route_id` al stagear.

#### ⚠️ FIXES OBLIGATORIOS antes de aplicar la migración:

**FIX 1 — Schema correcto de incidents (CRÍTICO)**

En `routes/routal_migration_routes.py` (función `migrate_legacy_journeys`), el bug original era:
```python
# ❌ MAL — incidents NO tienen package_id
await db.incidents.update_many(
    {"package_id": {"$in": pkg_ids}, "journey_id": legacy_id},
    {"$set": {"journey_id": doc["id"]}},
)
```

Debe ser:
```python
# ✅ BIEN — usar tracking_number
tracking_nums = [p.get("tracking_number") for p in pkgs if p.get("tracking_number")]
if tracking_nums:
    await db.incidents.update_many(
        {
            "tracking_number": {"$in": tracking_nums},
            "journey_id": legacy_id,
        },
        {"$set": {"journey_id": doc["id"]}},
    )
```

**FIX 2 — Validar antes de aplicar**

Antes de `dry_run=false`, ejecuta:
```python
# Pseudo-script de validación
async def validate_incident_migration(client_id, dry_run_response):
    """Asegurar que cada legacy con incidents tenga packages que cubran los tracking_numbers."""
    for detail in dry_run_response['details']:
        legacy_id = detail['legacy_journey_id']
        # Get incidents on this legacy
        incs = await db.incidents.count_documents({"journey_id": legacy_id})
        if incs == 0:
            continue
        # Get tracking_numbers on this legacy's incidents
        tns = set()
        async for inc in db.incidents.find({"journey_id": legacy_id}, {"tracking_number": 1}):
            if inc.get("tracking_number"):
                tns.add(inc["tracking_number"])
        # Get packages of new journeys
        new_pkgs_tn = set()
        async for p in db.packages.find(
            {"journey_id": {"$in": detail['new_journeys']}},
            {"tracking_number": 1}
        ):
            if p.get("tracking_number"):
                new_pkgs_tn.add(p["tracking_number"])
        missing = tns - new_pkgs_tn
        if missing:
            print(f"⚠ Legacy {legacy_id}: {len(missing)} incident tracking_numbers NOT in new packages")
            print(f"   Sample missing: {list(missing)[:5]}")
```

**FIX 3 — Filtro global con whitelist**

En lugar de:
```python
# ❌ Esto oculta legacy y por ende sus incidencias huérfanas
query["migrated_to_journeys"] = {"$exists": False}
```

Considerar:
```python
# ✅ Más seguro: sólo ocultar si TODAS las incidencias se movieron exitosamente
query["$or"] = [
    {"migrated_to_journeys": {"$exists": False}},
    {"_orphan_incidents_count": {"$gt": 0}},  # mantener visible si hay huérfanas
]
```

O alternativamente, **NO filtrar las legacy inicialmente** y agregar filtro sólo después de validar que `restore_orphan_incidents` corrió OK.

**Endpoints añadidos:**
- `POST /api/integrations/routal/migrate-legacy-journeys/{client_id}?days_back=30&dry_run=true&branch_id=...` — RBAC dev/coord
- `POST /api/integrations/routal/restore-orphan-incidents/{client_id}?dry_run=true&branch_id=...` — RBAC dev/coord (introducido en iter82, integrar desde el inicio)

**Filtros globales agregados (revisar antes de re-aplicar):**
- `routes/journey_routes.py` — `GET /api/journeys` línea ~37
- `routes/dashboard_routes.py` — `/dashboard/stats`, heatmap, provider-comparison
- `routes/analytics_routes.py` — `/reports/journeys`, `/reports/packages`, `/reports/incidents`, `/reports/generate`, `/reports/generate-excel`, `/export/journeys`

**Archivos modificados (re-aplicar TODOS, con FIX 1):**
- `backend/workers/routal_event_processor.py` — refactor `_handle_plan_created_direct` y `_handle_plan_created`
- `backend/routes/selection_routes.py` — backfill filtra stops por route_id
- `backend/routes/routal_migration_routes.py` — **archivo nuevo, USAR VERSIÓN CON FIX 1**
- `backend/routes/journey_routes.py` — filtro global
- `backend/routes/dashboard_routes.py` — filtro global (3 lugares)
- `backend/server.py` — `include_router(routal_migration_router)` + índice nuevo

---

### iter80 — UI "Migrar legacy" en Settings → Integraciones (P2)
**Frontend:** `components/settings/ClientIntegrationCard.jsx`
- Botón "Migrar legacy" amber visible sólo en cards Routal.
- Panel expandible con explicación + input días + Detectar (dry-run) / Aplicar.
- Tabla con plan/legacy/routes/drivers + package counts.
- `window.confirm` antes de aplicar.

**API helper:** `lib/api.js`
```js
export const migrateRoutalLegacyJourneys = (clientId, daysBack, dryRun, branchId) => {
    const params = new URLSearchParams({ days_back: String(daysBack), dry_run: String(dryRun) });
    if (branchId) params.append('branch_id', branchId);
    return api.post(
        `/integrations/routal/migrate-legacy-journeys/${clientId}?${params.toString()}`,
        null, { timeout: 120000 },
    );
};
```

**Backend idempotency:**
```python
# routal_migration_routes.py — query
query = {
    "client_id": client_id,
    "source": "routal",
    "routal_plan_id": {"$exists": True, "$ne": None},
    "routal_route_id": {"$exists": False},
    "migrated_to_journeys": {"$exists": False},  # excluir ya migradas
    "created_at": {"$gte": cutoff.isoformat()},
}
```

**Riesgo de reimplementación:** Medio. Hereda el bug de iter79 si no aplicas FIX 1.

---

### iter81 — Reports filters: multi-select + branch + date range (P1, sin riesgo)
**Backend:** `routes/analytics_routes.py`
```python
def _csv_to_list(val):
    if not val: return []
    if isinstance(val, list):
        out = []
        for v in val:
            out.extend([x.strip() for x in str(v).split(",") if x.strip()])
        return out
    return [x.strip() for x in str(val).split(",") if x.strip()]

def _apply_id_filter(query, field, raw_val):
    ids = _csv_to_list(raw_val)
    if not ids: return query
    if len(ids) == 1: query[field] = ids[0]
    else: query[field] = {"$in": ids}
    return query
```

Aplicar a estos endpoints (acepta CSV en `client_id`, `provider_id`, `branch_id`):
- `POST /reports/generate`
- `POST /reports/generate-excel`
- `GET /reports/quality`
- `POST /reports/quality-export`
- `GET /reports/journeys`
- `GET /reports/packages`
- `GET /reports/incidents`
- `GET /export/journeys`

**Pydantic:** `models.py` — `ReportRequest` agrega `branch_id: Optional[str] = None`.

**Frontend:**
- Nuevo `components/reports/MultiSelectChip.jsx` (search box + checkboxes verdes + X clear)
- Nuevo `components/reports/DateRangePicker.jsx` (1 popover, 2 meses, locale es)
- `pages/Reports.jsx` refactor: `clientId/providerId` (string) → `clientIds/providerIds` (arrays); nuevo `branchIds`. Helper `csvOrUndef()` para enviar CSV.

**Riesgo de reimplementación:** Bajo. No toca data, sólo queries.

---

### iter82 — Restaurar incidencias huérfanas (P0, **DEBE INCLUIRSE EN iter79 desde el día 1**)

**Backend:** `routes/routal_migration_routes.py`

```python
@router.post("/integrations/routal/restore-orphan-incidents/{client_id}")
async def restore_orphan_incidents(
    client_id: str,
    dry_run: bool = Query(True),
    branch_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Restaura incidencias huérfanas tras la migración legacy iter79.

    Estrategia:
      1. Encontrar journeys legacy migradas (`migrated_to_journeys[]` set)
      2. Por cada incidencia apuntando a una de esas legacy:
         a) Buscar package con ese tracking_number en alguna de las journeys nuevas
         b) Si encuentra → mover incidencia a esa nueva journey
         c) Si no → fallback a la primera nueva journey del split
    """
    if user.get("role") not in {"developer", "coordinator"}:
        raise HTTPException(status_code=403, detail="Solo developer/coordinator")

    legacy_query = {
        "client_id": client_id,
        "migrated_to_journeys": {"$exists": True, "$ne": []},
    }
    if branch_id:
        legacy_query["branch_id"] = branch_id

    legacy_journeys = [
        j async for j in db.journeys.find(
            legacy_query,
            {"_id": 0, "id": 1, "migrated_to_journeys": 1},
        )
    ]
    if not legacy_journeys:
        return {"orphan_incidents_found": 0, ...}

    legacy_ids = [j["id"] for j in legacy_journeys]
    legacy_to_new_map = {j["id"]: j.get("migrated_to_journeys", []) for j in legacy_journeys}

    orphan_incidents = [
        inc async for inc in db.incidents.find(
            {"journey_id": {"$in": legacy_ids}},
            {"_id": 0, "id": 1, "journey_id": 1, "tracking_number": 1},
        )
    ]

    restored_by_tracking = 0
    restored_by_fallback = 0
    bulk_updates = []

    for inc in orphan_incidents:
        legacy_id = inc["journey_id"]
        new_journeys_for_this_legacy = legacy_to_new_map.get(legacy_id, [])
        if not new_journeys_for_this_legacy:
            continue

        target_journey = None
        tn = inc.get("tracking_number")
        if tn:
            pkg = await db.packages.find_one(
                {"tracking_number": tn, "journey_id": {"$in": new_journeys_for_this_legacy}},
                {"_id": 0, "journey_id": 1},
            )
            if pkg and pkg.get("journey_id"):
                target_journey = pkg["journey_id"]
                restored_by_tracking += 1

        if not target_journey:
            target_journey = new_journeys_for_this_legacy[0]
            restored_by_fallback += 1

        bulk_updates.append((inc["id"], target_journey))

    if not dry_run and bulk_updates:
        for inc_id, new_jid in bulk_updates:
            await db.incidents.update_one(
                {"id": inc_id},
                {"$set": {"journey_id": new_jid, "_restored_at": datetime.now(timezone.utc).isoformat()}},
            )

    return {
        "orphan_incidents_found": len(orphan_incidents),
        "restored_by_tracking": restored_by_tracking,
        "restored_by_fallback": restored_by_fallback,
        ...
    }
```

**Frontend:** `components/settings/ClientIntegrationCard.jsx`
- Sub-panel "Restaurar incidencias huérfanas" debajo del panel "Migrar legacy".
- Botones Detectar / Restaurar con dashboard 3-col (Por tracking · Por fallback · Sin restaurar).

**API helper:** `lib/api.js`
```js
export const restoreOrphanIncidents = (clientId, dryRun = true, branchId = null) => {
    const params = new URLSearchParams({ dry_run: String(dryRun) });
    if (branchId) params.append('branch_id', branchId);
    return api.post(
        `/integrations/routal/restore-orphan-incidents/${clientId}?${params.toString()}`,
        null, { timeout: 60000 },
    );
};
```

---

## 🛡 PLAN DE REIMPLEMENTACIÓN SEGURA

### Orden recomendado tras el rollback:

1. **Backup completo** de `incidents`, `journeys`, `packages` (ver checklist arriba).
2. **Re-aplicar iter77 + iter78** (UI desglose + sparkline) — cero riesgo.
3. **Re-aplicar iter81** (Reports multi-select + date range) — cero riesgo.
4. **Re-aplicar iter79 + iter82 JUNTOS** con FIX 1 incluido:
   - Implementar el refactor de `_handle_plan_created_direct` (route→journey).
   - Implementar `migrate-legacy-journeys` con `tracking_number` correcto.
   - Implementar `restore-orphan-incidents` desde el día 1.
   - **Antes de aplicar la migración**, correr el script de validación (FIX 2).
5. **Aplicar migración en producción** con secuencia obligatoria:
   - `POST /api/integrations/routal/migrate-legacy-journeys/{cid}?dry_run=true` → revisar reporte
   - **Validar**: para cada legacy con incidents, los `tracking_numbers` están en los packages nuevos.
   - `POST /api/integrations/routal/migrate-legacy-journeys/{cid}?dry_run=false` → aplicar
   - **Inmediatamente**: `POST /api/integrations/routal/restore-orphan-incidents/{cid}?dry_run=true` → debe ser 0
   - Si ≠ 0: `POST /api/integrations/routal/restore-orphan-incidents/{cid}?dry_run=false`
   - **Validar conteo final**: `db.incidents.countDocuments()` debe coincidir con el snapshot inicial.
6. **Re-aplicar iter80** (UI Migrar legacy en Settings).

### Validación post-migración

```javascript
// Conectado a la DB
// 1. Ningún incident debe quedar apuntando a journey legacy oculta
const legacy_ids = db.journeys.distinct("id", { migrated_to_journeys: { $exists: true } });
const orphans = db.incidents.countDocuments({ journey_id: { $in: legacy_ids } });
print("Orphan incidents:", orphans);  // DEBE SER 0

// 2. Conteo total no debe haber cambiado
print("Total incidents:", db.incidents.countDocuments({}));  // Comparar con snapshot

// 3. Cada incident debe poder resolver su journey
db.incidents.aggregate([
    { $lookup: { from: "journeys", localField: "journey_id", foreignField: "id", as: "j" } },
    { $match: { j: { $size: 0 } } },
    { $count: "incidents_without_journey" }
]).forEach(printjson);  // DEBE SER vacío
```

---

## 📦 Lista de archivos modificados (referencia exacta)

### Backend
- `backend/server.py` — register `routal_migration_router` + index
- `backend/models.py` — `ReportRequest` con `branch_id`
- `backend/workers/routal_event_processor.py` — refactor route→journey
- `backend/routes/routal_migration_routes.py` — **NUEVO** (con FIX 1)
- `backend/routes/selection_routes.py` — backfill por route_id, summary con `branch_breakdown`, endpoint `branch-history`
- `backend/routes/journey_routes.py` — filtro `migrated_to_journeys`
- `backend/routes/dashboard_routes.py` — filtros `migrated_to_journeys`
- `backend/routes/analytics_routes.py` — helpers CSV + filtros + branch_id

### Frontend
- `frontend/src/lib/api.js` — `getBranchHistory`, `migrateRoutalLegacyJourneys`, `restoreOrphanIncidents`
- `frontend/src/components/settings/SettingsAuditTab.jsx` — branch_breakdown + sparkline + date picker
- `frontend/src/components/settings/ClientIntegrationCard.jsx` — botón Migrar legacy + Restaurar incidencias
- `frontend/src/components/reports/MultiSelectChip.jsx` — **NUEVO**
- `frontend/src/components/reports/DateRangePicker.jsx` — **NUEVO**
- `frontend/src/pages/Reports.jsx` — multi-select + date range

---

## Resumen ejecutivo

| Iter | Riesgo | Acción al reimplementar |
|---|---|---|
| iter77 (desglose UI) | ✅ Cero | Re-aplicar tal cual |
| iter78 (sparkline) | ✅ Cero | Re-aplicar tal cual |
| iter79 (route→journey + migración) | 🔴 Alto | **Re-aplicar con FIX 1 + FIX 2 + iter82 incluido** |
| iter80 (UI migrar legacy) | 🟡 Medio | Re-aplicar después de iter79 |
| iter81 (reports filters) | ✅ Cero | Re-aplicar tal cual |
| iter82 (restore incidents) | ✅ Cero | **Implementar JUNTO con iter79, no después** |

**Regla de oro:** No correr "Aplicar migración" en producción sin haber probado el flujo completo (migrar → restaurar) en preview/staging primero, y sin haber validado que el schema de `incidents` usa `tracking_number` en producción.
