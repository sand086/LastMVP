"""PDF export con WeasyPrint (PROMPT 23).

Genera PDFs de:
  - Ticket detail (timeline + metadata + evidence list)
  - Claim file (dictamen + estado + eventos + monto)
  - ZIP con varios PDFs (bulk export)
"""
from __future__ import annotations
import io
import zipfile
from datetime import datetime, timezone
from html import escape

from weasyprint import HTML

from core.db import get_db


_BASE_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; font-family: 'Helvetica', sans-serif; }
body { color: #1F3A5F; font-size: 10pt; line-height: 1.45; }
h1 { font-size: 18pt; color: #C2410C; margin: 0 0 4pt; }
h2 { font-size: 12pt; margin: 14pt 0 4pt; border-bottom: 1px solid #C2410C; padding-bottom: 2pt; }
h3 { font-size: 10pt; margin: 8pt 0 2pt; color: #6b7280; text-transform: uppercase; letter-spacing: 1pt; }
svg { width: auto; height: auto; overflow: visible; }
svg text, .svg-number { font-size: 18pt; font-weight: 700; dominant-baseline: middle; text-anchor: middle; }
.muted { color: #6b7280; font-size: 9pt; }
.mono { font-family: 'Courier New', monospace; font-size: 9pt; }
.kv { display: table; width: 100%; }
.kv > div { display: table-row; }
.kv > div > * { display: table-cell; padding: 3pt 0; vertical-align: top; }
.kv > div > strong { width: 40%; color: #6b7280; font-weight: 600; }
.summary { display: table; width: 100%; margin: 12pt 0 8pt; border-spacing: 6pt 0; }
.summary > div { display: table-cell; width: 33.33%; padding: 8pt; border: 1px solid #e5e7eb; border-radius: 6pt; background: #f9fafb; }
.summary .num { display: block; color: #C2410C; font-size: 22pt; font-weight: 700; line-height: 1; }
.summary .label { display: block; color: #6b7280; font-size: 8pt; text-transform: uppercase; letter-spacing: .5pt; margin-top: 3pt; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0; }
th, td { padding: 4pt 6pt; text-align: left; border-bottom: 1px solid #e5e7eb; font-size: 9pt; }
th { background: #f9fafb; color: #6b7280; text-transform: uppercase; font-size: 8pt; letter-spacing: 0.5pt; }
.badge { display: inline-block; padding: 2pt 7pt; border-radius: 99pt; font-size: 9pt; font-weight: 700; background: #f3f4f6; }
.signature { margin-top: 18pt; padding-top: 6pt; border-top: 1px dashed #6b7280; font-size: 8pt; color: #6b7280; }
"""


def _esc(v) -> str:
    if v is None:
        return ""
    return escape(str(v))


def _kv_row(label: str, value) -> str:
    return f'<div><strong>{_esc(label)}</strong><span>{_esc(value)}</span></div>'


def _kv_row_html(label: str, html: str) -> str:
    return f'<div><strong>{_esc(label)}</strong><span>{html}</span></div>'


def _badge(value) -> str:
    return f"<span class='badge'>{_esc(value)}</span>"


def _summary_card(number: int | str, label: str) -> str:
    return (
        "<div>"
        f"<span class='num'>{_esc(number)}</span>"
        f"<span class='label'>{_esc(label)}</span>"
        "</div>"
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def render_ticket_pdf(*, tenant_id: str, ticket_id: str) -> bytes:
    db = get_db()
    ticket = await db.tickets.find_one({"id": ticket_id, "tenant_id": tenant_id}, {"_id": 0})
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")
    timeline = []
    async for ev in db.ticket_events.find(
        {"ticket_id": ticket_id, "tenant_id": tenant_id}, {"_id": 0},
    ).sort("created_at", 1):
        timeline.append(ev)
    evidences = []
    async for ev in db.evidences.find(
        {"ticket_id": ticket_id, "tenant_id": tenant_id}, {"_id": 0},
    ).sort("created_at", 1):
        evidences.append(ev)
    client = await db.clients.find_one({"id": ticket.get("client_id"),
                                        "tenant_id": tenant_id}, {"_id": 0}) or {}
    carrier = await db.carriers.find_one({"id": ticket.get("carrier_id"),
                                          "tenant_id": tenant_id}, {"_id": 0}) or {}

    html = f"""
<!doctype html><html><head><meta charset='utf-8'>
<style>{_BASE_CSS}</style></head><body>
<h1>Expediente del ticket</h1>
<div class='muted mono'>ID {ticket['id']} · generado {_now()}</div>

<div class='summary'>
{_summary_card(len(timeline), "Eventos")}
{_summary_card(len(evidences), "Evidencias")}
{_summary_card(_esc(ticket.get('status') or "—"), "Estado")}
</div>

<h2>Información general</h2>
<div class='kv'>
{_kv_row("Cliente", client.get('name'))}
{_kv_row("Carrier", carrier.get('name') or carrier.get('code'))}
{_kv_row_html("Estado", _badge(ticket.get('status')))}
{_kv_row("Motivo", ticket.get('motivo_codigo'))}
{_kv_row("Solución asignada", ticket.get('solucion_codigo') or "—")}
{_kv_row("Tracking", ticket.get('tracking_id') or "—")}
{_kv_row("Creado", ticket.get('created_at'))}
{_kv_row("Actualizado", ticket.get('updated_at'))}
{_kv_row("Cerrado", ticket.get('closed_at') or "—")}
</div>
<h2>Timeline ({len(timeline)} eventos)</h2>
<table><thead><tr><th>Cuándo</th><th>Tipo</th><th>Detalle</th></tr></thead><tbody>
{"".join(f"<tr><td class='mono'>{_esc(ev.get('created_at',''))[:19]}</td><td>{_esc(ev.get('event_type'))}</td><td>{_esc(ev.get('description') or ev.get('payload'))}</td></tr>" for ev in timeline) or '<tr><td colspan="3" class="muted">Sin eventos</td></tr>'}
</tbody></table>
<h2>Evidencias ({len(evidences)})</h2>
<table><thead><tr><th>Cuándo</th><th>Tipo</th><th>Filename</th><th>Coords</th></tr></thead><tbody>
{"".join(f"<tr><td class='mono'>{_esc(e.get('created_at',''))[:19]}</td><td>{_esc(e.get('kind'))}</td><td class='mono'>{_esc(e.get('filename'))}</td><td class='mono'>{('{:.4f},{:.4f}'.format(e['lat'], e['lng']) if e.get('lat') is not None else '—')}</td></tr>" for e in evidences) or '<tr><td colspan="4" class="muted">Sin evidencias</td></tr>'}
</tbody></table>
<div class='signature'>
Documento generado automáticamente por MyExcellence v2.1.<br>
Tenant {ticket.get('tenant_id')[:12]}… · Total eventos {len(timeline)} · Total evidencias {len(evidences)}<br>
Este expediente NO sustituye dictámenes oficiales del carrier.
</div>
</body></html>
""".strip()
    return HTML(string=html).write_pdf()


async def render_bulk_zip(*, tenant_id: str, ticket_ids: list[str]) -> bytes:
    """Genera un ZIP con un PDF por cada ticket."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for tid in ticket_ids:
            try:
                pdf_bytes = await render_ticket_pdf(tenant_id=tenant_id, ticket_id=tid)
                zf.writestr(f"ticket-{tid}.pdf", pdf_bytes)
            except ValueError:
                # ticket no encontrado: ignorar
                continue
    return buf.getvalue()


async def render_claim_pdf(*, tenant_id: str, claim_id: str) -> bytes:
    """PDF del expediente completo de un reclamo (PROMPT 13 V1).

    Incluye: cabecera, ticket asociado, eventos del workflow, evidencias del
    expediente, dictamen y conciliación.
    """
    db = get_db()
    claim = await db.claims.find_one({"id": claim_id, "tenant_id": tenant_id}, {"_id": 0})
    if not claim:
        raise ValueError(f"Claim {claim_id} not found")
    ticket = await db.tickets.find_one(
        {"id": claim.get("ticket_id"), "tenant_id": tenant_id}, {"_id": 0},
    ) or {}
    client = await db.clients.find_one(
        {"id": claim.get("client_id"), "tenant_id": tenant_id}, {"_id": 0},
    ) or {}
    events: list[dict] = []
    async for ev in db.claim_events.find(
        {"claim_id": claim_id, "tenant_id": tenant_id}, {"_id": 0},
    ).sort("created_at", 1):
        events.append(ev)
    evidences: list[dict] = []
    async for ev in db.evidences.find(
        {"claim_id": claim_id, "tenant_id": tenant_id}, {"_id": 0},
    ).sort("created_at", 1):
        evidences.append(ev)

    monto = claim.get("monto_aprobado") or claim.get("monto_reclamado") or claim.get("monto_solicitado")
    div = claim.get("divisa", "MXN")
    monto_str = f"{div} {monto:,.2f}" if isinstance(monto, (int, float)) else "—"

    # Indemnización opcional (puede contener monto_aprobado/monto_conciliado)
    indem = await db.indemnizations.find_one(
        {"claim_id": claim_id, "tenant_id": tenant_id}, {"_id": 0},
    ) or {}

    html = f"""
<!doctype html><html><head><meta charset='utf-8'>
<style>{_BASE_CSS}</style></head><body>
<h1>Expediente del reclamo</h1>
<div class='muted mono'>Reclamo {claim['id']} · Ticket {ticket.get('id', '—')} · generado {_now()}</div>

<div class='summary'>
{_summary_card(len(events), "Eventos")}
{_summary_card(len(evidences), "Evidencias")}
{_summary_card(_esc(claim.get('estado') or claim.get('status') or "—"), "Estado")}
</div>

<h2>Información general</h2>
<div class='kv'>
{_kv_row("Cliente cartera", client.get('name'))}
{_kv_row_html("Estado del reclamo", _badge(claim.get('estado') or claim.get('status')))}
{_kv_row("Tipo de daño", claim.get('tipo_dano') or claim.get('tipo'))}
{_kv_row("Monto reclamado", monto_str)}
{_kv_row("Promovido por", claim.get('promoted_by') or "—")}
{_kv_row("Promovido en", claim.get('promoted_at') or "—")}
{_kv_row("Conciliado por", claim.get('conciliado_por') or "—")}
{_kv_row("Conciliado en", claim.get('conciliado_at') or "—")}
{_kv_row("Creado", claim.get('created_at'))}
{_kv_row("Actualizado", claim.get('updated_at'))}
</div>

<h2>Ticket asociado</h2>
<div class='kv'>
{_kv_row("Estado del ticket", ticket.get('status') or "—")}
{_kv_row("Tracking ID", ticket.get('tracking_id') or "—")}
{_kv_row("Motivo", ticket.get('motivo_codigo') or "—")}
{_kv_row("Carrier", ticket.get('carrier_id') or "—")}
</div>

<h2>Dictamen / Indemnización</h2>
<div class='kv'>
{_kv_row("Referencia carrier", indem.get('carrier_referencia') or "—")}
{_kv_row("Monto aprobado", f"{indem.get('divisa','')} {indem.get('monto_aprobado'):,.2f}" if isinstance(indem.get('monto_aprobado'), (int, float)) else "—")}
{_kv_row("Monto conciliado", f"{indem.get('divisa_conciliado','')} {indem.get('monto_conciliado'):,.2f}" if isinstance(indem.get('monto_conciliado'), (int, float)) else "—")}
{_kv_row("Conciliado en", indem.get('conciliado_at') or "—")}
</div>

<h2>Declaración del cliente</h2>
<div class='muted' style='white-space:pre-wrap;'>{_esc((claim.get('expediente') or {}).get('declaracion_cliente') or "—")}</div>

<h2>Eventos del workflow ({len(events)})</h2>
<table><thead><tr><th>Cuándo</th><th>Tipo</th><th>Estado anterior</th><th>Estado nuevo</th></tr></thead><tbody>
{"".join(f"<tr><td class='mono'>{_esc(e.get('created_at',''))[:19]}</td><td>{_esc(e.get('event_type'))}</td><td>{_esc(e.get('estado_anterior') or e.get('previous_status') or '—')}</td><td>{_esc(e.get('estado_nuevo') or e.get('new_status') or '—')}</td></tr>" for e in events) or '<tr><td colspan="4" class="muted">Sin eventos</td></tr>'}
</tbody></table>

<h2>Evidencias ({len(evidences)})</h2>
<table><thead><tr><th>Cuándo</th><th>Tipo</th><th>Filename</th></tr></thead><tbody>
{"".join(f"<tr><td class='mono'>{_esc(e.get('created_at',''))[:19]}</td><td>{_esc(e.get('kind'))}</td><td class='mono'>{_esc(e.get('filename'))}</td></tr>" for e in evidences) or '<tr><td colspan="3" class="muted">Sin evidencias</td></tr>'}
</tbody></table>

<div class='signature'>
Documento generado automáticamente por MyExcellence v2.1.<br>
Tenant {claim.get('tenant_id', '')[:12]}… · {len(events)} eventos · {len(evidences)} evidencias<br>
Este expediente NO sustituye dictámenes oficiales del carrier.
</div>
</body></html>
""".strip()
    return HTML(string=html).write_pdf()


async def render_claims_bulk_zip(*, tenant_id: str, claim_ids: list[str]) -> bytes:
    """Genera un ZIP con un PDF por cada reclamo."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid in claim_ids:
            try:
                pdf_bytes = await render_claim_pdf(tenant_id=tenant_id, claim_id=cid)
                zf.writestr(f"reclamo-{cid}.pdf", pdf_bytes)
            except ValueError:
                continue
    return buf.getvalue()

