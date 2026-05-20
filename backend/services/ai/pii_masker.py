"""PII Masker — R36 (PROMPT 26 V2).

Determinístico: la misma entidad obtiene el mismo token en una invocación.
Tokens: <PER_n>, <ADDR_n>, <PHONE_n>, <EMAIL_n>, <COORD_n>, <CARD_n>, <RFC_n>.

mask(text) → (masked_text, mapping) donde mapping permite unmask del output del modelo.
"""
from __future__ import annotations
import re
from typing import Iterable

# Detecta correos
RX_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Detecta teléfonos: +52..., +1..., (55)..., 5512345678, 55-1234-5678, etc.
RX_PHONE = re.compile(r"(?:\+\d{1,3}[\s\-\.]?)?(?:\(?\d{2,4}\)?[\s\-\.]?)?\d{3,4}[\s\-\.]?\d{4}")

# RFC México (12-13 alfanumérico) y CURP (18 alfanumérico)
RX_RFC = re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z\d]{3}\b", re.IGNORECASE)
RX_CURP = re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z\d]\d\b", re.IGNORECASE)

# Tarjeta crédito 13-19 dígitos en formato xxxx-xxxx... o continuo.
# Restringido para no consumir teléfonos: requiere agrupado con separadores
# O 16 dígitos contiguos sin prefijo '+' (las tarjetas reales no tienen "+").
RX_CARD = re.compile(
    r"(?<!\+)\b(?:\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}|\d{16})\b"
)

# Coordenadas lat,lng — requiere los dos números separados por coma
RX_COORD = re.compile(
    r"(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})"
)

# Calle + número + colonia (heurística simple es-MX)
# Ej: "Av. Reforma 123, Col. Centro" / "Calle Pino 45 Col Roma"
RX_ADDRESS = re.compile(
    r"(?:Av\.?|Avenida|Calle|Calz\.?|Calzada|Blvd\.?|Boulevard|Privada|Cda\.?)"
    r"\s+[A-ZÁÉÍÓÚÑa-záéíóúñ\s]+\d+(?:[-\s,]*(?:Col\.?|Colonia|Int\.?|No\.?)[\w\s]+)?",
    re.IGNORECASE,
)

# Lista de campos cuyos valores son nombres conocidos (alimenta detección PER)
KNOWN_NAME_FIELDS = ("destinatario", "cliente_nombre", "remitente", "name",
                     "full_name", "contact_name", "client_name", "agent_name")


def _next_token(prefix: str, counter: dict) -> str:
    n = counter.get(prefix, 0) + 1
    counter[prefix] = n
    return f"<{prefix}_{n}>"


def mask(text: str, *, known_names: Iterable[str] | None = None) -> tuple[str, dict[str, str]]:
    """Devuelve (texto_enmascarado, mapping) donde mapping[token] = original.

    Determinístico dentro de una invocación: misma entidad → mismo token.
    `known_names` es una lista opcional de nombres conocidos (extraídos de campos
    estructurados como destinatario/remitente) que se enmascaran como PER.
    """
    if not isinstance(text, str) or not text:
        return text, {}

    mapping: dict[str, str] = {}
    reverse: dict[str, str] = {}      # original → token (para determinismo)
    counter: dict[str, int] = {}

    def _replace(match_text: str, prefix: str) -> str:
        if match_text in reverse:
            return reverse[match_text]
        token = _next_token(prefix, counter)
        mapping[token] = match_text
        reverse[match_text] = token
        return token

    # 1) Nombres conocidos (los más sensibles) primero
    for name in (known_names or []):
        n = (name or "").strip()
        if len(n) < 3:
            continue
        # Match palabra-completa, case-insensitive
        pattern = re.compile(r"\b" + re.escape(n) + r"\b", re.IGNORECASE)
        text = pattern.sub(lambda m, raw=n: _replace(raw, "PER"), text)

    # 2) Tarjetas (antes que teléfonos: comparten dígitos)
    text = RX_CARD.sub(lambda m: _replace(m.group(0), "CARD"), text)

    # 3) RFC y CURP (oficiales)
    text = RX_CURP.sub(lambda m: _replace(m.group(0), "RFC"), text)
    text = RX_RFC.sub(lambda m: _replace(m.group(0), "RFC"), text)

    # 4) Direcciones (antes que teléfonos: pueden contener números)
    text = RX_ADDRESS.sub(lambda m: _replace(m.group(0), "ADDR"), text)

    # 5) Correos
    text = RX_EMAIL.sub(lambda m: _replace(m.group(0), "EMAIL"), text)

    # 6) Coordenadas (rounding a 2 decimales en el original NO es necesario;
    #    el modelo nunca ve las coords reales)
    text = RX_COORD.sub(lambda m: _replace(m.group(0), "COORD"), text)

    # 7) Teléfonos al final (más permisivo, podría comerse otros números)
    def _phone_sub(m):
        s = m.group(0).strip()
        # Filtrar si tiene <8 dígitos significativos
        digits = re.sub(r"\D", "", s)
        if len(digits) < 8 or len(digits) > 15:
            return s
        return _replace(s, "PHONE")
    text = RX_PHONE.sub(_phone_sub, text)

    return text, mapping


def unmask(text: str, mapping: dict[str, str]) -> str:
    """Restaura los valores reales en el output del modelo.

    Si el modelo emite un token que NO existe en el mapping, lo deja literal
    (el caller debería loggear la alucinación).
    """
    if not text or not mapping:
        return text
    out = text
    # Reemplazar en orden de longitud descendente para no comer subtokens
    for token in sorted(mapping.keys(), key=len, reverse=True):
        out = out.replace(token, mapping[token])
    return out


def detect_unknown_tokens(text: str, mapping: dict[str, str]) -> list[str]:
    """Devuelve tokens <XXX_n> presentes en `text` que NO están en mapping."""
    found = re.findall(r"<(?:PER|ADDR|PHONE|EMAIL|COORD|CARD|RFC)_\d+>", text or "")
    known = set(mapping.keys())
    return [t for t in found if t not in known]


def mask_dict(payload: dict, *, known_name_fields: Iterable[str] = KNOWN_NAME_FIELDS) -> tuple[dict, dict[str, str]]:
    """Enmascara recursivamente todos los strings en un dict, recolectando
    nombres conocidos desde `known_name_fields` para reforzar la detección.
    """
    known_names: list[str] = []

    def _harvest(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in known_name_fields and isinstance(v, str) and v.strip():
                    known_names.append(v.strip())
                _harvest(v)
        elif isinstance(node, list):
            for item in node:
                _harvest(item)

    _harvest(payload)

    mapping: dict[str, str] = {}
    counter: dict[str, int] = {}
    reverse: dict[str, str] = {}

    def _replace(match_text: str, prefix: str) -> str:
        if match_text in reverse:
            return reverse[match_text]
        token = _next_token(prefix, counter)
        mapping[token] = match_text
        reverse[match_text] = token
        return token

    def _mask_str(s: str) -> str:
        # Reusa la misma lógica que mask() pero compartiendo mapping/reverse
        out = s
        for name in known_names:
            n = (name or "").strip()
            if len(n) < 3:
                continue
            out = re.sub(r"\b" + re.escape(n) + r"\b",
                         lambda m, raw=n: _replace(raw, "PER"),
                         out, flags=re.IGNORECASE)
        out = RX_CARD.sub(lambda m: _replace(m.group(0), "CARD"), out)
        out = RX_CURP.sub(lambda m: _replace(m.group(0), "RFC"), out)
        out = RX_RFC.sub(lambda m: _replace(m.group(0), "RFC"), out)
        out = RX_ADDRESS.sub(lambda m: _replace(m.group(0), "ADDR"), out)
        out = RX_EMAIL.sub(lambda m: _replace(m.group(0), "EMAIL"), out)
        out = RX_COORD.sub(lambda m: _replace(m.group(0), "COORD"), out)
        def _phone_sub(m):
            s2 = m.group(0).strip()
            digits = re.sub(r"\D", "", s2)
            if len(digits) < 8 or len(digits) > 15:
                return s2
            return _replace(s2, "PHONE")
        out = RX_PHONE.sub(_phone_sub, out)
        return out

    def _walk(node):
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        if isinstance(node, str):
            return _mask_str(node)
        return node

    masked = _walk(payload)
    return masked, mapping
