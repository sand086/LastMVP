"""
Tests for iteration 44: New incidents catalog enum + comentario_asesor field.
- POST /api/incidents validation for incident_type='otro' requiring comentario_asesor
- Backwards-compat with legacy types
- IncidentBase exposes comentario_asesor as Optional[str]
- Manual 'detalle-ruta-guias' contains the new catalog section
"""
import os
import requests
import pytest
from datetime import datetime, timezone

BASE_URL = os.environ.get("TEST_API_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")
JOURNEY_ID = "86a2ba7f-eecd-4533-a542-57436571ea5d"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    token = r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def coord_session():
    return _login("yael@me.mx", os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"))


@pytest.fixture(scope="module")
def dev_session():
    return _login("dev@me.mx", os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"))


@pytest.fixture(scope="module")
def created_incident_ids():
    ids = []
    yield ids
    # cleanup after tests
    s = _login("yael@me.mx", os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"))
    for iid in ids:
        try:
            s.delete(f"{BASE_URL}/api/incidents/{iid}", timeout=10)
        except Exception:
            pass


def _payload(incident_type="otro", comentario_asesor=None, description="Test incident desc"):
    p = {
        "journey_id": JOURNEY_ID,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "incident_type": incident_type,
        "description": description,
        "severity": "Medio",
        "tracking_number": "TEST-TRACK-001",
        "action_taken": "TEST",
    }
    if comentario_asesor is not None:
        p["comentario_asesor"] = comentario_asesor
    return p


# ── Validation: 'otro' without comentario_asesor → 422 ─────────────────────────
def test_otro_without_comentario_returns_422(coord_session):
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload("otro"))
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    assert "Describe brevemente el tipo de incidencia" in detail, f"Unexpected detail: {detail}"


# ── Validation: 'otro' with whitespace-only comentario → 422 ───────────────────
def test_otro_with_whitespace_comentario_returns_422(coord_session):
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload("otro", comentario_asesor="   "))
    assert r.status_code == 422
    assert "Describe brevemente el tipo de incidencia" in r.json().get("detail", "")


# ── Persistence: 'otro' WITH comentario persists & returns it ──────────────────
def test_otro_with_comentario_persists(coord_session, created_incident_ids):
    comentario = "TEST_Comentario del asesor para tipo otro"
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload("otro", comentario_asesor=comentario))
    assert r.status_code == 200, f"Failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("incident_type") == "otro"
    assert body.get("comentario_asesor") == comentario
    assert "id" in body
    created_incident_ids.append(body["id"])

    # GET by listing for journey
    g = coord_session.get(f"{BASE_URL}/api/incidents", params={"journey_id": JOURNEY_ID})
    assert g.status_code == 200
    found = next((i for i in g.json() if i["id"] == body["id"]), None)
    assert found is not None
    assert found["comentario_asesor"] == comentario


# ── Discard: non-'otro' type with comentario in payload → null in response ─────
def test_non_otro_discards_comentario(coord_session, created_incident_ids):
    r = coord_session.post(
        f"{BASE_URL}/api/incidents",
        json=_payload("notas_incorrectas", comentario_asesor="should be discarded"),
    )
    assert r.status_code == 200, f"Failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("incident_type") == "notas_incorrectas"
    assert body.get("comentario_asesor") is None
    created_incident_ids.append(body["id"])


# ── Backward compat: legacy 'Evidencia Insuficiente' still accepted ────────────
def test_legacy_type_still_accepted(coord_session, created_incident_ids):
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload("Evidencia Insuficiente"))
    assert r.status_code == 200, f"Failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("incident_type") == "Evidencia Insuficiente"
    assert body.get("comentario_asesor") is None
    created_incident_ids.append(body["id"])


# ── Backward compat: legacy capitalized 'Otro' (without enum match) ───────────
def test_legacy_otro_capitalized_no_validation(coord_session, created_incident_ids):
    """Legacy capitalized 'Otro' (catálogo viejo) should NOT trigger comentario validation."""
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload("Otro"))
    assert r.status_code == 200, f"Expected 200 for legacy 'Otro', got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("incident_type") == "Otro"
    created_incident_ids.append(body["id"])


# ── Each new enum type is accepted ─────────────────────────────────────────────
@pytest.mark.parametrize("itype", [
    "evidencia_incidencia_incorrecta",
    "autorizacion_tercero_incorrecta",
    "evidencia_entrega_incorrecta",
    "notas_incorrectas",
])
def test_new_enum_types_accepted(coord_session, created_incident_ids, itype):
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload(itype))
    assert r.status_code == 200, f"Failed for {itype}: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("incident_type") == itype
    assert body.get("comentario_asesor") is None
    created_incident_ids.append(body["id"])


# ── IncidentBase model exposes comentario_asesor as Optional[str] ─────────────
def test_incident_base_has_comentario_asesor_field():
    from models import IncidentBase
    fields = IncidentBase.model_fields
    assert "comentario_asesor" in fields
    info = fields["comentario_asesor"]
    # Default is None, type is Optional[str]
    assert info.default is None


# ── Developer role gets 403 on POST /api/incidents (negative case) ────────────
def test_developer_cannot_create_incident(dev_session):
    r = dev_session.post(f"{BASE_URL}/api/incidents", json=_payload("notas_incorrectas"))
    assert r.status_code == 403, f"Expected 403 for dev role, got {r.status_code}"


# ── Manual 'detalle-ruta-guias' has new catalog section ───────────────────────
def test_manual_detalle_ruta_guias_has_new_catalog(coord_session):
    r = coord_session.get(f"{BASE_URL}/api/manuals/detalle-ruta-guias")
    assert r.status_code == 200, f"Manual not found: {r.status_code} {r.text}"
    content = r.json().get("content", [])
    # Find the section block with title containing "Modal Nueva incidencia"
    found_section = None
    for block in content:
        if block.get("type") == "section" and "Modal" in (block.get("title", "") or "") and "incidencia" in (block.get("title", "") or "").lower():
            found_section = block
            break
    assert found_section is not None, f"Section 'Modal Nueva incidencia' not found in content. Blocks: {[b.get('title') for b in content if b.get('type')=='section']}"
    items = found_section.get("items", [])
    expected_phrases = [
        "evidencia de incidencia",
        "autorizacion",
        "evidencia de entrega",
        "notas",
        "Otro",
    ]
    items_text = " || ".join(items).lower()
    for phrase in expected_phrases:
        assert phrase.lower() in items_text, f"Missing phrase '{phrase}' in items: {items}"


# ── Regression: PUT /api/incidents/{id} still works ───────────────────────────
def test_update_incident_still_works(coord_session, created_incident_ids):
    # create one to update
    r = coord_session.post(f"{BASE_URL}/api/incidents", json=_payload("notas_incorrectas"))
    assert r.status_code == 200
    iid = r.json()["id"]
    created_incident_ids.append(iid)

    upd = coord_session.put(
        f"{BASE_URL}/api/incidents/{iid}",
        json={"description": "Updated TEST description"},
    )
    assert upd.status_code == 200, f"PUT failed: {upd.status_code} {upd.text}"
