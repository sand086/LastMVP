#!/bin/bash
# ============================================================================
# 00_BACKUP_OBLIGATORIO.sh
# ============================================================================
# Backup de las 3 colecciones afectadas ANTES de ejecutar el reverso.
# DEBE correrse desde un host con acceso al MONGO_URL de producción.
# ============================================================================

set -e

# Carga MONGO_URL/DB_NAME del .env de producción
# (Ajusta la ruta si corresponde)
if [ -f "/app/backend/.env" ]; then
    export $(grep -E "^(MONGO_URL|DB_NAME)=" /app/backend/.env | xargs)
fi

if [ -z "$MONGO_URL" ] || [ -z "$DB_NAME" ]; then
    echo "❌ MONGO_URL o DB_NAME no definidos. Define ambas variables y reintenta."
    exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/lastmile_pre_reverse_iter79_${TS}"
mkdir -p "$BACKUP_DIR"

echo "📦 Backup destino: $BACKUP_DIR"
echo "📦 DB: $DB_NAME"
echo ""

for col in journeys packages incidents; do
    echo "→ Dumpeando $col ..."
    mongodump \
        --uri="$MONGO_URL" \
        --db="$DB_NAME" \
        --collection="$col" \
        --out="$BACKUP_DIR" \
        --quiet
    DOC_COUNT=$(ls -la "$BACKUP_DIR/$DB_NAME/$col.bson" 2>/dev/null | awk '{print $5}')
    echo "   ✓ Bytes: $DOC_COUNT"
done

echo ""
echo "✅ Backup completo en: $BACKUP_DIR"
echo ""
echo "Para restaurar luego (si algo sale mal):"
echo "  mongorestore --uri=\"\$MONGO_URL\" --drop $BACKUP_DIR/$DB_NAME"
echo ""
echo "Para verificar el backup sin restaurar:"
echo "  mongorestore --uri=\"\$MONGO_URL\" --dryRun $BACKUP_DIR/$DB_NAME"
