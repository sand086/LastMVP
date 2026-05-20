"""Layout v2 — Ingesta enriquecida MyExcellence (Iter39).

Reemplaza la plantilla CSV minimalista (5 columnas: tracking_id, carrier_code,
carrier_status, carrier_status_description, event_at) por una plantilla rica
de **36 columnas en español** que captura la guía de embarque completa:

  - 3 fechas operativas (creación, embarque, entrega).
  - Identidad de cliente externo (id TMS interno).
  - 7 campos remitente (persona + empresa + dirección + estado + CP + tel + email).
  - 7 campos destinatario (idem).
  - 4 campos servicio (servicio comercial, tipo de servicio, courier, tracking).
  - 3 campos pesos (real, volumétrico, cobrado).
  - 2 económicos (valor declarado, seguro Y/N).
  - 2 operativos (notas, incidencia carrier).
  - 5 metadata flexibles (contenido, alto, ancho, largo, hecho por).

Choice del PO (Iter39):
  - 4.c — Estrategia híbrida: críticos al doc principal + resto en `carrier_meta`.
  - 6.a — Reemplaza el layout v1 (no convivencia).

Layout headers son los EXACTOS del XLS que sube el cliente — case sensitive,
acentos preservados. El normalizador acepta variaciones razonables (con/sin
acentos, minúsculas, espacios extra) gracias a `_slugify_header()`.
"""
from __future__ import annotations
import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, Iterable

# ---------- Headers canónicos (36 columnas efectivas) ---------------------

LAYOUT_V2_HEADERS: list[str] = [
    "Fecha de entrega",
    "Status",
    "Fecha Creacion",
    "Fecha Embarque",
    "Cliente",
    "Contenido",
    "Remitente",
    "Empresa Remitente",
    "Dirección Rem.",
    "Estado Rem.",
    "CP Rem.",
    "Tel. Rem.",
    "Email Rem.",
    "Destinatario",
    "Empresa Destinatario",
    "Dirección Dest.",
    "Estado Dest.",
    "CP Dest.",
    "Tel. Dest.",
    "Email Dest.",
    "Hecho por",
    "Courier",
    "Servicio",
    "Tipo de Servicio",
    # "Tipo de Entrega" — contexto dice "Omitir dato"; lo aceptamos en parsing
    # pero NO persistimos.
    "Tipo de Entrega",
    "Tracking",
    "Referencia",
    "Alto",
    "Ancho",
    "Largo",
    "Peso Real",
    "Peso Volumétrico",
    "Peso Cobrado",
    "Valor",
    "Seguro",
    "Notas",
    "Incidencia",
]

REQUIRED_FIELDS = ["Tracking", "Courier", "Status"]


# ---------- Normalizers --------------------------------------------------

def _slugify_header(h: str) -> str:
    """Convierte 'Fecha de Entrega' → 'fecha_de_entrega'. Tolerante a acentos,
    case, espacios extra."""
    if not h:
        return ""
    # Eliminar acentos común
    repl = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
    s = h.translate(repl).lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s


# Slug → header canónico (para resolver headers del archivo del cliente).
_SLUG_TO_HEADER: dict[str, str] = {_slugify_header(h): h for h in LAYOUT_V2_HEADERS}


# Carrier ES → código canónico lowercase.
CARRIER_MAP: dict[str, str] = {
    "fedex": "fedex", "fed ex": "fedex",
    "dhl": "dhl",
    "estafeta": "estafeta",
    "paquetexpress": "paquetexpress", "paquete express": "paquetexpress",
    "99minutos": "99minutos", "99_minutos": "99minutos", "99 minutos": "99minutos",
    "ups": "ups",
    "redpack": "redpack",
    "ivoy": "ivoy",
    "treggo": "treggo",
}


# Status ES (carrier-side) → canonical interno. La engine ya tiene mapping
# carrier-status → internal_status; acá normalizamos sólo el string que viene
# del archivo para que la engine reconozca.
STATUS_NORMALIZE: dict[str, str] = {
    "entregado": "DELIVERED",
    "delivered": "DELIVERED",
    "en transito": "IN_TRANSIT",
    "en tránsito": "IN_TRANSIT",
    "in_transit": "IN_TRANSIT",
    "in transit": "IN_TRANSIT",
    "recolectado": "PICKED_UP",
    "recogido": "PICKED_UP",
    "picked_up": "PICKED_UP",
    "en reparto": "OUT_FOR_DELIVERY",
    "en ruta": "OUT_FOR_DELIVERY",
    "out_for_delivery": "OUT_FOR_DELIVERY",
    "rechazado": "RETURNED",
    "devuelto": "RETURNED",
    "returned": "RETURNED",
    "perdido": "LOST",
    "extraviado": "LOST",
    "lost": "LOST",
    "incidencia": "EXCEPTION",
    "exception": "EXCEPTION",
    "en espera": "PENDING",
    "pendiente": "PENDING",
}


def _normalize_carrier(raw: str) -> str:
    key = (raw or "").strip().lower()
    return CARRIER_MAP.get(key, key.replace(" ", ""))


def _normalize_status(raw: str) -> str:
    key = (raw or "").strip().lower()
    return STATUS_NORMALIZE.get(key, raw.strip().upper() if raw else "")


def _parse_fecha_mx(raw: Any) -> str | None:
    """Acepta dd/mm/yyyy [hh:mm[:ss]] o ISO. Devuelve ISO UTC string.
    Si está vacío o no parsea, devuelve None.

    El cliente trabaja en CDMX (UTC-6); no hacemos timezone math, asumimos
    que el string ya es local. Para SLA y cálculos, el frontend usa
    `formatFechaMX` que convierte ISO → CDMX display.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=timezone.utc)
        return raw.isoformat()
    s = str(raw).strip()
    if not s:
        return None
    # Try ISO first
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        pass
    # dd/mm/yyyy [hh:mm]
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:  # noqa: BLE001
            continue
    return None


def _to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", "."))
    except Exception:  # noqa: BLE001
        return None


def _to_yn_bool(raw: Any) -> bool | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip().lower()
    if s in ("y", "yes", "sí", "si", "true", "1"):
        return True
    if s in ("n", "no", "false", "0"):
        return False
    return None


def _trim(raw: Any) -> str | None:
    if raw is None:
        return None
    # Iter50 — clean_text aplica NFC normalize + remueve \uFFFD residual
    # (en caso de que el CSV ya haya llegado lossy de upstream).
    from services.text_normalizer import clean_text
    s = clean_text(str(raw)).strip()
    return s or None


def _normalize_cp(raw: Any) -> str | None:
    """Código Postal MX — 5 dígitos. Devuelve None si no cumple."""
    s = _trim(raw)
    if not s:
        return None
    s = re.sub(r"\D", "", s)
    return s if len(s) == 5 else None


# ---------- Row mapper ---------------------------------------------------

def normalize_row(raw_row: dict[str, Any], line_no: int) -> dict[str, Any]:
    """Convierte un row del XLSX/CSV (keys = headers en español) a dict
    canónico para `process_event(... carrier_meta=...)`.

    Si faltan campos REQUIRED → raises ValueError con mensaje explícito.
    """
    # Resolver headers usando slugify para tolerar variaciones del archivo.
    # raw_row.keys() → strings tal como vienen del archivo. Mapeamos al
    # header canónico.
    resolved: dict[str, Any] = {}
    for k, v in raw_row.items():
        canon = _SLUG_TO_HEADER.get(_slugify_header(k or ""))
        if canon:
            resolved[canon] = v

    # Required
    tracking = _trim(resolved.get("Tracking"))
    courier = _normalize_carrier(_trim(resolved.get("Courier")) or "")
    status_raw = _trim(resolved.get("Status"))
    missing = []
    if not tracking:
        missing.append("Tracking")
    if not courier:
        missing.append("Courier")
    if not status_raw:
        missing.append("Status")
    if missing:
        raise ValueError(
            f"Fila {line_no}: faltan campos obligatorios: {', '.join(missing)}",
        )

    status_canonical = _normalize_status(status_raw)

    # Fechas
    delivered_at = _parse_fecha_mx(resolved.get("Fecha de entrega"))
    created_at_external = _parse_fecha_mx(resolved.get("Fecha Creacion"))
    shipped_at = _parse_fecha_mx(resolved.get("Fecha Embarque"))

    # event_at: priorizamos la fecha de entrega si terminal, sino shipped, sino now.
    event_at = delivered_at or shipped_at or created_at_external

    # Sender (remitente)
    sender = {
        "name": _trim(resolved.get("Remitente")),
        "company": _trim(resolved.get("Empresa Remitente")),
        "address": _trim(resolved.get("Dirección Rem.")),
        "state": _trim(resolved.get("Estado Rem.")),
        "cp": _normalize_cp(resolved.get("CP Rem.")),
        "phone": _trim(resolved.get("Tel. Rem.")),
        "email": _trim(resolved.get("Email Rem.")),
    }
    # Recipient (destinatario)
    recipient = {
        "name": _trim(resolved.get("Destinatario")),
        "company": _trim(resolved.get("Empresa Destinatario")),
        "address": _trim(resolved.get("Dirección Dest.")),
        "state": _trim(resolved.get("Estado Dest.")),
        "cp": _normalize_cp(resolved.get("CP Dest.")),
        "phone": _trim(resolved.get("Tel. Dest.")),
        "email": _trim(resolved.get("Email Dest.")),
    }
    # Service
    service = {
        "commercial": _trim(resolved.get("Servicio")),
        "type_internal": _trim(resolved.get("Tipo de Servicio")),
    }
    # Pesos
    weights = {
        "real_kg": _to_float(resolved.get("Peso Real")),
        "volumetric_kg": _to_float(resolved.get("Peso Volumétrico")),
        "charged_kg": _to_float(resolved.get("Peso Cobrado")),
    }
    # Económico
    declared_value = _to_float(resolved.get("Valor"))
    insurance_purchased = _to_yn_bool(resolved.get("Seguro"))

    # Metadata flexible (no-tipado): contenido, dimensiones, hecho_por,
    # tipo_entrega (omitir igual lo guardamos por auditoría).
    metadata = {
        "contenido": _trim(resolved.get("Contenido")),
        "alto_cm": _to_float(resolved.get("Alto")),
        "ancho_cm": _to_float(resolved.get("Ancho")),
        "largo_cm": _to_float(resolved.get("Largo")),
        "hecho_por": _trim(resolved.get("Hecho por")),
        "tipo_entrega": _trim(resolved.get("Tipo de Entrega")),
    }
    # Drop Nones para que el doc Mongo sea más limpio.
    metadata = {k: v for k, v in metadata.items() if v is not None}

    return {
        "tracking_id": tracking,
        "carrier_code": courier,
        "carrier_status": status_canonical,
        "carrier_status_description": _trim(resolved.get("Notas")),
        "raw_code": _trim(resolved.get("Status")),  # preservamos el original
        "event_at": event_at,
        # Extended structured fields (Iter39 — hybrid persistence):
        "external_tms_client_id": _trim(resolved.get("Cliente")),
        "external_reference": _trim(resolved.get("Referencia")),
        "delivered_at_external": delivered_at,
        "shipped_at_external": shipped_at,
        "created_at_external": created_at_external,
        "sender": sender,
        "recipient": recipient,
        "service": service,
        "weights": weights,
        "declared_value": declared_value,
        "insurance_purchased": insurance_purchased,
        "delivery_notes": _trim(resolved.get("Notas")),
        "carrier_incidence": _trim(resolved.get("Incidencia")),
        # `carrier_meta` is the catch-all bag for non-typed extras.
        "carrier_meta": metadata,
    }


# ---------- File parsers -------------------------------------------------

def parse_csv(file_bytes: bytes) -> Iterable[dict[str, Any]]:
    """Yields dict[header] per row from a CSV.

    Iter50 — auto-detecta encoding (UTF-8 BOM → UTF-8 → CP1252 → Latin-1).
    Excel en español suele exportar CP1252, no UTF-8.
    """
    from services.text_normalizer import decode_bytes_smart
    text = decode_bytes_smart(file_bytes)
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        yield row


def parse_xlsx(file_bytes: bytes) -> Iterable[dict[str, Any]]:
    """Yields dict[header] per row from XLSX (first sheet only).
    openpyxl is imported lazily to avoid penalizing tests that don't need it.
    """
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = list(next(rows_iter))
    except StopIteration:
        return
    headers = [str(h or "").strip() for h in headers]
    for raw in rows_iter:
        # Skip fully empty rows.
        if not any(c is not None and c != "" for c in raw):
            continue
        row_dict = {headers[i]: raw[i] for i in range(min(len(headers), len(raw)))}
        yield row_dict


def detect_and_parse(file_bytes: bytes, filename: str) -> Iterable[dict[str, Any]]:
    """Routes by file extension. Raises ValueError on unsupported file."""
    fn = (filename or "").lower()
    if fn.endswith(".xlsx") or fn.endswith(".xlsm"):
        return parse_xlsx(file_bytes)
    if fn.endswith(".csv"):
        return parse_csv(file_bytes)
    raise ValueError("Solo se aceptan archivos .csv, .xlsx o .xlsm")


def build_template_csv() -> str:
    """Returns a CSV string with all headers and one example row (empty)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(LAYOUT_V2_HEADERS)
    # Una fila de ejemplo con los campos obligatorios marcados.
    example = {
        "Tracking": "ABC123",
        "Courier": "fedex",
        "Status": "Entregado",
        "Fecha de entrega": "07/05/2026 15:33",
        "Fecha Creacion": "01/05/2026 07:36",
        "Fecha Embarque": "05/05/2026 17:44",
        "CP Dest.": "06800",
    }
    writer.writerow([example.get(h, "") for h in LAYOUT_V2_HEADERS])
    return out.getvalue()
