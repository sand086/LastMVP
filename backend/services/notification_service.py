"""NotificationService — PROMPT 11.

Encapsula los canales de salida de MyExcellence:
  * Email transaccional via Resend (síncrono SDK envuelto en asyncio.to_thread)
  * WhatsApp deeplink (sin API — devuelve URL para que el agente la abra)

Diseño:
  - Si RESEND_API_KEY está vacío (CI / dev sin Resend), `send_email` devuelve
    un id mock y no rompe los tests. El comportamiento queda registrado.
  - Cualquier error real de Resend devuelve un dict con `ok=False` y la razón.
  - Templates HTML mínimos in-line — los emails nunca cargan CSS externo.
"""
from __future__ import annotations
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import resend

from core.config import RESEND_API_KEY, SENDER_EMAIL, SENDER_NAME
from core.logger import log


@dataclass
class EmailResult:
    ok: bool
    id: Optional[str]
    reason: Optional[str] = None
    mock: bool = False

    def to_dict(self) -> dict:
        return {"ok": self.ok, "id": self.id, "reason": self.reason, "mock": self.mock}


def _from_header() -> str:
    name = SENDER_NAME or "MyExcellence"
    return f"{name} <{SENDER_EMAIL}>"


def _key() -> str:
    """Pull the key fresh from the env so tests can patch it."""
    return os.environ.get("RESEND_API_KEY", RESEND_API_KEY or "")


async def send_email(
    *,
    to: str | list[str],
    subject: str,
    html: str,
    text: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    reply_to: Optional[str] = None,
    tags: Optional[dict] = None,
    tenant_id: Optional[str] = None,
) -> EmailResult:
    """Send a transactional email through Resend.

    Returns ``EmailResult.mock=True`` when no API key is configured (tenant-level
    nor env-level) — útil para CI y dev. Logs both success and failure.

    iter45 — cc, bcc, reply_to.
    iter46 — multi-tenant: si ``tenant_id`` se provee, intenta cargar las
    credenciales del tenant (Resend + sender identity) y cae a env si no hay.
    """
    recipients = [to] if isinstance(to, str) else list(to)
    cc_list = list(cc) if cc else []
    bcc_list = list(bcc) if bcc else []

    # iter46 — resolución de credenciales por tenant (con fallback a env)
    if tenant_id:
        from services.tenant_email_settings import resolve_credentials
        creds = await resolve_credentials(tenant_id)
        api_key = creds["api_key"]
        from_header = (
            f"{creds['sender_name']} <{creds['sender_email']}>"
            if creds["sender_name"] and creds["sender_email"]
            else creds.get("sender_email") or _from_header()
        )
        effective_reply_to = reply_to or creds.get("reply_to_default") or None
        creds_source = creds["source"]
    else:
        api_key = _key()
        from_header = _from_header()
        effective_reply_to = reply_to
        creds_source = "env"

    if not api_key:
        mock_id = f"mock_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        log.info("email_mock_sent", extra={"context": {
            "to": recipients, "cc": cc_list, "bcc": bcc_list,
            "subject": subject, "mock_id": mock_id,
            "creds_source": creds_source,
        }})
        return EmailResult(ok=True, id=mock_id, mock=True)

    resend.api_key = api_key
    params: dict = {
        "from": from_header,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if cc_list:
        params["cc"] = cc_list
    if bcc_list:
        params["bcc"] = bcc_list
    if effective_reply_to:
        params["reply_to"] = effective_reply_to
    if text:
        params["text"] = text
    if tags:
        params["tags"] = [{"name": k, "value": str(v)} for k, v in tags.items()]
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        msg_id = result.get("id") if isinstance(result, dict) else None
        log.info("email_sent", extra={"context": {
            "to": recipients, "cc": cc_list, "bcc": bcc_list,
            "subject": subject, "id": msg_id, "creds_source": creds_source,
        }})
        return EmailResult(ok=True, id=msg_id)
    except Exception as e:  # noqa: BLE001
        log.error("email_send_failed", extra={"context": {
            "to": recipients, "cc": cc_list, "bcc": bcc_list,
            "subject": subject, "error": str(e), "creds_source": creds_source,
        }})
        return EmailResult(ok=False, id=None, reason=str(e))


# ───────────────────────── Templates ──────────────────────────────────
_BASE_STYLE = (
    "font-family:'IBM Plex Sans',-apple-system,sans-serif;"
    "max-width:560px;margin:0 auto;color:#1F3A5F;line-height:1.5;"
)
_BTN_STYLE = (
    "display:inline-block;padding:10px 18px;background:#C2410C;color:#fff;"
    "text-decoration:none;border-radius:6px;font-weight:600;"
)


def render_incident_notice(*, recipient_name: str, ticket_id: str,
                           tracking_id: str, message: str,
                           cta_url: Optional[str] = None,
                           cta_label: str = "Abrir reclamo") -> tuple[str, str]:
    """HTML + texto para una notificación al ops del cliente.
    Devuelve `(html, text)`.
    """
    safe_name = recipient_name or "Equipo"
    cta_block = (
        f'<p style="text-align:center;margin:24px 0;">'
        f'<a href="{cta_url}" style="{_BTN_STYLE}">{cta_label}</a></p>'
    ) if cta_url else ""
    html = (
        f'<div style="{_BASE_STYLE}">'
        f'<h2 style="color:#C2410C;margin-bottom:8px;">Notificación MyExcellence</h2>'
        f'<p>Hola {safe_name},</p>'
        f'<p>{message}</p>'
        f'<p style="font-size:12px;color:#6b7280;">'
        f'Ticket <code style="background:#f5f3f0;padding:2px 6px;border-radius:4px;">{ticket_id[:8]}</code> · '
        f'Tracking <code style="background:#f5f3f0;padding:2px 6px;border-radius:4px;">{tracking_id}</code></p>'
        f'{cta_block}'
        f'<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">'
        f'<p style="font-size:11px;color:#9ca3af;">'
        f'Este mensaje fue enviado por MyExcellence v2.1 · operación {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}.'
        f'</p></div>'
    )
    text_lines = [
        f"Hola {safe_name},",
        "",
        message,
        "",
        f"Ticket: {ticket_id[:8]}",
        f"Tracking: {tracking_id}",
    ]
    if cta_url:
        text_lines += ["", f"{cta_label}: {cta_url}"]
    text_lines += ["", "— MyExcellence"]
    return html, "\n".join(text_lines)


def render_agent_message(*, agent_name: str, body: str,
                          ticket_id: str, tracking_id: str | None = None,
                          tenant_name: str = "MyExcellence") -> tuple[str, str]:
    """iter45 — HTML+texto para una comunicación libre del agente al cliente.

    Usado desde el composer del panel de agente cuando se manda un email
    externo. El cuerpo del mensaje es texto plano editado por el agente y
    se convierte a párrafos HTML automáticamente.
    """
    safe_agent = agent_name or "Equipo de soporte"
    paragraphs = [p.strip() for p in (body or "").split("\n") if p.strip()]
    html_body = "".join(f"<p>{_escape(p)}</p>" for p in paragraphs)
    tracking_html = (
        f'<p style="font-size:12px;color:#6b7280;">'
        f'Tracking <code style="background:#f5f3f0;padding:2px 6px;border-radius:4px;">{tracking_id}</code> · '
        f'Ticket <code style="background:#f5f3f0;padding:2px 6px;border-radius:4px;">{ticket_id[:8]}</code>'
        f'</p>'
    ) if tracking_id else (
        f'<p style="font-size:12px;color:#6b7280;">'
        f'Ticket <code style="background:#f5f3f0;padding:2px 6px;border-radius:4px;">{ticket_id[:8]}</code>'
        f'</p>'
    )
    html = (
        f'<div style="{_BASE_STYLE}">'
        f'<h2 style="color:#C2410C;margin-bottom:8px;">{_escape(tenant_name)}</h2>'
        f'{html_body}'
        f'{tracking_html}'
        f'<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">'
        f'<p style="font-size:11px;color:#9ca3af;">'
        f'— {_escape(safe_agent)} · {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}'
        f'</p></div>'
    )
    text_lines = [body or "", "", f"— {safe_agent}"]
    if tracking_id:
        text_lines.insert(-2, f"Tracking: {tracking_id}")
    return html, "\n".join(text_lines)


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


def render_test_email(*, recipient_name: str = "Equipo MyE") -> tuple[str, str]:
    return render_incident_notice(
        recipient_name=recipient_name,
        ticket_id="00000000-0000-0000-0000-000000000000",
        tracking_id="TEST-DELIVERY",
        message=(
            "Este es un mensaje de prueba del NotificationService. "
            "Si lo recibes, la integración con Resend está funcionando."
        ),
    )


async def render_incident_notice_for_tenant(
    *, tenant_id: str, recipient_name: str, ticket_id: str,
    tracking_id: str, message: str, cta_url: Optional[str] = None,
    cta_label: str = "Abrir reclamo", tenant_name: str = "",
) -> tuple[str, str, str]:
    """Versión tenant-aware. Retorna (subject, html, text).

    Si el tenant tiene override en `email_templates` para `incident_notice`,
    lo usa. En caso contrario, cae al template hardcoded (`render_incident_notice`).
    """
    from services.email_templates import render_for_tenant
    rendered = await render_for_tenant(
        tenant_id=tenant_id, key="incident_notice",
        ctx={
            "recipient_name": recipient_name,
            "ticket_id": ticket_id, "tracking_id": tracking_id,
            "message": message, "cta_url": cta_url or "",
            "cta_label": cta_label, "tenant_name": tenant_name,
        },
    )
    if rendered:
        return rendered["subject"], rendered["html"], rendered["text"]
    html, text = render_incident_notice(
        recipient_name=recipient_name, ticket_id=ticket_id,
        tracking_id=tracking_id, message=message,
        cta_url=cta_url, cta_label=cta_label,
    )
    return f"[MyExcellence] Incidencia en envío {tracking_id}", html, text
