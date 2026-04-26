"""
Tests for R00C / iter58 — PII at-rest encryption + role-based masking.
"""
import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lastmile_iter58")


@pytest.fixture
def fernet_key(monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    return key


@pytest_asyncio.fixture
async def init_enc(fernet_key):
    from utils import encryption
    fake_db = MagicMock()
    fake_db.config = MagicMock()
    fake_db.config.find_one = AsyncMock(return_value=None)
    fake_db.config.update_one = AsyncMock()
    await encryption.init_encryption(fake_db)
    yield


# ─────────────── ENCRYPT / DECRYPT ───────────────

@pytest.mark.asyncio
async def test_encrypt_round_trip(init_enc):
    from utils.pii import encrypt_pii, decrypt_pii, ENC_PREFIX
    enc = encrypt_pii("Juan Pérez")
    assert enc.startswith(ENC_PREFIX)
    assert "Juan" not in enc
    assert decrypt_pii(enc) == "Juan Pérez"


@pytest.mark.asyncio
async def test_encrypt_idempotent(init_enc):
    from utils.pii import encrypt_pii
    once = encrypt_pii("María García")
    twice = encrypt_pii(once)
    assert once == twice  # already-encrypted values not re-wrapped


@pytest.mark.asyncio
async def test_decrypt_legacy_plain_passthrough(init_enc):
    from utils.pii import decrypt_pii
    assert decrypt_pii("Juan plain") == "Juan plain"  # no enc:: prefix → return as-is
    assert decrypt_pii(None) is None
    assert decrypt_pii("") == ""


@pytest.mark.asyncio
async def test_encrypt_handles_none_empty(init_enc):
    from utils.pii import encrypt_pii
    assert encrypt_pii(None) is None
    assert encrypt_pii("") == ""


@pytest.mark.asyncio
async def test_decrypt_corrupted_token(init_enc):
    from utils.pii import decrypt_pii, ENC_PREFIX
    bad = f"{ENC_PREFIX}notvalidbase64!!!"
    assert decrypt_pii(bad) == "[encrypted]"  # graceful fallback


# ─────────────── MASKING ───────────────

def test_mask_name():
    from utils.pii import mask_name
    assert mask_name("Juan") == "Juan"  # single word kept
    assert mask_name("Juan Pérez") == "Juan P***"
    assert mask_name("Juan Pérez García") == "Juan P*** G***"
    assert mask_name("") == ""
    assert mask_name(None) == ""


def test_mask_phone():
    from utils.pii import mask_phone
    # "+52 55 1234 5678" → digits=12 → head 2 + 6 asterisks + tail 4
    assert mask_phone("+52 55 1234 5678") == "52******5678"
    assert mask_phone("5512345678") == "55****5678"
    assert mask_phone("123") == "***"
    assert mask_phone("") == ""


def test_mask_address():
    from utils.pii import mask_address
    out = mask_address("Calle 123, Col Centro 06000")
    assert "***" in out
    assert "06000" not in out
    assert "Calle" in out  # street prefix preserved
    assert mask_address("") == ""


# ─────────────── ROLE-BASED VISIBILITY ───────────────

@pytest.mark.asyncio
async def test_apply_visibility_developer_sees_plain(init_enc):
    from utils.pii import encrypt_pkg_pii, apply_pii_visibility_pkg
    pkg = {
        "id": "p1",
        "recipient_name": "Juan Pérez",
        "address": "Calle 123, Col Centro",
        "recipient_phone": "5512345678",
        "tracking_number": "TRK001",
    }
    encrypt_pkg_pii(pkg)
    assert pkg["recipient_name"].startswith("enc::")
    apply_pii_visibility_pkg(pkg, "developer")
    assert pkg["recipient_name"] == "Juan Pérez"
    assert pkg["address"] == "Calle 123, Col Centro"
    assert pkg["recipient_phone"] == "5512345678"
    assert pkg["tracking_number"] == "TRK001"  # untouched


@pytest.mark.asyncio
async def test_apply_visibility_agent_sees_masked(init_enc):
    from utils.pii import encrypt_pkg_pii, apply_pii_visibility_pkg
    pkg = {
        "recipient_name": "Juan Pérez",
        "address": "Calle 123, Col Centro 06000",
        "recipient_phone": "5512345678",
    }
    encrypt_pkg_pii(pkg)
    apply_pii_visibility_pkg(pkg, "agent")
    assert pkg["recipient_name"] == "Juan P***"
    assert "***" in pkg["address"]
    assert "06000" not in pkg["address"]
    assert pkg["recipient_phone"] == "55****5678"


@pytest.mark.asyncio
async def test_apply_visibility_proveedor_sees_masked(init_enc):
    from utils.pii import encrypt_pkg_pii, apply_pii_visibility_pkg
    pkg = {"recipient_name": "Ana López", "address": "Av Reforma 555", "recipient_phone": "5598765432"}
    encrypt_pkg_pii(pkg)
    apply_pii_visibility_pkg(pkg, "proveedor")
    assert pkg["recipient_name"] == "Ana L***"


@pytest.mark.asyncio
async def test_legacy_plain_data_still_works(init_enc):
    """Legacy packages without enc:: prefix should still work for both roles."""
    from utils.pii import apply_pii_visibility_pkg
    pkg = {"recipient_name": "Pedro Ruiz", "address": "Calle X 99", "recipient_phone": "5511112222"}
    # Don't encrypt — simulate legacy doc
    apply_pii_visibility_pkg(pkg, "coordinator")
    assert pkg["recipient_name"] == "Pedro Ruiz"

    pkg2 = {"recipient_name": "Pedro Ruiz", "address": "Calle X 99", "recipient_phone": "5511112222"}
    apply_pii_visibility_pkg(pkg2, "agent")
    assert pkg2["recipient_name"] == "Pedro R***"  # masked even for plain legacy


@pytest.mark.asyncio
async def test_bulk_visibility(init_enc):
    from utils.pii import encrypt_pkg_pii, apply_pii_visibility_pkgs
    pkgs = [
        {"recipient_name": f"User{i}", "address": f"Addr {i}", "recipient_phone": f"55{i:08d}"}
        for i in range(5)
    ]
    for p in pkgs:
        encrypt_pkg_pii(p)
    apply_pii_visibility_pkgs(pkgs, "agent")
    for p in pkgs:
        assert "***" in p["recipient_phone"] or "*" in p["recipient_phone"]


@pytest.mark.asyncio
async def test_no_role_defaults_to_plain(init_enc):
    """Internal/system calls without role get plain (executive default behaviour)."""
    from utils.pii import encrypt_pkg_pii, apply_pii_visibility_pkg
    pkg = {"recipient_name": "Sys User", "address": "X", "recipient_phone": "1234"}
    encrypt_pkg_pii(pkg)
    apply_pii_visibility_pkg(pkg, None)
    assert pkg["recipient_name"] == "Sys User"


# ─────────────── ENCRYPT-ON-WRITE HELPER ───────────────

@pytest.mark.asyncio
async def test_encrypt_pkg_pii_only_target_fields(init_enc):
    from utils.pii import encrypt_pkg_pii
    pkg = {
        "recipient_name": "Juan",
        "address": "Calle 1",
        "recipient_phone": "5511",
        "tracking_number": "TRK",  # NOT PII — must stay plain
        "address_cp": "06000",     # NOT PII (used for indexing) — must stay plain
        "zone": "Norte",
    }
    encrypt_pkg_pii(pkg)
    assert pkg["recipient_name"].startswith("enc::")
    assert pkg["address"].startswith("enc::")
    assert pkg["recipient_phone"].startswith("enc::")
    assert pkg["tracking_number"] == "TRK"
    assert pkg["address_cp"] == "06000"
    assert pkg["zone"] == "Norte"


@pytest.mark.asyncio
async def test_encrypt_pkg_pii_skips_empty(init_enc):
    from utils.pii import encrypt_pkg_pii
    pkg = {"recipient_name": "", "address": None, "recipient_phone": "55"}
    encrypt_pkg_pii(pkg)
    assert pkg["recipient_name"] == ""
    assert pkg["address"] is None
    assert pkg["recipient_phone"].startswith("enc::")
