# GitHub Action: Reverse iter79 (Production)

Workflow manual para ejecutar el reverso de iter79 contra la DB de producción
de forma controlada, auditable y reversible.

## Setup (una sola vez)

### 1. Conecta tu repo a GitHub

Si aún no lo hiciste, usa la opción **"Save to GitHub"** en Emergent para
publicar `/app` en un repo de GitHub.

### 2. Configura los secrets en GitHub

Ve a tu repo → **Settings → Secrets and variables → Actions → New repository secret**

| Nombre | Valor |
|---|---|
| `PROD_MONGO_URL` | `mongodb+srv://user:pass@cluster.mongodb.net/...` (tu URI de prod) |
| `PROD_DB_NAME` | `lastmile_db` (o como se llame tu DB) |

⚠️ **Doble verifica que los valores apunten a producción** y NO a preview.

## Uso

### Dry-run (recomendado primero)

1. Ve a **Actions → Reverse iter79 (Production) → Run workflow**
2. Inputs:
   - `apply`: **`false`** (default)
   - `confirmation`: dejar vacío
3. Click "Run workflow"
4. Revisa el log de `Run dry-run diagnóstico` y descarga los artefactos:
   - `db-backup-YYYYMMDD_HHMMSS` — backup completo (90 días retention)
   - `dry-run-YYYYMMDD_HHMMSS` — log del dry-run

### Apply real (solo después de validar dry-run)

1. Ve a **Actions → Reverse iter79 (Production) → Run workflow**
2. Inputs:
   - `apply`: **`true`**
   - `confirmation`: **`YES_REVERSE_ITER79`** (literal)
3. Click "Run workflow"
4. El workflow:
   - Vuelve a hacer backup (siempre se hace, antes del apply)
   - Vuelve a correr dry-run
   - Ejecuta el apply real
   - Sube los 3 artefactos

### Si algo sale mal

Descarga el artefacto `db-backup-XXXX` del workflow run, y restaura:

```bash
unzip db-backup-XXXX.zip -d backup
mongorestore --uri="$MONGO_URL" --drop ./backup/$DB_NAME
```

## Ventajas vs ejecución manual

- ✅ Backup garantizado en cada ejecución (artefactos GitHub, 90 días)
- ✅ Logs persistentes y auditables (incluyendo quién corrió qué)
- ✅ Doble confirmación (`apply=true` + `confirmation=YES_REVERSE_ITER79`) para evitar disparos accidentales
- ✅ Secrets de DB nunca se exponen en logs
- ✅ Cualquier rollback se hace bajando el artefacto del run específico

## Files

- `.github/workflows/reverse-iter79.yml` — el workflow
- `memory/recovery_scripts/00_BACKUP_OBLIGATORIO.sh` — backup standalone (si prefieres ejecutar manual)
- `memory/recovery_scripts/01_DRY_RUN_DIAGNOSTICO.js` — diagnóstico (read-only)
- `memory/recovery_scripts/02_APPLY_REVERSE.js` — apply (escrituras)
