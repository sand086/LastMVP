# P01 — Storage local sin S3 (riesgo conocido)

**Estado:** ⏸️ POSPUESTO. Skipeado por decisión del usuario en sesión 2026-04-25 (opción a).

## Riesgo
El backend almacena las evidencias subidas (fotos de inicio/cierre de ruta, evidencias de paquetes que NO vienen de Kosmo) en `/app/backend/uploads/`. En el deployment Emergent native, **el disco del pod es ephemeral**: cada redeploy borra el contenido.

Las URLs de Kosmo (storage.googleapis.com) NO se ven afectadas — el sistema usa esas URLs como fuente principal y solo guarda localmente las evidencias propias.

## Impacto cuantificado
- Imágenes de inicio de ruta (start_data): perdidas tras redeploy
- Imágenes de cierre de ruta (close_data): perdidas tras redeploy
- Imágenes de incidencias subidas manualmente: perdidas tras redeploy
- Imágenes de evidencia upload manual (vía /uploads endpoint): perdidas tras redeploy
- Audit photos: perdidas tras redeploy

Aproximación: en operación normal con ~30 journeys/día y ~3 fotos por inicio + ~3 por cierre + ~1.5 incidente promedio = ~225 imágenes/día * promedio 200KB cada una = ~45MB/día = ~1.4GB/mes.

## Mitigación temporal
1. **No redeployar antes de exportar evidencias críticas**. Antes del próximo redeploy, exportar a Excel todas las journeys cerradas con sus URLs de evidencia (las URLs siguen funcionando en Kosmo, solo nuestras imágenes propias se pierden).
2. **Banner en /api/health** (ya implementado): el campo `checks.storage.warning` muestra "Local disk; files do not persist across redeploys" — visible en monitoreo externo.
3. **Notificar al equipo IT antes de cada redeploy** para validar evidencias críticas.

## Solución definitiva (cuando el usuario abra una sesión específica)
Implementar storage S3-compatible:

### Opción A: AWS S3
- Bucket en us-east-1, ~$0.023/GB/mes Standard
- Vars: `S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- SDK: `boto3` con presigned URLs para descargas

### Opción B: Cloudflare R2 (recomendada)
- $0.015/GB/mes + egreso 100% gratis (vs AWS $0.09/GB egreso)
- Vars: `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL` (`https://<account>.r2.cloudflarestorage.com`)
- SDK: `boto3` con `endpoint_url` parameter (drop-in replacement)

### Tareas de implementación (~2-3h trabajo)
1. Crear `/app/backend/utils/storage.py` con interfaz unificada (`upload_file`, `delete_file`, `get_url`)
2. Migrar `/app/backend/routes/upload_routes.py` para usar `storage.upload_file()` en lugar de `aiofiles.open(uploads_dir)`
3. Reemplazar `StaticFiles` mount con redirect a presigned URLs (TTL 24h)
4. Migrar archivos existentes con script one-shot: `python3 backend/scripts/migrate_uploads_to_s3.py`
5. Actualizar `checks.storage` en `/api/health` para validar bucket accessibility
6. Variable env feature-flag: `STORAGE_BACKEND=local|s3` para rollback rápido

## Tickets relacionados
- ROADMAP P0: este archivo
- Documentación previa: `/app/memory/PRECEDENT_BUDGET_INCONSISTENCY.md`
- Audit doc: `/app/memory/AUDIT_REPORT.md`
