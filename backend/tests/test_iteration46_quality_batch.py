"""Iteration 46 - P2/P3 quality batch regression
Tests: lifespan migration, cancel_job 404/400 diff, /ai-evaluation/health,
SSE json.dumps, manuals (monitor-procesos + Monitoreo de workers section),
incidents catalog regression.
"""
import os
import json
import uuid
import requests
import pytest

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not found")


BASE = _load_base()
API = f"{BASE}/api"

CREDS = {
    "coord": ("yael@me.mx", "LastMile2026"),
    "dev": ("dev@me.mx", "LastMile2026"),
    "agent": ("agente@me.mx", "LastMile2026"),
}


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def coord_token():
    return _login(*CREDS["coord"])


@pytest.fixture(scope="session")
def agent_token():
    return _login(*CREDS["agent"])


@pytest.fixture(scope="session")
def coord_headers(coord_token):
    return {"Authorization": f"Bearer {coord_token}"}


# ─────────── Lifespan / boot smoke ───────────
def test_backend_alive_post_lifespan():
    r = requests.get(f"{API}/health", timeout=10)
    # health endpoint may or may not exist; fallback on /api/auth/me 401
    assert r.status_code in (200, 404)


def test_auth_me_requires_token():
    r = requests.get(f"{API}/auth/me", timeout=10)
    assert r.status_code in (401, 403)


def _extract_list(body):
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("data", "items", "jobs", "results"):
            if key in body and isinstance(body[key], list):
                return body[key]
    return []


# ─────────── cancel_job 404 vs 400 ───────────
def test_cancel_job_404_nonexistent(coord_headers):
    fake = f"nonexistent-{uuid.uuid4().hex[:8]}"
    r = requests.delete(f"{API}/ai-evaluation/jobs/{fake}", headers=coord_headers, timeout=10)
    assert r.status_code == 404
    assert "no encontrado" in r.json().get("detail", "").lower()


def test_cancel_job_400_wrong_state(coord_headers):
    """Find a job in non-En_Cola status (Evaluando/Evaluada/Error/Parcial) and try to cancel."""
    r = requests.get(f"{API}/ai-evaluation/jobs?limit=50", headers=coord_headers, timeout=15)
    assert r.status_code == 200
    jobs = _extract_list(r.json())
    non_queue = [j for j in jobs if j.get("status") in ("Evaluando", "Evaluada", "Error", "Parcial")]
    if not non_queue:
        pytest.skip("No non-En_Cola jobs available to test 400 differentiation")
    job_id = non_queue[0].get("job_id") or non_queue[0].get("id")
    r = requests.delete(f"{API}/ai-evaluation/jobs/{job_id}", headers=coord_headers, timeout=10)
    assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"
    detail = r.json().get("detail", "")
    assert "En_Cola" in detail and "actual" in detail.lower()


def test_cancel_job_200_en_cola(coord_headers):
    r = requests.get(f"{API}/ai-evaluation/jobs?status=En_Cola&limit=5", headers=coord_headers, timeout=15)
    if r.status_code != 200:
        pytest.skip("Cannot list jobs")
    jobs = _extract_list(r.json())
    queued = [j for j in jobs if j.get("status") == "En_Cola"]
    if not queued:
        pytest.skip("No En_Cola jobs to cancel")
    job_id = queued[0].get("job_id") or queued[0].get("id")
    r = requests.delete(f"{API}/ai-evaluation/jobs/{job_id}", headers=coord_headers, timeout=10)
    assert r.status_code == 200
    assert r.json().get("message") == "Job cancelado"


# ─────────── worker_health ───────────
def test_worker_health_shape(coord_headers):
    r = requests.get(f"{API}/ai-evaluation/health", headers=coord_headers, timeout=10)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert data["status"] in ("healthy", "saturated", "stuck")
    w = data["worker"]
    assert isinstance(w["max_concurrent"], int)
    assert isinstance(w["slots_in_use"], int)
    assert isinstance(w["slots_free"], int)
    assert "cron_interval_minutes" in w
    q = data["queue"]
    assert "running" in q and "queued" in q and "oldest_running_age_seconds" in q
    assert "last_terminal_job" in data


def test_worker_health_status_logic(coord_headers):
    r = requests.get(f"{API}/ai-evaluation/health", headers=coord_headers, timeout=10)
    assert r.status_code == 200
    d = r.json()
    mc = d["worker"]["max_concurrent"]
    running = d["queue"]["running"]
    queued = d["queue"]["queued"]
    age = d["queue"]["oldest_running_age_seconds"]
    status = d["status"]
    # Verify logical consistency with branch conditions in route code
    if running >= mc and queued > 0:
        assert status == "saturated"
    elif age is not None and age > 1800:
        assert status == "stuck"
    else:
        assert status == "healthy"


# ─────────── SSE json.dumps ───────────
def test_sse_stream_content_type_and_json(coord_headers):
    fake = f"nonexistent-{uuid.uuid4().hex[:8]}"
    with requests.get(
        f"{API}/ai-evaluation/jobs/{fake}/stream",
        headers=coord_headers,
        stream=True,
        timeout=10,
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        # Read first event which should contain error JSON
        got_json = False
        for raw in r.iter_lines(decode_unicode=True):
            if raw and raw.startswith("data: "):
                payload = raw[6:]
                parsed = json.loads(payload)  # raises if malformed
                assert isinstance(parsed, dict)
                got_json = True
                break
        assert got_json, "No data: line received from SSE stream"


# ─────────── Incidents catalog regression ───────────
def test_incidents_catalog_otro_missing_comment_422(agent_token):
    headers = {"Authorization": f"Bearer {agent_token}"}
    # Find any journey the agent can see
    r = requests.get(f"{API}/journeys?limit=1", headers=headers, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"journeys list failed {r.status_code}")
    data = r.json()
    items = _extract_list(data)
    if not items:
        pytest.skip("No journeys available for incident test")
    journey_id = items[0].get("id") or items[0].get("journey_id")
    payload = {
        "journey_id": journey_id,
        "incident_type": "otro",
        "description": "TEST_ regression iter46",
        "occurred_at": "2026-04-22T04:00:00Z",
    }
    r = requests.post(f"{API}/incidents", json=payload, headers=headers, timeout=10)
    assert r.status_code == 422, f"expected 422 for 'otro' without comentario_asesor, got {r.status_code}: {r.text[:200]}"


def test_incidents_catalog_valid_type(agent_token):
    headers = {"Authorization": f"Bearer {agent_token}"}
    r = requests.get(f"{API}/journeys?limit=1", headers=headers, timeout=15)
    if r.status_code != 200:
        pytest.skip("journeys unavailable")
    items = _extract_list(r.json())
    if not items:
        pytest.skip("no journeys")
    journey_id = items[0].get("id") or items[0].get("journey_id")
    for itype in ["evidencia_incidencia_incorrecta", "autorizacion_tercero_incorrecta", "evidencia_entrega_incorrecta", "notas_incorrectas"]:
        payload = {
            "journey_id": journey_id,
            "incident_type": itype,
            "description": f"TEST_ iter46 {itype}",
            "severity": "media",
            "occurred_at": "2026-04-22T04:00:00Z",
        }
        r = requests.post(f"{API}/incidents", json=payload, headers=headers, timeout=10)
        assert r.status_code in (200, 201), f"{itype}: {r.status_code} {r.text[:200]}"
        inc_id = r.json().get("id") or r.json().get("incident_id")
        if inc_id:
            requests.delete(f"{API}/incidents/{inc_id}", headers=headers, timeout=10)


# ─────────── Manuals ───────────
def test_manuals_count_and_new_slug(coord_headers):
    r = requests.get(f"{API}/manuals", headers=coord_headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    manuals = body if isinstance(body, list) else body.get("data", body.get("items", []))
    assert len(manuals) >= 9, f"expected >=9 manuals got {len(manuals)}"
    slugs = [m.get("slug") for m in manuals]
    assert "monitor-procesos" in slugs
    if isinstance(body, dict) and "total" in body:
        assert body["total"] >= 9


def test_manual_monitor_procesos_sections(coord_headers):
    r = requests.get(f"{API}/manuals/monitor-procesos", headers=coord_headers, timeout=10)
    assert r.status_code == 200
    m = r.json()
    content = m.get("content") or m.get("sections") or m.get("body") or []
    # content is a list of blocks
    titles = []
    if isinstance(content, list):
        titles = [b.get("title", "") for b in content if isinstance(b, dict)]
    else:
        # stringify fallback
        titles = [json.dumps(content)]
    joined = " | ".join(titles) if titles else json.dumps(m)
    for needed in ["Estados de un job", "Filtros disponibles", "Acciones por job", "Arquitectura del worker"]:
        assert needed in joined, f"missing section '{needed}' in monitor-procesos manual. titles={titles}"


def test_manual_api_integraciones_has_health_section(coord_headers):
    r = requests.get(f"{API}/manuals/api-integraciones", headers=coord_headers, timeout=10)
    assert r.status_code == 200
    body = json.dumps(r.json())
    assert "Monitoreo de workers" in body
    assert "/api/ai-evaluation/health" in body
