/**
 * AdminWebhooks — PROMPT 39 V3 · Webhooks salientes.
 *
 * 5 tabs:
 *   1. Suscripciones (CRUD + ver secreto solo al crear)
 *   2. Catálogo de eventos (read-only del global)
 *   3. Log de entregas (filtrable)
 *   4. DLQ (replay/archivar)
 *   5. Health (métricas por suscripción)
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { fechaRelativa } from "@/lib/formatFechaMX";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";
import {
  Webhook, BookOpen, Send, AlertOctagon, Activity, ArrowLeft, LogOut,
  Plus, X, RefreshCw, Copy, RotateCcw, Trash2, RefreshCcw, AlertTriangle,
  Eye, EyeOff, ShieldCheck, KeySquare, Search, BarChart3, TrendingDown,
} from "lucide-react";

const TABS = [
  { key: "dashboard",     label: "Dashboard",     icon: BarChart3 },
  { key: "subscriptions", label: "Suscripciones", icon: Webhook },
  { key: "catalog",       label: "Catálogo",      icon: BookOpen },
  { key: "deliveries",    label: "Entregas",      icon: Send },
  { key: "dlq",           label: "DLQ",           icon: AlertOctagon },
  { key: "health",        label: "Health",        icon: Activity },
];

export default function AdminWebhooks() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("dashboard");

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="webhooks-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white">
              <Webhook className="h-4 w-4" />
            </div>
            <div className="leading-tight">
              <div className="font-semibold text-sm tracking-tight">Webhooks salientes</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">
                R43-R49 · HMAC SHA-256 · Anti-SSRF · Append-only
              </div>
            </div>
          </div>
          <div className="ml-auto" />
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-10 space-y-6 animate-fade-in">
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 39 V3 · Outbound Webhooks
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Eventos salientes</h1>
          <p className="text-mye-ink-muted max-w-3xl">
            Tu plataforma como <strong>publisher</strong>. Suscripciones por cliente cartera,
            firma HMAC SHA-256, reintentos exponenciales y DLQ tras 7 fallas.
          </p>
        </section>

        <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="webhooks-tabs">
          {TABS.map((t) => {
            const Active = tab === t.key;
            const Icon = t.icon;
            return (
              <button key={t.key}
                      onClick={() => setTab(t.key)}
                      data-testid={`webhooks-tab-${t.key}`}
                      className={
                        "inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-md -mb-px transition-colors " +
                        (Active
                          ? "bg-white border border-mye-border border-b-white text-mye-ink"
                          : "text-mye-ink-muted hover:text-mye-ink")
                      }>
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
          {tab === "dashboard" && <DashboardTab />}
          {tab === "subscriptions" && <SubscriptionsTab />}
          {tab === "catalog" && <CatalogTab />}
          {tab === "deliveries" && <DeliveriesTab />}
          {tab === "dlq" && <DlqTab />}
          {tab === "health" && <HealthTab />}
        </div>
      </main>
    </div>
  );
}


// ═════════════ Tab 0 — Dashboard agregado tenant ═════════════════════════
function DashboardTab() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hours, setHours] = useState(24);

  async function refresh() {
    setBusy(true);
    try {
      const r = await api.get(`/admin/webhooks/dashboard?hours=${hours}`);
      setData(r.data?.data || null);
    } finally { setBusy(false); }
  }
  useEffect(() => { refresh();   }, [hours]);

  return (
    <div className="p-5 space-y-6" data-testid="webhooks-dashboard-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <BarChart3 className="h-5 w-5 text-mye-accent" />
          <div>
            <div className="font-medium">Vista agregada</div>
            <div className="text-xs text-mye-ink-muted font-mono">
              Métricas tenant-wide de las últimas {hours}h
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))}
                  className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs"
                  data-testid="dashboard-window">
            <option value={1}>1h</option>
            <option value={6}>6h</option>
            <option value={24}>24h</option>
            <option value={72}>3 días</option>
            <option value={168}>7 días</option>
          </select>
          <button onClick={refresh} disabled={busy}
                  className="rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition inline-flex items-center gap-1"
                  data-testid="dashboard-refresh">
            <RefreshCw className="h-3.5 w-3.5" /> {busy ? "…" : "Refrescar"}
          </button>
        </div>
      </div>

      {!data && busy && <div className="text-sm text-mye-ink-muted">Cargando…</div>}
      {data && (
        <>
          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <KpiCard label="Intentos" value={(data.totals?.total_attempts || 0).toLocaleString()} />
            <KpiCard label="Success rate" value={`${((data.totals?.success_rate || 0) * 100).toFixed(1)}%`}
                     tone={data.totals?.success_rate < 0.95 ? "warn" : "good"} />
            <KpiCard label="Latencia avg" value={`${Math.round(data.totals?.avg_latency_ms || 0)}ms`} />
            <KpiCard label="DLQ" value={data.dlq_unresolved || 0}
                     tone={data.dlq_unresolved > 0 ? "warn" : "good"} />
            <KpiCard label="Suscripciones" value={`${data.subscriptions?.active || 0} / ${data.subscriptions?.total || 0}`} />
          </div>

          {/* Status alerts */}
          {(data.subscriptions?.circuit_open > 0 || data.subscriptions?.paused > 0) && (
            <div className="grid sm:grid-cols-2 gap-3">
              {data.subscriptions.circuit_open > 0 && (
                <div className="rounded-md border border-status-escalated/40 bg-status-escalated/5 p-3 text-sm" data-testid="dashboard-alert-cb">
                  <div className="flex items-center gap-2 font-medium text-status-escalated">
                    <AlertTriangle className="h-4 w-4" />
                    {data.subscriptions.circuit_open} circuito(s) abierto(s)
                  </div>
                  <div className="text-xs text-mye-ink-muted mt-1">
                    Pausas automáticas por &gt;30% fallas en 1h. Revisa la tab Suscripciones.
                  </div>
                </div>
              )}
              {data.subscriptions.paused > 0 && (
                <div className="rounded-md border border-status-waiting/40 bg-status-waiting/5 p-3 text-sm" data-testid="dashboard-alert-paused">
                  <div className="flex items-center gap-2 font-medium text-status-waiting">
                    ⏸ {data.subscriptions.paused} suscripción(es) pausada(s)
                  </div>
                  <div className="text-xs text-mye-ink-muted mt-1">
                    Eventos retenidos en queue. Reanuda desde la tab Suscripciones.
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Top frágiles */}
          <div>
            <div className="font-medium mb-2 inline-flex items-center gap-2">
              <TrendingDown className="h-4 w-4 text-status-escalated" />
              Top 5 endpoints frágiles ({hours}h)
            </div>
            <div className="rounded-md border border-mye-border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-mye-app/60">
                  <tr>
                    {["URL", "Intentos", "Success", "Avg latencia", "Estado"].map((h) => (
                      <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data.top_fragile_endpoints || []).length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-sm text-mye-ink-muted font-mono">
                      🎉 Ningún endpoint frágil en la ventana
                    </td></tr>
                  )}
                  {(data.top_fragile_endpoints || []).map((e) => (
                    <tr key={e.subscription_id} className="border-t border-mye-border" data-testid="dashboard-fragile-row">
                      <td className="px-4 py-2 font-mono text-[11px] max-w-[280px] truncate" title={e.endpoint_url}>{e.endpoint_url}</td>
                      <td className="px-4 py-2 font-mono tabular-nums text-[11px]">{e.total_attempts}</td>
                      <td className="px-4 py-2 font-mono tabular-nums text-[11px]">
                        <span className={(e.success_rate < 0.7 ? "text-status-escalated" : (e.success_rate < 0.95 ? "text-status-waiting" : "text-mye-ink"))}>
                          {(e.success_rate * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="px-4 py-2 font-mono tabular-nums text-[11px]">{Math.round(e.avg_latency_ms)}ms</td>
                      <td className="px-4 py-2">
                        {e.is_circuit_open && <span className="text-[10px] font-mono text-status-escalated">⚡ circuito</span>}
                        {e.is_paused && <span className="text-[10px] font-mono text-status-waiting">⏸ pausa</span>}
                        {!e.is_circuit_open && !e.is_paused && <span className="text-[10px] font-mono text-mye-ink-muted">activa</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Por evento */}
          <div>
            <div className="font-medium mb-2">Por evento</div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {Object.entries(data.by_event_code || {}).map(([code, m]) => (
                <div key={code} className="rounded-md border border-mye-border bg-mye-app/40 p-3" data-testid="dashboard-event-card">
                  <div className="font-mono text-[11px] mb-1">{code}</div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-mye-ink-muted">{m.total} intentos</span>
                    <span className="text-xs font-mono tabular-nums">{(m.success_rate * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
              {Object.keys(data.by_event_code || {}).length === 0 && (
                <div className="text-sm text-mye-ink-muted col-span-full">Sin actividad en la ventana.</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function KpiCard({ label, value, tone }) {
  const toneCls = tone === "warn" ? "border-status-waiting/40 bg-status-waiting/5"
                : tone === "good" ? "border-status-resolved/40 bg-status-resolved/5"
                : "border-mye-border bg-mye-app/40";
  return (
    <div className={"rounded-md border p-3 " + toneCls} data-testid="dashboard-kpi">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">{label}</div>
      <div className="text-2xl tabular-nums font-mono mt-0.5">{value}</div>
    </div>
  );
}


// ═════════════ Tab 1 — Suscripciones ════════════════════════════════════
function SubscriptionsTab() {
  const [items, setItems] = useState([]);
  const [clients, setClients] = useState([]);
  const [events, setEvents] = useState([]);
  const [open, setOpen] = useState(false);
  const [createdSecret, setCreatedSecret] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [search, setSearch] = useState("");
  const [showSecret, setShowSecret] = useState(false);

  const empty = {
    client_id: "", endpoint_url: "", event_codes: [],
    include_pii: false, pii_consent_signature: "",
    allow_extra_ports: false, filter_jsonpath: {},
  };
  const [form, setForm] = useState(empty);

  async function refresh() {
    const [a, b, c] = await Promise.all([
      api.get("/admin/webhooks/subscriptions"),
      api.get("/admin/clients"),
      api.get("/admin/webhooks/events"),
    ]);
    setItems(a.data?.data?.items || []);
    setClients(b.data?.data?.items || []);
    setEvents(c.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((s) =>
      (s.endpoint_url + " " + (s.client_id || "")).toLowerCase().includes(q));
  }, [items, search]);

  function toggleCode(code) {
    setForm((s) => ({
      ...s,
      event_codes: s.event_codes.includes(code)
        ? s.event_codes.filter((x) => x !== code)
        : [...s.event_codes, code],
    }));
  }

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const payload = {
        ...form,
        filter_jsonpath: Object.keys(form.filter_jsonpath || {}).length
          ? form.filter_jsonpath : null,
      };
      if (!payload.include_pii) delete payload.pii_consent_signature;
      const r = await api.post("/admin/webhooks/subscriptions", payload);
      const sub = r.data?.data?.subscription;
      setCreatedSecret({ id: sub.id, secret: sub.hmac_secret, url: sub.endpoint_url });
      setForm(empty);
      setOpen(false);
      await refresh();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  async function rotateSecret(id) {
    if (!window.confirm("¿Rotar el secreto? El antiguo queda activo 7 días con header X-MyE-Signature-V2.")) return;
    try {
      const r = await api.post(`/admin/webhooks/subscriptions/${id}/rotate-secret`);
      setCreatedSecret({
        id, secret: r.data?.data?.new_hmac_secret,
        old_active_until: r.data?.data?.old_secret_active_until,
        rotated: true,
      });
      await refresh();
    } catch (e) {
      alert(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  async function toggleActive(sub) {
    try {
      await api.patch(`/admin/webhooks/subscriptions/${sub.id}`,
                      { is_active: !sub.is_active });
      await refresh();
    } catch (e) {
      alert(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  async function revokePii(sub) {
    if (!window.confirm("¿Revocar consentimiento PII? Las próximas emisiones se enmascararán.")) return;
    await api.post(`/admin/webhooks/subscriptions/${sub.id}/revoke-pii`);
    await refresh();
  }

  async function resetCircuit(id) {
    if (!window.confirm("¿Cerrar el circuito manualmente? El próximo intento se ejecutará al instante.")) return;
    try {
      await api.post(`/admin/webhooks/subscriptions/${id}/reset-circuit`);
      await refresh();
    } catch (e) {
      alert(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  async function togglePause(sub) {
    const action = sub.is_paused ? "resume" : "pause";
    if (!window.confirm(sub.is_paused
      ? "¿Reanudar la suscripción? Los eventos retenidos comenzarán a entregarse."
      : "¿Pausar la suscripción? Los eventos se acumularán en queue sin entregarse (no se pierden)."))
      return;
    try {
      await api.post(`/admin/webhooks/subscriptions/${sub.id}/${action}`);
      await refresh();
    } catch (e) {
      alert(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  async function downloadReadme(id) {
    try {
      const token = localStorage.getItem("mye_access_token");
      const res = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/admin/webhooks/subscriptions/${id}/readme`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) { alert(`HTTP ${res.status}`); return; }
      const blob = await res.blob();
      const link = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = link; a.download = `webhook-${id.slice(0, 8)}.md`; a.click();
      URL.revokeObjectURL(link);
    } catch (e) { alert(e.message); }
  }

  return (
    <div data-testid="webhooks-subs-tab">
      <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-mye-border flex-wrap">
        <div>
          <div className="font-medium">Suscripciones</div>
          <div className="text-xs text-mye-ink-muted font-mono">
            {filtered.length}{search ? ` / ${items.length}` : ""} registros
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mye-ink-muted" />
            <input value={search} onChange={(e) => setSearch(e.target.value)}
                   placeholder="Buscar URL / client_id…"
                   className="rounded-md border border-mye-border bg-white pl-7 pr-2 py-1.5 text-xs w-56 outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                   data-testid="webhooks-subs-search" />
          </div>
          <button onClick={refresh} className={btnGhost + " text-xs inline-flex items-center gap-1"}
                  data-testid="webhooks-subs-refresh">
            <RefreshCw className="h-3.5 w-3.5" /> Refrescar
          </button>
          <button onClick={() => { setForm(empty); setOpen(true); setErr(null); }}
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition"
                  data-testid="webhooks-subs-create">
            <Plus className="h-3.5 w-3.5" /> Nueva suscripción
          </button>
        </div>
      </div>

      {createdSecret && (
        <SecretBanner data={createdSecret} onClose={() => setCreatedSecret(null)} />
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["URL", "Cliente", "Eventos", "PII", "Status", "Acciones"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">
                {items.length === 0 ? "Sin suscripciones todavía." : `Sin coincidencias para \u201C${search}\u201D.`}
              </td></tr>
            )}
            {filtered.map((s) => (
              <tr key={s.id} className="border-t border-mye-border" data-testid="webhooks-sub-row">
                <td className="px-4 py-2.5 font-mono text-[12px] max-w-[280px] truncate" title={s.endpoint_url}>
                  {s.endpoint_url}
                </td>
                <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">
                  {clients.find((c) => c.id === s.client_id)?.name || s.client_id?.slice(0, 8)}
                </td>
                <td className="px-4 py-2.5 text-[11px] font-mono">
                  {(s.event_codes || []).map((c) => (
                    <span key={c} className="inline-block mr-1 mb-0.5 px-1.5 py-0.5 rounded bg-mye-app text-[10px]">
                      {c}
                    </span>
                  ))}
                </td>
                <td className="px-4 py-2.5">
                  {s.include_pii
                    ? <span className="inline-flex items-center gap-1 text-status-escalated text-[11px] font-mono">
                        <ShieldCheck className="h-3 w-3" /> con consent
                      </span>
                    : <span className="text-mye-ink-muted text-[11px] font-mono">enmascarado</span>}
                </td>
                <td className="px-4 py-2.5">
                  <button onClick={() => toggleActive(s)}
                          className={"text-[11px] font-mono " +
                            (s.is_active ? "text-status-resolved" : "text-mye-ink-muted")}
                          data-testid={`webhook-toggle-${s.id}`}>
                    {s.is_active ? "● activa" : "○ inactiva"}
                  </button>
                  {s.is_circuit_open && (
                    <div className="text-[10px] text-status-escalated font-mono mt-0.5"
                         data-testid={`webhook-cb-open-${s.id}`}>
                      ⚡ circuito abierto
                    </div>
                  )}
                  {s.is_paused && (
                    <div className="text-[10px] text-status-waiting font-mono mt-0.5"
                         data-testid={`webhook-paused-${s.id}`}>
                      ⏸ pausada (eventos retenidos)
                    </div>
                  )}
                </td>
                <td className="px-4 py-2.5 space-x-2 whitespace-nowrap">
                  {s.is_circuit_open && (
                    <button onClick={() => resetCircuit(s.id)}
                            className="inline-flex items-center gap-1 text-xs text-status-escalated hover:underline"
                            data-testid={`webhook-cb-reset-${s.id}`}
                            title="Cerrar circuito manualmente">
                      <RefreshCcw className="h-3 w-3" /> Cerrar circuito
                    </button>
                  )}
                  <button onClick={() => togglePause(s)}
                          className={"inline-flex items-center gap-1 text-xs hover:underline " +
                            (s.is_paused ? "text-status-resolved" : "text-mye-ink-muted")}
                          data-testid={`webhook-pause-${s.id}`}>
                    {s.is_paused ? "Reanudar" : "Pausar"}
                  </button>
                  <button onClick={() => downloadReadme(s.id)}
                          className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline"
                          data-testid={`webhook-readme-${s.id}`}
                          title="Descargar README markdown con ejemplos de verificación HMAC">
                    README
                  </button>
                  <button onClick={() => rotateSecret(s.id)}
                          className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline"
                          data-testid={`webhook-rotate-${s.id}`}>
                    <KeySquare className="h-3 w-3" /> Rotar
                  </button>
                  {s.include_pii && (
                    <button onClick={() => revokePii(s)}
                            className="inline-flex items-center gap-1 text-xs text-status-escalated hover:underline">
                      Revocar PII
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" data-testid="webhooks-create-dialog">
          <div className="bg-white border border-mye-border rounded-lg shadow-xl w-full max-w-xl animate-fade-in max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border sticky top-0 bg-white">
              <div className="font-medium text-sm">Nueva suscripción</div>
              <button onClick={() => setOpen(false)}><X className="h-4 w-4 text-mye-ink-muted" /></button>
            </div>
            <form onSubmit={submit} className="p-5 space-y-4">
              <Field label="Cliente cartera" required>
                {clients.length === 0 ? (
                  <div className="rounded-md border border-status-waiting/40 bg-status-waiting/5 px-3 py-2 text-xs text-mye-ink">
                    No hay clientes cartera disponibles. Crea uno primero en{" "}
                    <a href="/admin/jerarquia" className="text-mye-accent underline">/admin/jerarquia</a>.
                  </div>
                ) : (
                  <select className={inputCls} value={form.client_id}
                          onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                          required data-testid="webhook-form-client">
                    <option value="">— elegir —</option>
                    {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                )}
              </Field>
              <Field label="Endpoint URL (https://)" required>
                <input className={inputCls} value={form.endpoint_url}
                       onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                       placeholder="https://api.cliente.com/webhooks/mye"
                       required data-testid="webhook-form-url" />
                <div className="text-[10px] text-mye-ink-muted mt-1 font-mono">
                  R45 · solo HTTPS · IPs privadas/loopback bloqueadas
                </div>
              </Field>
              <Field label="Eventos a recibir" required>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5" data-testid="webhook-form-events">
                  {events.map((ev) => (
                    <label key={ev.event_code}
                           className="inline-flex items-center gap-2 rounded border border-mye-border bg-mye-app/40 px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft cursor-pointer">
                      <input type="checkbox" className="h-3.5 w-3.5 accent-mye-accent"
                             checked={form.event_codes.includes(ev.event_code)}
                             onChange={() => toggleCode(ev.event_code)}
                             data-testid={`webhook-form-event-${ev.event_code}`} />
                      <span className="font-mono">{ev.event_code}</span>
                      {ev.contains_pii && <span className="ml-auto text-[9px] text-status-escalated font-mono">PII</span>}
                    </label>
                  ))}
                </div>
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.include_pii}
                       onChange={(e) => setForm({ ...form, include_pii: e.target.checked })}
                       className="h-4 w-4 accent-mye-accent"
                       data-testid="webhook-form-pii" />
                <span>Incluir PII (R49 — requiere consent firmado)</span>
              </label>
              {form.include_pii && (
                <Field label="Firma de consentimiento PII" required>
                  <textarea className={inputCls + " min-h-[60px] resize-y"}
                            value={form.pii_consent_signature}
                            onChange={(e) => setForm({ ...form, pii_consent_signature: e.target.value })}
                            placeholder="Pegado del email firmado por el responsable del cliente."
                            required={form.include_pii}
                            data-testid="webhook-form-consent" />
                </Field>
              )}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.allow_extra_ports}
                       onChange={(e) => setForm({ ...form, allow_extra_ports: e.target.checked })}
                       className="h-4 w-4 accent-mye-accent" />
                <span>Permitir puertos personalizados (&gt;1024)</span>
              </label>

              {err && <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated">{err}</div>}

              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setOpen(false)} className={btnGhost}>Cancelar</button>
                <button type="submit" disabled={busy || form.event_codes.length === 0 || clients.length === 0 || !form.client_id}
                        className="rounded-md bg-mye-accent text-white px-4 py-1.5 text-sm hover:brightness-110 transition disabled:opacity-60"
                        data-testid="webhook-form-submit">
                  {busy ? "Creando…" : "Crear suscripción"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function SecretBanner({ data, onClose }) {
  const [shown, setShown] = useState(false);
  return (
    <div className="px-5 py-4 bg-mye-accent/5 border-b-2 border-mye-accent/30" data-testid="webhook-secret-banner">
      <div className="flex items-start gap-3">
        <ShieldCheck className="h-5 w-5 text-mye-accent flex-none mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm mb-1">
            {data.rotated ? "Secreto rotado" : "Suscripción creada"} · guarda este secreto
          </div>
          <div className="text-xs text-mye-ink-muted mb-2">
            No se mostrará nuevamente. Úsalo para verificar X-MyE-Signature.
            {data.old_active_until && ` El secreto anterior queda válido hasta ${data.old_active_until.slice(0, 19).replace("T", " ")}.`}
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 bg-white border border-mye-border rounded px-3 py-2 text-[11px] font-mono break-all" data-testid="webhook-secret-value">
              {shown ? data.secret : "•".repeat(Math.min(48, data.secret.length))}
            </code>
            <button onClick={() => setShown(!shown)} className={btnGhost + " inline-flex items-center gap-1 text-xs"}>
              {shown ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              {shown ? "Ocultar" : "Ver"}
            </button>
            <button onClick={() => navigator.clipboard?.writeText(data.secret)}
                    className={btnGhost + " inline-flex items-center gap-1 text-xs"}>
              <Copy className="h-3 w-3" /> Copiar
            </button>
          </div>
        </div>
        <button onClick={onClose} className="text-mye-ink-muted hover:text-mye-ink"><X className="h-4 w-4" /></button>
      </div>
    </div>
  );
}


// ═════════════ Tab 2 — Catálogo ═══════════════════════════════════════════
function CatalogTab() {
  const [items, setItems] = useState([]);
  const [sample, setSample] = useState(null);
  useEffect(() => {
    api.get("/admin/webhooks/events").then((r) => setItems(r.data?.data?.items || []));
  }, []);

  async function loadSample(code) {
    const r = await api.get(`/admin/webhooks/events/${code}/sample`);
    setSample({ code, ...r.data?.data });
  }

  return (
    <div className="grid lg:grid-cols-[1fr_1fr] divide-y lg:divide-y-0 lg:divide-x divide-mye-border min-h-[400px]" data-testid="webhooks-catalog-tab">
      <div className="p-5 space-y-3">
        <div className="font-medium">Eventos disponibles · {items.length}</div>
        <div className="space-y-2">
          {items.map((ev) => (
            <button key={ev.event_code}
                    onClick={() => loadSample(ev.event_code)}
                    className={"w-full text-left rounded-md border p-3 text-sm transition " +
                      (sample?.code === ev.event_code
                        ? "border-mye-accent bg-mye-accent/5"
                        : "border-mye-border bg-white hover:bg-mye-primary-soft")}
                    data-testid={`webhooks-catalog-item-${ev.event_code}`}>
              <div className="font-mono text-[12px]">{ev.event_code}</div>
              <div className="text-xs text-mye-ink-muted">{ev.event_name}</div>
              {ev.contains_pii && <div className="mt-1 text-[10px] font-mono text-status-escalated">contiene PII</div>}
            </button>
          ))}
        </div>
      </div>
      <div className="p-5">
        <div className="font-medium mb-2">Payload de ejemplo</div>
        {!sample && <div className="text-xs text-mye-ink-muted font-mono">Selecciona un evento.</div>}
        {sample && (
          <pre className="bg-mye-app/40 border border-mye-border rounded-md p-3 text-[10px] overflow-auto max-h-[480px]" data-testid="webhooks-sample-json">
{JSON.stringify(sample.sample_payload, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}


// ═════════════ Tab 3 — Entregas ═══════════════════════════════════════════
function DeliveriesTab() {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({ status: "", subscription_id: "" });

  async function refresh() {
    setBusy(true);
    try {
      const p = new URLSearchParams({ limit: "200" });
      if (filters.status) p.append("status", filters.status);
      if (filters.subscription_id) p.append("subscription_id", filters.subscription_id);
      const r = await api.get(`/admin/webhooks/deliveries?${p.toString()}`);
      setItems(r.data?.data?.items || []);
    } finally { setBusy(false); }
  }
  useEffect(() => { refresh();   }, []);

  return (
    <div data-testid="webhooks-deliveries-tab">
      <div className="px-5 py-4 border-b border-mye-border flex flex-wrap items-end gap-3">
        <Field label="Status">
          <select className={inputCls} value={filters.status}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">Todos</option>
            <option value="delivered">delivered</option>
            <option value="failed_temporary">failed_temporary</option>
            <option value="failed_permanent">failed_permanent</option>
            <option value="timeout">timeout</option>
            <option value="blocked_ssrf">blocked_ssrf</option>
            <option value="circuit_open">circuit_open</option>
          </select>
        </Field>
        <Field label="Subscription ID">
          <input className={inputCls} value={filters.subscription_id}
                 onChange={(e) => setFilters({ ...filters, subscription_id: e.target.value })}
                 placeholder="UUID" />
        </Field>
        <button onClick={refresh} disabled={busy} className={btnGhost + " text-xs"}
                data-testid="webhooks-deliveries-refresh">
          {busy ? "Cargando…" : "Aplicar"}
        </button>
        <span className="ml-auto text-xs text-mye-ink-muted font-mono">{items.length} registros · cap 200</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Fecha", "Evento", "Sub", "Status", "HTTP", "Latencia", "IP", "Intento"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !busy && (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">Sin entregas.</td></tr>
            )}
            {items.map((it) => (
              <tr key={it.id} className="border-t border-mye-border" data-testid="webhook-delivery-row">
                <td
                  className="px-4 py-2 font-mono text-[10px] text-mye-ink-muted"
                  title={it.created_at ? new Date(it.created_at).toLocaleString("es-MX", { timeZone: "America/Mexico_City" }) : ""}
                  data-testid="webhook-delivery-fecha"
                >
                  {fechaRelativa(it.created_at)}
                </td>
                <td className="px-4 py-2 font-mono text-[11px]">{it.event_code}</td>
                <td className="px-4 py-2 font-mono text-[10px] text-mye-ink-muted">{it.subscription_id?.slice(0, 8)}…</td>
                <td className="px-4 py-2"><DeliveryPill v={it.status} /></td>
                <td className="px-4 py-2 font-mono text-[11px] tabular-nums">{it.http_status_code ?? "—"}</td>
                <td className="px-4 py-2 font-mono text-[11px] tabular-nums">{it.latency_ms ?? "—"}ms</td>
                <td className="px-4 py-2 font-mono text-[10px] text-mye-ink-muted">{it.resolved_ip || "—"}</td>
                <td className="px-4 py-2 font-mono text-[11px] tabular-nums">{it.attempt_number ?? 1}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ═════════════ Tab 4 — DLQ ════════════════════════════════════════════════
function DlqTab() {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const r = await api.get("/admin/webhooks/dlq");
      setItems(r.data?.data?.items || []);
    } finally { setBusy(false); }
  }
  useEffect(() => { refresh(); }, []);

  async function replay(id) {
    if (!window.confirm("¿Reencolar este evento? Resetea el contador de intentos.")) return;
    await api.post(`/admin/webhooks/dlq/${id}/replay`);
    await refresh();
  }
  async function archive(id) {
    if (!window.confirm("¿Archivar este evento? Quedará marcado como resuelto sin reintentar.")) return;
    await api.delete(`/admin/webhooks/dlq/${id}`);
    await refresh();
  }

  return (
    <div data-testid="webhooks-dlq-tab">
      <div className="px-5 py-4 border-b border-mye-border flex items-center gap-2">
        <div className="font-medium">Dead Letter Queue · {items.length}</div>
        <button onClick={refresh} disabled={busy} className={"ml-auto " + btnGhost + " text-xs inline-flex items-center gap-1"}
                data-testid="webhooks-dlq-refresh">
          <RefreshCw className="h-3.5 w-3.5" /> {busy ? "…" : "Refrescar"}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Fecha DLQ", "Evento", "Intentos", "Last status", "Last error", "Acciones"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !busy && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">DLQ vacío 🎉</td></tr>
            )}
            {items.map((d) => (
              <tr key={d.id} className="border-t border-mye-border" data-testid="webhook-dlq-row">
                <td className="px-4 py-2 font-mono text-[10px] text-mye-ink-muted">{d.moved_to_dlq_at?.slice(0, 19).replace("T", " ")}</td>
                <td className="px-4 py-2 font-mono text-[11px]">{d.event_code}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{d.attempts_made}</td>
                <td className="px-4 py-2"><DeliveryPill v={d.last_status} /></td>
                <td className="px-4 py-2 font-mono text-[11px] text-mye-ink-muted max-w-[240px] truncate">{d.last_error || "—"}</td>
                <td className="px-4 py-2 space-x-2 whitespace-nowrap">
                  <button onClick={() => replay(d.id)} className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline"
                          data-testid={`webhook-dlq-replay-${d.id}`}>
                    <RefreshCcw className="h-3 w-3" /> Reencolar
                  </button>
                  <button onClick={() => archive(d.id)} className="inline-flex items-center gap-1 text-xs text-mye-ink-muted hover:text-mye-ink">
                    <Trash2 className="h-3 w-3" /> Archivar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


// ═════════════ Tab 5 — Health ═════════════════════════════════════════════
function HealthTab() {
  const [subs, setSubs] = useState([]);
  const [healthBySub, setHealthBySub] = useState({});

  async function refresh() {
    const r = await api.get("/admin/webhooks/subscriptions");
    const items = r.data?.data?.items || [];
    setSubs(items);
    const next = {};
    await Promise.all(items.map(async (s) => {
      try {
        const h = await api.get(`/admin/webhooks/subscriptions/${s.id}/health`);
        next[s.id] = h.data?.data;
      } catch (_e) { next[s.id] = null; }
    }));
    setHealthBySub(next);
  }
  useEffect(() => { refresh(); }, []);

  return (
    <div className="p-5 space-y-3" data-testid="webhooks-health-tab">
      <div className="text-xs text-mye-ink-muted font-mono">Métricas de las últimas 24h por suscripción.</div>
      {subs.length === 0 && <div className="text-sm text-mye-ink-muted">Sin suscripciones.</div>}
      <div className="grid md:grid-cols-2 gap-3">
        {subs.map((s) => {
          const h = healthBySub[s.id];
          return (
            <div key={s.id} className="rounded-md border border-mye-border bg-white p-4" data-testid="webhook-health-card">
              <div className="font-mono text-[12px] truncate" title={s.endpoint_url}>{s.endpoint_url}</div>
              <div className="text-[11px] text-mye-ink-muted font-mono">id {s.id.slice(0, 8)}…</div>
              {h && (
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <div className="rounded bg-mye-app/40 p-2">
                    <div className="text-[9px] uppercase font-mono text-mye-ink-muted">Success rate</div>
                    <div className="text-lg tabular-nums font-mono">{(h.success_rate * 100).toFixed(1)}%</div>
                  </div>
                  <div className="rounded bg-mye-app/40 p-2">
                    <div className="text-[9px] uppercase font-mono text-mye-ink-muted">Latencia</div>
                    <div className="text-lg tabular-nums font-mono">{Math.round(h.avg_latency_ms || 0)}ms</div>
                  </div>
                  <div className="rounded bg-mye-app/40 p-2">
                    <div className="text-[9px] uppercase font-mono text-mye-ink-muted">DLQ</div>
                    <div className="text-lg tabular-nums font-mono">{h.dlq_unresolved}</div>
                  </div>
                </div>
              )}
              {h?.is_circuit_open && (
                <div className="mt-2 rounded border border-status-escalated/40 bg-status-escalated/5 p-2 text-[11px] font-mono text-status-escalated"
                     data-testid="webhook-health-cb-open">
                  <AlertTriangle className="h-3 w-3 inline mr-1" />
                  circuito abierto
                  {h.circuit_open_until && <> · hasta {h.circuit_open_until.slice(11, 19)} UTC</>}
                </div>
              )}
              {h?.circuit_metrics_1h && (
                <div className="mt-2 text-[10px] font-mono text-mye-ink-muted">
                  Última hora: {h.circuit_metrics_1h.failures}/{h.circuit_metrics_1h.total_attempts} fallas
                  {h.circuit_metrics_1h.total_attempts > 0 && ` (${h.circuit_metrics_1h.rate_pct}%)`}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ═════════════ Atoms ══════════════════════════════════════════════════════
const inputCls =
  "w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors";
const btnGhost =
  "rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft transition";

function Field({ label, required, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">
        {label} {required && <span className="text-status-escalated">*</span>}
      </span>
      {children}
    </label>
  );
}

function DeliveryPill({ v }) {
  const map = {
    delivered: "border-status-resolved/40 bg-status-resolved/10 text-status-resolved",
    failed_temporary: "border-status-waiting/40 bg-status-waiting/10 text-status-waiting",
    failed_permanent: "border-status-escalated/40 bg-status-escalated/10 text-status-escalated",
    timeout: "border-status-waiting/40 bg-status-waiting/10 text-status-waiting",
    blocked_ssrf: "border-status-escalated/40 bg-status-escalated/10 text-status-escalated",
    circuit_open: "border-mye-border text-mye-ink-muted",
  };
  return (
    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono " +
      (map[v] || "border-mye-border text-mye-ink-muted")}>
      {v || "—"}
    </span>
  );
}
