param(
  [string]$ComposeFile = "docker-compose.dev.yml",
  [string]$DumpDir = "lastmile-mvp-test_database_dump_20260521_160025",
  [string]$Database = "myexcellence_legacy",
  [switch]$DropDatabase,
  [switch]$All,
  [int]$MaxSecondsPerFile = 900
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$hostDumpPath = Join-Path $root "db\$DumpDir"
if (-not (Test-Path $hostDumpPath)) {
  throw "Dump directory not found: $hostDumpPath"
}

$containerDumpPath = "/seed-data/$DumpDir"

Write-Host "Checking mongo container and import tooling..."
docker compose -f $ComposeFile up -d mongo | Out-Host
$mongoimport = docker compose -f $ComposeFile exec -T mongo sh -lc "command -v mongoimport"
if (-not $mongoimport) {
  throw "mongoimport was not found in the mongo container."
}

if ($DropDatabase) {
  Write-Host "Dropping database '$Database' before import..."
  docker compose -f $ComposeFile exec -T mongo mongosh --quiet --eval "db.getSiblingDB('$Database').dropDatabase()" | Out-Host
}

$files = Get-ChildItem -Path $hostDumpPath -Filter "*.json" | Sort-Object Name
if (-not $files) {
  throw "No JSON files found in $hostDumpPath"
}

if (-not $All) {
  $coreCollections = @(
    "ai_evaluation_jobs",
    "architecture_changelog",
    "architecture_snapshots",
    "audit_log",
    "audit_logs",
    "branches",
    "client_config",
    "client_integrations",
    "clients",
    "config",
    "driver_audit_log",
    "incidents",
    "integrity_results",
    "journey_images",
    "journeys",
    "leader_election",
    "login_attempts",
    "manual_pages",
    "manuals",
    "messenger_mappings",
    "packages",
    "providers",
    "revoked_tokens",
    "routal_daily_plans",
    "routal_events",
    "route_edits",
    "system_config",
    "system_errors",
    "token_usage_log",
    "training_samples",
    "users",
    "webhook_deliveries",
    "webhooks"
  )
  $files = $files | Where-Object {
    $base = $_.BaseName -replace "_part\d+$", ""
    $coreCollections -contains $base
  }
  Write-Host "Core mode: skipping high-volume request_metrics. Pass -All to import every JSON file."
}

$total = $files.Count
$i = 0
$collections = $files | ForEach-Object { $_.BaseName -replace "_part\d+$", "" } | Sort-Object -Unique
Write-Host "Ensuring id indexes for $($collections.Count) collections..."
$collectionsJs = ($collections | ForEach-Object { "'$_'" }) -join ","
docker compose -f $ComposeFile exec -T mongo mongosh --quiet --eval @"
const dbx = db.getSiblingDB('$Database');
[$collectionsJs].forEach((name) => dbx.getCollection(name).createIndex({ id: 1 }, { background: true }));
"@ | Out-Host

foreach ($file in $files) {
  $i += 1
  $collection = $file.BaseName -replace "_part\d+$", ""
  $containerFile = "$containerDumpPath/$($file.Name)"
  Write-Host "[$i/$total] Importing $($file.Name) -> $Database.$collection"

  $cmd = "timeout $MaxSecondsPerFile mongoimport --db '$Database' --collection '$collection' --file '$containerFile' --jsonArray --mode upsert --upsertFields id"
  docker compose -f $ComposeFile exec -T mongo sh -lc $cmd | Out-Host
}

Write-Host "Import complete. Collection counts:"
docker compose -f $ComposeFile exec -T mongo mongosh --quiet --eval @"
const dbx = db.getSiblingDB('$Database');
dbx.getCollectionNames().sort().forEach((name) => {
  print(name + ': ' + dbx.getCollection(name).countDocuments());
});
"@ | Out-Host
