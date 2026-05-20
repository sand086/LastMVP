"""Iter64 · Decode robusto para archivos CSV mixed-encoding (Layout V2).

Bug reportado por usuario: CSV de Thinkme tenía las direcciones correctas
pero ``recipient.address`` venía null en DB. Causa raíz: el archivo es
mixed-encoding (headers UTF-8 + algunas celdas cp1252 con caracteres
sueltos como \\xe1 = "á"). El decode caía a cp1252 strict y los headers
UTF-8 (``Dirección Rem.``) se convertían en mojibake (``DirecciÃ³n Rem.``)
que el SLUG_TO_HEADER del parser no matcheaba.

Fix: ``decode_bytes_smart`` ahora detecta este caso (headers UTF-8 válidos
pero datos rotos) y usa ``utf-8 errors='replace'`` en lugar de cp1252
strict, preservando los headers y reemplazando bytes problemáticos por
\\uFFFD (limpiados luego por ``clean_text``).
"""
from __future__ import annotations

from services.text_normalizer import decode_bytes_smart
from services.ingest.layout_v2 import detect_and_parse, normalize_row


def test_utf8_pure_decodes_clean():
    text = "Dirección Rem.,Calle Méndez,Querétaro"
    decoded = decode_bytes_smart(text.encode("utf-8"))
    assert decoded == text


def test_cp1252_pure_decodes_clean():
    """Archivos legacy de Excel-Windows."""
    text = "Dirección Rem.,Calle"
    decoded = decode_bytes_smart(text.encode("cp1252"))
    # NFC normalize garantiza 1 codepoint para ó
    assert "Dirección Rem." in decoded
    assert "DirecciÃ³n" not in decoded


def test_mixed_encoding_preserves_headers():
    """Caso Thinkme: header UTF-8 limpio + datos con bytes cp1252 sueltos."""
    # Header en UTF-8, luego una línea con \xe1 (cp1252 'á' inválido en UTF-8)
    data = ("Dirección Rem.,Estado Rem.\n".encode("utf-8")
            + b"Calle Ju\xe1rez 123,CDMX\n")
    decoded = decode_bytes_smart(data)
    # Headers DEBEN quedar correctos (no DirecciÃ³n)
    assert "Dirección Rem." in decoded
    assert "DirecciÃ³n" not in decoded


def test_thinkme_csv_parses_address_correctly():
    """Smoke test contra el caso real reportado por el usuario."""
    csv_bytes = (
        b"Fecha de entrega,Status,Fecha Creacion,Fecha Embarque,Cliente,"
        b"Contenido,Remitente,Empresa Remitente,Direcci\xc3\xb3n Rem.,"
        b"Estado Rem.,CP Rem.,Tel. Rem.,Email Rem.,Destinatario,"
        b"Empresa Destinatario,Direcci\xc3\xb3n Dest.,Estado Dest.,"
        b"CP Dest.,Tel. Dest.,Email Dest.,Hecho por,Courier,Servicio,"
        b"Tipo de Servicio,Tipo de Entrega,Tracking,Referencia,Alto,"
        b"Ancho,Largo,Peso Real,Peso Vol,Peso Cob,Valor,Seguro,Notas,"
        b"Incidencia\n"
        b"05/05/2026,Incidencia,01/05/2026,04/05/2026,Pilares,Mercanc"
        b"\xe1as,Pilares,Soriana,"  # \xe1 = cp1252 'á' INVALID utf-8
        b'"pilares 541 SN, col. Del Valle",CDMX,3100,55,jair@x,'
        b'Mariana,-,"Calle Constitucion 343",Jalisco,45580,56,jair@x,'
        b"User,Fedex,Eco,Eco,Local,131678,REF,50,20,20,4,4,4,450,N,,"
        b"Direccion Incorrecta\n"
    )
    rows = list(detect_and_parse(csv_bytes, "test.csv"))
    assert len(rows) == 1
    # CRITICAL: el header debe haberse decodificado correctamente
    assert "Dirección Rem." in rows[0], (
        f"keys: {list(rows[0].keys())[:18]}")
    norm = normalize_row(rows[0], line_no=1)
    # ahora address sí debe estar poblada
    assert norm["recipient"]["address"] == "Calle Constitucion 343"
    assert norm["sender"]["address"] == "pilares 541 SN, col. Del Valle"
