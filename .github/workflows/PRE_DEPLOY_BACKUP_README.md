# Pre-Deploy Backup — Guía rápida

> Workflow `pre-deploy-backup.yml` para generar un snapshot completo de la DB
> de producción antes de cualquier deploy. Backup persistido como artefacto
> de GitHub con 90 días de retención.

## Setup (una sola vez)

1. **Push del repo a GitHub** (botón "Save to GitHub" en el chat de Emergent)
2. **Configurar secrets** en GitHub: Settings → Secrets and variables → Actions:
   - `PROD_MONGO_URL` — URI mongodb://… o mongodb+srv://… de producción
   - `PROD_DB_NAME` — Nombre de la DB (ej: `lastmile_db`)

## Cómo correr el backup

1. Ve a tu repo en GitHub → pestaña **Actions**
2. Selecciona el workflow **"Pre-Deploy Backup (Production)"**
3. Click **"Run workflow"**
4. Inputs:
   - **Razón** (requerido): describe el motivo. Ej: `pre-deploy iter77-87`
   - **Colecciones** (opcional): CSV de colecciones específicas. Vacío = TODAS
5. Click **"Run workflow"** verde
6. Espera ~1-3 min (depende del tamaño de la DB)

## Qué obtienes

- ✅ Artefacto **`prod-backup-YYYYMMDD_HHMMSS`** descargable desde el workflow run
- ✅ Archivo **`BACKUP_INFO.txt`** con metadata: timestamp, razón, conteos por colección
- ✅ Summary en GitHub UI con instrucciones de restore listas para copy-paste
- ✅ Retención: **90 días** automática

## Restaurar desde un backup

```bash
# 1. Descarga el .zip del artefacto desde Actions → run específico → Artifacts
unzip prod-backup-YYYYMMDD_HHMMSS.zip -d ./backup

# 2. Restaura completo (--drop reemplaza colecciones existentes)
mongorestore --uri="$MONGO_URL" --drop ./backup/$DB_NAME

# 3. O solo una colección específica
mongorestore --uri="$MONGO_URL" --drop \
  --nsInclude="$DB_NAME.journeys" \
  ./backup/$DB_NAME
```

## Recomendaciones de uso

- **Antes de cualquier deploy**: corre este workflow con `Razón = "pre-deploy <iter#>"`
- **Después de migrar datos**: corre con `Razón = "post-migración iter79"` para tener un punto de retorno
- **Ad-hoc**: cualquier momento que quieras un snapshot (auditoría, debug, etc.)

## Diferencia vs `reverse-iter79.yml`

| Workflow | Propósito | Modifica DB |
|---|---|---|
| `pre-deploy-backup.yml` | **Snapshot completo** de toda la DB | ❌ Read-only |
| `reverse-iter79.yml` | Backup parcial (3 colecciones) + reverso de migración iter79 | ⚠️ Sí, si `apply=true` |

Usa **`pre-deploy-backup.yml`** para protección genérica antes de deploys.
Usa **`reverse-iter79.yml`** solo si necesitas reversar específicamente iter79.

## Archivos relacionados

- `.github/workflows/pre-deploy-backup.yml` — el workflow
- `.github/workflows/reverse-iter79.yml` — workflow de reverso (compañero)
- `memory/recovery_scripts/00_BACKUP_OBLIGATORIO.sh` — versión local (sin GitHub)
