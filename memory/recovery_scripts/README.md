# Recovery scripts — Reverso iter79 (Escenario 1)

> **Contexto:** Tras el rollback de código a Deployment 48, la DB de producción
> aún tiene los cambios de iter79 (journeys nuevas + journeys legacy desmarcadas
> con `migrated_to_journeys[]`). Este set de scripts revierte la DB al modelo
> original "1 plan = 1 journey", manteniendo todas las incidencias.

## Orden de ejecución (estricto)

### 0️⃣ Backup (obligatorio, sin esto no continúes)

```bash
chmod +x 00_BACKUP_OBLIGATORIO.sh
./00_BACKUP_OBLIGATORIO.sh
```

Esto genera un backup de las colecciones `journeys`, `packages` e `incidents`
en `/tmp/lastmile_pre_reverse_iter79_<TIMESTAMP>/`. **Guárdalo en un sitio seguro**
(p. ej. S3 / drive personal). Si algo sale mal:

```bash
mongorestore --uri="$MONGO_URL" --drop /tmp/lastmile_pre_reverse_iter79_<TS>/lastmile_db
```

### 1️⃣ Dry-run (lectura exclusiva, no modifica nada)

```bash
mongosh "$MONGO_URL/$DB_NAME" --file 01_DRY_RUN_DIAGNOSTICO.js
```

Revisa los counts en la salida. Validar:

- ✅ "Sample mapping consistente" — sin mismatches.
- ✅ Los packages a reasignar coinciden con lo que esperas.
- ✅ Los incidents en NUEVAS deberían ser 0 o mínimo (porque iter79 no los movió correctamente).

### 2️⃣ Apply (escritura real)

```bash
mongosh "$MONGO_URL/$DB_NAME" --file 02_APPLY_REVERSE.js
```

El script:

1. Mueve `packages.journey_id`: nueva → legacy (vía `journey.migrated_from`).
2. Mueve `incidents.journey_id`: nueva → legacy.
3. Borra journeys creadas por iter79 (`migrated_from` set).
4. Limpia campos de migración en legacy (`migrated_to_journeys[]`, etc.).
5. Recalcula `packages_total / _delivered / _failed` en cada legacy.

Idempotente: si ya se corrió, los pasos repetidos quedan en 0.

### 3️⃣ Validación visual

Tras el apply:

1. `/rutas` debe mostrar el modelo 1-plan-1-journey original.
2. Cada ruta legacy debe tener sus packages e incidencias visibles.
3. **No debe haber rutas con 0 paquetes y N incidencias** (síntoma original).

## Si algo falla

Restaurar desde backup:

```bash
mongorestore --uri="$MONGO_URL" --drop /tmp/lastmile_pre_reverse_iter79_<TS>/lastmile_db
```

## Limpieza opcional (días después)

Si todo funciona bien por al menos 48h, puedes limpiar marcadores residuales:

```javascript
// Conectado al mongosh
db.journeys.updateMany({}, { $unset: { _reverse_iter79_at: "" } });
db.packages.updateMany({}, { $unset: { _reversed_from: "", _reversed_at: "" } });
db.incidents.updateMany({}, { $unset: { _reversed_from: "", _reversed_at: "" } });
```

## Archivos

- `00_BACKUP_OBLIGATORIO.sh` — Genera backup vía mongodump.
- `01_DRY_RUN_DIAGNOSTICO.js` — Lectura exclusiva, muestra plan.
- `02_APPLY_REVERSE.js` — Escrituras reales con validación post.
