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

    async def get_routal_client(self, client_id: str, branch_id: Optional[str] = None) -> Optional[RoutalClient]:
        """Factory: returns a configured RoutalClient or None if not set up.

        Multi-project (RT-01): if `branch_id` is provided, looks up credentials in
        `client_integrations.branches[branch_id]`. Falls back to top-level
        `credentials_encrypted` if branch credentials are missing (legacy clients
        with single Routal project).
        """
        doc = await self.get_client_integration(client_id)
        if not doc:
            return None
        if doc.get("integration_type") != "routal":
            return None
        if doc.get("status") != "active":
            return None

        # Try branch credentials first
        if branch_id:
            branches = doc.get("branches") or {}
            b_entry = branches.get(branch_id)
            if b_entry and b_entry.get("active", True) and b_entry.get("credentials_encrypted"):
                b_creds = decrypt_credentials(b_entry["credentials_encrypted"])
                api_key = b_creds.get("routal_api_key")
                project_id = b_creds.get("routal_project_id")
                if api_key:
                    return RoutalClient(api_key=api_key, project_id=project_id)

        # Fallback to client-level (legacy single-project)
        creds = doc.get("credentials") or {}
        api_key = creds.get("routal_api_key")
        project_id = creds.get("routal_project_id")
        if not api_key:
            return None
        return RoutalClient(api_key=api_key, project_id=project_id)

    async def set_branch_credentials(
        self, client_id: str, branch_id: str,
        api_key: Optional[str] = None, project_id: Optional[str] = None,
        webhook_secret: Optional[str] = None, active: Optional[bool] = None,
    ) -> dict:
        """Insert or update a branch's Routal credentials. Encrypted at rest.
        Merge semantics: only fields with non-empty values overwrite existing ones.
        """
        existing = await self.db.client_integrations.find_one(
            {"client_id": client_id, "integration_type": "routal"},
            {"_id": 0},
        )
        if not existing:
            raise ValueError(f"Integración Routal no existe para cliente {client_id}. Crea primero la integración base.")

        branches = existing.get("branches") or {}
        b_entry = dict(branches.get(branch_id) or {})

        # Decrypt existing branch creds (if any) and merge incoming ones
        existing_creds = {}
        if b_entry.get("credentials_encrypted"):
            existing_creds = decrypt_credentials(b_entry["credentials_encrypted"])
        new_creds = dict(existing_creds)
        if api_key not in (None, ""):
            new_creds["routal_api_key"] = api_key
        if project_id not in (None, ""):
            new_creds["routal_project_id"] = project_id
        if webhook_secret not in (None, ""):
            new_creds["routal_webhook_secret"] = webhook_secret

        b_entry["credentials_encrypted"] = encrypt_credentials(new_creds) if new_creds else ""
        if active is not None:
            b_entry["active"] = active
        elif "active" not in b_entry:
            b_entry["active"] = True
        b_entry["updated_at"] = datetime.now(timezone.utc).isoformat()

        branches[branch_id] = b_entry
        await self.db.client_integrations.update_one(
            {"client_id": client_id, "integration_type": "routal"},
            {"$set": {"branches": branches, "updated_at": datetime.now(timezone.utc)}},
        )

        # Return public branch summary
        return {
            "branch_id": branch_id,
            "active": b_entry.get("active", True),
            "credentials_summary": public_credentials_summary(new_creds),
            "updated_at": b_entry["updated_at"],
        }

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

    async def list_active_routal_branches(self) -> List[dict]:
        """Return list of {client_id, branch_id} pairs for active branch-level Routal
        integrations (used by SEL01 multi-project + periodic sync workers).
        """
        out = []
        async for doc in self.db.client_integrations.find(
            {"integration_type": "routal", "status": "active"},
            {"_id": 0, "client_id": 1, "branches": 1},
        ):
            cid = doc.get("client_id")
            branches = doc.get("branches") or {}
            for bid, entry in branches.items():
                if entry.get("active", True) and entry.get("credentials_encrypted"):
                    out.append({"client_id": cid, "branch_id": bid})
        return out

    async def find_client_by_routal_signature(self, project_id: str) -> Optional[str]:
        """Used by webhook receiver to map an incoming event to a client.
        Returns client_id only (legacy single-project mapping).
        """
        result = await self.find_client_branch_by_routal_signature(project_id)
        return result.get("client_id") if result else None

    async def find_client_branch_by_routal_signature(self, project_id: str) -> Optional[dict]:
        """Resolve a Routal project_id to {client_id, branch_id?}.

        Search order (RT-01 multi-project):
          1. Branch-level: any client_integrations.branches[*].project_id matching → return both
          2. Top-level: legacy single-project clients → return {client_id} (no branch)
        """
        async for doc in self.db.client_integrations.find(
            {"integration_type": "routal", "status": "active"},
            {"_id": 0, "client_id": 1, "credentials_encrypted": 1, "branches": 1},
        ):
            cid = doc.get("client_id")
            # Check branches first (preferred for multi-project clients)
            branches = doc.get("branches") or {}
            for bid, entry in branches.items():
                if not entry.get("active", True):
                    continue
                enc = entry.get("credentials_encrypted") or ""
                if not enc:
                    continue
                creds = decrypt_credentials(enc)
                if creds.get("routal_project_id") == project_id:
                    return {"client_id": cid, "branch_id": bid}
            # Fall back to top-level
            top_creds = decrypt_credentials(doc.get("credentials_encrypted") or "")
            if top_creds.get("routal_project_id") == project_id:
                return {"client_id": cid, "branch_id": None}
        return None
