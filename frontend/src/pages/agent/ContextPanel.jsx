/**
 * Right-hand context panel of the 3-column agent layout.
 *
 * Tabs: Envío · Cliente · Evidencias · SLA.
 * Pulls from the same /api/agent/tickets/{id} payload (no extra calls).
 */
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import {
  Truck, User2, Camera, Activity, MapPin, Mail, Phone, ExternalLink,
  Building2, Package, FileText, ChevronDown, ChevronRight,
  Copy, Map, AlertCircle, Image as ImageIcon, MessageSquare,
  ChevronLeft, ChevronRight as ChevronRightIcon,
  Send, MessageCircle, Clock,
} from "lucide-react";
import { slaInfo, SLA_BAR } from "./sla";

const TABS = [
  { key: "shipment", label: "Envío", icon: Truck },
  { key: "client", label: "Cliente", icon: Building2 },
  { key: "evidence", label: "Evidencias", icon: Camera },
  { key: "sla", label: "SLA", icon: Activity },
];

export default function ContextPanel({ ticket, guia, client, evidenceCount = 0 }) {
  const [tab, setTab] = useState("shipment");
  return (
    <aside className="w-[320px] flex-shrink-0 border-l border-mye-border bg-white flex flex-col"
           data-testid="agent-context-panel">
      <div className="flex border-b border-mye-border px-2 py-2 gap-1">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button key={t.key} onClick={() => setTab(t.key)}
                    className={"flex-1 inline-flex flex-col items-center gap-0.5 rounded-md px-2 py-1.5 text-[10px] font-mono transition " +
                      (active ? "bg-mye-primary-soft text-mye-ink" : "text-mye-ink-muted hover:bg-mye-app")}
                    data-testid={`context-tab-${t.key}`}>
              <Icon className="h-3.5 w-3.5" />
              {t.label}
              {t.key === "evidence" && evidenceCount > 0 && (
                <span className="text-[9px] font-mono text-mye-accent">{evidenceCount}</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-auto p-4 text-sm">
        {tab === "shipment" && <ShipmentTab ticket={ticket} guia={guia} />}
        {tab === "client" && <ClientTab client={client} />}
        {tab === "evidence" && <EvidenceTab ticket={ticket} count={evidenceCount} />}
        {tab === "sla" && <SLATab ticket={ticket} />}
      </div>
    </aside>
  );
}

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-2 py-1.5 text-xs border-b border-mye-border/50 last:border-0">
      <span className="font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted">{label}</span>
      <span className="break-words">{children}</span>
    </div>
  );
}

function ShipmentTab({ ticket, guia }) {
  const recipient = guia?.recipient || {};
  const sender = guia?.sender || {};
  const meta = guia?.carrier_meta || {};
  const hasRecipient = recipient.name || recipient.address || recipient.phone || recipient.email;
  const hasSender = sender.name || sender.address;
  const hasDetails = guia?.delivery_notes || guia?.external_reference
    || guia?.declared_value || meta.contenido
    || meta.alto_cm || meta.ancho_cm || meta.largo_cm;
  return (
    <div className="space-y-4" data-testid="context-shipment">
      {/* Identificación — siempre visible */}
      <Section icon={Truck} title="Identificación" defaultOpen>
        <Row label="Tracking">
          <span className="font-mono">{ticket?.tracking_id || guia?.tracking_id || "—"}</span>
        </Row>
        <Row label="Carrier">{guia?.carrier_code || guia?.carrier_id || ticket?.carrier_id || "—"}</Row>
        <Row label="Estado raw">{guia?.raw_code || ticket?.carrier_status_raw || "—"}</Row>
        <Row label="Incidente">{guia?.carrier_incidence || ticket?.incident_type_label || ticket?.incident_type || "—"}</Row>
        <Row label="Motivo">{ticket?.motivo_codigo || "—"}</Row>
        {guia?.external_reference && (
          <Row label="Referencia">
            <span className="font-mono">{guia.external_reference}</span>
          </Row>
        )}
        {guia?.service?.commercial && (
          <Row label="Servicio">{guia.service.commercial}</Row>
        )}
        {guia?.url_seguimiento && (
          <a href={guia.url_seguimiento} target="_blank" rel="noopener noreferrer"
             className="mt-2 inline-flex items-center gap-1 text-xs text-mye-accent hover:underline"
             data-testid="context-tracking-link">
            <ExternalLink className="h-3 w-3" /> Abrir tracking
          </a>
        )}
      </Section>

      {/* Iter61 — Reporte del transportista (Routal driver feedback) */}
      <CarrierReport ticket={ticket} guia={guia} />

      {/* Iter67 — Comentarios bidireccionales con el transportista */}
      <CarrierComments ticket={ticket} guia={guia} />

      {/* Destinatario — Layout V2 */}
      {hasRecipient && (
        <Section icon={User2} title="Destinatario" defaultOpen>
          {recipient.name && (
            <Row label="Nombre"><span className="font-medium">{recipient.name}</span></Row>
          )}
          {recipient.company && <Row label="Empresa">{recipient.company}</Row>}
          {recipient.address ? (
            <Row label="Dirección">
              <div className="space-y-1">
                <div>{recipient.address}</div>
                <AddressActions party={recipient} testidPrefix="recipient" />
              </div>
            </Row>
          ) : formatFullAddress(recipient) ? (
            <Row label="Dirección">
              <div className="space-y-1">
                <span className="text-mye-ink-muted italic">Sin dirección registrada</span>
                <AddressActions party={recipient} testidPrefix="recipient" />
              </div>
            </Row>
          ) : null}
          {(recipient.state || recipient.cp) && (
            <Row label="Estado / CP">
              {[recipient.state, recipient.cp].filter(Boolean).join(" · ")}
            </Row>
          )}
          {recipient.phone && (
            <Row label="Teléfono">
              <a href={`tel:${recipient.phone}`}
                 className="inline-flex items-center gap-1 text-mye-accent hover:underline"
                 data-testid="context-recipient-phone">
                <Phone className="h-3 w-3" /> {recipient.phone}
              </a>
            </Row>
          )}
          {recipient.email && (
            <Row label="Email">
              <a href={`mailto:${recipient.email}`}
                 className="inline-flex items-center gap-1 text-mye-accent hover:underline"
                 data-testid="context-recipient-email">
                <Mail className="h-3 w-3" /> {recipient.email}
              </a>
            </Row>
          )}
        </Section>
      )}

      {/* Remitente — Layout V2 */}
      {hasSender && (
        <Section icon={Building2} title="Remitente">
          {sender.name && <Row label="Nombre">{sender.name}</Row>}
          {sender.company && <Row label="Empresa">{sender.company}</Row>}
          {sender.address ? (
            <Row label="Dirección">
              <div className="space-y-1">
                <div>{sender.address}</div>
                <AddressActions party={sender} testidPrefix="sender" />
              </div>
            </Row>
          ) : formatFullAddress(sender) ? (
            <Row label="Dirección">
              <div className="space-y-1">
                <span className="text-mye-ink-muted italic">Sin dirección registrada</span>
                <AddressActions party={sender} testidPrefix="sender" />
              </div>
            </Row>
          ) : null}
          {(sender.state || sender.cp) && (
            <Row label="Estado / CP">
              {[sender.state, sender.cp].filter(Boolean).join(" · ")}
            </Row>
          )}
          {sender.phone && (
            <Row label="Teléfono">
              <a href={`tel:${sender.phone}`}
                 className="inline-flex items-center gap-1 text-mye-accent hover:underline">
                <Phone className="h-3 w-3" /> {sender.phone}
              </a>
            </Row>
          )}
          {sender.email && (
            <Row label="Email">
              <a href={`mailto:${sender.email}`}
                 className="inline-flex items-center gap-1 text-mye-accent hover:underline">
                <Mail className="h-3 w-3" /> {sender.email}
              </a>
            </Row>
          )}
        </Section>
      )}

      {/* Detalles del paquete / notas */}
      {hasDetails && (
        <Section icon={Package} title="Detalles del envío">
          {meta.contenido && <Row label="Contenido">{meta.contenido}</Row>}
          {(meta.alto_cm || meta.ancho_cm || meta.largo_cm) && (
            <Row label="Dimensiones">
              <span className="font-mono text-[11px]">
                {[meta.alto_cm, meta.ancho_cm, meta.largo_cm]
                  .map((v) => v != null ? `${v}` : "?").join(" × ")} cm
              </span>
            </Row>
          )}
          {guia?.weights?.real_kg != null && (
            <Row label="Peso real">
              <span className="font-mono text-[11px]">{guia.weights.real_kg} kg</span>
            </Row>
          )}
          {guia?.declared_value != null && (
            <Row label="Valor declarado">
              <span className="font-mono text-[11px]">${guia.declared_value} MXN</span>
            </Row>
          )}
          {guia?.insurance_purchased && (
            <Row label="Seguro"><span className="text-status-resolved">✓ Sí</span></Row>
          )}
          {meta.hecho_por && <Row label="Hecho por">{meta.hecho_por}</Row>}
          {meta.tipo_entrega && <Row label="Tipo entrega">{meta.tipo_entrega}</Row>}
          {guia?.delivery_notes && (
            <Row label="Notas">
              <span className="italic text-mye-ink-muted">{guia.delivery_notes}</span>
            </Row>
          )}
        </Section>
      )}
    </div>
  );
}

function Section({ icon: Icon, title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-md border border-mye-border bg-white"
         data-testid={`section-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      <button type="button" onClick={() => setOpen(!open)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-mye-app/50 transition-colors">
        <Icon className="h-3.5 w-3.5 text-mye-accent" />
        <span className="text-[10px] uppercase tracking-wider font-mono font-semibold">{title}</span>
        <span className="ml-auto text-mye-ink-muted">
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </span>
      </button>
      {open && <div className="px-3 pb-2 space-y-0.5">{children}</div>}
    </div>
  );
}

/**
 * AddressActions — botones rápidos junto a una dirección.
 *  · Copia "Empresa, Dirección, Estado, CP" al portapapeles.
 *  · Abre la dirección + empresa en Google Maps en una pestaña nueva
 *    (la empresa mejora la precisión de geocoding cuando es un comercio/bodega).
 *
 * `party` es el objeto `recipient` o `sender` del guia (Layout V2).
 */
const _PLACEHOLDER_VALUES = new Set(["-", "—", "n/a", "na", "null", "."]);
function _isPlaceholder(v) {
  if (!v || typeof v !== "string") return true;
  return _PLACEHOLDER_VALUES.has(v.trim().toLowerCase());
}
function formatFullAddress(party) {
  return [party.company, party.address, party.state, party.cp]
    .filter((v) => !_isPlaceholder(v))
    .join(", ");
}

function AddressActions({ party, testidPrefix = "address" }) {
  const full = formatFullAddress(party);
  if (!full) return null;
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(full)}`;

  async function copyAddress() {
    try {
      await navigator.clipboard.writeText(full);
      toast.success("Dirección copiada");
    } catch {
      // Fallback para navegadores sin Clipboard API
      const ta = document.createElement("textarea");
      ta.value = full;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      toast.success("Dirección copiada");
    }
  }

  return (
    <div className="flex items-center gap-2 pt-1">
      <button type="button" onClick={copyAddress}
              className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-0.5 text-[10px] font-mono text-mye-ink-muted hover:bg-mye-primary-soft hover:text-mye-ink transition-colors"
              data-testid={`${testidPrefix}-copy-address`}
              title="Copiar dirección completa">
        <Copy className="h-3 w-3" /> Copiar
      </button>
      <a href={mapsUrl} target="_blank" rel="noopener noreferrer"
         className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-0.5 text-[10px] font-mono text-mye-accent hover:bg-mye-primary-soft transition-colors"
         data-testid={`${testidPrefix}-open-maps`}
         title="Abrir en Google Maps">
        <Map className="h-3 w-3" /> Maps
      </a>
    </div>
  );
}

function ClientTab({ client }) {
  if (!client) return <div className="text-xs text-mye-ink-muted">Sin cliente vinculado.</div>;
  return (
    <div className="space-y-1" data-testid="context-client">
      <Row label="Nombre">
        <span className="font-medium">{client.name}</span>
      </Row>
      <Row label="Slug">
        <span className="font-mono text-[11px]">{client.slug}</span>
      </Row>
      <Row label="Automation">
        {client.automation_enabled ? "Activa" : "Inactiva"}
      </Row>
      {client.ops_contact_email && (
        <a href={`mailto:${client.ops_contact_email}`}
           className="mt-2 inline-flex items-center gap-1 text-xs text-mye-accent hover:underline">
          <Mail className="h-3 w-3" /> {client.ops_contact_email}
        </a>
      )}
    </div>
  );
}

function EvidenceTab({ ticket, count }) {
  return (
    <div className="space-y-2" data-testid="context-evidence">
      <div className="flex items-center gap-2 text-xs">
        <Camera className="h-3.5 w-3.5 text-mye-accent" />
        <span className="font-mono">{count} adjunta{count === 1 ? "" : "s"}</span>
      </div>
      <a href={`/admin/tickets/${ticket?.id}`}
         className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline"
         data-testid="context-evidence-open">
        <MapPin className="h-3 w-3" /> Ver / agregar evidencias
      </a>
      <p className="text-[10px] font-mono text-mye-ink-muted leading-relaxed mt-2">
        Antes de promover a reclamo, recordá adjuntar al menos 2 fotos del daño + foto de la guía (R35).
      </p>
    </div>
  );
}

function SLATab({ ticket }) {
  const sla = slaInfo(ticket);
  if (!sla) return <div className="text-xs text-mye-ink-muted">Sin SLA configurado para este ticket.</div>;
  const pct = Math.round(sla.elapsedRatio * 100);
  return (
    <div className="space-y-3" data-testid="context-sla">
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="text-mye-ink-muted">Tiempo restante</span>
          <span className={"font-mono font-semibold " +
            (sla.level === "risk" ? "text-status-escalated"
              : sla.level === "warn" ? "text-status-waiting" : "text-status-resolved")}>
            {sla.label}
          </span>
        </div>
        <div className="h-2 rounded-full bg-mye-border overflow-hidden">
          <div className={"h-full transition-all " + SLA_BAR[sla.level]}
               style={{ width: `${Math.min(100, pct)}%` }} />
        </div>
        <div className="flex items-center justify-between text-[10px] font-mono text-mye-ink-muted">
          <span>{pct}% transcurrido</span>
          <span>{sla.deadline.toISOString().slice(0, 16).replace("T", " ")}</span>
        </div>
      </div>
      <Row label="Status">{ticket?.status}</Row>
      <Row label="Asignado">
        <span className="font-mono text-[11px]">
          {ticket?.assigned_agent_id?.slice(0, 8) || "— sin asignar —"}
        </span>
      </Row>
      <Row label="Prioridad">{ticket?.priority || "normal"}</Row>
    </div>
  );
}

// Iter61 — Reporte del transportista (Routal driver feedback)
function CarrierReport({ ticket, guia }) {
  // Detalle puede venir de ticket.carrier_incident_detail (post-enrich) o
  // de guia.carrier_meta.routal_report (raw del adapter)
  const detail = ticket?.carrier_incident_detail
    || guia?.carrier_meta?.routal_report
    || null;
  const [lightbox, setLightbox] = useState(null); // { url, index }
  const [loadingIdx, setLoadingIdx] = useState(null);
  const [navLoading, setNavLoading] = useState(false);

  function closeLightbox() {
    if (lightbox?.url) URL.revokeObjectURL(lightbox.url);
    setLightbox(null);
  }

  // Iter66 — fetch helper para 1 imagen (reusable por openImage y goTo)
  async function _fetchImage(imageId) {
    const token = localStorage.getItem("mye_access_token");
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/agent/routal/image-proxy?ticket_id=${encodeURIComponent(ticket.id)}&report_id=${encodeURIComponent(detail?.report_id)}&image_id=${encodeURIComponent(imageId)}`;
    const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return URL.createObjectURL(await resp.blob());
  }

  // Iter66 — Navegar a la foto idx (con wrap-around)
  async function goTo(newIdx) {
    if (!lightbox) return;
    const images = detail?.images || [];
    if (images.length <= 1) return;
    const total = images.length;
    const wrappedIdx = ((newIdx % total) + total) % total;
    if (wrappedIdx === lightbox.index) return;
    setNavLoading(true);
    try {
      const objectUrl = await _fetchImage(images[wrappedIdx].id);
      URL.revokeObjectURL(lightbox.url);
      setLightbox({ url: objectUrl, index: wrappedIdx });
    } catch {
      toast.error("No se pudo cargar la siguiente imagen");
    } finally {
      setNavLoading(false);
    }
  }

  // Cerrar con tecla Escape + navegar con ←/→
  useEffect(() => {
    if (!lightbox) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") closeLightbox();
      else if (e.key === "ArrowLeft") goTo(lightbox.index - 1);
      else if (e.key === "ArrowRight") goTo(lightbox.index + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lightbox]);

  if (!detail) return null;
  const reason = detail.reason_label;
  const comments = detail.comments;
  const images = detail.images || [];
  const reportAt = detail.report_at;
  const reportId = detail.report_id;

  // Iter65 — abre foto en lightbox via proxy autenticado.
  async function openImage(imageId, idx) {
    setLoadingIdx(idx);
    try {
      const objectUrl = await _fetchImage(imageId);
      setLightbox({ url: objectUrl, index: idx });
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("openImage error:", e);
      toast.error("No se pudo cargar la imagen del transportista");
    } finally {
      setLoadingIdx(null);
    }
  }

  return (
    <>
    <Section icon={AlertCircle} title="Reporte del transportista" defaultOpen
             data-testid="context-carrier-report">
      {reason && (
        <Row label="Motivo">
          <span className="inline-flex items-center rounded-full bg-status-escalated/10 text-status-escalated border border-status-escalated/30 px-2 py-0.5 text-[11px] font-medium"
                data-testid="carrier-report-reason">
            {reason}
          </span>
        </Row>
      )}
      {comments && (
        <Row label="Comentario">
          <div className="flex items-start gap-1.5 text-mye-ink"
               data-testid="carrier-report-comments">
            <MessageSquare className="h-3.5 w-3.5 mt-0.5 text-mye-ink-muted shrink-0" />
            <span className="italic">"{comments}"</span>
          </div>
        </Row>
      )}
      {reportAt && (
        <Row label="Reportado">
          <span className="font-mono text-[11px] text-mye-ink-muted">
            {new Date(reportAt).toLocaleString("es-MX")}
          </span>
        </Row>
      )}
      {images.length > 0 && reportId && (
        <Row label={`Evidencia (${images.length})`}>
          <div className="flex flex-wrap gap-1.5 mt-0.5"
               data-testid="carrier-report-images">
            {images.map((img, i) => (
              <button key={img.id || i} type="button"
                      onClick={() => openImage(img.id, i)}
                      disabled={loadingIdx === i}
                      className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-mye-app/40 px-2 py-1 text-[11px] hover:bg-mye-primary-soft/40 transition disabled:opacity-50"
                      data-testid={`carrier-report-img-${i}`}>
                <ImageIcon className="h-3 w-3" />
                {loadingIdx === i ? "Cargando…" : `Foto ${i + 1}`}
              </button>
            ))}
          </div>
        </Row>
      )}
      {detail.report_type && (
        <Row label="Tipo">
          <span className="font-mono text-[10px] text-mye-ink-muted">{detail.report_type}</span>
        </Row>
      )}
    </Section>

    {lightbox && (
      <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6"
           role="dialog"
           data-testid="carrier-image-lightbox"
           onClick={closeLightbox}>
        <div className="absolute top-4 right-4 flex items-center gap-2">
          {images.length > 1 && (
            <span className="inline-flex items-center rounded-md bg-white/10 text-white px-3 py-1.5 text-xs backdrop-blur-sm font-mono"
                  data-testid="carrier-image-counter">
              {lightbox.index + 1} / {images.length}
            </span>
          )}
          <a href={lightbox.url} download={`evidencia-${lightbox.index + 1}.jpg`}
             onClick={(e) => e.stopPropagation()}
             className="inline-flex items-center gap-1 rounded-md bg-white/10 text-white px-3 py-1.5 text-xs hover:bg-white/20 transition backdrop-blur-sm"
             data-testid="carrier-image-download">
            Descargar
          </a>
          <button type="button" onClick={closeLightbox}
                  className="inline-flex items-center gap-1 rounded-md bg-white/10 text-white px-3 py-1.5 text-xs hover:bg-white/20 transition backdrop-blur-sm"
                  data-testid="carrier-image-close">
            Cerrar (Esc)
          </button>
        </div>

        {/* Iter66 — Flecha Prev */}
        {images.length > 1 && (
          <button type="button"
                  onClick={(e) => { e.stopPropagation(); goTo(lightbox.index - 1); }}
                  disabled={navLoading}
                  className="absolute left-4 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-12 h-12 rounded-full bg-white/10 text-white hover:bg-white/20 transition backdrop-blur-sm disabled:opacity-50"
                  data-testid="carrier-image-prev"
                  title="Anterior (←)">
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}

        {/* Iter66 — Flecha Next */}
        {images.length > 1 && (
          <button type="button"
                  onClick={(e) => { e.stopPropagation(); goTo(lightbox.index + 1); }}
                  disabled={navLoading}
                  className="absolute right-4 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-12 h-12 rounded-full bg-white/10 text-white hover:bg-white/20 transition backdrop-blur-sm disabled:opacity-50"
                  data-testid="carrier-image-next"
                  title="Siguiente (→)">
            <ChevronRightIcon className="h-6 w-6" />
          </button>
        )}

        <img src={lightbox.url}
             alt={`Evidencia ${lightbox.index + 1}`}
             className={`max-h-[90vh] max-w-[90vw] object-contain rounded-md shadow-2xl transition-opacity ${navLoading ? "opacity-50" : "opacity-100"}`}
             onClick={(e) => e.stopPropagation()} />

        {/* Thumbnails inferiores cuando hay 2+ fotos */}
        {images.length > 1 && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5"
               data-testid="carrier-image-thumbs"
               onClick={(e) => e.stopPropagation()}>
            {images.map((_, i) => (
              <button key={i} type="button"
                      onClick={(e) => { e.stopPropagation(); goTo(i); }}
                      disabled={navLoading || i === lightbox.index}
                      className={`h-2 rounded-full transition-all backdrop-blur-sm ${i === lightbox.index ? "bg-white w-8" : "bg-white/40 w-2 hover:bg-white/70"}`}
                      data-testid={`carrier-image-thumb-${i}`}
                      aria-label={`Ir a foto ${i + 1}`}/>
            ))}
          </div>
        )}
      </div>
    )}
    </>
  );
}


// ─────────────────────────────────────────────────────────────────────
// Iter67 — Comentarios al transportista (sincronizado con Routal)
// ─────────────────────────────────────────────────────────────────────
const ROUTAL_COMMENT_TEMPLATES = [
  { slug: "schedule", label: "Reagendar",
    text: "Reagendar para [fecha/hora]: " },
  { slug: "call", label: "Llamar antes",
    text: "Llamar antes de llegar al teléfono: " },
  { slug: "leave-with", label: "Dejar con",
    text: "Dejar con [persona] (vecino/portero/portería): " },
  { slug: "confirm-address", label: "Confirmar domicilio",
    text: "Se confirma domicilio correcto: ___ - Liga Google Maps: ___ - Referencias adicionales: ___" },
  { slug: "schedule-window", label: "Horario disponible",
    text: "Cliente disponible solo en horario: " },
];

function CarrierComments({ ticket, guia }) {
  const isRoutal = (guia?.carrier_code || "").toLowerCase() === "routal";
  const stopId = guia?.raw_payload?.stop_id;
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [mode] = useState("append");
  const [sending, setSending] = useState(false);
  const [current, setCurrent] = useState("");
  const [history, setHistory] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (!open || !isRoutal || !stopId || loaded) return;
    api.get("/agent/routal/comments", { params: { ticket_id: ticket.id } })
      .then((r) => {
        setCurrent(r.data?.data?.current_comment || "");
        setHistory(r.data?.data?.history || []);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [open, isRoutal, stopId, ticket?.id, loaded]);

  if (!isRoutal || !stopId) return null;

  async function send() {
    if (!comment.trim()) {
      toast.error("Escribe un comentario primero");
      return;
    }
    setSending(true);
    try {
      const r = await api.post("/agent/routal/comments", {
        ticket_id: ticket.id, comment: comment.trim(), mode,
      });
      setCurrent(r.data?.data?.current_comment || "");
      // Refrescamos historial
      const r2 = await api.get("/agent/routal/comments",
        { params: { ticket_id: ticket.id } });
      setHistory(r2.data?.data?.history || []);
      setComment("");
      toast.success("Comentario enviado al driver (Routal)");
    } catch (e) {
      toast.error(e.response?.data?.detail
        || e.response?.data?.errors?.[0]?.message
        || "Error enviando el comentario");
    } finally {
      setSending(false);
    }
  }

  function applyTemplate(tpl) {
    setComment((c) => (c ? `${c}\n${tpl.text}` : tpl.text));
  }

  return (
    <section className="rounded-lg border border-mye-border bg-mye-surface overflow-hidden"
             data-testid="context-carrier-comments">
      <button type="button"
              onClick={() => setOpen((v) => !v)}
              className="w-full flex items-center justify-between px-3 py-2 border-b border-mye-border bg-mye-app/40 hover:bg-mye-app/60 transition">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-mye-ink">
          <MessageCircle className="h-3.5 w-3.5 text-mye-accent" />
          Comentarios al driver
          {current && (
            <span className="ml-1 inline-flex items-center rounded-full bg-mye-accent/10 text-mye-accent px-1.5 py-0.5 text-[10px] font-mono"
                  data-testid="routal-comments-has-current">
              activo
            </span>
          )}
        </span>
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </button>

      {open && (
        <div className="px-3 py-3 space-y-3">
          {current && (
            <div className="rounded-md border border-mye-border bg-mye-app/30 px-2.5 py-2 text-[11px]"
                 data-testid="routal-comments-current">
              <div className="font-mono text-[9px] uppercase tracking-wider text-mye-ink-muted mb-1">
                Visible para el driver ahora
              </div>
              <pre className="whitespace-pre-wrap font-sans text-mye-ink leading-snug">{current}</pre>
            </div>
          )}

          {/* Plantillas */}
          <div>
            <div className="font-mono text-[9px] uppercase tracking-wider text-mye-ink-muted mb-1">
              Plantillas
            </div>
            <div className="flex flex-wrap gap-1">
              {ROUTAL_COMMENT_TEMPLATES.map((tpl) => (
                <button key={tpl.slug} type="button"
                        onClick={() => applyTemplate(tpl)}
                        className="inline-flex items-center rounded-full border border-mye-border bg-white px-2.5 py-0.5 text-[10px] hover:bg-mye-primary-soft/40 transition"
                        data-testid={`routal-comment-template-${tpl.slug}`}>
                  {tpl.label}
                </button>
              ))}
            </div>
          </div>

          {/* Textarea */}
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={4}
            maxLength={4000}
            placeholder="Escribe lo que el driver debe ver en su app móvil al reintentar la entrega…"
            className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-xs focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 resize-y"
            data-testid="routal-comments-textarea"
          />

          <div className="flex items-center justify-between">
            <span className="text-[10px] font-mono text-mye-ink-muted">
              {comment.length}/4000 · modo: append (se agrega arriba)
            </span>
            <button type="button"
                    onClick={send}
                    disabled={sending || !comment.trim()}
                    className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 disabled:opacity-50 transition"
                    data-testid="routal-comments-send">
              <Send className="h-3 w-3" />
              {sending ? "Enviando…" : "Enviar al driver"}
            </button>
          </div>

          {/* Historial */}
          {history.length > 0 && (
            <div className="pt-2 border-t border-mye-border">
              <button type="button"
                      onClick={() => setShowHistory((v) => !v)}
                      className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-mye-ink-muted hover:text-mye-ink"
                      data-testid="routal-comments-history-toggle">
                <Clock className="h-3 w-3" />
                Historial ({history.length})
                {showHistory ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              </button>
              {showHistory && (
                <ul className="mt-1 space-y-1.5 max-h-48 overflow-y-auto"
                    data-testid="routal-comments-history">
                  {history.slice().reverse().map((h, i) => (
                    <li key={i} className="text-[11px] rounded-md border border-mye-border bg-mye-app/40 px-2 py-1.5">
                      <div className="flex items-center justify-between text-[10px] font-mono text-mye-ink-muted">
                        <span>@{(h.agent_email || "?").split("@")[0]}</span>
                        <span>{h.at ? new Date(h.at).toLocaleString("es-MX") : ""}</span>
                      </div>
                      <div className="text-mye-ink mt-0.5">"{h.comment}"</div>
                      {!h.success && (
                        <div className="text-[10px] text-status-escalated mt-0.5">
                          ⚠ {h.error || "Falló"}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

