import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import InboxBell from "@/components/InboxBell";
import {
  Inbox, ListChecks, Hand, CheckCircle2, AlertTriangle, RefreshCw,
  LogOut, LayoutGrid, Table as TableIcon, ArrowLeft, Filter,
  Save, Trash2, X, Rows3, Keyboard, Search, Sparkles,
} from "lucide-react";

import InboxList from "./agent/InboxList";
import TicketDetail from "./agent/TicketDetail";
import ContextPanel from "./agent/ContextPanel";
import KeyboardShortcutsHelp from "./agent/KeyboardShortcutsHelp";
import { useAgentShortcuts } from "./agent/shortcuts";
import { slaInfo, STATUS_COLOR, STATUS_OPTIONS } from "./agent/sla";

const LAYOUT_STORAGE_KEY = "mye:agent:layout";

export default function AgentPanel() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { ticketId } = useParams();
  const [data, setData] = useState({ mine: [], pool: [], totals: { mine: 0, pool: 0 } });
  const [layout, setLayout] = useState(() =>
    localStorage.getItem(LAYOUT_STORAGE_KEY) || "inbox");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ status: "", incident_type: "", q: "" });
  const [savedFilters, setSavedFilters] = useState([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [contextData, setContextData] = useState(null);
  const searchRef = useRef(null);

  // Persist layout choice
  useEffect(() => { localStorage.setItem(LAYOUT_STORAGE_KEY, layout); }, [layout]);

  async function refresh() {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/agent/queue");
      setData(r.data?.data || { mine: [], pool: [], totals: { mine: 0, pool: 0 } });
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setLoading(false); }
  }
  async function loadSaved() {
    try {
      const r = await api.get("/saved-filters");
      setSavedFilters(r.data?.data?.items || []);
    } catch (_e) { /* ok */ }
  }
  useEffect(() => { refresh(); loadSaved(); }, []);

  function applyClientSideFilter(rows) {
    return rows.filter((r) => {
      if (filters.status && r.status !== filters.status) return false;
      if (filters.incident_type && r.incident_type !== filters.incident_type) return false;
      if (filters.q) {
        const q = filters.q.toLowerCase();
        if (!(r.id + " " + (r.tracking_id || "") + " " + (r.motivo_codigo || "")).toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }
  const filteredMine = useMemo(() => applyClientSideFilter(data.mine || []),
    [data.mine, filters]);  
  const filteredPool = useMemo(() => applyClientSideFilter(data.pool || []),
    [data.pool, filters]);  

  const allRows = useMemo(() => [...filteredMine, ...filteredPool],
    [filteredMine, filteredPool]);

  // SLA risk count for the header
  const slaRiskCount = useMemo(() => filteredMine.filter((t) => {
    const s = slaInfo(t);
    return s && (s.level === "risk" || s.level === "warn");
  }).length, [filteredMine]);

  // Keyboard navigation
  function navByOffset(offset) {
    if (allRows.length === 0) return;
    const currentIdx = ticketId
      ? allRows.findIndex((t) => t.id === ticketId)
      : -1;
    const nextIdx = currentIdx === -1
      ? 0
      : Math.max(0, Math.min(allRows.length - 1, currentIdx + offset));
    navigate(`/agente/${allRows[nextIdx].id}`);
  }
  useAgentShortcuts({
    onSearch: () => searchRef.current?.focus(),
    onNext: () => navByOffset(1),
    onPrev: () => navByOffset(-1),
    onOpen: () => {
      if (ticketId) return; // already in detail
      if (allRows[0]) navigate(`/agente/${allRows[0].id}`);
    },
    onClose: () => { if (ticketId) navigate("/agente"); },
    onHelp: () => setShowHelp((v) => !v),
  });

  async function saveCurrentFilter() {
    if (!saveName.trim()) return;
    try {
      await api.post("/saved-filters", {
        name: saveName.trim(), scope: "agent_queue", filters,
      });
      toast.success("Filtro guardado");
      setShowSaveDialog(false); setSaveName("");
      await loadSaved();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  async function deleteSavedFilter(id) {
    if (!window.confirm("¿Borrar filtro guardado?")) return;
    await api.delete(`/saved-filters/${id}`);
    await loadSaved();
  }
  function applySaved(sf) {
    setFilters(sf.filters || {});
    toast.success(`Filtro "${sf.name}" aplicado`);
  }

  function toggle(id) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleAll(rows) {
    setSelected((s) => {
      if (rows.every((r) => s.has(r.id))) {
        const n = new Set(s); rows.forEach((r) => n.delete(r.id)); return n;
      }
      const n = new Set(s); rows.forEach((r) => n.add(r.id)); return n;
    });
  }

  async function bulkTake() {
    setBusy(true);
    try {
      const r = await api.post("/agent/tickets/bulk-take",
        { ticket_ids: Array.from(selected) });
      const d = r.data?.data || {};
      toast.success(`Tomados: ${d.totals?.taken || 0}` +
        (d.totals?.skipped ? ` · omitidos: ${d.totals.skipped}` : ""));
      setSelected(new Set());
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }
  async function bulkSetStatus(status) {
    setBusy(true);
    try {
      const r = await api.post("/agent/tickets/bulk-status",
        { ticket_ids: Array.from(selected), status });
      const d = r.data?.data || {};
      toast.success(`Status → ${status}: ${d.totals?.updated || 0}` +
        (d.totals?.skipped ? ` · omitidos: ${d.totals.skipped}` : ""));
      setSelected(new Set());
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  // -------------------- Render -----------------------------------------
  // 3-column detail layout when a ticket is selected
  if (ticketId) {
    return (
      <div className="min-h-screen flex flex-col bg-mye-app text-mye-ink"
           data-testid="agent-panel-page">
        <Header user={user} logout={logout} navigate={navigate}
                slaRiskCount={slaRiskCount} totals={data.totals}
                onHelp={() => setShowHelp(true)} />
        <div className="flex-1 flex overflow-hidden">
          {/* Left rail: compact inbox */}
          <aside className="w-[300px] flex-shrink-0 border-r border-mye-border bg-white flex flex-col">
            <div className="px-4 py-2.5 border-b border-mye-border flex items-center gap-2">
              <button onClick={() => navigate("/agente")}
                      className="inline-flex items-center gap-1 text-[11px] font-mono text-mye-accent hover:underline"
                      data-testid="back-to-bandeja">
                <ArrowLeft className="h-3 w-3" /> Bandeja
              </button>
              <span className="ml-auto font-mono text-[10px] text-mye-ink-muted">
                {filteredMine.length + filteredPool.length} tickets
              </span>
            </div>
            <div className="flex-1 overflow-auto">
              <InboxList rows={[...filteredMine, ...filteredPool]}
                         selected={selected}
                         focusedId={ticketId}
                         onToggle={toggle}
                         onOpen={(t) => navigate(`/agente/${t.id}`)}
                         compact />
            </div>
          </aside>
          {/* Detail center column */}
          <TicketDetail ticketId={ticketId}
                        onChanged={refresh}
                        onContext={setContextData} />
          {/* Right context panel */}
          <ContextPanel ticket={contextData?.ticket}
                         guia={contextData?.guia}
                         client={contextData?.client}
                         evidenceCount={contextData?.evidence_count || 0} />
        </div>
        {showHelp && <KeyboardShortcutsHelp onClose={() => setShowHelp(false)} />}
      </div>
    );
  }

  // Bandeja mode (list)
  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="agent-panel-page">
      <Header user={user} logout={logout} navigate={navigate}
              slaRiskCount={slaRiskCount} totals={data.totals}
              onHelp={() => setShowHelp(true)} />

      <main className="max-w-[1400px] mx-auto px-6 py-8 space-y-5 animate-fade-in">
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 08 · Operación CS
          </div>
          <div className="flex items-baseline gap-3 flex-wrap">
            <h1 className="text-3xl font-semibold tracking-tight">
              Tu cola
            </h1>
            <span className="font-mono text-sm text-mye-ink-muted">
              {data.totals.mine} asignados · {data.totals.pool} en pool
            </span>
            {slaRiskCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-status-escalated/10 text-status-escalated border border-status-escalated/30 px-2 py-0.5 text-[11px] font-mono"
                    data-testid="agent-sla-risk-count">
                <AlertTriangle className="h-3 w-3" /> {slaRiskCount} en riesgo
              </span>
            )}
          </div>
        </section>

        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={refresh}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="agent-refresh">
            <RefreshCw className={"h-3.5 w-3.5 " + (loading ? "animate-spin" : "")} /> Refrescar
          </button>
          <div className="inline-flex rounded-md border border-mye-border bg-white p-0.5"
               data-testid="agent-layout-switch">
            <LayoutBtn active={layout === "inbox"} onClick={() => setLayout("inbox")}
                       icon={Rows3} label="Inbox" testId="layout-inbox" />
            <LayoutBtn active={layout === "table"} onClick={() => setLayout("table")}
                       icon={TableIcon} label="Tabla" testId="layout-table" />
            <LayoutBtn active={layout === "cards"} onClick={() => setLayout("cards")}
                       icon={LayoutGrid} label="Tarjetas" testId="layout-cards" />
          </div>
          <button onClick={() => setShowHelp(true)}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  title="Ver atajos de teclado (?)"
                  data-testid="agent-help-button">
            <Keyboard className="h-3.5 w-3.5" /> ?
          </button>
        </div>

        {/* Bulk-bar (animated slide-down) */}
        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 bg-mye-accent/5 border border-mye-accent/30 rounded-lg px-4 py-2 animate-fade-in"
               data-testid="agent-bulkbar">
            <span className="text-xs font-mono text-mye-accent">
              {selected.size} seleccionado(s)
            </span>
            <button onClick={bulkTake} disabled={busy}
                    className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1 text-xs hover:brightness-110 transition disabled:opacity-60"
                    data-testid="bulk-take">
              <Hand className="h-3.5 w-3.5" /> Tomar
            </button>
            <button onClick={() => bulkSetStatus("resolved")} disabled={busy}
                    className="inline-flex items-center gap-1 rounded-md border border-status-resolved/30 bg-status-resolved/5 text-status-resolved px-3 py-1 text-xs hover:brightness-95 transition disabled:opacity-60"
                    data-testid="bulk-resolve">
              <CheckCircle2 className="h-3.5 w-3.5" /> Resolver
            </button>
            <button onClick={() => bulkSetStatus("waiting_client")} disabled={busy}
                    className="inline-flex items-center gap-1 rounded-md border border-status-waiting/30 bg-status-waiting/5 text-status-waiting px-3 py-1 text-xs hover:brightness-95 transition disabled:opacity-60"
                    data-testid="bulk-waiting-client">
              Espera cliente
            </button>
            <button onClick={() => setSelected(new Set())}
                    className="ml-auto inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1 text-xs hover:bg-mye-primary-soft transition"
                    data-testid="bulk-clear">
              <X className="h-3 w-3" /> Limpiar
            </button>
          </div>
        )}

        {/* Filtros + Saved filters */}
        <div className="flex flex-wrap items-end gap-2 bg-white border border-mye-border rounded-lg px-4 py-3"
             data-testid="agent-filters-block">
          <Filter className="h-3.5 w-3.5 text-mye-accent mt-2" />
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted">Status</label>
            <select value={filters.status}
                    onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                    className="rounded-md border border-mye-border bg-white px-2 py-1 text-xs font-mono min-w-[140px]"
                    data-testid="agent-filter-status">
              <option value="">— Todos —</option>
              {STATUS_OPTIONS.concat(["pending"]).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted">Incident type</label>
            <input value={filters.incident_type}
                   onChange={(e) => setFilters({ ...filters, incident_type: e.target.value })}
                   placeholder="ej. damaged"
                   className="rounded-md border border-mye-border bg-white px-2 py-1 text-xs font-mono w-40"
                   data-testid="agent-filter-incident-type" />
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[220px]">
            <label className="font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted flex items-center gap-1">
              <Search className="h-3 w-3" /> Buscar <kbd className="ml-1 px-1 py-0 rounded border border-mye-border bg-mye-app/60 text-[9px] font-mono">⌘K</kbd>
            </label>
            <input ref={searchRef} value={filters.q}
                   onChange={(e) => setFilters({ ...filters, q: e.target.value })}
                   placeholder="ID / rastreo / motivo…"
                   className="rounded-md border border-mye-border bg-white px-2 py-1 text-xs font-mono w-full"
                   data-testid="agent-filter-search" />
          </div>
          {(filters.status || filters.incident_type || filters.q) && (
            <button onClick={() => setFilters({ status: "", incident_type: "", q: "" })}
                    className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1 text-xs hover:bg-mye-primary-soft transition"
                    data-testid="agent-filter-clear">
              <X className="h-3 w-3" /> Limpiar
            </button>
          )}
          <button onClick={() => setShowSaveDialog(true)}
                  disabled={!(filters.status || filters.incident_type || filters.q)}
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-2.5 py-1 text-xs hover:brightness-110 transition disabled:opacity-60"
                  data-testid="agent-saved-filter-save">
            <Save className="h-3 w-3" /> Guardar filtro
          </button>
          {savedFilters.length > 0 && (
            <div className="flex items-center gap-1 ml-2"
                 data-testid="agent-saved-filters-list">
              <span className="font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted mr-1">Guardados</span>
              {savedFilters.map((sf) => (
                <span key={sf.id}
                      className="inline-flex items-center gap-1 rounded-full border border-mye-border bg-mye-primary-soft/40 pl-2.5 pr-1 py-0.5 text-[11px] font-mono"
                      data-testid={`agent-saved-filter-item-${sf.id}`}>
                  <button onClick={() => applySaved(sf)}
                          className="hover:underline truncate max-w-[120px]"
                          title={sf.name}
                          data-testid={`agent-saved-filter-apply-${sf.id}`}>
                    {sf.name}
                  </button>
                  <button onClick={() => deleteSavedFilter(sf.id)}
                          className="rounded-full hover:bg-status-escalated/15 p-0.5 text-status-escalated"
                          data-testid={`agent-saved-filter-delete-${sf.id}`}>
                    <Trash2 className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        {showSaveDialog && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-mye-ink/40 backdrop-blur-sm"
               onClick={() => setShowSaveDialog(false)}
               data-testid="agent-saved-filter-dialog">
            <div className="bg-white rounded-lg border border-mye-border p-5 w-[360px] space-y-3"
                 onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center gap-2">
                <Save className="h-4 w-4 text-mye-accent" />
                <h3 className="font-medium text-sm">Guardar filtro actual</h3>
              </div>
              <input value={saveName}
                     onChange={(e) => setSaveName(e.target.value)}
                     placeholder="Nombre del filtro" autoFocus
                     onKeyDown={(e) => e.key === "Enter" && saveCurrentFilter()}
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                     data-testid="agent-saved-filter-name-input" />
              <div className="text-[11px] font-mono text-mye-ink-muted">
                {Object.entries(filters).filter(([_k, v]) => v).map(([k, v]) => `${k}=${v}`).join(" · ")}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button onClick={() => setShowSaveDialog(false)}
                        className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition">
                  Cancelar
                </button>
                <button onClick={saveCurrentFilter} disabled={!saveName.trim()}
                        className="rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                        data-testid="agent-saved-filter-confirm">
                  Guardar
                </button>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated">
            <AlertTriangle className="h-4 w-4 mt-0.5" /> {error}
          </div>
        )}

        <Section title="Mis tickets" rows={filteredMine} layout={layout}
                 onRefresh={refresh} navigate={navigate}
                 selected={selected} onToggle={toggle} onToggleAll={toggleAll}
                 editable />
        <Section title="Pool · sin asignar" rows={filteredPool} layout={layout}
                 onRefresh={refresh} navigate={navigate}
                 selected={selected} onToggle={toggle} onToggleAll={toggleAll}
                 editable={false} />
      </main>
      {showHelp && <KeyboardShortcutsHelp onClose={() => setShowHelp(false)} />}
    </div>
  );
}

function Header({ user, logout, navigate, slaRiskCount, totals, onHelp }) {
  return (
    <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
      <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
        <button onClick={() => navigate("/default")}
                className="inline-flex items-center gap-1.5 text-xs text-mye-ink-muted hover:text-mye-ink"
                data-testid="agent-back-default">
          <ArrowLeft className="h-3.5 w-3.5" /> Default
        </button>
        <div className="flex items-center gap-3 ml-2">
          <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
            <div className="font-mono text-[10px] text-mye-ink-muted">
              Panel de Agente
              {slaRiskCount > 0 && (
                <span className="ml-2 inline-flex items-center gap-1 text-status-escalated">
                  <AlertTriangle className="h-2.5 w-2.5" /> {slaRiskCount} SLA en riesgo
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs font-mono text-mye-ink-muted hidden sm:inline">
            {user?.email} · {totals?.mine || 0} tickets
          </span>
          <InboxBell />
          <button onClick={() => window.__myeReplayTour && window.__myeReplayTour()}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="agent-replay-tour"
                  title="Volver a hacer el tour">
            <Sparkles className="h-3.5 w-3.5" />
          </button>
          <button onClick={onHelp}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="agent-shortcuts-trigger">
            <Keyboard className="h-3.5 w-3.5" />
          </button>
          <button onClick={async () => { await logout(); navigate("/login"); }}
                  className="inline-flex items-center gap-1.5 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="agent-logout">
            <LogOut className="h-3.5 w-3.5" /> Salir
          </button>
        </div>
      </div>
    </header>
  );
}

function LayoutBtn({ active, onClick, icon: Icon, label, testId }) {
  return (
    <button onClick={onClick}
            aria-pressed={active}
            className={"inline-flex items-center gap-1 px-3 py-1 text-xs rounded transition " +
              (active ? "bg-mye-primary-soft text-mye-ink" : "text-mye-ink-muted")}
            data-testid={testId}>
      <Icon className="h-3.5 w-3.5" /> {label}
    </button>
  );
}

function Section({
  title, rows, layout, onRefresh, navigate, selected, onToggle, onToggleAll, editable,
}) {
  if (rows.length === 0) {
    return (
      <div className="bg-white border border-mye-border rounded-lg px-6 py-10 text-center text-sm text-mye-ink-muted">
        <Inbox className="h-6 w-6 mx-auto mb-2 text-mye-ink-muted" /> {title}: vacío
      </div>
    );
  }

  if (layout === "inbox") {
    return (
      <div className="space-y-2">
        <SectionHeader title={title} count={rows.length} />
        <InboxList rows={rows} selected={selected} onToggle={onToggle}
                   onOpen={(t) => navigate(`/agente/${t.id}`)}
                   onTake={editable ? null : async (t) => {
                     await api.post(`/agent/tickets/${t.id}/take`);
                     toast.success("Caso asignado a vos");
                     onRefresh();
                   }} />
      </div>
    );
  }

  if (layout === "table") {
    return (
      <div className="bg-white border border-mye-border rounded-lg overflow-hidden">
        <SectionHeader title={title} count={rows.length} inline />
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              <th className="w-10 px-3 py-2.5">
                <input type="checkbox" checked={rows.every((r) => selected.has(r.id))}
                       onChange={() => onToggleAll(rows)}
                       className="h-4 w-4 accent-mye-accent" />
              </th>
              {["#", "Status", "Incidente", "Carrier", "Creado", "SLA"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-3 py-2.5">{h}</th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => {
              const sla = slaInfo(t);
              return (
                <tr key={t.id}
                    onClick={() => navigate(`/agente/${t.id}`)}
                    className="border-t border-mye-border hover:bg-mye-primary-soft/30 transition cursor-pointer"
                    data-testid={`agent-row-${t.id}`}>
                  <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(t.id)}
                           onChange={() => onToggle(t.id)}
                           className="h-4 w-4 accent-mye-accent" />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-mye-ink-muted">{t.id.slice(0, 8)}</td>
                  <td className="px-3 py-2.5">
                    <span className={"inline-flex rounded-full border px-2 py-0.5 text-[11px] font-mono " +
                      (STATUS_COLOR[t.status] || "border-mye-border")}>{t.status}</span>
                  </td>
                  <td className="px-3 py-2.5 text-mye-ink-muted" data-testid={`agent-row-incident-${t.id}`}>{t.incident_label || t.incident_type_label || t.incident_type || "—"}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px]" data-testid={`agent-row-carrier-${t.id}`}>{t.carrier_code || t.carrier_id || "—"}</td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-mye-ink-muted">{String(t.created_at).slice(0, 16)}</td>
                  <td className="px-3 py-2.5">
                    {sla && (
                      <span className={"inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-mono " +
                        (sla.level === "risk" ? "bg-status-escalated/10 text-status-escalated"
                          : sla.level === "warn" ? "bg-status-waiting/10 text-status-waiting"
                          : "bg-status-resolved/10 text-status-resolved")}>
                        {sla.label}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                    {editable ? <StatusDropdown ticket={t} onChanged={onRefresh} />
                              : <TakeButton ticket={t} onChanged={onRefresh} />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  // Cards
  return (
    <div className="space-y-2">
      <SectionHeader title={title} count={rows.length} />
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {rows.map((t) => {
          const sla = slaInfo(t);
          return (
            <div key={t.id}
                 onClick={() => navigate(`/agente/${t.id}`)}
                 className="rounded-md border border-mye-border bg-white p-3 space-y-2 hover:shadow-sm transition cursor-pointer"
                 data-testid={`agent-card-${t.id}`}>
              <div className="flex items-center gap-2"
                   onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" checked={selected.has(t.id)}
                       onChange={() => onToggle(t.id)}
                       className="h-4 w-4 accent-mye-accent" />
                <span className={"inline-flex rounded-full border px-2 py-0.5 text-[11px] font-mono " +
                  (STATUS_COLOR[t.status] || "border-mye-border")}>{t.status}</span>
                <span className="ml-auto font-mono text-[11px] text-mye-ink-muted">#{t.id.slice(0, 6)}</span>
              </div>
              <div className="text-sm" data-testid={`agent-card-incident-${t.id}`}>{t.incident_label || t.incident_type_label || t.incident_type || "—"}</div>
              <div className="text-xs font-mono text-mye-ink-muted" data-testid={`agent-card-carrier-${t.id}`}>{t.carrier_code || t.carrier_id || "—"}{t.carrier_status_raw ? ` · ${t.carrier_status_raw}` : ""}</div>
              {sla && (
                <div className={"text-[10px] font-mono " +
                  (sla.level === "risk" ? "text-status-escalated"
                    : sla.level === "warn" ? "text-status-waiting"
                    : "text-status-resolved")}>SLA · {sla.label}</div>
              )}
              <div className="pt-2 border-t border-mye-border flex items-center gap-2"
                   onClick={(e) => e.stopPropagation()}>
                {editable ? <StatusDropdown ticket={t} onChanged={onRefresh} />
                          : <TakeButton ticket={t} onChanged={onRefresh} />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SectionHeader({ title, count, inline = false }) {
  if (inline) {
    return (
      <div className="flex items-center gap-2 px-5 py-3 border-b border-mye-border">
        <ListChecks className="h-4 w-4 text-mye-accent" />
        <div className="font-medium text-sm">{title}</div>
        <span className="text-xs font-mono text-mye-ink-muted">· {count}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <ListChecks className="h-3.5 w-3.5 text-mye-accent" />
      <div className="font-medium text-sm">{title}</div>
      <span className="text-xs font-mono text-mye-ink-muted">· {count}</span>
    </div>
  );
}

function StatusDropdown({ ticket, onChanged }) {
  const [busy, setBusy] = useState(false);
  return (
    <select disabled={busy} value={ticket.status}
            onChange={async (e) => {
              setBusy(true);
              try {
                await api.patch(`/agent/tickets/${ticket.id}/status`, { status: e.target.value });
                toast.success(`Status → ${e.target.value}`);
                await onChanged();
              } finally { setBusy(false); }
            }}
            className="rounded-md border border-mye-border bg-white px-2 py-1 text-xs font-mono"
            data-testid={`status-dropdown-${ticket.id}`}>
      <option value={ticket.status}>{ticket.status}</option>
      {STATUS_OPTIONS.filter((s) => s !== ticket.status).map((s) => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

function TakeButton({ ticket, onChanged }) {
  const [busy, setBusy] = useState(false);
  return (
    <button disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api.post(`/agent/tickets/${ticket.id}/take`);
                toast.success("Caso asignado a vos");
                await onChanged();
              } finally { setBusy(false); }
            }}
            className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1 text-xs hover:brightness-110 transition disabled:opacity-60"
            data-testid={`take-button-${ticket.id}`}>
      <Hand className="h-3.5 w-3.5" /> Tomar
    </button>
  );
}
