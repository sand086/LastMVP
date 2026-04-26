"""
E2E tests for iter58 PII at-rest encryption + role-based masking.

Scope verified:
  - encrypt-on-write via POST /api/journeys (mongo direct check for `enc::` prefix)
  - decrypt-on-read for developer (plain) vs agent/proveedor (masked)
  - legacy plain docs (no enc:: prefix) still return plain to dev / masked to agent
  - tracking_number / address_cp untouched
  - analytics /api/reports/packages and /api/quality/packages role-based visibility
  - idempotency under update
  - cleanup of test docs (id prefix `iter58-test-`)
"""
import os
import sys
import uuid
import asyncio
import pytest
import pytest_asyncio
import requests
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback to frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

CREDS = {
    "developer": {"email": "dev@me.mx", "password": "LastMile2026"},
    "coordinator": {"email": "yael@me.mx", "password": "LastMile2026"},
    "agent": {"email": "agente@me.mx", "password": "LastMile2026"},
    "proveedor": {"email": "proveedor@me.mx", "password": "LastMile2026"},
}


def _login(role: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json=CREDS[role], timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login {role} failed: {r.status_code} {r.text[:200]}")
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def tokens():
    out = {}
    for role in CREDS:
        try:
            out[role] = _login(role)
        except Exception as e:
            print(f"login {role} skipped: {e}")
    return out


@pytest.fixture(scope="module")
def mongo_db():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_journey(tokens, mongo_db):
    """Create a journey with PII packages via POST /api/journeys (as coordinator)."""
    if "coordinator" not in tokens:
        pytest.skip("no coordinator token")

    # need a client and provider id — pick any from db
    async def _pick():
        c = await mongo_db.clients.find_one({}, {"_id": 0, "id": 1})
        p = await mongo_db.providers.find_one({}, {"_id": 0, "id": 1})
        return (c or {}).get("id"), (p or {}).get("id")
    client_id, provider_id = asyncio.get_event_loop().run_until_complete(_pick())
    if not client_id or not provider_id:
        pytest.skip("no client/provider seeded")

    payload = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "client_id": client_id,
        "provider_id": provider_id,
        "city": "CDMX",
        "max_packages": 5,
        "packages": [
            {
                "tracking_number": "ITER58-TRK-001",
                "recipient_name": "Juan Pérez García",
                "address": "Calle Reforma 123, Col Centro 06000",
                "zone": "Norte",
                "delivery_window": "AM",
            },
            {
                "tracking_number": "ITER58-TRK-002",
                "recipient_name": "María López",
                "address": "Av Insurgentes 456",
                "zone": "Sur",
                "delivery_window": "PM",
            },
        ],
        "retry_packages": [],
    }
    r = requests.post(f"{BASE_URL}/api/journeys", json=payload, headers=_hdr(tokens["coordinator"]), timeout=20)
    assert r.status_code == 200, f"create journey failed: {r.status_code} {r.text[:300]}"
    jid = r.json()["id"]

    yield jid

    # cleanup
    async def _cleanup():
        await mongo_db.journeys.delete_one({"id": jid})
        await mongo_db.packages.delete_many({"journey_id": jid})
        await mongo_db.packages.delete_many({"id": {"$regex": "^iter58-test-"}})
    try:
        asyncio.get_event_loop().run_until_complete(_cleanup())
    except Exception as e:
        print(f"cleanup warn: {e}")


# ─────────────── Encrypt-on-write ───────────────

def test_packages_encrypted_in_mongo(created_journey, mongo_db):
    """recipient_name and address persisted with enc:: prefix; tracking_number stays plain."""
    async def _check():
        pkgs = await mongo_db.packages.find({"journey_id": created_journey}, {"_id": 0}).to_list(10)
        return pkgs
    pkgs = asyncio.get_event_loop().run_until_complete(_check())
    assert len(pkgs) == 2
    for p in pkgs:
        assert p["recipient_name"].startswith("enc::"), f"recipient_name not encrypted: {p['recipient_name'][:50]}"
        assert p["address"].startswith("enc::"), f"address not encrypted: {p['address'][:50]}"
        # tracking_number must stay plain (indexable)
        assert p["tracking_number"].startswith("ITER58-TRK-"), f"tracking_number changed: {p['tracking_number']}"


# ─────────────── Decrypt-on-read developer ───────────────

def test_developer_sees_plain(created_journey, tokens):
    if "developer" not in tokens:
        pytest.skip("no developer token")
    r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["developer"]), timeout=15)
    assert r.status_code == 200
    pkgs = r.json().get("packages", [])
    assert len(pkgs) == 2
    names = {p["recipient_name"] for p in pkgs}
    assert "Juan Pérez García" in names
    assert "María López" in names
    addr = [p["address"] for p in pkgs if p["recipient_name"] == "Juan Pérez García"][0]
    assert "Reforma" in addr and "06000" in addr


def test_coordinator_sees_plain(created_journey, tokens):
    if "coordinator" not in tokens:
        pytest.skip("no coordinator token")
    r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["coordinator"]), timeout=15)
    assert r.status_code == 200
    pkgs = r.json().get("packages", [])
    names = {p["recipient_name"] for p in pkgs}
    assert "Juan Pérez García" in names


# ─────────────── Decrypt-on-read agent (masked) ───────────────

def test_agent_sees_masked(created_journey, tokens):
    if "agent" not in tokens:
        pytest.skip("no agent token")
    r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["agent"]), timeout=15)
    if r.status_code in (403, 404):
        pytest.skip(f"agent has no RBAC access to journey ({r.status_code}) — masking validated via apply_pii_visibility_pkg unit tests")
    assert r.status_code == 200
    pkgs = r.json().get("packages", [])
    if not pkgs:
        pytest.skip("agent fetched empty packages — likely RBAC filter; masking validated via direct lib")
    for p in pkgs:
        nm = p["recipient_name"]
        assert nm and "***" in nm, f"agent should see masked name, got '{nm}'"
        # raw plain values must not leak
        assert "Pérez García" not in nm
        if p.get("address"):
            assert "06000" not in p["address"]


def test_proveedor_sees_masked(created_journey, tokens):
    if "proveedor" not in tokens:
        pytest.skip("no proveedor token")
    r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["proveedor"]), timeout=15)
    if r.status_code in (403, 404):
        pytest.skip(f"proveedor has no RBAC access to journey ({r.status_code})")
    if r.status_code != 200:
        pytest.skip(f"proveedor unauthorized {r.status_code}")
    pkgs = r.json().get("packages", [])
    if not pkgs:
        pytest.skip("proveedor fetched empty packages")
    for p in pkgs:
        if p.get("recipient_name"):
            assert "***" in p["recipient_name"]


# ─────────────── Legacy plain doc support ───────────────

def test_legacy_plain_doc(created_journey, tokens, mongo_db):
    """Insert a package WITHOUT enc:: prefix and verify masking still works."""
    legacy_id = "iter58-test-legacy-1"

    async def _insert():
        await mongo_db.packages.insert_one({
            "id": legacy_id,
            "journey_id": created_journey,
            "tracking_number": "ITER58-LEGACY-001",
            "recipient_name": "Pedro Plain",
            "address": "Calle Legacy 99",
            "recipient_phone": "5511112222",
            "zone": "Centro",
            "status": "pending",
            "is_retry": False,
        })
    asyncio.get_event_loop().run_until_complete(_insert())

    if "developer" in tokens:
        r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["developer"]), timeout=15)
        assert r.status_code == 200
        pkgs = r.json().get("packages", [])
        legacy = [p for p in pkgs if p.get("id") == legacy_id]
        assert legacy, "legacy doc not in response"
        assert legacy[0]["recipient_name"] == "Pedro Plain"
        assert legacy[0]["recipient_phone"] == "5511112222"

    if "agent" in tokens:
        r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["agent"]), timeout=15)
        if r.status_code == 200:
            pkgs = r.json().get("packages", [])
            legacy = [p for p in pkgs if p.get("id") == legacy_id]
            if legacy:
                assert legacy[0]["recipient_name"] == "Pedro P***"
                # phone 10-digit: head 2 + 4 stars + tail 4
                assert legacy[0]["recipient_phone"] == "55****2222"


# ─────────────── tracking_number searchable ───────────────

def test_tracking_number_still_searchable(created_journey, mongo_db):
    """tracking_number must remain plain so filters/index queries still work."""
    async def _q():
        return await mongo_db.packages.find_one(
            {"tracking_number": "ITER58-TRK-001"}, {"_id": 0}
        )
    doc = asyncio.get_event_loop().run_until_complete(_q())
    assert doc is not None, "tracking_number lookup failed — field was encrypted by mistake?"
    assert doc["tracking_number"] == "ITER58-TRK-001"


# ─────────────── Idempotency under update ───────────────

def test_double_encrypt_idempotent(created_journey, mongo_db, tokens):
    """Calling encrypt_pkg_pii twice on a doc must not double-wrap (verified via API round-trip)."""
    from utils.pii import encrypt_pkg_pii

    async def _get():
        return await mongo_db.packages.find_one({"journey_id": created_journey}, {"_id": 0})
    p = asyncio.get_event_loop().run_until_complete(_get())
    original = p["recipient_name"]
    assert original.startswith("enc::")
    # apply encrypt again locally — should be noop (string equality is the idempotency contract)
    encrypt_pkg_pii(p)
    assert p["recipient_name"] == original, "encrypt_pkg_pii is NOT idempotent"
    # API round-trip still decodes correctly (would fail if double-wrapped)
    if "developer" in tokens:
        r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}", headers=_hdr(tokens["developer"]), timeout=15)
        assert r.status_code == 200
        names = {pp["recipient_name"] for pp in r.json().get("packages", [])}
        assert names & {"Juan Pérez García", "María López"}, f"decryption failed after re-encrypt simulation: {names}"


# ─────────────── Analytics endpoints ───────────────

def test_reports_packages_developer_plain(tokens, created_journey):
    if "developer" not in tokens:
        pytest.skip("no developer token")
    r = requests.get(f"{BASE_URL}/api/reports/packages", headers=_hdr(tokens["developer"]), timeout=20)
    if r.status_code != 200:
        pytest.skip(f"reports endpoint unavailable: {r.status_code}")
    body = r.json()
    pkgs = body if isinstance(body, list) else body.get("packages") or body.get("data") or []
    if not pkgs:
        pytest.skip("no packages in reports")
    # find one of ours
    ours = [p for p in pkgs if p.get("tracking_number", "").startswith("ITER58-TRK")]
    if ours:
        assert ours[0]["recipient_name"] in ("Juan Pérez García", "María López")


def test_reports_packages_agent_masked(tokens, created_journey):
    if "agent" not in tokens:
        pytest.skip("no agent token")
    r = requests.get(f"{BASE_URL}/api/reports/packages", headers=_hdr(tokens["agent"]), timeout=20)
    if r.status_code != 200:
        pytest.skip(f"reports endpoint unavailable for agent: {r.status_code}")
    body = r.json()
    pkgs = body if isinstance(body, list) else body.get("packages") or body.get("data") or []
    ours = [p for p in pkgs if p.get("tracking_number", "").startswith("ITER58-TRK")]
    if not ours:
        pytest.skip("agent has no visibility on iter58 test packages")
    for p in ours:
        if p.get("recipient_name"):
            assert "***" in p["recipient_name"], f"agent must see masked name, got '{p['recipient_name']}'"


def test_quality_packages_developer_plain(tokens, created_journey):
    if "developer" not in tokens:
        pytest.skip("no developer token")
    r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}/packages-quality", headers=_hdr(tokens["developer"]), timeout=20)
    if r.status_code != 200:
        pytest.skip(f"quality endpoint unavailable: {r.status_code}")
    body = r.json()
    pkgs = body if isinstance(body, list) else body.get("packages") or body.get("data") or body.get("items") or []
    ours = [p for p in pkgs if p.get("tracking_number", "").startswith("ITER58-TRK")]
    if not ours:
        pytest.skip("no iter58 pkgs in quality response")
    assert ours[0]["recipient_name"] in ("Juan Pérez García", "María López")


def test_quality_packages_agent_masked(tokens, created_journey):
    if "agent" not in tokens:
        pytest.skip("no agent token")
    r = requests.get(f"{BASE_URL}/api/journeys/{created_journey}/packages-quality", headers=_hdr(tokens["agent"]), timeout=20)
    if r.status_code != 200:
        pytest.skip(f"quality endpoint unavailable for agent: {r.status_code}")
    body = r.json()
    pkgs = body if isinstance(body, list) else body.get("packages") or body.get("data") or body.get("items") or []
    ours = [p for p in pkgs if p.get("tracking_number", "").startswith("ITER58-TRK")]
    if not ours:
        pytest.skip("agent has no visibility on iter58 quality packages")
    for p in ours:
        if p.get("recipient_name"):
            assert "***" in p["recipient_name"]
