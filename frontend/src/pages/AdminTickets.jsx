import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import EvidenceCard from "@/components/EvidenceCard";
import GuiaCancelButton from "@/components/GuiaCancelButton";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";
import WhatsAppPanel from "@/components/WhatsAppPanel";
import {
  ArrowLeft, LogOut, Inbox, AlertTriangle, Clock, MapPin,
  CheckCircle2, RefreshCw, Scale, ExternalLink,
} from "lucide-react";

// Bundle A · FIX-A1: typed confirmation threshold mirrors backend.
const BULK_TYPED_CONFIRMATION_THRESHOLD = 10;
const BULK_TYPED_CONFIRMATION_KEYWORD = "CERRAR";

const STATUS_COLOR = {
  pending: "bg-status-pending/10 text-status-pending border-status-pending/30",
  in_progress: "bg-status-active/10 text-status-active border-status-active/30",
  waiting_client: "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  waiting_carrier: "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  resolved: "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
  closed: "bg-status-closed/10 text-status-closed border-status-closed/30",
  claim: "bg-status-claim/10 text-status-claim border-status-claim/30",
};

export default function AdminTickets() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tickets, setTickets] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkErr, setBulkErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  // Bundle A · FIX-A1: typed confirmation dialog state
  const [confirmDialog, setConfirmDialog] = useState(null);
  // { action, payload, count } | null

  async function refresh() {
    setLoading(true);
    try {
      const params = filter ? { status: filter } : {};
      const r = await api.get("/admin/tickets", { params });
      setTickets(r.data?.data?.items || []);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, [filter]);

  // Bundle A · FIX-A1: ejecutar bulk (con typed_confirmation si vino del modal)
  async function executeBulk(action, payload, typedConfirmation) {
    setBulkBusy(true); setBulkErr(null);
    const ids = Array.from(selected);
    try {
      if (action === "export_pdf") {
        const token = localStorage.getItem("mye_access_token");
        const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin/tickets/bulk`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ ticket_ids: ids, action, payload: payload || {} }),
        });
        if (!res.ok) { setBulkErr(`HTTP ${res.status}`); return; }
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `tickets-${ids.length}.zip`;
        a.click();
        URL.revokeObjectURL(a.href);
      } else {
        const body = { ticket_ids: ids, action, payload: payload || {} };
        if (typedConfirmation) body.typed_confirmation = typedConfirmation;
        const r = await api.post("/admin/tickets/bulk", body);
        const txnId = r.data?.data?.transaction_id;
        if (txnId && (action === "close" || action === "change_status")) {
          showUndoToast({
            transactionId: txnId,
            affected: r.data?.data?.affected ?? ids.length,
            actionLabel: action === "close" ? "cerrados" : "actualizados",
          });
        }
      }
      setSelected(new Set());
      await refresh();
    } catch (e) {
      setBulkErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBulkBusy(false); }
  }

  // Bundle A · FIX-A1: toast con botón Deshacer (30 segundos)
  function showUndoToast({ transactionId, affected, actionLabel }) {
    toast.success(`${affected} ticket${affected !== 1 ? "s" : ""} ${actionLabel}`, {
      duration: 30_000,
      action: {
        label: "Deshacer",
        onClick: async () => {
          try {
            const r = await api.post("/admin/tickets/bulk-undo", {
              transaction_id: transactionId,
            });
            const { reverted_count, skipped_count } = r.data?.data || {};
            if (skipped_count > 0) {
              toast.warning(
                `Se revirtieron ${reverted_count} de ${reverted_count + skipped_count}. ` +
                `${skipped_count} no se pudieron revertir (carrier confirmó cambio o ` +
                `terceros modificaron el ticket).`,
              );
            } else {
              toast.success(`${reverted_count} ticket${reverted_count !== 1 ? "s" : ""} revertidos.`);
            }
            await refresh();
          } catch (e) {
            const msg = e.response?.data?.errors?.[0]?.message || e.message;
            toast.error(`No se pudo deshacer: ${msg}`);
          }
        },
      },
    });
  }

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-tickets-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Admin · Casos</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <SaaSHierarchyBreadcrumb className="hidden md:inline-flex mr-2" />
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 05 · WorkflowEngine
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Casos generados por la engine</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            Cada incidencia detectada por el normalizer del CAE se convierte en ticket aquí —
            auto-asignado al primer agente activo. El Panel de Agente completo (PROMPT 08)
            heredará esta lista.
          </p>
        </section>

        <div className="flex flex-wrap items-center gap-2 bg-white border border-mye-border rounded-lg p-2">
          <span className="text-xs font-mono text-mye-ink-muted px-2">Filtro:</span>
          {["", "pending", "in_progress", "waiting_client", "resolved", "closed"].map((s) => (
            <button key={s || "all"} onClick={() => setFilter(s)}
                    className={"px-3 py-1.5 rounded-md text-xs font-mono transition " +
                      (filter === s
                        ? "bg-mye-accent text-white"
                        : "text-mye-ink-muted hover:bg-mye-primary-soft")}
                    data-testid={`tickets-filter-${s || "all"}`}>
              {s || "todos"}
            </button>
          ))}
          <button onClick={refresh} className="ml-auto inline-flex items-center gap-1 rounded-md border border-mye-border px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition">
            <RefreshCw className="h-3.5 w-3.5" /> Refrescar
          </button>
        </div>

        <div className="bg-white border border-mye-border rounded-lg overflow-hidden">
          {loading ? (
            <div className="px-6 py-10 text-center text-sm text-mye-ink-muted font-mono">Cargando…</div>
          ) : tickets.length === 0 ? (
            <div className="px-6 py-12 text-center" data-testid="tickets-empty">
              <Inbox className="h-8 w-8 mx-auto text-mye-ink-muted mb-2" />
              <div className="text-sm text-mye-ink-muted">
                Sin tickets. Dispara una guía con incidente desde
                <Link to="/admin/ingesta" className="underline text-mye-accent ml-1">Ingesta</Link> para generar uno.
              </div>
            </div>
          ) : (
            <>
              {selected.size > 0 && (
                <BulkBar
                  count={selected.size}
                  busy={bulkBusy}
                  err={bulkErr}
                  onAction={(action, payload) => {
                    // Bundle A · FIX-A1: si es close/change_status y >=10 → modal typed
                    if (
                      (action === "close" || action === "change_status") &&
                      selected.size >= BULK_TYPED_CONFIRMATION_THRESHOLD
                    ) {
                      setConfirmDialog({
                        action,
                        payload,
                        count: selected.size,
                      });
                      return;
                    }
                    executeBulk(action, payload);
                  }}
                  onClear={() => setSelected(new Set())}
                />
              )}
            <table className="w-full text-sm">
              <thead className="bg-mye-app/60">
                <tr>
                  <th className="px-3 py-2.5 w-10">
                    <input type="checkbox"
                           checked={tickets.length > 0 && selected.size === tickets.length}
                           onChange={(e) => setSelected(e.target.checked
                             ? new Set(tickets.map((t) => t.id))
                             : new Set())}
                           className="h-3.5 w-3.5 accent-mye-accent"
                           data-testid="tickets-select-all" />
                  </th>
                  {["#", "Status", "Incident", "Carrier raw", "Asignado", "Creado"].map((h) => (
                    <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tickets.map((t) => (
                  <tr key={t.id} className="border-t border-mye-border hover:bg-mye-primary-soft/30 transition"
                      data-testid={`tickets-row-${t.id}`}>
                    <td className="px-3 py-2.5 w-10" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={selected.has(t.id)}
                             onChange={(e) => {
                               const s = new Set(selected);
                               if (e.target.checked) s.add(t.id); else s.delete(t.id);
                               setSelected(s);
                             }}
                             className="h-3.5 w-3.5 accent-mye-accent"
                             data-testid={`tickets-select-${t.id}`} />
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted cursor-pointer"
                        onClick={() => navigate(`/admin/tickets/${t.id}`)}>{t.id.slice(0, 8)}</td>
                    <td className="px-4 py-2.5 cursor-pointer" onClick={() => navigate(`/admin/tickets/${t.id}`)}>
                      <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono " +
                        (STATUS_COLOR[t.status] || "border-mye-border")}>
                        {t.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-mye-ink-muted cursor-pointer" onClick={() => navigate(`/admin/tickets/${t.id}`)}>{t.incident_type || "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] cursor-pointer" onClick={() => navigate(`/admin/tickets/${t.id}`)}>{t.carrier_status_raw || "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted cursor-pointer" onClick={() => navigate(`/admin/tickets/${t.id}`)}>{t.assigned_agent_id?.slice(0, 8) || "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted cursor-pointer" onClick={() => navigate(`/admin/tickets/${t.id}`)}>{t.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </>
          )}
        </div>
      </main>
      {confirmDialog && (
        <BulkTypedConfirmDialog
          count={confirmDialog.count}
          action={confirmDialog.action}
          onCancel={() => setConfirmDialog(null)}
          onConfirm={async () => {
            const { action, payload } = confirmDialog;
            setConfirmDialog(null);
            await executeBulk(action, payload, BULK_TYPED_CONFIRMATION_KEYWORD);
          }}
        />
      )}
    </div>
  );
}

export function TicketDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [showPromote, setShowPromote] = useState(false);

  async function refresh() {
    try {
      const r = await api.get(`/admin/tickets/${id}`);
      setData(r.data?.data);
    } catch (e) {
      setError(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }
  useEffect(() => { refresh(); }, [id]);

  if (error) return <div className="min-h-screen flex items-center justify-center text-status-escalated">{error}</div>;
  if (!data) return <div className="min-h-screen flex items-center justify-center text-mye-ink-muted text-sm">Cargando…</div>;

  const { ticket, timeline, guia, active_claim } = data;
  const canPromote = !active_claim && ["resolved", "closed"].includes(ticket.status);

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="ticket-detail-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1100px] mx-auto px-6 py-3 flex items-center gap-3">
          <button onClick={() => navigate("/admin/tickets")} className="inline-flex items-center gap-1.5 text-xs text-mye-ink-muted hover:text-mye-ink">
            <ArrowLeft className="h-3.5 w-3.5" /> Casos
          </button>
          <div className="font-mono text-[11px] text-mye-ink-muted">#{ticket.id.slice(0, 8)}</div>
          <div className="ml-auto flex items-center gap-3">
            <SaaSHierarchyBreadcrumb
              className="hidden md:inline-flex mr-2"
              clientName={ticket?.client_name || ticket?.recipient_name || undefined}
            />
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1100px] mx-auto px-6 py-10 grid lg:grid-cols-3 gap-6 animate-fade-in">
        <section className="lg:col-span-2 space-y-6">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono " +
                (STATUS_COLOR[ticket.status] || "border-mye-border")}>{ticket.status}</span>
              {ticket.incident_type && (
                <span className="inline-flex items-center gap-1 text-mye-ink-muted text-xs">
                  <AlertTriangle className="h-3.5 w-3.5" /> {ticket.incident_type}
                </span>
              )}
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Caso {ticket.id.slice(0, 8)}</h1>
            <p className="text-mye-ink-muted text-sm">
              Estado canónico: <span className="font-mono">{ticket.canonical_status || "—"}</span> · raw del carrier:{" "}
              <span className="font-mono">{ticket.carrier_status_raw || "—"}</span>
            </p>
          </div>

          {guia && (
            <div className="bg-white border border-mye-border rounded-lg p-5 space-y-3">
              <div className="font-medium text-sm flex items-center justify-between">
                <span>Guía</span>
                {(guia.carrier_code === "routal" && guia.carrier_meta?.routal_project_id) && (
                  <GuiaCancelButton guiaId={guia.id}
                                      tracking={guia.tracking_id}
                                      projectId={guia.carrier_meta.routal_project_id}
                                      onDone={refresh} />
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <KV k="tracking_id" v={guia.tracking_id} mono />
                <KV k="carrier_code" v={guia.carrier_code} mono />
                <KV k="carrier_status" v={guia.carrier_status} mono />
                <KV k="internal_status" v={guia.internal_status} mono />
                <KV k="is_terminal" v={guia.is_terminal ? "true" : "false"} mono />
                <KV k="ingest_source" v={guia.ingest_source} mono />
                <KV k="last_ingest_at" v={guia.last_ingest_at} mono />
                {guia.carrier_meta?.routal_project_id && (
                  <KV k="routal_project_id" v={guia.carrier_meta.routal_project_id} mono />
                )}
                {guia.outbound_last_action && (
                  <KV k="outbound_last" v={`${guia.outbound_last_action}/${guia.outbound_last_status}`} mono />
                )}
              </div>
            </div>
          )}

          <EvidenceCard ownerKind="ticket" ownerId={ticket.id} onChanged={refresh} />

          <div className="bg-white border border-mye-border rounded-lg p-5 space-y-3">
            <div className="flex items-center gap-2 font-medium text-sm">
              <Clock className="h-4 w-4 text-mye-accent" /> Timeline (append-only · R04)
            </div>
            <ol className="space-y-3" data-testid="ticket-timeline">
              {timeline.map((e) => (
                <li key={e.id} className="flex gap-3">
                  <div className="mt-1 h-2 w-2 rounded-full bg-mye-accent flex-none" />
                  <div className="text-sm flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-[12px]">{e.event_type}</span>
                      <span className="text-[11px] font-mono text-mye-ink-muted">· {e.actor_type}</span>
                      <span className="text-[11px] font-mono text-mye-ink-muted ml-auto">{e.created_at}</span>
                    </div>
                    {e.payload && Object.keys(e.payload).length > 0 && (
                      <pre className="mt-1 bg-mye-app rounded px-2 py-1 text-[11px] font-mono text-mye-ink-muted overflow-x-auto">
{JSON.stringify(e.payload, null, 2)}
                      </pre>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <aside className="space-y-3">
          <div className="bg-white border border-mye-border rounded-lg p-4 space-y-2">
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Asignación</div>
            <div className="font-mono text-[12px]">{ticket.assigned_agent_id?.slice(0, 8) || "—"}</div>
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted pt-2">Cliente</div>
            <div className="font-mono text-[12px]">{ticket.client_id.slice(0, 8)}</div>
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted pt-2">Source</div>
            <div className="font-mono text-[12px]">{ticket.source}</div>
          </div>

          {/* Reclamo card — PROMPT 13 */}
          <div className="bg-white border border-mye-border rounded-lg p-4 space-y-3" data-testid="ticket-claim-card">
            <div className="flex items-center gap-2 font-medium text-sm">
              <Scale className="h-4 w-4 text-mye-accent" /> Reclamo
            </div>
            {active_claim ? (
              <>
                <div className="text-xs text-mye-ink-muted">
                  Hay un reclamo activo asociado a este ticket.
                </div>
                <div className="space-y-1">
                  <div className="font-mono text-[11px] text-mye-ink-muted">id: {active_claim.id.slice(0, 8)}</div>
                  <div className="font-mono text-[11px]">estado: {active_claim.estado}</div>
                  <div className="font-mono text-[11px]">monto: {active_claim.monto_reclamado} {active_claim.divisa}</div>
                </div>
                <Link to={`/reclamos/${active_claim.id}`}
                      data-testid="ticket-view-claim-link"
                      className="inline-flex items-center gap-1.5 w-full justify-center rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition">
                  Ver reclamo <ExternalLink className="h-3.5 w-3.5" />
                </Link>
              </>
            ) : canPromote ? (
              <>
                <div className="text-xs text-mye-ink-muted">
                  Este ticket cerró en estado {ticket.status}. Si la incidencia derivó en daño, extravío o retraso, conviértelo en reclamo.
                </div>
                <button data-testid="ticket-promote-claim-btn"
                        onClick={() => setShowPromote(true)}
                        className="inline-flex items-center gap-1.5 w-full justify-center rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition">
                  Promover a reclamo
                </button>
              </>
            ) : (
              <div className="text-xs text-mye-ink-muted">
                Sólo tickets en estado <span className="font-mono">resolved</span> o <span className="font-mono">closed</span> pueden promoverse a reclamo.
              </div>
            )}
          </div>

          {ticket.status === "resolved" && (
            <div className="rounded-md border border-status-resolved/40 bg-status-resolved/5 p-3 text-xs text-status-resolved flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" /> Cerrado automáticamente por la engine.
            </div>
          )}

          <a href={`${process.env.REACT_APP_BACKEND_URL}/api/admin/tickets/${ticket.id}/export.pdf`}
             target="_blank" rel="noreferrer"
             onClick={async (e) => {
               e.preventDefault();
               const token = localStorage.getItem("mye_access_token");
               const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin/tickets/${ticket.id}/export.pdf`,
                 { headers: { Authorization: `Bearer ${token}` } });
               if (!res.ok) return;
               const blob = await res.blob();
               const a = document.createElement("a");
               a.href = URL.createObjectURL(blob);
               a.download = `ticket-${ticket.id.slice(0, 8)}.pdf`;
               a.click();
               URL.revokeObjectURL(a.href);
             }}
             className="inline-flex items-center gap-1.5 w-full justify-center rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition"
             data-testid="ticket-export-pdf">
            Exportar a PDF
          </a>
        </aside>
      </main>

      <section className="max-w-[1400px] mx-auto px-6 pb-10">
        <WhatsAppPanel ticketId={ticket.id} clientPhone={ticket.client_phone || ""} />
      </section>

      {showPromote && (
        <PromoteClaimModal
          ticketId={ticket.id}
          onClose={() => setShowPromote(false)}
          onCreated={(claimId) => {
            setShowPromote(false);
            navigate(`/reclamos/${claimId}`);
          }}
        />
      )}
    </div>
  );
}

function PromoteClaimModal({ ticketId, onClose, onCreated }) {
  const [tipoDano, setTipoDano] = useState("dano_total");
  const [monto, setMonto] = useState("");
  const [divisa, setDivisa] = useState("MXN");
  const [notas, setNotas] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true); setErr(null);
    try {
      const r = await api.post(`/tickets/${ticketId}/promote-to-claim`, {
        tipo_dano: tipoDano,
        monto_reclamado: parseFloat(monto),
        divisa,
        notas_iniciales: notas || undefined,
      });
      if (r.data?.success) onCreated(r.data.data.id);
      else setErr(r.data?.errors?.[0]?.message || "No se pudo crear el reclamo.");
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setSubmitting(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
         data-testid="promote-claim-modal" onClick={onClose}>
      <div className="bg-white border border-mye-border rounded-lg w-full max-w-md p-6 space-y-4 shadow-xl"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <Scale className="h-4 w-4 text-mye-accent" />
          <h2 className="text-lg font-semibold">Promover a reclamo</h2>
        </div>
        <p className="text-xs text-mye-ink-muted">
          Una vez creado, el reclamo entra al estado <span className="font-mono">promovido</span>.
          Reglas R28-R35 aplican (estado terminal protegido, expediente obligatorio antes de enviar al carrier).
        </p>
        <form onSubmit={submit} className="space-y-3" data-testid="promote-claim-form">
          <div>
            <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              Tipo de daño
            </label>
            <select value={tipoDano} onChange={(e) => setTipoDano(e.target.value)}
                    data-testid="promote-tipo-dano"
                    className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm">
              <option value="extravio">Extravío</option>
              <option value="dano_total">Daño total</option>
              <option value="dano_parcial">Daño parcial</option>
              <option value="retraso">Retraso</option>
            </select>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2">
              <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                Monto reclamado
              </label>
              <input type="number" step="0.01" min="0.01" required
                     value={monto} onChange={(e) => setMonto(e.target.value)}
                     data-testid="promote-monto"
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono" />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                Divisa
              </label>
              <select value={divisa} onChange={(e) => setDivisa(e.target.value)}
                      data-testid="promote-divisa"
                      className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono">
                <option>MXN</option><option>USD</option><option>EUR</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              Notas (opcional)
            </label>
            <textarea value={notas} onChange={(e) => setNotas(e.target.value)}
                      data-testid="promote-notas"
                      rows={3} maxLength={2000}
                      className="w-full rounded-md border border-mye-border px-3 py-2 text-sm" />
          </div>
          {err && (
            <div className="rounded-md border border-status-escalated/40 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
                 data-testid="promote-error">
              {err}
            </div>
          )}
          <div className="flex items-center justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
                    className="rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition">
              Cancelar
            </button>
            <button type="submit" disabled={submitting}
                    data-testid="promote-submit"
                    className="rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-50">
              {submitting ? "Creando…" : "Crear reclamo"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function KV({ k, v, mono }) {
  return (
    <div className="rounded-md border border-mye-border bg-mye-app/40 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">{k}</div>
      <div className={"text-sm " + (mono ? "font-mono text-[12px]" : "")}>{v ?? "—"}</div>
    </div>
  );
}


function BulkBar({ count, busy, err, onAction, onClear }) {
  const [showAssign, setShowAssign] = useState(false);
  const [showStatus, setShowStatus] = useState(false);
  const [showComment, setShowComment] = useState(false);
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState("");
  const [status, setStatus] = useState("waiting_carrier");
  const [comment, setComment] = useState("");

  useEffect(() => {
    if (showAssign && agents.length === 0) {
      api.get("/admin/users").then((r) => setAgents(r.data?.data?.items?.filter(
        (u) => ["agent", "supervisor"].includes(u.role)) || [])).catch(() => {});
    }
  }, [showAssign, agents.length]);

  return (
    <div className="border-b border-mye-border bg-mye-accent/5 px-4 py-2.5 flex flex-wrap items-center gap-2" data-testid="bulk-bar">
      <span className="text-xs font-mono text-mye-accent font-semibold" data-testid="bulk-count">
        {count} ticket{count > 1 ? "s" : ""} seleccionados
      </span>
      <div className="flex flex-wrap items-center gap-2 ml-auto">
        <button onClick={() => onAction("close")} disabled={busy}
                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1 text-xs hover:bg-mye-primary-soft transition disabled:opacity-60"
                data-testid="bulk-close">
          Cerrar
        </button>
        <button onClick={() => setShowAssign((v) => !v)} disabled={busy}
                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1 text-xs hover:bg-mye-primary-soft transition disabled:opacity-60"
                data-testid="bulk-assign-toggle">
          Asignar
        </button>
        <button onClick={() => setShowStatus((v) => !v)} disabled={busy}
                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1 text-xs hover:bg-mye-primary-soft transition disabled:opacity-60"
                data-testid="bulk-status-toggle">
          Cambiar status
        </button>
        <button onClick={() => setShowComment((v) => !v)} disabled={busy}
                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1 text-xs hover:bg-mye-primary-soft transition disabled:opacity-60"
                data-testid="bulk-comment-toggle">
          Comentar
        </button>
        <button onClick={() => onAction("export_pdf")} disabled={busy}
                className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-2.5 py-1 text-xs hover:brightness-110 transition disabled:opacity-60"
                data-testid="bulk-export-pdf">
          Exportar ZIP de PDFs
        </button>
        <button onClick={onClear} disabled={busy}
                className="text-xs text-mye-ink-muted hover:text-mye-ink ml-2"
                data-testid="bulk-clear">
          Limpiar
        </button>
      </div>

      {showAssign && (
        <div className="w-full mt-2 flex items-center gap-2">
          <select value={agentId} onChange={(e) => setAgentId(e.target.value)}
                  className="rounded border border-mye-border bg-white px-2 py-1 text-xs flex-1"
                  data-testid="bulk-assign-select">
            <option value="">Seleccionar agente…</option>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.email} ({a.role})</option>)}
          </select>
          <button onClick={() => agentId && onAction("assign", { agent_id: agentId })}
                  disabled={!agentId || busy}
                  className="rounded bg-mye-accent text-white px-3 py-1 text-xs disabled:opacity-60"
                  data-testid="bulk-assign-confirm">
            Asignar
          </button>
        </div>
      )}
      {showStatus && (
        <div className="w-full mt-2 flex items-center gap-2">
          <select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="rounded border border-mye-border bg-white px-2 py-1 text-xs flex-1"
                  data-testid="bulk-status-select">
            <option value="open">open</option>
            <option value="in_progress">in_progress</option>
            <option value="waiting_client">waiting_client</option>
            <option value="waiting_carrier">waiting_carrier</option>
            <option value="resolved">resolved</option>
          </select>
          <button onClick={() => onAction("change_status", { status })}
                  disabled={busy}
                  className="rounded bg-mye-accent text-white px-3 py-1 text-xs disabled:opacity-60"
                  data-testid="bulk-status-confirm">
            Cambiar
          </button>
        </div>
      )}
      {showComment && (
        <div className="w-full mt-2 flex items-center gap-2">
          <input value={comment} onChange={(e) => setComment(e.target.value)}
                 placeholder="Comentario (queda en el timeline)"
                 className="rounded border border-mye-border bg-white px-2 py-1 text-xs flex-1"
                 data-testid="bulk-comment-text" />
          <button onClick={() => comment.trim() && onAction("add_comment", { text: comment.trim() })}
                  disabled={busy || !comment.trim()}
                  className="rounded bg-mye-accent text-white px-3 py-1 text-xs disabled:opacity-60"
                  data-testid="bulk-comment-submit">
            Agregar
          </button>
        </div>
      )}
      {err && (
        <div className="w-full text-[11px] text-status-escalated mt-1">{err}</div>
      )}
    </div>
  );
}


// Bundle A · FIX-A1 — Modal de confirmación tipeada
function BulkTypedConfirmDialog({ count, action, onCancel, onConfirm }) {
  const [typed, setTyped] = useState("");
  const matches = typed === "CERRAR";
  const actionLabel = action === "close" ? "cerrar" : "cambiar el estado de";

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm"
      data-testid="bulk-typed-confirm-overlay"
      // No cerrar al hacer click fuera: forzar interacción consciente.
    >
      <div
        className="w-[min(440px,92vw)] rounded-lg bg-white shadow-xl border border-mye-border p-5"
        data-testid="bulk-typed-confirm-dialog"
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-status-escalated mt-0.5 shrink-0" />
          <div className="flex-1">
            <h2 className="text-base font-semibold text-mye-ink">
              Confirma la acción masiva
            </h2>
            <p className="text-sm text-mye-ink-muted mt-1.5 leading-relaxed">
              Estás por <strong>{actionLabel}</strong> {count} tickets. Esta acción
              será reversible durante <strong>30 segundos</strong> después de ejecutarse.
            </p>
            <p className="text-sm text-mye-ink mt-3">
              Escribí <span className="font-mono text-mye-accent font-semibold">CERRAR</span> para
              confirmar:
            </p>
            <input
              autoFocus
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder="CERRAR"
              className="mt-2 w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono uppercase
                         focus:outline-none focus:ring-2 focus:ring-mye-accent/40"
              data-testid="bulk-typed-confirm-input"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 mt-5">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft"
            data-testid="bulk-typed-confirm-cancel"
          >
            Cancelar (Esc)
          </button>
          <button
            type="button"
            disabled={!matches}
            onClick={onConfirm}
            className="rounded-md bg-status-escalated text-white px-3 py-1.5 text-sm
                       hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed
                       transition"
            data-testid="bulk-typed-confirm-submit"
          >
            Confirmar
          </button>
        </div>
      </div>
    </div>
  );
}
