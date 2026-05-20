"""Anchor adapters — FedEx, DHL, Estafeta, 99 Minutos, Paquetexpress.

Estafeta / 99 Minutos / Paquetexpress remain mock-only for the MVP — they ship
deterministic ``RawCarrierEvent`` based on md5(tracking_id) via ``_BaseAdapter``.

FedEx, DHL and Routal are registered HERE but their REAL classes live in
``fedex.py``, ``dhl.py`` and ``routal.py``. The registration happens via
``_register_real_adapters()`` called from this module's tail (after the stub
classes are defined) — this avoids a circular import because the real adapters
only depend on ``_base.py`` (which has no back-reference to ``anchor_stubs``).
"""
from __future__ import annotations

from core.errors import NotImplementedStubException
from ..interface import CarrierAdapterInterface
from ._base import _BaseAdapter, _now  # noqa: F401 — re-exported for back-compat


# ────────────── FedEx ──────────────
class FedExAdapter(_BaseAdapter):
    carrier_id = "fedex"
    NATIVE_CODES = {
        # raw_code: (canonical, incident_type, is_terminal, requires_action, display_label_es, confidence)
        "PU": ("in_transit",  None,            False, False, "Recolectado",                95),
        "IT": ("in_transit",  None,            False, False, "En tránsito",                98),
        "OD": ("in_transit",  None,            False, False, "En ruta de entrega",         98),
        "DL": ("delivered",   None,            True,  False, "Entregado",                  100),
        "DE": ("exception",   "address_issue", False, True,  "Excepción de dirección",     90),
        "RS": ("returned",    "returned",      True,  True,  "Devuelto al remitente",      95),
        "CA": ("cancelled",   None,            True,  False, "Cancelado",                  100),
    }


# ────────────── DHL ──────────────
class DhlAdapter(_BaseAdapter):
    carrier_id = "dhl"
    NATIVE_CODES = {
        "PR": ("in_transit",  None,            False, False, "Procesado en origen",        95),
        "AF": ("in_transit",  None,            False, False, "Salida de centro",           95),
        "OK": ("delivered",   None,            True,  False, "Entregado",                  100),
        "TD": ("exception",   "customs",       False, True,  "Retenido en aduana",         92),
        "RT": ("returned",    "returned",      True,  True,  "Devuelto",                   95),
    }


# ────────────── Estafeta ──────────────
class EstafetaAdapter(_BaseAdapter):
    carrier_id = "estafeta"
    NATIVE_CODES = {
        "ENT":   ("delivered",   None,             True,  False, "Entregado",              100),
        "TRA":   ("in_transit",  None,             False, False, "En tránsito",            98),
        "DEV":   ("returned",    "returned",       True,  True,  "Devuelto",               95),
        "DOM":   ("exception",   "address_issue",  False, True,  "Domicilio no localizado",90),
        "REJ":   ("exception",   "refused",        False, True,  "Rechazo del destinatario",92),
    }


# ────────────── 99 Minutos ──────────────
class NinetyNineMinAdapter(_BaseAdapter):
    carrier_id = "99min"
    NATIVE_CODES = {
        "IN_ROUTE":  ("in_transit",  None,            False, False, "En ruta",             97),
        "DELIVERED": ("delivered",   None,            True,  False, "Entregado",           100),
        "FAILED":    ("exception",   "failed",        False, True,  "Entrega fallida",     92),
        "RETURNED":  ("returned",    "returned",      True,  True,  "Devuelto",            95),
    }


# ────────────── Paquetexpress ──────────────
class PaquetExpressAdapter(_BaseAdapter):
    carrier_id = "paqex"
    NATIVE_CODES = {
        "01": ("in_transit",  None,             False, False, "Recolectado",               95),
        "02": ("in_transit",  None,             False, False, "En tránsito",               97),
        "03": ("delivered",   None,             True,  False, "Entregado",                 100),
        "04": ("exception",   "address_issue",  False, True,  "Datos incompletos",         88),
        "05": ("returned",    "returned",       True,  True,  "Devuelto al cliente",       93),
    }


ADAPTER_REGISTRY = {
    "fedex":    FedExAdapter,
    "dhl":      DhlAdapter,
    "estafeta": EstafetaAdapter,
    "99min":    NinetyNineMinAdapter,
    "paqex":    PaquetExpressAdapter,
}


def _register_real_adapters() -> None:
    """Real adapters (HTTP-backed) — registered lazily so the import doesn't
    fail if httpx is missing in unrelated environments. They fall back to
    mock_mode automatically when no credentials are configured, so existing
    tests continue to use the deterministic data via ``_BaseAdapter._mock_event``.
    """
    from .routal import RoutalAdapter
    from .dhl import DhlAdapter as RealDhlAdapter
    from .fedex import FedExAdapter as RealFedExAdapter
    ADAPTER_REGISTRY["routal"] = RoutalAdapter
    ADAPTER_REGISTRY["dhl"] = RealDhlAdapter
    ADAPTER_REGISTRY["fedex"] = RealFedExAdapter


_register_real_adapters()


def get_adapter(carrier_id: str) -> CarrierAdapterInterface:
    cls = ADAPTER_REGISTRY.get(carrier_id)
    if not cls:
        raise NotImplementedStubException(f"No adapter registered for carrier '{carrier_id}'")
    return cls()
