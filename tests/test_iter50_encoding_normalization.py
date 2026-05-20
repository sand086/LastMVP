"""Iter50 · Normalización de encoding en ingesta + cleanup retroactivo.

Cubre:
  - `text_normalizer.decode_bytes_smart` con UTF-8/CP1252/Latin-1
  - `text_normalizer.clean_text` quita `\\uFFFD`, normaliza NFC
  - `ingest/layout_v2.parse_csv` decodea CP1252 correctamente (caso real)
  - `ingest/layout_v2._trim` aplica clean_text
  - `scripts.fix_encoding_legacy.fix_encoding_in_db` repara guías con `�`
  - Endpoint `POST /api/admin/maintenance/fix-encoding` (RBAC superadmin+)
"""
from __future__ import annotations
import unicodedata
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token, hash_password
from core.uuid import new_id
from services.text_normalizer import (
    clean_text, clean_dict, decode_bytes_smart,
)
from services.ingest.layout_v2 import _trim, parse_csv
from scripts.fix_encoding_legacy import _apply_repairs, fix_encoding_in_db


# ─────────────────────────── Unit tests ─────────────────────────────
class TestDecodeBytesSmart:
    def test_utf8_strict_is_preferred(self):
        s = "Dirección Incorrecta"
        result = decode_bytes_smart(s.encode("utf-8"))
        assert result == s

    def test_utf8_with_bom_is_handled(self):
        s = "Rechazo"
        result = decode_bytes_smart(b"\xef\xbb\xbf" + s.encode("utf-8"))
        assert result == s

    def test_cp1252_excel_export_decoded_correctly(self):
        """Caso REAL del bug: Excel español exporta cp1252.
        Antes producía 'Direcci�n', ahora 'Dirección'.
        """
        s = "Dirección Incorrecta · Notificación pendiente"
        bytes_cp1252 = s.encode("cp1252")
        # Verificamos que NO sea UTF-8 válido (sino el test no probaría nada)
        with pytest.raises(UnicodeDecodeError):
            bytes_cp1252.decode("utf-8")
        # Y que decode_bytes_smart sí lo recupera
        result = decode_bytes_smart(bytes_cp1252)
        assert result == s

    def test_latin1_fallback_never_fails(self):
        # Bytes raros que no son ni utf-8 ni cp1252 válido perfectamente
        data = bytes(range(128, 256))
        result = decode_bytes_smart(data)
        assert isinstance(result, str)
        assert len(result) > 0  # algún decode tuvo éxito

    def test_empty_bytes_returns_empty_str(self):
        assert decode_bytes_smart(b"") == ""

    def test_result_is_nfc_normalized(self):
        # NFD: 'é' como 'e' + combining acute (2 codepoints)
        nfd = "Direccio\u0301n".encode("utf-8")
        result = decode_bytes_smart(nfd)
        # NFC: 'é' como 1 codepoint
        assert result == unicodedata.normalize("NFC", "Direccion".replace(
            "o", "ó"))
        assert "\u0301" not in result  # no combining marks sueltos


class TestCleanText:
    def test_removes_replacement_char(self):
        assert clean_text("Direcci\ufffdn") == "Direccin"

    def test_nfc_normalizes(self):
        nfd = "Direccio\u0301n"
        result = clean_text(nfd)
        assert "\u0301" not in result
        assert "ó" in result

    def test_non_string_passthrough(self):
        assert clean_text(None) is None
        assert clean_text(123) == 123
        assert clean_text(True) is True

    def test_empty_string(self):
        assert clean_text("") == ""


class TestCleanDict:
    def test_recurses_one_level(self):
        d = {
            "a": "Direcci\ufffdn",
            "b": {"address": "Calle\ufffd 5"},
            "c": 42,
            "d": None,
        }
        clean_dict(d)
        assert d["a"] == "Direccin"
        assert d["b"]["address"] == "Calle 5"
        assert d["c"] == 42
        assert d["d"] is None


class TestParseCsvAutoEncoding:
    def test_parses_cp1252_csv_correctly(self):
        """Bug real: CSV exportado en cp1252 con tildes."""
        rows = "Tracking,Status,Notas\nABC123,Entregado,Dirección Incorrecta\n"
        bytes_cp1252 = rows.encode("cp1252")
        result = list(parse_csv(bytes_cp1252))
        assert len(result) == 1
        assert result[0]["Notas"] == "Dirección Incorrecta"

    def test_parses_utf8_bom_csv(self):
        rows = "Tracking,Status\nABC123,Rechazo\n"
        bytes_bom = b"\xef\xbb\xbf" + rows.encode("utf-8")
        result = list(parse_csv(bytes_bom))
        assert len(result) == 1
        assert result[0]["Status"] == "Rechazo"


class TestTrimAppliesCleanText:
    def test_trim_removes_replacement_char(self):
        assert _trim("Direcci\ufffdn Incorrecta") == "Direccin Incorrecta"

    def test_trim_nfc_normalizes(self):
        result = _trim("Direccio\u0301n")
        assert "\u0301" not in result
        assert result == "Dirección"


class TestLegacyRepairs:
    def test_repairs_direccin_to_direccion(self):
        out = _apply_repairs("Direcci\ufffdn Incorrecta")
        # Tras quitar \uFFFD queda "Direccin", el diccionario lo repara
        assert out == "Dirección Incorrecta"

    def test_preserves_capitalization(self):
        # "direcci<FFFD>n" minúsculas → "dirección"
        out = _apply_repairs("direcci\ufffdn pendiente")
        assert out == "dirección pendiente"

    def test_unknown_word_just_drops_replacement_char(self):
        # "tokenrarox<FFFD>z" no está en diccionario → solo quita \uFFFD
        out = _apply_repairs("token\ufffdrar")
        assert out == "tokenrar"

    def test_idempotent_no_replacement_char(self):
        # Sin \uFFFD → no toca
        out = _apply_repairs("Dirección correcta")
        assert out == "Dirección correcta"

    def test_repairs_multiple_words(self):
        out = _apply_repairs("Direcci\ufffdn y devoluci\ufffdn")
        assert out == "Dirección y devolución"


# ─────────────────────────── DB cleanup ─────────────────────────────
@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as ac:
        yield ac


def _bearer(*, user_id: str, tenant_id: str, role: str = "superadmin",
            email: str = "su@t.io"):
    tok = create_access_token(user_id=user_id, tenant_id=tenant_id,
                              role=role, email=email)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
async def env(db):
    t_id = new_id()
    su_id = new_id()
    agent_id = new_id()
    pwd = hash_password("x")
    await db.tenants.insert_one(
        {"id": t_id, "slug": "t-50", "name": "T-50", "status": "active"})
    await db.users.insert_many([
        {"id": su_id, "tenant_id": t_id,
         "email": "su@t-50.io", "role": "superadmin",
         "password_hash": pwd, "status": "active"},
        {"id": agent_id, "tenant_id": t_id,
         "email": "agent@t-50.io", "role": "agent",
         "password_hash": pwd, "status": "active"},
    ])
    return {"tenant_id": t_id, "superadmin_id": su_id, "agent_id": agent_id}


@pytest.mark.asyncio
class TestFixEncodingInDb:
    async def test_dry_run_reports_without_persisting(self, db, env):
        t_id = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t_id, "tracking_id": "T1",
            "carrier_incidence": "Direcci\ufffdn Incorrecta",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        stats = await fix_encoding_in_db(dry_run=True, tenant_id=t_id)
        assert stats["scanned"] >= 1
        assert stats["repaired"] == 1
        # No debe persistir
        doc = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert "\ufffd" in doc["carrier_incidence"]  # sigue corrupto

    async def test_apply_persists_repairs(self, db, env):
        t_id = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t_id, "tracking_id": "T2",
            "carrier_incidence": "Direcci\ufffdn Incorrecta",
            "delivery_notes": "Devoluci\ufffdn requerida",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        stats = await fix_encoding_in_db(dry_run=False, tenant_id=t_id)
        assert stats["repaired"] == 1
        doc = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert "\ufffd" not in doc["carrier_incidence"]
        assert doc["carrier_incidence"] == "Dirección Incorrecta"
        assert doc["delivery_notes"] == "Devolución requerida"

    async def test_tenant_scope_isolation(self, db, env):
        t_id = env["tenant_id"]
        other_t = new_id()
        await db.tenants.insert_one(
            {"id": other_t, "slug": "other", "name": "Other",
             "status": "active"})
        gid_mine = new_id()
        gid_other = new_id()
        now = datetime.now(timezone.utc).isoformat()
        await db.guias.insert_many([
            {"id": gid_mine, "tenant_id": t_id, "tracking_id": "T3",
             "carrier_incidence": "Direcci\ufffdn X", "created_at": now},
            {"id": gid_other, "tenant_id": other_t, "tracking_id": "T4",
             "carrier_incidence": "Direcci\ufffdn Y", "created_at": now},
        ])
        stats = await fix_encoding_in_db(dry_run=False, tenant_id=t_id)
        assert stats["repaired"] == 1
        # La guía del otro tenant queda intacta
        other = await db.guias.find_one({"id": gid_other}, {"_id": 0})
        assert "\ufffd" in other["carrier_incidence"]

    async def test_idempotent_second_run_zero_repairs(self, db, env):
        t_id = env["tenant_id"]
        await db.guias.insert_one({
            "id": new_id(), "tenant_id": t_id, "tracking_id": "T5",
            "carrier_incidence": "Direcci\ufffdn",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fix_encoding_in_db(dry_run=False, tenant_id=t_id)
        stats2 = await fix_encoding_in_db(dry_run=False, tenant_id=t_id)
        assert stats2["repaired"] == 0


@pytest.mark.asyncio
class TestMaintenanceEndpoint:
    async def test_superadmin_can_fix(self, db, env, http_client):
        t_id = env["tenant_id"]
        await db.guias.insert_one({
            "id": new_id(), "tenant_id": t_id, "tracking_id": "T6",
            "carrier_incidence": "Direcci\ufffdn rota",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        headers = _bearer(user_id=env["superadmin_id"], tenant_id=t_id)
        r = await http_client.post(
            "/api/admin/maintenance/fix-encoding?dry_run=false",
            headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["repaired"] == 1
        assert len(data["samples"]) == 1
        assert data["samples"][0]["after"] == "Dirección rota"

    async def test_agent_forbidden(self, env, http_client):
        headers = _bearer(user_id=env["agent_id"],
                          tenant_id=env["tenant_id"], role="agent")
        r = await http_client.post(
            "/api/admin/maintenance/fix-encoding",
            headers=headers)
        assert r.status_code == 403, r.text

    async def test_dry_run_default(self, db, env, http_client):
        t_id = env["tenant_id"]
        gid = new_id()
        await db.guias.insert_one({
            "id": gid, "tenant_id": t_id, "tracking_id": "T7",
            "carrier_incidence": "Direcci\ufffdn dry",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        headers = _bearer(user_id=env["superadmin_id"], tenant_id=t_id)
        r = await http_client.post(
            "/api/admin/maintenance/fix-encoding", headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["repaired"] == 1
        # No persiste por dry_run=true default
        doc = await db.guias.find_one({"id": gid}, {"_id": 0})
        assert "\ufffd" in doc["carrier_incidence"]
