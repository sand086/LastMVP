import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import {
  readDraft, clearDraft, useReclamoDraft,
} from "@/lib/useReclamoDraft";
import { useRulesContext } from "@/lib/useRulesContext";
import { formatCurrencyMX, fechaCompacta } from "@/lib/formatFechaMX";
import EvidenceCard from "@/components/EvidenceCard";
import InboxBell from "@/components/InboxBell";
import {
  ArrowLeft, LogOut, RefreshCw, Scale, Clock, FileText, AlertTriangle,
  CheckCircle2, XCircle, Send, Inbox, ListTree, Download, FileDown, Sparkles,
} from "lucide-react";

const ESTADOS = [
  "promovido", "expediente_en_armado", "enviado_carrier",
  "en_dictamen_carrier", "aprobado_carrier", "rechazado_carrier",
  "en_conciliacion", "conciliado", "desistido",
];
const TERMINALES = new Set(["conciliado", "desistido"]);

const ALLOWED_TRANSITIONS = {
  promovido:            ["expediente_en_armado", "desistido"],
  expediente_en_armado: ["enviado_carrier", "desistido"],
  enviado_carrier:      ["en_dictamen_carrier"],
  en_dictamen_carrier:  ["aprobado_carrier", "rechazado_carrier"],
  aprobado_carrier:     ["en_conciliacion"],
  rechazado_carrier:    ["desistido", "en_conciliacion"],
  en_conciliacion:      ["conciliado", "desistido"],
  conciliado:           [],
  desistido:            [],
};

const ESTADO_COLOR = {
  promovido:            "bg-status-pending/10 text-status-pending border-status-pending/30",
  expediente_en_armado: "bg-status-active/10 text-status-active border-status-active/30",
  enviado_carrier:      "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  en_dictamen_carrier:  "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  aprobado_carrier:     "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
  rechazado_carrier:    "bg-status-escalated/10 text-status-escalated border-status-escalated/30",
  en_conciliacion:      "bg-status-claim/10 text-status-claim border-status-claim/30",
  conciliado:           "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
  desistido:            "bg-status-closed/10 text-status-closed border-status-closed/30",
};

function Header({ trail = [] }) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  return (
    <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
      <div className="max-w-[1200px] mx-auto px-6 py-3 flex items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
            <div className="font-mono text-[10px] text-mye-ink-muted">
              {trail.length ? trail.join(" · ") : "Reclamos · PROMPT 13"}
            </div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <InboxBell />
        </div>
      </div>
    </header>
  );
}

export default function Reclamos() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMsg, setBulkMsg] = useState(null);
  const [seedBusy, setSeedBusy] = useState(false);

  const isAdmin = ["admin", "superadmin", "root_dev"].includes(user?.role);

  async function refresh() {
    setLoading(true);
    try {
      const params = filter ? { estado: filter } : {};
      const r = await api.get("/reclamos", { params });
      setItems(r.data?.data?.items || []);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, [filter]);

  function toggle(id) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleAll() {
    setSelected((s) => {
      if (items.every((r) => s.has(r.id))) return new Set();
      return new Set(items.map((r) => r.id));
    });
  }

  async function bulkExportZip() {
    setBulkBusy(true); setBulkMsg(null);
    try {
      const ids = Array.from(selected);
      const r = await api.post("/admin/claims/bulk-export.zip",
        { claim_ids: ids }, { responseType: "blob" });
      const blob = new Blob([r.data], { type: "application/zip" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `reclamos-${ids.length}-${Date.now()}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
      setBulkMsg(`ZIP descargado · ${ids.length} reclamo(s)`);
    } catch (e) {
      setBulkMsg(`Error: ${e.response?.data?.errors?.[0]?.message || e.message}`);
    } finally { setBulkBusy(false); }
  }
  async function downloadOne(claimId) {
    try {
      const r = await api.get(`/admin/claims/${claimId}/export.pdf`,
        { responseType: "blob" });
      const blob = new Blob([r.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `reclamo-${claimId}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Error: ${e.response?.data?.errors?.[0]?.message || e.message}`);
    }
  }
  async function seedDemo() {
    setSeedBusy(true); setBulkMsg(null);
    try {
      const r = await api.post("/admin/seed/demo-claims");
      const d = r.data?.data || {};
      setBulkMsg(
        d.created > 0
          ? `${d.created} reclamo(s) demo creado(s)`
          : `Ya seedeado (${d.skipped} reclamos existentes)`,
      );
      await refresh();
    } catch (e) {
      setBulkMsg(`Error: ${e.response?.data?.errors?.[0]?.message || e.message}`);
    } finally { setSeedBusy(false); }
  }

  const allSelected = items.length > 0 && items.every((r) => selected.has(r.id));

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="reclamos-page">
      <Header />
      <main className="max-w-[1200px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 13 · Módulo Reclamos
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Reclamos a carriers</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            Cada reclamo nace desde un ticket cerrado y avanza por la matriz de transiciones
            (R31). El estado terminal es inmutable (R28); sólo se permite un reclamo activo
            por ticket (R29).
          </p>
        </section>

        <div className="flex flex-wrap items-center gap-2 bg-white border border-mye-border rounded-lg p-2">
          <span className="text-xs font-mono text-mye-ink-muted px-2">Filtro:</span>
          {["", ...ESTADOS].map((s) => (
            <button key={s || "all"} onClick={() => setFilter(s)}
                    className={"px-3 py-1.5 rounded-md text-xs font-mono transition " +
                      (filter === s
                        ? "bg-mye-accent text-white"
                        : "text-mye-ink-muted hover:bg-mye-primary-soft")}
                    data-testid={`reclamos-filter-${s || "all"}`}>
              {s || "todos"}
            </button>
          ))}
          <button onClick={refresh}
                  className="ml-auto inline-flex items-center gap-1 rounded-md border border-mye-border px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="reclamos-refresh">
            <RefreshCw className="h-3.5 w-3.5" /> Refrescar
          </button>
          {isAdmin && items.length === 0 && (
            <button onClick={seedDemo} disabled={seedBusy}
                    className="inline-flex items-center gap-1 rounded-md border border-mye-accent/40 bg-mye-accent/5 text-mye-accent px-2.5 py-1.5 text-xs hover:bg-mye-accent/10 transition disabled:opacity-60"
                    data-testid="reclamos-seed-demo">
              <Sparkles className="h-3.5 w-3.5" /> Seed 3 reclamos demo
            </button>
          )}
        </div>

        {/* Bulkbar */}
        {isAdmin && selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 bg-mye-accent/5 border border-mye-accent/30 rounded-lg px-4 py-2"
               data-testid="reclamos-bulkbar">
            <span className="text-xs font-mono text-mye-accent">
              {selected.size} reclamo(s) seleccionado(s)
            </span>
            <button onClick={bulkExportZip} disabled={bulkBusy}
                    className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                    data-testid="reclamos-bulk-export-zip">
              <FileDown className="h-3.5 w-3.5" />
              {bulkBusy ? "Generando ZIP…" : "Exportar PDFs (ZIP)"}
            </button>
            <button onClick={() => setSelected(new Set())}
                    className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                    data-testid="reclamos-bulk-clear">
              <XCircle className="h-3 w-3" /> Limpiar selección
            </button>
            {bulkMsg && (
              <span className="text-xs font-mono text-mye-ink-muted ml-auto"
                    data-testid="reclamos-bulk-msg">{bulkMsg}</span>
            )}
          </div>
        )}
        {bulkMsg && (!isAdmin || selected.size === 0) && (
          <div className="rounded-md border border-mye-border bg-white px-3 py-2 text-xs font-mono text-mye-ink"
               data-testid="reclamos-bulk-msg-standalone">{bulkMsg}</div>
        )}

        <div className="bg-white border border-mye-border rounded-lg overflow-hidden">
          {loading ? (
            <div className="px-6 py-10 text-center text-sm text-mye-ink-muted font-mono">Cargando…</div>
          ) : items.length === 0 ? (
            <div className="px-6 py-12 text-center" data-testid="reclamos-empty">
              <Inbox className="h-8 w-8 mx-auto text-mye-ink-muted mb-2" />
              <div className="text-sm text-mye-ink-muted">
                Sin reclamos. Promueve uno desde
                <Link to="/admin/tickets" className="underline text-mye-accent ml-1">Tickets</Link>.
              </div>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-mye-app/60">
                <tr>
                  {isAdmin && (
                    <th className="w-10 px-3 py-2.5">
                      <input type="checkbox" checked={allSelected} onChange={toggleAll}
                             className="h-4 w-4 accent-mye-accent"
                             data-testid="reclamos-select-all" />
                    </th>
                  )}
                  {["#", "Estado", "Tipo daño", "Monto", "Promovido", "Ticket"].map((h) => (
                    <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
                  ))}
                  {isAdmin && <th className="w-10"></th>}
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id}
                      className="border-t border-mye-border hover:bg-mye-primary-soft/30 transition cursor-pointer"
                      onClick={() => navigate(`/reclamos/${c.id}`)}
                      data-testid={`reclamos-row-${c.id}`}>
                    {isAdmin && (
                      <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={selected.has(c.id)}
                               onChange={() => toggle(c.id)}
                               className="h-4 w-4 accent-mye-accent"
                               data-testid={`reclamos-select-${c.id}`} />
                      </td>
                    )}
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{c.id.slice(0, 8)}</td>
                    <td className="px-4 py-2.5">
                      <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono " +
                        (ESTADO_COLOR[c.estado] || "border-mye-border")}>
                        {c.estado}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-mye-ink-muted">{c.tipo_dano || "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px]">{c.monto_reclamado} {c.divisa}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{c.promoted_at}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{c.ticket_id?.slice(0, 8)}</td>
                    {isAdmin && (
                      <td className="px-2 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                        <button onClick={() => downloadOne(c.id)}
                                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-primary-soft transition"
                                title="Descargar PDF"
                                data-testid={`reclamos-pdf-${c.id}`}>
                          <Download className="h-3 w-3" />
                          PDF
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}

// ──────────────────────────── Detail ─────────────────────────────────
export function ReclamoDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [actionErr, setActionErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const r = await api.get(`/reclamos/${id}`);
      setData(r.data?.data);
    } catch (e) {
      setError(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }
  useEffect(() => { refresh(); }, [id]);

  // Bundle B · R50 · FIX-B3 — proyección R28 (estados terminales reclamo)
  // NOTA: useRulesContext debe llamarse ANTES de cualquier early return
  // para cumplir con las Rules of Hooks de React.
  const rules = useRulesContext(data?.projection);

  if (error) return <div className="min-h-screen flex items-center justify-center text-status-escalated">{error}</div>;
  if (!data) return <div className="min-h-screen flex items-center justify-center text-mye-ink-muted text-sm">Cargando…</div>;

  const { claim, events, indemnization, projection } = data;
  const allowed = ALLOWED_TRANSITIONS[claim.estado] || [];
  const isTerminal = TERMINALES.has(claim.estado);
  const isCoordinator = ["coordinator", "admin", "superadmin", "root_dev"].includes(user?.role);
  const terminalReason = isTerminal ? (
    claim.estado === "conciliado"
      ? "Conciliado"
      : claim.estado === "desistido" ? "Desistido" : "Cerrado"
  ) : null;
  // Identificar evento de conciliación o desistimiento para metadata banner.
  const terminalEvent = isTerminal
    ? (events || []).slice().reverse().find((ev) =>
        ev.event_type === "state_change" && ev.estado_nuevo === claim.estado,
      )
    : null;

  async function transition(target) {
    setBusy(true); setActionErr(null);
    try {
      const r = await api.post(`/reclamos/${claim.id}/transition`, { target });
      if (!r.data?.success) {
        const errs = r.data?.errors || [];
        setActionErr(errs.map((e) => e.message).join(" · "));
      }
      await refresh();
    } catch (e) {
      const errs = e.response?.data?.errors || [];
      setActionErr(errs.map((er) => er.message).join(" · ") || e.message);
    } finally { setBusy(false); }
  }

  async function sendToCarrier() {
    setBusy(true); setActionErr(null);
    try {
      await api.post(`/reclamos/${claim.id}/enviar-carrier`);
      await refresh();
    } catch (e) {
      setActionErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  async function downloadPdf() {
    try {
      const r = await api.get(`/admin/claims/${claim.id}/export.pdf`,
        { responseType: "blob" });
      const blob = new Blob([r.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `reclamo-${claim.id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setActionErr(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="reclamo-detail-page">
      <Header trail={["Reclamo", claim.id.slice(0, 8)]} />
      <main className="max-w-[1200px] mx-auto px-6 py-10 grid lg:grid-cols-3 gap-6 animate-fade-in">
        <section className="lg:col-span-2 space-y-6">
          <div>
            <button onClick={() => navigate("/reclamos")}
                    className="inline-flex items-center gap-1.5 text-xs text-mye-ink-muted hover:text-mye-ink transition mb-2">
              <ArrowLeft className="h-3.5 w-3.5" /> Reclamos
            </button>
            <div className="flex items-center gap-2 mb-1">
              <span data-testid="reclamo-estado"
                    className={"inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-mono " +
                (ESTADO_COLOR[claim.estado] || "border-mye-border")}>
                {claim.estado}
              </span>
              {isTerminal && (
                <span className="inline-flex items-center gap-1 text-mye-ink-muted text-xs">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Terminal · inmutable (R28)
                </span>
              )}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight">Reclamo {claim.id.slice(0, 8)}</h1>
            <p className="text-mye-ink-muted text-sm">
              Tipo: <span className="font-mono">{claim.tipo_dano}</span> ·
              Monto reclamado: <span className="font-mono">{formatCurrencyMX(claim.monto_reclamado, claim.divisa)}</span> ·
              <Link to={`/admin/tickets/${claim.ticket_id}`} className="underline text-mye-accent ml-1"
                    data-testid="reclamo-ticket-link">
                Ver ticket origen
              </Link>
            </p>
          </div>

          {/* Bundle B · FIX-B3 — Banner R28 terminal */}
          {isTerminal && (
            <div
              data-testid="reclamo-terminal-banner"
              className="rounded-md border border-status-resolved/40 bg-status-resolved/5 px-4 py-3 flex items-start gap-3 text-sm text-status-resolved"
            >
              <CheckCircle2 className="h-5 w-5 mt-0.5 shrink-0" />
              <div className="flex-1 leading-relaxed">
                <div className="font-semibold">
                  {terminalReason} · solo lectura.
                </div>
                <div className="text-status-resolved/80 mt-0.5">
                  {terminalEvent?.created_at && (
                    <>
                      {claim.estado === "conciliado" ? "Conciliado" : "Desistido"} el{" "}
                      <span className="font-mono">
                        {String(terminalEvent.created_at).slice(0, 10)}
                      </span>
                      {terminalEvent.actor_id && (
                        <>
                          {" "}por <span className="font-mono">{terminalEvent.actor_id.slice(0, 8)}</span>
                        </>
                      )}
                    </>
                  )}
                  {indemnization?.monto_conciliado != null && (
                    <>
                      {" · Monto conciliado: "}
                      <span className="font-mono">
                        {formatCurrencyMX(
                          indemnization.monto_conciliado,
                          indemnization.divisa_conciliado || claim.divisa,
                        )}
                      </span>
                    </>
                  )}
                </div>
                {rules.isAllowed("request_reopen") && (
                  <p className="mt-2 text-xs text-status-resolved/70">
                    {rules.tooltip("request_reopen")}
                  </p>
                )}
              </div>
            </div>
          )}

          <StateMachineStrip current={claim.estado} />

          <div className="bg-white border border-mye-border rounded-lg p-5 space-y-4">
            <div className="flex items-center gap-2 font-medium text-sm">
              <FileText className="h-4 w-4 text-mye-accent" /> Expediente (R35)
            </div>
            <ExpedienteEditor claim={claim} disabled={isTerminal} onSaved={refresh} />
          </div>

          <EvidenceCard ownerKind="claim" ownerId={claim.id} disabled={isTerminal} onChanged={refresh} />

          {indemnization && (
            <div className="bg-white border border-mye-border rounded-lg p-5 space-y-3"
                 data-testid="reclamo-indemnization">
              <div className="flex items-center gap-2 font-medium text-sm">
                <Scale className="h-4 w-4 text-mye-accent" /> Indemnización
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <KV k="monto_aprobado" v={`${indemnization.monto_aprobado ?? "—"} ${indemnization.divisa ?? ""}`} mono />
                <KV k="referencia" v={indemnization.carrier_referencia} mono />
                <KV k="monto_conciliado" v={
                  indemnization.monto_conciliado != null
                    ? `${indemnization.monto_conciliado} ${indemnization.divisa_conciliado ?? ""}`
                    : "—"
                } mono />
                <KV k="conciliado_at" v={indemnization.conciliado_at} mono />
              </div>
            </div>
          )}

          <div className="bg-white border border-mye-border rounded-lg p-5 space-y-3">
            <div className="flex items-center gap-2 font-medium text-sm">
              <Clock className="h-4 w-4 text-mye-accent" /> Eventos (append-only · R30)
            </div>
            <ol className="space-y-3" data-testid="reclamo-eventos">
              {events.map((e) => (
                <li key={e.id} className="flex gap-3">
                  <div className="mt-1 h-2 w-2 rounded-full bg-mye-accent flex-none" />
                  <div className="text-sm flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-[12px]">{e.event_type}</span>
                      <span className="text-[11px] font-mono text-mye-ink-muted">
                        · {e.estado_anterior || "∅"} → {e.estado_nuevo || "—"}
                      </span>
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
          <div className="bg-white border border-mye-border rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-2 font-medium text-sm">
              <ListTree className="h-4 w-4 text-mye-accent" /> Acciones
            </div>
            {actionErr && (
              <div className="rounded-md border border-status-escalated/40 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
                   data-testid="reclamo-action-error">
                {actionErr}
              </div>
            )}
            {/* PDF export para admin+ siempre disponible (incluso terminal) */}
            {["admin", "superadmin", "root_dev"].includes(user?.role) && (
              <button onClick={downloadPdf}
                      data-testid="reclamo-download-pdf"
                      className="w-full inline-flex items-center justify-center gap-1.5 rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition">
                <FileText className="h-3.5 w-3.5" /> Descargar expediente PDF
              </button>
            )}
            {isTerminal ? (
              <div className="text-xs text-mye-ink-muted">
                Este reclamo está en estado terminal y no admite cambios.
              </div>
            ) : (
              <>
                {claim.estado === "expediente_en_armado" && (
                  <button onClick={sendToCarrier} disabled={busy}
                          data-testid="reclamo-send-carrier"
                          className="w-full inline-flex items-center justify-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-50">
                    <Send className="h-3.5 w-3.5" /> Enviar a carrier (R33)
                  </button>
                )}
                {allowed.map((target) => (
                  <button key={target} onClick={() => transition(target)} disabled={busy}
                          data-testid={`reclamo-transition-${target}`}
                          className="w-full inline-flex items-center justify-center gap-1.5 rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition disabled:opacity-50">
                    {target === "desistido" ? <XCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                    {target}
                  </button>
                ))}
                {claim.estado === "en_conciliacion" && isCoordinator && (
                  <ConciliateForm claimId={claim.id} divisa={claim.divisa}
                                  defaultMonto={indemnization?.monto_aprobado || claim.monto_reclamado}
                                  onDone={refresh} />
                )}
              </>
            )}
          </div>

          <div className="bg-white border border-mye-border rounded-lg p-4 space-y-2 text-xs">
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Cliente</div>
            <div className="font-mono text-[12px]">{claim.client_id?.slice(0, 8)}</div>
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted pt-2">Promovido por</div>
            <div className="font-mono text-[12px]">{claim.promoted_by?.slice(0, 8)}</div>
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted pt-2">Promovido en</div>
            <div className="font-mono text-[12px]">{claim.promoted_at}</div>
            {claim.conciliado_at && (
              <>
                <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted pt-2">Conciliado en</div>
                <div className="font-mono text-[12px]">{claim.conciliado_at}</div>
              </>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}

function StateMachineStrip({ current }) {
  const flow = [
    "promovido", "expediente_en_armado", "enviado_carrier",
    "en_dictamen_carrier", "aprobado_carrier", "en_conciliacion", "conciliado",
  ];
  const idx = flow.indexOf(current);
  const isOffPath = idx < 0;
  return (
    <div className="bg-white border border-mye-border rounded-lg p-4" data-testid="state-machine-strip">
      <div className="flex items-center gap-2 font-medium text-sm mb-3">
        <ListTree className="h-4 w-4 text-mye-accent" /> State machine (R31)
      </div>
      <div className="flex items-center flex-wrap gap-2">
        {flow.map((s, i) => {
          const isCurrent = s === current;
          const isPast = !isOffPath && i < idx;
          return (
            <div key={s} className="flex items-center gap-2">
              <div className={"px-2.5 py-1 rounded-md text-[11px] font-mono border " +
                (isCurrent
                  ? "bg-mye-accent text-white border-mye-accent"
                  : isPast
                    ? "bg-mye-primary-soft text-mye-ink border-mye-border"
                    : "bg-white text-mye-ink-muted border-mye-border")}>
                {s}
              </div>
              {i < flow.length - 1 && <span className="text-mye-ink-muted text-xs">→</span>}
            </div>
          );
        })}
      </div>
      {(current === "rechazado_carrier" || current === "desistido") && (
        <div className="mt-3 text-xs text-status-escalated flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5" /> Estado fuera del happy-path: {current}
        </div>
      )}
    </div>
  );
}

function ExpedienteEditor({ claim, disabled, onSaved }) {
  const { user } = useAuth();
  const initialMonto = claim.monto_reclamado || "";
  const initialTipoDano = claim.tipo_dano || "dano_total";
  const initialDecl = claim.expediente?.declaracion_cliente || "";
  const initialEvidencia = (claim.expediente?.evidencia_ids || []).join(", ");

  const [decl, setDecl] = useState(initialDecl);
  const [evidencia, setEvidencia] = useState(initialEvidencia);
  const [monto, setMonto] = useState(initialMonto);
  const [tipoDano, setTipoDano] = useState(initialTipoDano);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [okMsg, setOkMsg] = useState(null);
  // Confirmación inline para descartar borrador (no usamos window.confirm
  // porque algunos contextos de automation lo bloquean silenciosamente).
  const [discardConfirm, setDiscardConfirm] = useState(false);

  // Bundle A · FIX-A2: auto-save de borrador con clave tenant+claim+user.
  const draftScope = useMemo(() => ({
    tenantId: user?.tenant_id, claimId: claim.id, userId: user?.id,
  }), [user?.tenant_id, user?.id, claim.id]);

  // Banner de borrador previo (decisión one-shot al montar).
  const [pendingDraft, setPendingDraft] = useState(() =>
    !disabled ? readDraft(draftScope) : null,
  );

  // Snapshot de los campos para que el hook debounce los guarde juntos.
  const draftValue = useMemo(() => ({
    monto,
    tipo_dano: tipoDano,
    declaracion_cliente: decl,
    evidencia_ids: evidencia,
    divisa: claim.divisa || "MXN",
  }), [monto, tipoDano, decl, evidencia, claim.divisa]);

  const { savedAt, quotaError, flush, isSaving } = useReclamoDraft({
    ...draftScope, value: draftValue, debounceMs: 5_000,
    enabled: !disabled && !pendingDraft,
  });

  function applyDraft(draft) {
    if (draft?.monto != null) setMonto(draft.monto);
    if (draft?.tipo_dano) setTipoDano(draft.tipo_dano);
    if (typeof draft?.declaracion_cliente === "string") setDecl(draft.declaracion_cliente);
    if (typeof draft?.evidencia_ids === "string") setEvidencia(draft.evidencia_ids);
    setPendingDraft(null);
  }

  function discardDraft() {
    // Limpiar localStorage + ocultar banner + resetear los inputs al estado
    // original del servidor para que el debounce no re-persista el borrador.
    clearDraft(draftScope);
    setMonto(initialMonto);
    setTipoDano(initialTipoDano);
    setDecl(initialDecl);
    setEvidencia(initialEvidencia);
    setPendingDraft(null);
    setDiscardConfirm(false);
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true); setErr(null); setOkMsg(null);
    flush();  // garantizar un save final antes del submit
    const evidencia_ids = evidencia
      .split(",").map((s) => s.trim()).filter(Boolean);
    try {
      const body = {
        monto_reclamado: monto ? parseFloat(monto) : undefined,
        tipo_dano: tipoDano,
        declaracion_cliente: decl || undefined,
        evidencia_ids: evidencia_ids.length ? evidencia_ids : undefined,
      };
      const r = await api.patch(`/reclamos/${claim.id}/expediente`, body);
      if (r.data?.success) {
        setOkMsg("Expediente actualizado.");
        // Submit exitoso → borrador ya no es necesario.
        clearDraft(draftScope);
        onSaved && onSaved();
      } else {
        setErr(r.data?.errors?.[0]?.message || "No se pudo guardar.");
      }
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  const savedAgo = useDraftSavedAgo(savedAt);
  const pendingDraftAgo = useDraftSavedAgo(
    pendingDraft ? new Date(pendingDraft.saved_at) : null,
  );

  return (
    <form onSubmit={save} className="space-y-3 relative" data-testid="expediente-form">
      {pendingDraft && (
        <div
          className="rounded-md border border-mye-accent/30 bg-mye-accent/5 px-3 py-2 flex items-center gap-2 text-xs flex-wrap"
          data-testid="expediente-draft-banner"
        >
          <Clock className="h-3.5 w-3.5 text-mye-accent shrink-0" />
          <div className="flex-1 min-w-0">
            Tenés un borrador local guardado hace{" "}
            <span className="font-mono">
              {pendingDraftAgo || "unos segundos"}
            </span>.
          </div>
          {!discardConfirm && (
            <>
              <button type="button" onClick={() => applyDraft(pendingDraft)}
                      className="rounded bg-mye-accent text-white px-2 py-1 text-[11px] hover:brightness-110 transition"
                      data-testid="expediente-draft-continue">
                Continuar
              </button>
              <button type="button" onClick={() => setDiscardConfirm(true)}
                      className="rounded border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-app/40 transition"
                      data-testid="expediente-draft-discard">
                Descartar
              </button>
            </>
          )}
          {discardConfirm && (
            <>
              <span className="text-mye-ink-muted">¿Seguro?</span>
              <button type="button" onClick={discardDraft}
                      className="rounded bg-status-escalated text-white px-2 py-1 text-[11px] hover:brightness-110 transition"
                      data-testid="expediente-draft-discard-confirm">
                Sí, descartar
              </button>
              <button type="button" onClick={() => setDiscardConfirm(false)}
                      className="rounded border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-app/40 transition"
                      data-testid="expediente-draft-discard-cancel">
                Cancelar
              </button>
            </>
          )}
        </div>
      )}
      {!disabled && !pendingDraft && (
        <div
          className="absolute -top-1 right-0 text-[10px] font-mono text-mye-ink-muted inline-flex items-center gap-1"
          data-testid="expediente-draft-indicator"
        >
          {isSaving ? (
            <>
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
              Guardando…
            </>
          ) : savedAgo ? (
            <>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Guardado · hace {savedAgo}
            </>
          ) : null}
        </div>
      )}
      {quotaError && (
        <div className="text-xs text-status-escalated" data-testid="expediente-draft-quota-error">
          Tu navegador no puede guardar borradores. Considerá cerrar otras pestañas.
        </div>
      )}
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2">
          <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Monto reclamado
          </label>
          <input type="number" step="0.01" min="0.01" value={monto} disabled={disabled}
                 onChange={(e) => setMonto(e.target.value)}
                 data-testid="exp-monto"
                 className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono disabled:opacity-50" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Tipo de daño
          </label>
          <select value={tipoDano} onChange={(e) => setTipoDano(e.target.value)} disabled={disabled}
                  data-testid="exp-tipo-dano"
                  className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm disabled:opacity-50">
            <option value="extravio">Extravío</option>
            <option value="dano_total">Daño total</option>
            <option value="dano_parcial">Daño parcial</option>
            <option value="retraso">Retraso</option>
          </select>
        </div>
      </div>
      <div>
        <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
          Declaración del cliente
        </label>
        <textarea value={decl} onChange={(e) => setDecl(e.target.value)} disabled={disabled}
                  rows={3} maxLength={8000}
                  data-testid="exp-declaracion"
                  className="w-full rounded-md border border-mye-border px-3 py-2 text-sm disabled:opacity-50" />
      </div>
      <div>
        <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
          Evidencia IDs (separados por comas, ≥ 2 para enviar al carrier)
        </label>
        <input value={evidencia} onChange={(e) => setEvidencia(e.target.value)} disabled={disabled}
               data-testid="exp-evidencia"
               placeholder="ev1, ev2, ev3"
               className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono disabled:opacity-50" />
      </div>
      {err && <div className="text-xs text-status-escalated" data-testid="exp-error">{err}</div>}
      {okMsg && <div className="text-xs text-status-resolved">{okMsg}</div>}
      <button type="submit" disabled={disabled || busy}
              data-testid="exp-save"
              className="rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-50">
        {busy ? "Guardando…" : "Guardar expediente"}
      </button>
    </form>
  );
}


// Helper local para indicador "Guardado hace N seg". Tick liviano cada 5s.
function useDraftSavedAgo(date) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!date) return;
    const id = setInterval(() => setTick((t) => t + 1), 5_000);
    return () => clearInterval(id);
  }, [date]);
  if (!date) return null;
  const ms = Date.now() - new Date(date).getTime();
  if (ms < 60_000) return `${Math.max(1, Math.floor(ms / 1000))} s`;
  const mins = Math.floor(ms / 60_000);
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  return `${hours} h`;
}

function ConciliateForm({ claimId, divisa, defaultMonto, onDone }) {
  const [monto, setMonto] = useState(defaultMonto || "");
  const [notas, setNotas] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await api.post(`/reclamos/${claimId}/conciliar`, {
        monto_conciliado: parseFloat(monto),
        divisa,
        notas_conciliacion: notas || undefined,
      });
      if (!r.data?.success) {
        setErr(r.data?.errors?.[0]?.message || "No se pudo conciliar.");
      }
      onDone && onDone();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="space-y-2 pt-2 border-t border-mye-border" data-testid="conciliate-form">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Conciliación (coordinator+)</div>
      <input type="number" step="0.01" min="0.01" required value={monto}
             onChange={(e) => setMonto(e.target.value)}
             placeholder="Monto conciliado"
             data-testid="conc-monto"
             className="w-full rounded-md border border-mye-border px-2.5 py-1.5 text-xs font-mono" />
      <textarea value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} maxLength={2000}
                placeholder="Notas (opcional)"
                data-testid="conc-notas"
                className="w-full rounded-md border border-mye-border px-2.5 py-1.5 text-xs" />
      {err && <div className="text-xs text-status-escalated">{err}</div>}
      <button type="submit" disabled={busy}
              data-testid="conc-submit"
              className="w-full rounded-md bg-mye-accent text-white px-2.5 py-1.5 text-xs hover:opacity-90 transition disabled:opacity-50">
        {busy ? "Conciliando…" : "Conciliar y cerrar reclamo"}
      </button>
    </form>
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
