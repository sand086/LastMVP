#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker-compose.qa.yml"
EMAIL=""
PASSWORD=""
ROLE="admin"
NAME="QA Development"
TENANT_SLUG="myexcellence"

usage() {
  cat <<'EOF'
Usage: scripts/create_qa_user.sh --email EMAIL [options]

Options:
  --compose-file FILE  Compose file to use (default: docker-compose.qa.yml)
  --email EMAIL        User email to create or update
  --password PASSWORD  Password to set. If omitted, prompts securely
  --role ROLE          App role (default: admin)
  --name NAME          Display name (default: QA Development)
  --tenant-slug SLUG   Tenant slug (default: myexcellence)
  -h, --help           Show this help

Valid roles:
  root_dev, superadmin, admin, coordinator, supervisor, agent,
  client_viewer, client_auditor
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --email)
      EMAIL="$2"
      shift 2
      ;;
    --password)
      PASSWORD="$2"
      shift 2
      ;;
    --role)
      ROLE="$2"
      shift 2
      ;;
    --name)
      NAME="$2"
      shift 2
      ;;
    --tenant-slug)
      TENANT_SLUG="$2"
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

if [[ -z "$EMAIL" ]]; then
  echo "--email is required" >&2
  usage >&2
  exit 1
fi

if [[ -z "$PASSWORD" ]]; then
  read -r -s -p "Password for $EMAIL: " PASSWORD
  echo
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

docker compose -f "$COMPOSE_FILE" up -d mongo backend

docker compose -f "$COMPOSE_FILE" exec -T \
  -e QA_USER_EMAIL="$EMAIL" \
  -e QA_USER_PASSWORD="$PASSWORD" \
  -e QA_USER_ROLE="$ROLE" \
  -e QA_USER_NAME="$NAME" \
  -e QA_TENANT_SLUG="$TENANT_SLUG" \
  backend python - <<'PY'
import asyncio
import os
from datetime import datetime, timezone

from core.db import get_db
from core.security import hash_password
from core.uuid import new_id

VALID_ROLES = {
    "root_dev", "superadmin", "admin", "coordinator", "supervisor", "agent",
    "client_viewer", "client_auditor",
}


async def main():
    email = os.environ["QA_USER_EMAIL"].strip().lower()
    password = os.environ["QA_USER_PASSWORD"]
    role = os.environ["QA_USER_ROLE"].strip()
    name = os.environ["QA_USER_NAME"].strip()
    tenant_slug = os.environ["QA_TENANT_SLUG"].strip()

    if role not in VALID_ROLES:
        raise SystemExit(f"Invalid role: {role}")
    if not password:
        raise SystemExit("Password cannot be empty")

    db = get_db()
    tenant = await db.tenants.find_one({"slug": tenant_slug}, {"_id": 0})
    if not tenant:
        raise SystemExit(
            f"Tenant '{tenant_slug}' not found. Start backend once so initial seeds run."
        )

    now = datetime.now(timezone.utc).isoformat()
    existing = await db.users.find_one(
        {"tenant_id": tenant["id"], "email": email},
        {"_id": 0},
    )

    updates = {
        "tenant_id": tenant["id"],
        "email": email,
        "name": name,
        "role": role,
        "status": "active",
        "password_hash": hash_password(password),
        "must_reset_password": False,
        "updated_at": now,
    }

    if existing:
        await db.users.update_one({"id": existing["id"]}, {"$set": updates})
        user_id = existing["id"]
        action = "updated"
    else:
        doc = {
            "id": new_id(),
            "created_at": now,
            "last_login_at": None,
            **updates,
        }
        await db.users.insert_one(doc)
        user_id = doc["id"]
        action = "created"

    print(f"user_{action}: {email} ({role}) tenant={tenant_slug} id={user_id}")


asyncio.run(main())
PY
