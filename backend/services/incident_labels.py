"""Iter49 — Mapeo de `incident_type` (clave de sistema) a label legible en español.

El catálogo de keys está definido en `routes/admin_cae_catalog.py::IncidentType`
y se persiste en `tickets.incident_type` por `WorkflowEngine`/`StatusNormalizer`.

Mantener este módulo como **fuente única** del label en español. Si querés
soportar más idiomas, agregar `LABELS_<lang>` y resolver por `Accept-Language`.

Uso:
    from services.incident_labels import enrich_incident_label
    enrich_incident_label(ticket)                        # solo `incident_type`
    enrich_incident_label(ticket, carrier_incidence="…")  # prefiere descripción adapter
    enrich_incident_label_many(items)                    # idem para una lista
"""
from __future__ import annotations

INCIDENT_TYPE_LABELS_ES: dict[str, str] = {
    "address_issue":   "Problema de dirección",
    "refused":         "Rechazo del destinatario",
    "recipient_absent": "Destinatario ausente",
    "customs":         "Retenido en aduana",
    "damage":          "Mercancía dañada",
    "lost":            "Paquete extraviado",
    "failed":          "Entrega fallida",
    "returned":        "Devolución",
    "exception":       "Incidencia genérica",
    "other":           "Otro",
}


def label_for(incident_type: str | None) -> str | None:
    """Devuelve el label en español; si la key es desconocida o nula → None."""
    if not incident_type:
        return None
    return INCIDENT_TYPE_LABELS_ES.get(incident_type, incident_type)


def resolve_incident_label(
    incident_type: str | None,
    carrier_incidence: str | None = None,
) -> str | None:
    """Jerarquía de resolución (más específico primero):

    1. `carrier_incidence` — descripción humana del adapter (ej. "Rechazo del
       destinatario", "Domicilio no localizado"). Es el dato más rico.
    2. label español de `incident_type` (ej. exception → "Incidencia genérica").
    3. `incident_type` crudo si la key es desconocida.
    4. None si nada está disponible.
    """
    if carrier_incidence:
        return carrier_incidence
    return label_for(incident_type)


def enrich_incident_label(
    doc: dict | None,
    carrier_incidence: str | None = None,
) -> dict | None:
    """In-place: agrega `incident_type_label` (label español del enum) y
    `incident_label` (label final resuelto con jerarquía).

    - `incident_type_label`: SIEMPRE el español del enum si hay incident_type
       (útil para debug / vistas que quieran solo el tipo).
    - `incident_label`: la etiqueta final a renderizar (prefiere carrier_incidence).

    No-op si doc es None.
    """
    if not doc:
        return doc
    incident_type = doc.get("incident_type")
    if incident_type:
        doc["incident_type_label"] = label_for(incident_type)
    final = resolve_incident_label(incident_type, carrier_incidence)
    if final:
        doc["incident_label"] = final
    return doc


def enrich_incident_label_many(
    items: list[dict],
    carrier_incidence_by_guia: dict[str, str] | None = None,
) -> list[dict]:
    """Aplica enrich a cada elemento. Si se pasa el mapa
    `{guia_id: carrier_incidence}`, se usa para resolver el label final.
    """
    cmap = carrier_incidence_by_guia or {}
    for it in items:
        gid = it.get("guia_id")
        carrier_incidence = cmap.get(gid) if gid else None
        enrich_incident_label(it, carrier_incidence=carrier_incidence)
    return items

