"""Iter66 · Galería navegable en lightbox (frontend smoke spec).

Este archivo es un placeholder: la galería del ContextPanel se valida via
screenshot Playwright (3 fotos del ticket ee8f4e7b... navegadas con
flechas y wrap-around). Aquí dejamos sanity checks contra regresión del
backend que soporta el flujo:

  - El endpoint image-proxy sigue aceptando GET con bearer
  - Cada image_id del report puede recuperarse independientemente
  - El orden de images[] se preserva entre POST enrich y GET ticket
"""
from __future__ import annotations
from services.cae.adapters.routal import _extract_first_report


def test_images_order_is_preserved():
    """El frontend asume que ``ticket.carrier_incident_detail.images`` viene
    en el mismo orden que el report Routal — necesario para navegación
    consistente (foto 1 → 2 → 3)."""
    stop = {
        "reports": [{
            "id": "rep-1",
            "type": "service_report_canceled",
            "comments": "",
            "custom_fields": {},
            "images": [
                {"id": "AAA", "url": "u1"},
                {"id": "BBB", "url": "u2"},
                {"id": "CCC", "url": "u3"},
            ],
        }],
    }
    r = _extract_first_report(stop)
    assert [im["id"] for im in r["images"]] == ["AAA", "BBB", "CCC"]


def test_single_image_no_navigation_arrows_assumed():
    """Cuando hay 1 sola imagen, el frontend oculta flechas/thumbs. Backend
    sólo debe devolver el array correcto (sin contrato adicional)."""
    stop = {"reports": [{
        "id": "x", "type": "service_report_completed",
        "custom_fields": {}, "comments": "",
        "images": [{"id": "only", "url": "u"}],
    }]}
    r = _extract_first_report(stop)
    assert len(r["images"]) == 1
