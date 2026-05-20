"""WhatsApp deeplink builder — PROMPT 11.

Cliente toca el botón → se abre wa.me con el cuerpo prellenado en su WhatsApp.
NO hace HTTP a la API de WhatsApp Business (eso vive en PROMPT_20 con Twilio).

R26 — el agente queda como auditor: el deeplink se registra en timeline_events
para tener trazabilidad del momento en que se generó.
"""
from __future__ import annotations
from urllib.parse import quote
import re


_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # E.164 simplificado


def normalize_phone(phone: str) -> str:
    """Devuelve el número sin '+' y sin espacios. Lanza ValueError si es inválido."""
    if not phone:
        raise ValueError("phone vacío")
    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone.strip())
    if not _PHONE_RE.match(cleaned):
        raise ValueError(f"phone inválido: {phone!r}")
    return cleaned.lstrip("+")


def build_wa_deeplink(phone: str, text: str) -> str:
    """Construye una URL https://wa.me/<phone>?text=<urlencoded>.

    Ejemplo:
      build_wa_deeplink("+5215551234567", "Hola Juan")
      → "https://wa.me/5215551234567?text=Hola%20Juan"
    """
    digits = normalize_phone(phone)
    return f"https://wa.me/{digits}?text={quote(text or '', safe='')}"
