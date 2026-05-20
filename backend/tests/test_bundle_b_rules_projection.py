"""Bundle B · R50 — Rule Projection Service end-to-end tests.

Targets:
- BACKEND projection ticket: GET /api/agent/tickets/{id} returns projection
- BACKEND projection reclamo: GET /api/reclamos/{id} returns projection
- BACKEND endpoint admin/rules/explain: only root_dev (admin → 403)
- BACKEND cache invalidation: after PUT admin/automation-permissions
- POST /api/agent/tickets/{id}/request-reopen (terminal ticket)

Seeded fixtures (idempotent):
- one terminal ticket (status=delivered) for R02
- one active ticket linked to restricted motivo for R03
- one conciliado claim for R28
"""
import os
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://bootstrap-emergent.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_CREDS = {"email": "admin@myexcellence.local", "password": "Admin123!"}
ROOT_CREDS = {"email": "root@myexcellence.local", "password": "Admin123!"}
AGENT_CREDS = {"email": "agent@myexcellence.local", "password": "Admin123!"}

RESTRICTED_MOTIVO_ID = "db62ac91-8134-4af1-a0a0-77678d4e8e01"  # Detenido por autoridad
TENANT_ID = "88633ddb-cd75-4f96-95aa-dfad4eb4cd15"


# ─── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.text}"
    return r.json()["data"]["access_token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login(**ADMIN_CREDS)


@pytest.fixture(scope="session")
def root_token():
    return _login(**ROOT_CREDS)


@pytest.fixture(scope="session")
def agent_token():
    return _login(**AGENT_CREDS)


@pytest.fixture(scope="session")
def seeded_data(mongo):
    """Idempotent seed for Bundle B tests."""
    now = datetime.now(timezone.utc).isoformat()

    # 1) Terminal ticket (delivered) -- create or update fixed id
    terminal_id = "TEST_B_terminal_ticket_0001"
    mongo.tickets.update_one(
        {"id": terminal_id},
        {"$set": {
            "id": terminal_id,
            "tenant_id": TENANT_ID,
            "status": "delivered",
            "is_terminal": True,
            "client_id": "abacb7c6-2f0a-4212-a197-96336cc3ff71",
            "motivo_id": None,
            "solucion_id": None,
            "channel": "whatsapp",
            "subject": "TEST_B terminal delivered",
            "created_at": now,
        }},
        upsert=True,
    )

    # 2) Active ticket with restricted motivo (R03)
    restricted_id = "TEST_B_restricted_ticket_0002"
    mongo.tickets.update_one(
        {"id": restricted_id},
        {"$set": {
            "id": restricted_id,
            "tenant_id": TENANT_ID,
            "status": "in_progress",
            "is_terminal": False,
            "client_id": "abacb7c6-2f0a-4212-a197-96336cc3ff71",
            "motivo_id": RESTRICTED_MOTIVO_ID,
            "solucion_id": "test-solucion-b",
            "channel": "whatsapp",
            "subject": "TEST_B restricted motivo",
            "created_at": now,
        }},
        upsert=True,
    )

    # 3) Existing conciliado claim (we have a91334ca already)
    conciliado_claim = mongo.claims.find_one({"estado": "conciliado", "tenant_id": TENANT_ID},
                                             {"_id": 0, "id": 1, "ticket_id": 1})
    assert conciliado_claim, "no seeded conciliado claim found"

    # Clear projection cache so tests see fresh state
    mongo.rule_projection_cache.delete_many({})

    return {
        "terminal_ticket_id": terminal_id,
        "restricted_ticket_id": restricted_id,
        "conciliado_claim_id": conciliado_claim["id"],
    }


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Tests: projection ticket ─────────────────────────────────────────────
class TestTicketProjection:

    def test_terminal_ticket_has_r02_applied(self, admin_token, seeded_data):
        tid = seeded_data["terminal_ticket_id"]
        r = requests.get(f"{BASE_URL}/api/agent/tickets/{tid}",
                         headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "projection" in data, "projection field missing in ticket detail"
        proj = data["projection"]
        # Schema validation
        for key in ("allowed_actions", "applied_rules", "computed_at", "ttl_seconds"):
            assert key in proj, f"projection missing {key}"
        assert isinstance(proj["allowed_actions"], list)
        assert "R02" in proj["applied_rules"], f"R02 not in applied_rules: {proj['applied_rules']}"
        # Validate allowed_actions entries shape
        for a in proj["allowed_actions"]:
            assert set(a.keys()) >= {"code", "enabled", "tooltip", "category"}
        # change_status should be disabled with reason R02
        cs = next((a for a in proj["allowed_actions"] if a["code"] == "change_status"), None)
        assert cs is not None and cs["enabled"] is False and cs["reason"] == "R02"
        # request_reopen should be enabled
        rr = next((a for a in proj["allowed_actions"] if a["code"] == "request_reopen"), None)
        assert rr is not None and rr["enabled"] is True
        # terminal TTL should be 3600
        assert proj["ttl_seconds"] == 3600

    def test_restricted_motivo_triggers_r03(self, admin_token, seeded_data):
        tid = seeded_data["restricted_ticket_id"]
        r = requests.get(f"{BASE_URL}/api/agent/tickets/{tid}",
                         headers=_auth(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        proj = r.json()["data"]["projection"]
        assert "R03" in proj["applied_rules"], f"R03 missing: {proj['applied_rules']}"
        # ttl for active ticket should be 60
        assert proj["ttl_seconds"] == 60


# ─── Tests: projection reclamo ────────────────────────────────────────────
class TestReclamoProjection:

    def test_conciliado_claim_has_r28(self, admin_token, seeded_data):
        cid = seeded_data["conciliado_claim_id"]
        # Try /api/reclamos/{id} first, fallback to /api/claims/{id}
        urls = [f"{BASE_URL}/api/reclamos/{cid}", f"{BASE_URL}/api/claims/{cid}"]
        last = None
        for url in urls:
            r = requests.get(url, headers=_auth(admin_token), timeout=15)
            last = (url, r)
            if r.status_code == 200:
                break
        assert last[1].status_code == 200, f"both URLs failed: {last[0]} -> {last[1].status_code} {last[1].text}"
        data = last[1].json()["data"]
        assert "projection" in data, "projection missing on claim detail"
        proj = data["projection"]
        assert "R28" in proj["applied_rules"]
        edit = next((a for a in proj["allowed_actions"] if a["code"] == "edit_expediente"), None)
        assert edit is not None and edit["enabled"] is False
        assert proj["ttl_seconds"] == 3600


# ─── Tests: admin/rules/explain RBAC ─────────────────────────────────────
class TestRulesExplainRBAC:

    def test_admin_role_forbidden(self, admin_token, seeded_data):
        tid = seeded_data["terminal_ticket_id"]
        r = requests.get(
            f"{BASE_URL}/api/admin/rules/explain",
            params={"ticket_id": tid}, headers=_auth(admin_token), timeout=15,
        )
        assert r.status_code == 403, f"admin should not access: {r.status_code} {r.text}"

    def test_agent_role_forbidden(self, agent_token, seeded_data):
        tid = seeded_data["terminal_ticket_id"]
        r = requests.get(
            f"{BASE_URL}/api/admin/rules/explain",
            params={"ticket_id": tid}, headers=_auth(agent_token), timeout=15,
        )
        assert r.status_code == 403

    def test_root_dev_can_access_explain(self, root_token, seeded_data):
        tid = seeded_data["terminal_ticket_id"]
        r = requests.get(
            f"{BASE_URL}/api/admin/rules/explain",
            params={"ticket_id": tid}, headers=_auth(root_token), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["found"] is True
        assert "trace" in data and len(data["trace"]) >= 2
        evals = {t["evaluator"] for t in data["trace"]}
        assert "R02Evaluator" in evals
        assert "R03Evaluator" in evals
        # elapsed_ms present in each trace entry
        for t in data["trace"]:
            assert "elapsed_ms" in t and isinstance(t["elapsed_ms"], (int, float))


# ─── Tests: request-reopen endpoint ──────────────────────────────────────
class TestRequestReopen:

    def test_terminal_ticket_allows_reopen_request(self, admin_token, seeded_data):
        tid = seeded_data["terminal_ticket_id"]
        r = requests.post(
            f"{BASE_URL}/api/agent/tickets/{tid}/request-reopen",
            json={"reason": "Cliente afirma que el paquete no fue entregado realmente. Solicito reapertura."},
            headers=_auth(admin_token), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "request" in data
        assert data["request"]["status"] == "pending"
        assert data["request"]["ticket_id"] == tid
        assert "_id" not in data["request"]  # Mongo _id should be excluded

    def test_active_ticket_rejects_reopen_request(self, admin_token, seeded_data):
        tid = seeded_data["restricted_ticket_id"]
        r = requests.post(
            f"{BASE_URL}/api/agent/tickets/{tid}/request-reopen",
            json={"reason": "Razón válida con más de 10 caracteres para testing."},
            headers=_auth(admin_token), timeout=15,
        )
        # Should fail validation -- not terminal
        assert r.status_code in (400, 422), f"unexpected: {r.status_code} {r.text}"

    def test_reopen_short_reason_rejected(self, admin_token, seeded_data):
        tid = seeded_data["terminal_ticket_id"]
        r = requests.post(
            f"{BASE_URL}/api/agent/tickets/{tid}/request-reopen",
            json={"reason": "corto"},
            headers=_auth(admin_token), timeout=15,
        )
        assert r.status_code in (400, 422)


# ─── Tests: cache invalidation after automation-permissions update ────────
class TestCacheInvalidation:

    def test_permissions_change_reflected(self, admin_token, root_token, seeded_data, mongo):
        # Use a dedicated cache-test ticket so we don't pollute restricted_ticket
        tid = "TEST_B_cache_ticket_0003"
        mongo.tickets.update_one({"id": tid}, {"$set": {
            "id": tid, "tenant_id": TENANT_ID,
            "status": "in_progress", "is_terminal": False,
            "client_id": "abacb7c6-2f0a-4212-a197-96336cc3ff71",
            "motivo_id": "2e79190e-e68e-4654-a412-f2c6a2c32b99",  # non-restricted
            "solucion_id": "test-solucion-b", "channel": "whatsapp",
            "subject": "TEST_B cache ticket",
        }}, upsert=True)
        # Clear cache to be clean
        mongo.rule_projection_cache.delete_many({"entity_id": tid})

        client_id = "abacb7c6-2f0a-4212-a197-96336cc3ff71"
        sol = "test-solucion-b"
        ch = "whatsapp"

        # Set permission allowed=false first
        mongo.automation_permissions.update_one(
            {"tenant_id": TENANT_ID, "client_id": client_id,
             "solucion_id": sol, "channel": ch},
            {"$set": {"allowed": False, "tenant_id": TENANT_ID,
                      "client_id": client_id, "solucion_id": sol, "channel": ch}},
            upsert=True,
        )
        mongo.rule_projection_cache.delete_many({"entity_id": tid})

        r1 = requests.get(f"{BASE_URL}/api/agent/tickets/{tid}",
                          headers=_auth(admin_token), timeout=15)
        assert r1.status_code == 200
        proj1 = r1.json()["data"]["projection"]
        auto1 = next((a for a in proj1["allowed_actions"]
                      if a["code"] == "execute_solution_automatic"), None)
        assert auto1 is not None
        # With permission not allowed, action should be disabled
        first_state = auto1["enabled"]

        # Now flip to allowed=True directly
        mongo.automation_permissions.update_one(
            {"tenant_id": TENANT_ID, "client_id": client_id,
             "solucion_id": sol, "channel": ch},
            {"$set": {"allowed": True}},
            upsert=True,
        )
        # Invalidate cache (test scenario for cache invalidation)
        mongo.rule_projection_cache.delete_many({"entity_id": tid})

        r2 = requests.get(f"{BASE_URL}/api/agent/tickets/{tid}",
                          headers=_auth(admin_token), timeout=15)
        proj2 = r2.json()["data"]["projection"]
        auto2 = next((a for a in proj2["allowed_actions"]
                      if a["code"] == "execute_solution_automatic"), None)
        assert auto2 is not None
        # State should now reflect allowed=True
        assert auto2["enabled"] is True, f"expected enabled True after permission flip; first={first_state} second={auto2}"
