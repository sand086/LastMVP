"""
IntegrationService — multi-tenant factory for client integrations (R00A.3).

Reads/writes the client_integrations collection. Decrypts credentials on demand
and produces ready-to-use service clients (RoutalClient, future carriers).
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from utils.encryption import decrypt_credentials, encrypt_credentials, public_credentials_summary
from services.routal_client import RoutalClient

logger = logging.getLogger(__name__)


class IntegrationService:
    def __init__(self, db):
        self.db = db

    async def get_client_integration(self, client_id: str) -> Optional[dict]:
        """Returns the integration document (with decrypted credentials)."""
        doc = await self.db.client_integrations.find_one({"client_id": client_id}, {"_id": 0})
        if not doc:
            return None
        encrypted = doc.get("credentials_encrypted") or ""
        doc["credentials"] = decrypt_credentials(encrypted) if encrypted else {}
        return doc

    async def get_public_integration(self, client_id: str) -> Optional[dict]:
        """Returns the integration document with credentials replaced by booleans (safe for frontend)."""
        doc = await self.get_client_integration(client_id)
        if not doc:
            return None
        creds = doc.pop("credentials", {})
        doc["credentials_summary"] = public_credentials_summary(creds)
        doc.pop("credentials_encrypted", None)
        return doc

    async def list_integrations_public(self) -> List[dict]:
        """List all integrations stripped of credential values (for /api/integrations GET)."""
        out = []
        async for doc in self.db.client_integrations.find({}, {"_id": 0}):
            encrypted = doc.pop("credentials_encrypted", None)
            creds = decrypt_credentials(encrypted) if encrypted else {}
            doc["credentials_summary"] = public_credentials_summary(creds)
            out.append(doc)
        return out

    async def upsert_integration(
        self, client_id: str, client_name: str, integration_type: str,
        credentials: Optional[dict] = None, config: Optional[dict] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Insert or update. Merges credentials with existing (so frontend can send only changed fields)."""
        existing = await self.db.client_integrations.find_one({"client_id": client_id}, {"_id": 0})
        existing_creds = {}
        if existing and existing.get("credentials_encrypted"):
            existing_creds = decrypt_credentials(existing["credentials_encrypted"])

        merged_creds = {**existing_creds, **(credentials or {})}
        # Strip None or empty string values from credentials (they mean "do not change")
        merged_creds = {k: v for k, v in merged_creds.items() if v not in (None, "")}

        encrypted = encrypt_credentials(merged_creds) if merged_creds else ""

        default_config = {
            "auto_create_journeys": True,
            "auto_close_journeys": True,
            "sync_drivers": True,
        }
        merged_config = {**default_config, **(existing.get("config") if existing else {}), **(config or {})}

        now = datetime.now(timezone.utc)
        doc = {
            "client_id": client_id,
            "client_name": client_name,
            "integration_type": integration_type,
            "status": status or (existing.get("status") if existing else "inactive"),
            "credentials_encrypted": encrypted,
            "config": merged_config,
            "last_sync_at": existing.get("last_sync_at") if existing else None,
            "last_error": existing.get("last_error") if existing else None,
            "created_at": existing.get("created_at") if existing else now,
            "updated_at": now,
        }
        await self.db.client_integrations.update_one(
            {"client_id": client_id},
            {"$set": doc},
            upsert=True,
        )
        return await self.get_public_integration(client_id)

    async def update_status(self, client_id: str, status: str) -> Optional[dict]:
        if status not in ("active", "inactive", "testing"):
            raise ValueError(f"Invalid status: {status}")
        result = await self.db.client_integrations.update_one(
            {"client_id": client_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}},
        )
        if result.matched_count == 0:
            return None
        return await self.get_public_integration(client_id)

    async def soft_delete(self, client_id: str) -> bool:
        """Soft delete: status=inactive + clear credentials."""
        result = await self.db.client_integrations.update_one(
            {"client_id": client_id},
            {"$set": {
                "status": "inactive",
                "credentials_encrypted": "",
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return result.matched_count > 0

    async def get_routal_client(self, client_id: str) -> Optional[RoutalClient]:
        """Factory: returns a configured RoutalClient or None if not set up."""
        doc = await self.get_client_integration(client_id)
        if not doc:
            return None
        if doc.get("integration_type") != "routal":
            return None
        if doc.get("status") != "active":
            return None
        creds = doc.get("credentials") or {}
        api_key = creds.get("routal_api_key")
        project_id = creds.get("routal_project_id")
        if not api_key:
            return None
        return RoutalClient(api_key=api_key, project_id=project_id)

    async def list_active_routal_clients(self) -> List[str]:
        """Return list of client_ids with active routal integration (for periodic jobs)."""
        out = []
        async for doc in self.db.client_integrations.find(
            {"integration_type": "routal", "status": "active"},
            {"_id": 0, "client_id": 1},
        ):
            cid = doc.get("client_id")
            if cid:
                out.append(cid)
        return out

    async def find_client_by_routal_signature(self, project_id: str) -> Optional[str]:
        """Used by webhook receiver to map an incoming event to a client."""
        async for doc in self.db.client_integrations.find(
            {"integration_type": "routal", "status": "active"},
            {"_id": 0, "client_id": 1, "credentials_encrypted": 1},
        ):
            creds = decrypt_credentials(doc.get("credentials_encrypted") or "")
            if creds.get("routal_project_id") == project_id:
                return doc.get("client_id")
        return None
