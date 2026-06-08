#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.dev.yml"
DUMP_DIR="lastmile-mvp-test_database_dump_20260521_160025"
DATABASE="myexcellence_legacy"
DROP_DATABASE=0
IMPORT_ALL=0
MAX_SECONDS_PER_FILE=900

usage() {
  cat <<'EOF'
Usage: scripts/import_legacy_dump.sh [options]

Options:
  --compose-file FILE       Compose file to use (default: docker-compose.dev.yml)
  --dump-dir DIR            Directory under db/ with JSON dump files
  --database NAME           Target Mongo database (default: myexcellence_legacy)
  --drop-database           Drop target database before importing
  --all                     Import every JSON file, including high-volume request_metrics
  --max-seconds-per-file N  Timeout per JSON file import (default: 900)
  -h, --help                Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --dump-dir)
      DUMP_DIR="$2"
      shift 2
      ;;
    --database)
      DATABASE="$2"
      shift 2
      ;;
    --drop-database)
      DROP_DATABASE=1
      shift
      ;;
    --all)
      IMPORT_ALL=1
      shift
      ;;
    --max-seconds-per-file)
      MAX_SECONDS_PER_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST_DUMP_PATH="$ROOT_DIR/db/$DUMP_DIR"
CONTAINER_DUMP_PATH="/seed-data/$DUMP_DIR"

if [[ ! -d "$HOST_DUMP_PATH" ]]; then
  echo "Dump directory not found: $HOST_DUMP_PATH" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "Checking mongo container and import tooling..."
docker compose -f "$COMPOSE_FILE" up -d mongo
docker compose -f "$COMPOSE_FILE" exec -T mongo sh -lc "command -v mongoimport" >/dev/null

if [[ "$DROP_DATABASE" -eq 1 ]]; then
  echo "Dropping database '$DATABASE' before import..."
  docker compose -f "$COMPOSE_FILE" exec -T mongo mongosh --quiet --eval "db.getSiblingDB('$DATABASE').dropDatabase()"
fi

mapfile -t FILES < <(find "$HOST_DUMP_PATH" -maxdepth 1 -type f -name "*.json" -printf "%f\n" | sort)
if [[ "${#FILES[@]}" -eq 0 ]]; then
  echo "No JSON files found in $HOST_DUMP_PATH" >&2
  exit 1
fi

if [[ "$IMPORT_ALL" -eq 0 ]]; then
  echo "Core mode: skipping high-volume request_metrics. Pass --all to import every JSON file."
  FILTERED=()
  for file in "${FILES[@]}"; do
    base="${file%.json}"
    collection="$(sed -E 's/_part[0-9]+$//' <<<"$base")"
    case "$collection" in
      ai_evaluation_jobs|architecture_changelog|architecture_snapshots|audit_log|audit_logs|branches|client_config|client_integrations|clients|config|driver_audit_log|incidents|integrity_results|journey_images|journeys|leader_election|login_attempts|manual_pages|manuals|messenger_mappings|packages|providers|revoked_tokens|routal_daily_plans|routal_events|route_edits|system_config|system_errors|token_usage_log|training_samples|users|webhook_deliveries|webhooks)
        FILTERED+=("$file")
        ;;
    esac
  done
  FILES=("${FILTERED[@]}")
fi

COLLECTIONS=()
for file in "${FILES[@]}"; do
  base="${file%.json}"
  COLLECTIONS+=("$(sed -E 's/_part[0-9]+$//' <<<"$base")")
done
mapfile -t UNIQUE_COLLECTIONS < <(printf "%s\n" "${COLLECTIONS[@]}" | sort -u)

echo "Ensuring id indexes for ${#UNIQUE_COLLECTIONS[@]} collections..."
COLLECTIONS_JS="$(printf "'%s'," "${UNIQUE_COLLECTIONS[@]}")"
COLLECTIONS_JS="${COLLECTIONS_JS%,}"
docker compose -f "$COMPOSE_FILE" exec -T mongo mongosh --quiet --eval "
const dbx = db.getSiblingDB('$DATABASE');
[$COLLECTIONS_JS].forEach((name) => dbx.getCollection(name).createIndex({ id: 1 }, { background: true }));
"

total="${#FILES[@]}"
i=0
for file in "${FILES[@]}"; do
  i=$((i + 1))
  base="${file%.json}"
  collection="$(sed -E 's/_part[0-9]+$//' <<<"$base")"
  container_file="$CONTAINER_DUMP_PATH/$file"
  echo "[$i/$total] Importing $file -> $DATABASE.$collection"
  docker compose -f "$COMPOSE_FILE" exec -T mongo sh -lc \
    "timeout '$MAX_SECONDS_PER_FILE' mongoimport --db '$DATABASE' --collection '$collection' --file '$container_file' --jsonArray --mode upsert --upsertFields id"
done

echo "Import complete. Collection counts:"
docker compose -f "$COMPOSE_FILE" exec -T mongo mongosh --quiet --eval "
const dbx = db.getSiblingDB('$DATABASE');
dbx.getCollectionNames().sort().forEach((name) => {
  print(name + ': ' + dbx.getCollection(name).countDocuments());
});
"
