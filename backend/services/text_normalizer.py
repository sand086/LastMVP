"""Iter50 — Helpers de normalización de texto para ingesta robusta.

Problema: archivos CSV exportados desde Excel en español llegan en CP1252
(Windows-1252) o Latin-1, no UTF-8. Decodificar con `utf-8` y
`errors="replace"` produce `\\uFFFD` (el char `�` visible en UI).

Estrategia:
  1. **Auto-detect** encoding cuando recibimos bytes (UTF-8 strict → UTF-8 BOM →
     CP1252 → Latin-1). Devuelve el primer decode que no haga `replace`.
  2. **NFC normalize** todos los strings al persistir (composición canónica
     evita que "é" se guarde como "e + combining acute").
  3. **clean_text()** quita `\\uFFFD` residuales (si por alguna razón ya
     llegaron corruptos antes de este módulo).

Pipeline recomendado:
    raw_bytes = upload.read()
    text = decode_bytes_smart(raw_bytes)           # auto-detect
    rows = csv.DictReader(io.StringIO(text))
    for r in rows:
        cleaned = {k: clean_text(v) for k, v in r.items()}

Para persistir en BD, ya viene NFC + sin `\\uFFFD`.
"""
from __future__ import annotations
import unicodedata
from typing import Any

# Orden de intentos. UTF-8 strict primero (mejor caso); CP1252 cubre el 95%
# de exports de Excel en español/portugués/francés; Latin-1 nunca falla
# (cada byte es válido) → garantizamos terminar.
_ENCODING_ATTEMPTS: tuple[str, ...] = (
    "utf-8-sig",  # UTF-8 con BOM (la convención más limpia)
    "utf-8",      # UTF-8 estricto
    "cp1252",     # Windows-1252 (Excel español/europeo)
    "latin-1",    # ISO-8859-1 (fallback total — nunca falla)
)


def decode_bytes_smart(data: bytes) -> str:
    """Intenta decodificar bytes probando encodings comunes en orden.

    Devuelve el primer decode que no genere `UnicodeDecodeError`. Si TODOS
    fallan en strict (imposible con latin-1 al final), cae a `utf-8` con
    `errors="replace"` como último recurso.

    Iter64 — Soporta archivos **mixed-encoding**: cuando los headers están
    en UTF-8 pero algunos datos están en cp1252 (caso típico Excel
    exportado en Windows), preferimos preservar los headers UTF-8 usando
    ``utf-8 errors='replace'`` antes que caer a cp1252 strict, lo cual
    convertiría todos los caracteres UTF-8 multibyte en mojibake (Ã³, Ã©…).
    Los `\\uFFFD` resultantes se limpian luego con ``clean_text``.
    """
    if not data:
        return ""
    # 1. UTF-8 strict (mejor caso: archivo limpio)
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return unicodedata.normalize("NFC", data.decode(enc))
        except UnicodeDecodeError:
            continue
    # 2. Detectar si el archivo tiene UTF-8 multibyte VÁLIDO antes del
    #    primer byte problemático. Si sí → es mixed-encoding (utf-8 base
    #    con celdas cp1252 sueltas, caso Excel Win en MX) y preferimos
    #    preservar el resto del UTF-8 con errors='replace'. Si no hay
    #    NINGÚN UTF-8 multibyte válido → es cp1252 puro → usar cp1252.
    has_utf8_multibyte = False
    i = 0
    while i < min(len(data), 4096):
        b = data[i]
        if b < 0x80:
            i += 1
            continue
        # Intentar decodificar una secuencia UTF-8 multibyte aquí
        for nbytes in (2, 3, 4):
            try:
                data[i:i + nbytes].decode("utf-8")
                has_utf8_multibyte = True
                i += nbytes
                break
            except UnicodeDecodeError:
                continue
        else:
            break  # byte no-ASCII que no inicia UTF-8 válido → cp1252
        if has_utf8_multibyte:
            break

    if has_utf8_multibyte:
        text = data.decode("utf-8", errors="replace")
        return unicodedata.normalize("NFC", text)
    # 3. Fallback: cp1252 / latin-1 (archivos legacy Excel en español)
    for enc in ("cp1252", "latin-1"):
        try:
            return unicodedata.normalize("NFC", data.decode(enc))
        except UnicodeDecodeError:
            continue
    return unicodedata.normalize(
        "NFC", data.decode("utf-8", errors="replace"))


def clean_text(value: Any) -> Any:
    """Normaliza un string a NFC y remueve `\\uFFFD` residual.

    - No-string values se devuelven sin tocar.
    - None → None.
    - Strings vacíos / solo whitespace → ""(devuelve el string original
      trimmed para que `_trim` decida si nulificar).
    - `\\uFFFD` (replacement char) se reemplaza por "" (preferimos limpieza
      antes que `?` ruidoso).
    """
    if value is None or not isinstance(value, str):
        return value
    # NFC composición canónica (é como 1 codepoint, no e+acute)
    s = unicodedata.normalize("NFC", value)
    # Eliminar replacement char residual (de decodes lossy upstream)
    if "\ufffd" in s:
        s = s.replace("\ufffd", "")
    return s


def clean_dict(d: dict[str, Any] | None) -> dict[str, Any] | None:
    """In-place: aplica `clean_text` a todos los valores string del dict
    (recursivo para sub-dicts un nivel). Devuelve el mismo dict.
    """
    if not d:
        return d
    for k, v in d.items():
        if isinstance(v, str):
            d[k] = clean_text(v)
        elif isinstance(v, dict):
            clean_dict(v)
    return d
