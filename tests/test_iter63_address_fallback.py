"""Iter63 · Address Actions tolera address vacía.

Bug reportado por usuario: para guías de Thinkme (Layout V2 con columnas
"Dirección Rem./Dest." vacías) el panel del agente no mostraba el botón
"Maps" ni "Copiar" porque la Row "Dirección" estaba condicionada a
``recipient.address`` truthy.

Cobertura: tests JSX se simulan vía verificación de la lógica
``formatFullAddress`` que ahora se evalúa también cuando ``address`` viene
null/vacío.

Este archivo es un placeholder de cobertura en pytest — el comportamiento
real se valida con screenshot. Los tests aquí son sanity checks contra
regresión del helper backend ``_synthesize_recipient_from_raw_payload``
para que entregue datos compatibles con el render del ContextPanel.
"""
from __future__ import annotations

from services.ingest_service import _synthesize_recipient_from_raw_payload


def test_synthesize_with_only_state_cp_phone():
    """Caso Thinkme: webhook viene sin location.address ni location.label
    pero con state+cp+phone+email. El helper sigue devolviendo algo útil
    aunque address falte, para que la UI muestre Estado/CP y los botones
    de Maps/Copiar."""
    rp = {
        "phone": "5610084233",
        "email": "jair.vargas@thinkme.com.mx",
        "location": {"state": "Nuevo León", "postal_code": "67100",
                     "country_code": "MX"},
    }
    r = _synthesize_recipient_from_raw_payload(rp)
    assert r is not None
    assert r.get("state") == "Nuevo León"
    assert r.get("cp") == "67100"
    assert r.get("phone") == "5610084233"
    # address es None: la UI mostrará "Sin dirección registrada" + botones
    assert r.get("address") is None or r.get("address") == ""


def test_synthesize_returns_none_only_when_truly_empty():
    """No devolver dict vacío — la condición de la UI es ``recipient is
    truthy``, así que helper retorna None para no crear falsos positivos.
    """
    assert _synthesize_recipient_from_raw_payload({}) is None
    assert _synthesize_recipient_from_raw_payload(
        {"location": {}, "label": ""}) is None
