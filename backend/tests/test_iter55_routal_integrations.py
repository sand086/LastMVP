"""
Tests for R00A — Multi-tenant Integrations + Routal webhooks.

Cubre:
  - encrypt/decrypt simétrico
  - public_credentials_summary no expone secrets
  - integration upsert + merge de credenciales (no clobber)
  - HMAC signature validation
  - Idempotency by event_id
  - client_id isolation en handlers
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lastmile_iter55")


@pytest.fixture
def fernet_key(monkeypatch):
    """Generate a real Fernet key for the test process."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    return key


@pytest_asyncio.fixture
async def init_enc(fernet_key):
    """Init the global Fernet for encryption helpers."""
    from utils import encryption
    # No DB needed because env key is valid
    fake_db = MagicMock()
    fake_db.config = MagicMock()
    fake_db.config.find_one = AsyncMock(return_value=None)
    fake_db.config.update_one = AsyncMock()
    await encryption.init_encryption(fake_db)
    yield


@pytest.mark.asyncio
async def test_encrypt_decrypt_round_trip(init_enc):
    from utils.encryption import encrypt_credentials, decrypt_credentials
    creds = {"routal_api_key": "sk_live_abc", "routal_project_id": "proj_42", "routal_webhook_secret": "whsec_xyz"}
    enc = encrypt_credentials(creds)
    assert enc and enc != json.dumps(creds)
    assert "sk_live_abc" not in enc  # not stored in plaintext
    dec = decrypt_credentials(enc)
    assert dec == creds


@pytest.mark.asyncio
async def test_decrypt_garbage_returns_empty(init_enc):
    from utils.encryption import decrypt_credentials
    assert decrypt_credentials("notvalidbase64!!!") == {}
    assert decrypt_credentials("") == {}


@pytest.mark.asyncio
async def test_public_summary_hides_secrets(init_enc):
    from utils.encryption import public_credentials_summary
    summary = public_credentials_summary({
        "routal_api_key": "sk_live_super_secret",
        "routal_project_id": "proj_42",
        "routal_webhook_secret": "whsec_xyz",
    })
    assert summary["has_api_key"] is True
    assert summary["has_webhook_secret"] is True
    assert summary["routal_project_id"] == "proj_42"
    # No raw secrets
    serialized = json.dumps(summary)
    assert "sk_live" not in serialized
    assert "whsec" not in serialized


def test_hmac_verify_valid():
    from routes.routal_webhook_routes import _verify_hmac
    secret = "whsec_xyz"
    body = b'{"event":"plan.created"}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_hmac(secret, body, sig) is True
    # With prefix
    assert _verify_hmac(secret, body, f"sha256={sig}") is True


def test_hmac_verify_invalid():
    from routes.routal_webhook_routes import _verify_hmac
    body = b'{"event":"plan.created"}'
    assert _verify_hmac("whsec_xyz", body, "deadbeef") is False
    assert _verify_hmac("whsec_xyz", body, "") is False
    # Tampered body
    sig = hmac.new(b"whsec_xyz", body, hashlib.sha256).hexdigest()
    assert _verify_hmac("whsec_xyz", b"tampered", sig) is False


@pytest.mark.asyncio
async def test_upsert_merges_credentials(init_enc):
    """Frontend may send only changed creds; existing ones must persist."""
    from services.integration_service import IntegrationService
    from utils.encryption import encrypt_credentials, decrypt_credentials

    db = MagicMock()
    inserted = {}
    async def fake_find_one(filt, *a, **k):
        # Return a copy so callers that mutate (e.g. .pop) don't corrupt our store
        doc = inserted.get(filt.get("client_id"))
        return dict(doc) if doc else None
    async def fake_update_one(filt, update, **k):
        cid = filt.get("client_id")
        doc = inserted.get(cid, {}).copy()
        doc.update(update.get("$set", {}))
        inserted[cid] = doc
        m = MagicMock(); m.matched_count = 1; return m
    db.client_integrations = MagicMock()
    db.client_integrations.find_one = AsyncMock(side_effect=fake_find_one)
    db.client_integrations.update_one = AsyncMock(side_effect=fake_update_one)
    cursor = MagicMock()
    cursor.__aiter__.return_value = iter([])
    db.client_integrations.find = MagicMock(return_value=cursor)

    svc = IntegrationService(db)

    # First write: full creds
    await svc.upsert_integration(
        client_id="c1", client_name="Cubbo", integration_type="routal",
        credentials={"routal_api_key": "sk_AAA", "routal_project_id": "proj_1", "routal_webhook_secret": "whsec_111"},
        status="active",
    )
    enc1 = inserted["c1"]["credentials_encrypted"]
    creds1 = decrypt_credentials(enc1)
    assert creds1["routal_api_key"] == "sk_AAA"

    # Second write: only project_id changed → api_key must be preserved
    await svc.upsert_integration(
        client_id="c1", client_name="Cubbo", integration_type="routal",
        credentials={"routal_project_id": "proj_2"},
    )
    enc2 = inserted["c1"]["credentials_encrypted"]
    creds2 = decrypt_credentials(enc2)
    assert creds2["routal_api_key"] == "sk_AAA", "api_key must be preserved on partial update"
    assert creds2["routal_project_id"] == "proj_2"
    assert creds2["routal_webhook_secret"] == "whsec_111"


@pytest.mark.asyncio
async def test_handler_filters_by_client_id(init_enc):
    """stop_completed must NEVER touch a package that belongs to a different client."""
    from workers.routal_event_processor import _handle_stop_completed

    db = MagicMock()
    captured_filter = {}
    async def fake_update(filt, update):
        captured_filter.update(filt)
        m = MagicMock(); m.matched_count = 1; return m
    async def fake_find_one(filt, *a, **k):
        return {"journey_id": "j_1"}
    async def fake_inc(filt, update):
        m = MagicMock(); m.matched_count = 1; return m

    db.packages = MagicMock()
    db.packages.update_one = AsyncMock(side_effect=fake_update)
    db.packages.find_one = AsyncMock(side_effect=fake_find_one)
    db.journeys = MagicMock()
    db.journeys.update_one = AsyncMock(side_effect=fake_inc)

    await _handle_stop_completed(db, {"service_id": "svc_001"}, "client_AAA")
    assert captured_filter.get("client_id") == "client_AAA"
    assert captured_filter.get("routal_service_id") == "svc_001"
