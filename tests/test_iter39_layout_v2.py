"""Iter39 — Layout v2 · Ingesta enriquecida (36 columnas en español).

Cobertura:
  * Parser CSV con headers ES (con/sin acentos, case-insensitive).
  * Parser XLSX con openpyxl.
  * Normalizadores: fechas dd/mm/yyyy → ISO, carriers ES → canónico,
    status ES → interno, CP MX 5 dígitos, Y/N → bool.
  * Required fields → ValueError.
  * Endpoint /api/admin/ingest/layout acepta XLSX y CSV.
  * Endpoint /api/admin/ingest/layout/template descarga plantilla.
  * Persistencia híbrida: campos críticos tipados + metadata bag.
"""
from __future__ import annotations
import io

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id


def _bearer(*, user_id, tenant_id, role="admin"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email="t@t")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def env(db):
    tid = new_id()
    uid = new_id()
    cid = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "t", "name": "T",
                                  "status": "active", "created_at": "2026-01-01T00:00:00+00:00"})
    await db.users.insert_one({"id": uid, "tenant_id": tid, "email": "a@t",
                                "role": "admin", "status": "active"})
    await db.clients.insert_one({"id": cid, "tenant_id": tid, "project_id": new_id(),
                                  "name": "Cliente Demo", "ingest_mode": "layout"})
    return {"tid": tid, "uid": uid, "cid": cid, "db": db}


# ──────────────────────────────────────────────────────────────────────
# Normalizadores unitarios
# ──────────────────────────────────────────────────────────────────────

def test_carrier_mapping_es_to_canonical():
    from services.ingest.layout_v2 import _normalize_carrier
    assert _normalize_carrier("Fedex") == "fedex"
    assert _normalize_carrier("DHL") == "dhl"
    assert _normalize_carrier("99 Minutos") == "99minutos"
    assert _normalize_carrier("Paquete Express") == "paquetexpress"
    # Unknown carrier passes through lowercase no-space
    assert _normalize_carrier("OtroCourier") == "otrocourier"


def test_status_normalize_es():
    from services.ingest.layout_v2 import _normalize_status
    assert _normalize_status("Entregado") == "DELIVERED"
    assert _normalize_status("En tránsito") == "IN_TRANSIT"
    assert _normalize_status("En transito") == "IN_TRANSIT"
    assert _normalize_status("Recolectado") == "PICKED_UP"
    # Unknown passes through uppercase
    assert _normalize_status("XYZ_CUSTOM") == "XYZ_CUSTOM"


def test_parse_fecha_dd_mm_yyyy_to_iso():
    from services.ingest.layout_v2 import _parse_fecha_mx
    iso = _parse_fecha_mx("07/05/2026 15:33")
    assert iso is not None and iso.startswith("2026-05-07T15:33:00")
    iso2 = _parse_fecha_mx("01/05/2026")
    assert iso2.startswith("2026-05-01T00:00:00")
    # Bad input returns None
    assert _parse_fecha_mx("not-a-date") is None
    assert _parse_fecha_mx(None) is None
    assert _parse_fecha_mx("") is None


def test_cp_validation_5_digits():
    from services.ingest.layout_v2 import _normalize_cp
    assert _normalize_cp("06800") == "06800"
    assert _normalize_cp("6800") is None  # 4 digits invalid
    assert _normalize_cp(" 06800 ") == "06800"
    assert _normalize_cp("") is None
    assert _normalize_cp(None) is None


def test_yn_bool():
    from services.ingest.layout_v2 import _to_yn_bool
    assert _to_yn_bool("Y") is True
    assert _to_yn_bool("yes") is True
    assert _to_yn_bool("Sí") is True
    assert _to_yn_bool("N") is False
    assert _to_yn_bool("no") is False
    assert _to_yn_bool("") is None
    assert _to_yn_bool(None) is None


def test_required_fields_raises_value_error():
    from services.ingest.layout_v2 import normalize_row
    with pytest.raises(ValueError) as exc:
        normalize_row({"Tracking": "", "Courier": "", "Status": ""}, line_no=2)
    assert "obligatorios" in str(exc.value).lower()


def test_normalize_row_happy_path():
    from services.ingest.layout_v2 import normalize_row
    row = {
        "Tracking": "ABC123",
        "Courier": "Fedex",
        "Status": "Entregado",
        "Fecha de entrega": "07/05/2026 15:33",
        "Fecha Creacion": "01/05/2026 07:36",
        "Cliente": "TMS-001",
        "Remitente": "Juan López",
        "Empresa Remitente": "Acme S.A.",
        "Destinatario": "Aylin Ramirez",
        "Empresa Destinatario": "Walmart Coyoacán",
        "Dirección Dest.": "Av. Universidad 1330",
        "Estado Dest.": "CDMX",
        "CP Dest.": "06800",
        "Tel. Dest.": "+525511112222",
        "Email Dest.": "aylin@example.com",
        "Servicio": "Económico",
        "Tipo de Servicio": "Estándar",
        "Tipo de Entrega": "Local",  # debería ir a metadata
        "Peso Real": "2.5",
        "Peso Volumétrico": "3.0",
        "Peso Cobrado": "3.0",
        "Valor": "1500.00",
        "Seguro": "Y",
        "Notas": "Dejar en conserjería",
        "Incidencia": "N",
        "Contenido": "Ropa",
        "Alto": "20",
        "Ancho": "15",
        "Largo": "30",
        "Hecho por": "Operador 42",
        "Referencia": "REF-OPS-99",
    }
    norm = normalize_row(row, line_no=2)
    # Críticos tipados
    assert norm["tracking_id"] == "ABC123"
    assert norm["carrier_code"] == "fedex"
    assert norm["carrier_status"] == "DELIVERED"
    assert norm["event_at"].startswith("2026-05-07T15:33")  # priorizó delivered
    assert norm["recipient"]["cp"] == "06800"
    assert norm["recipient"]["name"] == "Aylin Ramirez"
    assert norm["sender"]["company"] == "Acme S.A."
    assert norm["service"]["commercial"] == "Económico"
    assert norm["weights"]["real_kg"] == 2.5
    assert norm["declared_value"] == 1500.00
    assert norm["insurance_purchased"] is True
    assert norm["delivery_notes"] == "Dejar en conserjería"
    # Metadata flexible
    assert norm["carrier_meta"]["contenido"] == "Ropa"
    assert norm["carrier_meta"]["alto_cm"] == 20.0
    assert norm["carrier_meta"]["hecho_por"] == "Operador 42"
    assert norm["carrier_meta"]["tipo_entrega"] == "Local"
    assert norm["external_tms_client_id"] == "TMS-001"
    assert norm["external_reference"] == "REF-OPS-99"


def test_normalize_tolerates_header_variations():
    """Slug del header: 'Direccion Rem.' debería resolverse igual que
    'Dirección Rem.' (sin acento + diferente case)."""
    from services.ingest.layout_v2 import normalize_row
    row = {
        "tracking": "Z1",
        "COURIER": "DHL",
        "status": "Entregado",
        "DIRECCION REM.": "Calle Falsa 123",
        "cp dest.": "06800",
    }
    norm = normalize_row(row, line_no=2)
    assert norm["tracking_id"] == "Z1"
    assert norm["carrier_code"] == "dhl"
    assert norm["sender"]["address"] == "Calle Falsa 123"
    assert norm["recipient"]["cp"] == "06800"


# ──────────────────────────────────────────────────────────────────────
# Endpoint /layout
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_download_has_36_headers(env, http_client):
    h = _bearer(user_id=env["uid"], tenant_id=env["tid"], role="admin")
    r = await http_client.get("/api/admin/ingest/layout/template", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "filename=myexcellence_layout_v2.csv" in r.headers["content-disposition"]
    text = r.text
    first_line = text.splitlines()[0]
    headers = first_line.split(",")
    # 35 efectivos en CSV (Tipo de Entrega incluido)
    from services.ingest.layout_v2 import LAYOUT_V2_HEADERS
    assert len(headers) == len(LAYOUT_V2_HEADERS)
    assert "Tracking" in headers
    assert "Courier" in headers
    assert "Status" in headers


@pytest.mark.asyncio
async def test_upload_csv_v2_creates_guia_with_extended_fields(env, http_client):
    h = _bearer(user_id=env["uid"], tenant_id=env["tid"], role="admin")
    # Construyo un CSV con headers v2 y 1 fila
    headers = [
        "Tracking", "Courier", "Status",
        "Fecha de entrega", "CP Dest.", "Destinatario",
        "Empresa Destinatario", "Peso Real", "Valor", "Seguro",
    ]
    row = [
        "BUNDLE-G1", "Fedex", "Entregado",
        "07/05/2026 15:33", "06800", "Aylin Ramirez",
        "Walmart", "2.5", "1500.00", "Y",
    ]
    import csv as _csv
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(headers); w.writerow(row)
    files = {"file": ("layout.csv", buf.getvalue().encode("utf-8"), "text/csv")}
    r = await http_client.post(
        f"/api/admin/ingest/layout?client_id={env['cid']}",
        headers=h, files=files,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["summary"]["rows"] == 1
    assert body["summary"]["created"] == 1
    assert body["layout_version"] == "v2"

    # Verifico que la guía persistió campos extendidos.
    db = env["db"]
    g = await db.guias.find_one({"tenant_id": env["tid"], "tracking_id": "BUNDLE-G1"}, {"_id": 0})
    assert g is not None
    assert g["carrier_code"] == "fedex"
    assert g["carrier_status"] == "DELIVERED"
    assert g["recipient"]["cp"] == "06800"
    assert g["recipient"]["name"] == "Aylin Ramirez"
    assert g["weights"]["real_kg"] == 2.5
    assert g["declared_value"] == 1500.00
    assert g["insurance_purchased"] is True


@pytest.mark.asyncio
async def test_upload_xlsx_v2(env, http_client):
    h = _bearer(user_id=env["uid"], tenant_id=env["tid"], role="admin")
    # Construyo un XLSX en memoria con openpyxl
    import openpyxl  # noqa: PLC0415
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Tracking", "Courier", "Status", "CP Dest.", "Peso Real"])
    ws.append(["XL-001", "DHL", "En tránsito", "11000", "1.2"])
    bio = io.BytesIO()
    wb.save(bio); bio.seek(0)
    files = {"file": ("layout.xlsx", bio.read(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    r = await http_client.post(
        f"/api/admin/ingest/layout?client_id={env['cid']}",
        headers=h, files=files,
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["summary"]["rows"] == 1
    assert body["summary"]["created"] == 1


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(env, http_client):
    h = _bearer(user_id=env["uid"], tenant_id=env["tid"], role="admin")
    files = {"file": ("layout.txt", b"hello", "text/plain")}
    r = await http_client.post(
        f"/api/admin/ingest/layout?client_id={env['cid']}",
        headers=h, files=files,
    )
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_upload_rejects_missing_required_fields(env, http_client):
    h = _bearer(user_id=env["uid"], tenant_id=env["tid"], role="admin")
    # CSV con Tracking y Status pero SIN Courier
    csv_text = "Tracking,Status,CP Dest.\nNOCAR-1,Entregado,06800\n"
    files = {"file": ("layout.csv", csv_text.encode("utf-8"), "text/csv")}
    r = await http_client.post(
        f"/api/admin/ingest/layout?client_id={env['cid']}",
        headers=h, files=files,
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["summary"]["errors"] == 1
    assert "Courier" in body["errors"][0]["error"]
