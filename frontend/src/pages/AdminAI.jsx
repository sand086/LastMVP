/**
 * AdminAI — Configuración IA (PROMPT 26 V2).
 * 4 tabs: Catálogo de features · Brackets · Configuración por cliente · Consumo.
 *
 * RBAC:
 *  - features/brackets CRUD: root_dev | superadmin
 *  - client-config:          admin+
 *  - consumption dashboard:  admin+
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";
import { formatCurrencyMX, fechaCompacta, fechaRelativa } from "@/lib/formatFechaMX";
import {
  ArrowLeft, LogOut, Sparkles, Layers, Building2, BarChart3,
  Plus, X, RefreshCw, AlertTriangle, CheckCircle2, Lock, Eye,
  Gauge, FileSignature, Download, Play, TrendingUp,
} from "lucide-react";

const TABS = [
  { key: "features",   label: "Catálogo de features",       icon: Sparkles },
  { key: "brackets",   label: "Brackets de tarificación",   icon: Layers },
  { key: "clients",    label: "Configuración por cliente",  icon: Building2 },
  { key: "consumption",label: "Dashboard de consumo",       icon: BarChart3 },
  { key: "cost_trend", label: "Tendencia cost/feature 30d", icon: TrendingUp },
  { key: "benchmark",  label: "Benchmark de modelos",       icon: Gauge },
  { key: "audit",      label: "Auditoría externa",          icon: FileSignature },
];

const SUPER = ["root_dev", "superadmin"];

export default function AdminAI() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("features");
  const isSuper = useMemo(() => SUPER.includes(user?.role), [user]);

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-ai-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Configuración IA · PROMPT 26 V2</div>
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
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 26 V2 · Configuración IA
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Infraestructura de IA — gateway, guardas y topes</h1>
          <p className="text-mye-ink-muted max-w-3xl">
            R36 (PII masking) · R37 (log append-only) · R38 (gateway único) · R39 (opt-in) ·
            R40 (tope sin override) · R41 (no atributos discriminatorios) · R42 (validación humana).
            La activación por cliente es <span className="text-mye-accent font-medium">opt-in explícito con firma</span>.
          </p>
        </section>

        <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="ai-tabs">
          {TABS.map((t) => {
            const Icon = t.icon;
            const Active = tab === t.key;
            return (
              <button key={t.key} onClick={() => setTab(t.key)}
                      className={"inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-md transition-colors -mb-px " +
                        (Active ? "bg-white border border-mye-border border-b-white text-mye-ink"
                                : "text-mye-ink-muted hover:text-mye-ink")}
                      data-testid={`ai-tab-${t.key}`}>
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
          {tab === "features"    && <FeaturesPanel canEdit={isSuper} />}
          {tab === "brackets"    && <BracketsPanel canEdit={isSuper} />}
          {tab === "clients"     && <ClientsPanel />}
          {tab === "consumption" && <ConsumptionPanel />}
          {tab === "cost_trend"  && <CostTrendPanel />}
          {tab === "benchmark"   && <BenchmarkPanel canRunLive={isSuper} />}
          {tab === "audit"       && <AuditPanel canExport={isSuper} />}
        </div>
      </main>
    </div>
  );
}

// ─── Tab 1: Features (catálogo) ──────────────────────────────────────────
function FeaturesPanel({ canEdit }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState({
    feature_code: "", feature_name: "",
    recommended_model: "claude-sonnet-4-5-20250929",
    recommended_provider: "anthropic",
    avg_input_tokens: 500, avg_output_tokens: 200, avg_cost_usd: 0.005,
    destinatario: "agent_internal", cache_enabled: false, active: true,
  });

  async function refresh() {
    const r = await api.get("/admin/ai/features");
    setItems(r.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await api.post("/admin/ai/features", form);
      setOpen(false);
      await refresh();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="ai-features-panel">
      <PanelHeader title="Features de IA"
                   subtitle={`${items.length} en catálogo · destinatario decide R42`}
                   onRefresh={refresh}
                   onCreate={canEdit ? () => { setOpen(true); setErr(null); } : null}
                   testid="ai-features" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Code", "Nombre", "Provider · Modelo", "Destinatario", "Avg cost", "Cache", "Activa"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">Sin features en catálogo.</td></tr>
            )}
            {items.map((f) => (
              <tr key={f.id} className="border-t border-mye-border" data-testid={`ai-feature-${f.feature_code}`}>
                <td className="px-4 py-2.5 font-mono text-[12px]">{f.feature_code}</td>
                <td className="px-4 py-2.5">{f.feature_name}</td>
                <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{f.recommended_provider} · {f.recommended_model}</td>
                <td className="px-4 py-2.5">
                  <DestinatarioBadge v={f.destinatario} />
                </td>
                <td className="px-4 py-2.5 font-mono text-[12px]">{formatCurrencyMX(f.avg_cost_usd, "USD")}</td>
                <td className="px-4 py-2.5 text-[11px] font-mono">
                  {f.cache_enabled ? <span className="text-mye-accent">on</span> : <span className="text-mye-ink-muted">off</span>}
                </td>
                <td className="px-4 py-2.5">{f.active ? <CheckCircle2 className="h-3.5 w-3.5 text-status-resolved" /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <Dialog title="Nueva feature de IA" onClose={() => setOpen(false)} testid="ai-features-dialog">
          <form onSubmit={submit} className="space-y-3">
            <Field label="Code (snake_case)" required>
              <input value={form.feature_code}
                     onChange={(e) => setForm({ ...form, feature_code: e.target.value.toLowerCase() })}
                     placeholder="suggest_solution" required
                     className={inputCls} data-testid="ai-feature-code" />
            </Field>
            <Field label="Nombre" required>
              <input value={form.feature_name}
                     onChange={(e) => setForm({ ...form, feature_name: e.target.value })}
                     required className={inputCls} data-testid="ai-feature-name" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Provider">
                <select value={form.recommended_provider}
                        onChange={(e) => setForm({ ...form, recommended_provider: e.target.value })}
                        className={inputCls}>
                  <option value="anthropic">Anthropic</option>
                  <option value="openai">OpenAI</option>
                  <option value="gemini">Gemini</option>
                </select>
              </Field>
              <Field label="Modelo">
                <input value={form.recommended_model}
                       onChange={(e) => setForm({ ...form, recommended_model: e.target.value })}
                       required className={inputCls} />
              </Field>
            </div>
            <Field label="Destinatario">
              <select value={form.destinatario}
                      onChange={(e) => setForm({ ...form, destinatario: e.target.value })}
                      className={inputCls} data-testid="ai-feature-destinatario">
                <option value="agent_internal">agent_internal — interno (puede desenmascarar)</option>
                <option value="client_final">client_final — al cliente (R42 draft)</option>
                <option value="both">both</option>
              </select>
            </Field>
            <label className="flex items-start gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.cache_enabled}
                     onChange={(e) => setForm({ ...form, cache_enabled: e.target.checked })}
                     className="mt-0.5 h-4 w-4 accent-mye-accent"
                     data-testid="ai-feature-cache-enabled" />
              <span>
                <span className="font-medium">Activar cache de prompts (P1)</span>
                <br />
                <span className="text-[11px] text-mye-ink-muted">
                  Recomendado sólo para features deterministas (ej. clasificadores). TTL: 5 min.
                </span>
              </span>
            </label>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Avg input tokens">
                <input type="number" value={form.avg_input_tokens}
                       onChange={(e) => setForm({ ...form, avg_input_tokens: +e.target.value })}
                       className={inputCls} />
              </Field>
              <Field label="Avg output tokens">
                <input type="number" value={form.avg_output_tokens}
                       onChange={(e) => setForm({ ...form, avg_output_tokens: +e.target.value })}
                       className={inputCls} />
              </Field>
              <Field label="Avg cost USD">
                <input type="number" step="0.0001" value={form.avg_cost_usd}
                       onChange={(e) => setForm({ ...form, avg_cost_usd: +e.target.value })}
                       className={inputCls} />
              </Field>
            </div>
            {err && <ErrorRow msg={err} />}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setOpen(false)} className={btnGhost}>Cancelar</button>
              <button type="submit" disabled={busy} className={btnPrimary} data-testid="ai-features-submit">
                {busy ? "Guardando…" : "Guardar"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}

// ─── Tab 2: Brackets ─────────────────────────────────────────────────────
function BracketsPanel({ canEdit }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState({
    bracket_name: "", included_invocations_per_month: 100,
    included_tokens_per_month: 100000, overage_per_1k_tokens_usd: 0.02,
    hard_cap_usd_per_month: 50, alert_threshold_pct: 80, monthly_fee_usd: 99,
    active: true,
  });

  async function refresh() {
    const r = await api.get("/admin/ai/brackets");
    setItems(r.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await api.post("/admin/ai/brackets", form);
      setOpen(false);
      await refresh();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="ai-brackets-panel">
      <PanelHeader title="Brackets de tarificación"
                   subtitle={`${items.length} brackets · R40 sin override en runtime`}
                   onRefresh={refresh}
                   onCreate={canEdit ? () => { setOpen(true); setErr(null); } : null}
                   testid="ai-brackets" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Nombre", "Cuota mensual", "Invocations/mes", "Tokens/mes", "Overage", "Hard cap USD", "Alerta %", "Activo"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((b) => (
              <tr key={b.id} className="border-t border-mye-border" data-testid={`ai-bracket-${b.bracket_name}`}>
                <td className="px-4 py-2.5 font-mono text-[12px]">{b.bracket_name}</td>
                <td className="px-4 py-2.5 font-mono">${b.monthly_fee_usd}</td>
                <td className="px-4 py-2.5 tabular-nums">{b.included_invocations_per_month}</td>
                <td className="px-4 py-2.5 tabular-nums">{b.included_tokens_per_month.toLocaleString()}</td>
                <td className="px-4 py-2.5 font-mono text-[12px]">${b.overage_per_1k_tokens_usd}/1k</td>
                <td className="px-4 py-2.5 font-mono text-mye-accent">${b.hard_cap_usd_per_month}</td>
                <td className="px-4 py-2.5">{b.alert_threshold_pct}%</td>
                <td className="px-4 py-2.5">{b.active ? <CheckCircle2 className="h-3.5 w-3.5 text-status-resolved" /> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <Dialog title="Nuevo bracket" onClose={() => setOpen(false)} testid="ai-brackets-dialog">
          <form onSubmit={submit} className="space-y-3">
            <Field label="Nombre (snake_case)" required>
              <input value={form.bracket_name}
                     onChange={(e) => setForm({ ...form, bracket_name: e.target.value.toLowerCase() })}
                     required className={inputCls} data-testid="ai-bracket-name" />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Cuota mensual USD">
                <input type="number" step="0.01" value={form.monthly_fee_usd}
                       onChange={(e) => setForm({ ...form, monthly_fee_usd: +e.target.value })}
                       className={inputCls} />
              </Field>
              <Field label="Hard cap USD/mes (R40)">
                <input type="number" step="0.01" value={form.hard_cap_usd_per_month}
                       onChange={(e) => setForm({ ...form, hard_cap_usd_per_month: +e.target.value })}
                       className={inputCls} data-testid="ai-bracket-cap" />
              </Field>
              <Field label="Invocaciones incluidas">
                <input type="number" value={form.included_invocations_per_month}
                       onChange={(e) => setForm({ ...form, included_invocations_per_month: +e.target.value })}
                       className={inputCls} />
              </Field>
              <Field label="Tokens incluidos">
                <input type="number" value={form.included_tokens_per_month}
                       onChange={(e) => setForm({ ...form, included_tokens_per_month: +e.target.value })}
                       className={inputCls} />
              </Field>
              <Field label="Overage USD/1k tokens">
                <input type="number" step="0.0001" value={form.overage_per_1k_tokens_usd}
                       onChange={(e) => setForm({ ...form, overage_per_1k_tokens_usd: +e.target.value })}
                       className={inputCls} />
              </Field>
              <Field label="Umbral de alerta %">
                <input type="number" value={form.alert_threshold_pct}
                       onChange={(e) => setForm({ ...form, alert_threshold_pct: +e.target.value })}
                       className={inputCls} />
              </Field>
            </div>
            {err && <ErrorRow msg={err} />}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setOpen(false)} className={btnGhost}>Cancelar</button>
              <button type="submit" disabled={busy} className={btnPrimary} data-testid="ai-brackets-submit">
                {busy ? "Guardando…" : "Guardar"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}

// ─── Tab 3: Clients (opt-in / opt-out) ───────────────────────────────────
function ClientsPanel() {
  const [clients, setClients] = useState([]);
  const [features, setFeatures] = useState([]);
  const [brackets, setBrackets] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [editClient, setEditClient] = useState(null);
  const [optOutClient, setOptOutClient] = useState(null);

  async function refresh() {
    const [c, f, b, cfg] = await Promise.all([
      api.get("/admin/clients"),
      api.get("/admin/ai/features"),
      api.get("/admin/ai/brackets"),
      api.get("/admin/ai/client-config"),
    ]);
    setClients(c.data?.data?.items || []);
    setFeatures(f.data?.data?.items || []);
    setBrackets(b.data?.data?.items || []);
    setConfigs(cfg.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  function configOf(clientId) {
    return configs.find((c) => c.client_id === clientId) || null;
  }

  return (
    <div data-testid="ai-clients-panel">
      <PanelHeader title="Configuración por cliente"
                   subtitle="R39 — opt-in explícito con firma + bracket + features habilitadas"
                   onRefresh={refresh}
                   testid="ai-clients" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Cliente", "Estado", "Bracket", "Features", "Override", "Custom key", "Acciones"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {clients.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">No hay clientes registrados.</td></tr>
            )}
            {clients.map((cl) => {
              const cfg = configOf(cl.id);
              const bracket = cfg ? brackets.find((b) => b.id === cfg.bracket_id) : null;
              return (
                <tr key={cl.id} className="border-t border-mye-border" data-testid={`ai-client-row-${cl.id}`}>
                  <td className="px-4 py-2.5">{cl.name}</td>
                  <td className="px-4 py-2.5">
                    {!cfg ? (
                      <span className="font-mono text-[11px] text-mye-ink-muted">sin configurar</span>
                    ) : cfg.is_active ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-mono text-status-resolved">
                        <CheckCircle2 className="h-3 w-3" /> activa
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-mono text-mye-ink-muted">
                        <Lock className="h-3 w-3" /> opt-out
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[12px]">{bracket?.bracket_name || "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">
                    {cfg?.enabled_features?.length ? cfg.enabled_features.join(", ") : "—"}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[12px]">
                    {cfg?.monthly_cap_override_usd != null ? `$${cfg.monthly_cap_override_usd}` : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    {cfg?.custom_provider ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-mono text-mye-accent">
                        <Lock className="h-3 w-3" /> {cfg.custom_provider}
                      </span>
                    ) : <span className="text-[10px] font-mono text-mye-ink-muted">universal</span>}
                  </td>
                  <td className="px-4 py-2.5 space-x-2">
                    <button onClick={() => setEditClient(cl)} className="text-xs text-mye-accent hover:underline"
                            data-testid={`ai-client-config-${cl.id}`}>
                      Configurar
                    </button>
                    {cfg?.is_active && (
                      <button onClick={() => setOptOutClient(cl)} className="text-xs text-status-escalated hover:underline"
                              data-testid={`ai-client-optout-${cl.id}`}>
                        Opt-out
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editClient && (
        <ClientConfigDialog client={editClient} initial={configOf(editClient.id)}
                            features={features} brackets={brackets}
                            onClose={() => setEditClient(null)}
                            onSaved={async () => { setEditClient(null); await refresh(); }} />
      )}
      {optOutClient && (
        <OptOutDialog client={optOutClient}
                      onClose={() => setOptOutClient(null)}
                      onDone={async () => { setOptOutClient(null); await refresh(); }} />
      )}
    </div>
  );
}

function ClientConfigDialog({ client, initial, features, brackets, onClose, onSaved }) {
  const [form, setForm] = useState({
    client_id: client.id,
    bracket_id: initial?.bracket_id || (brackets[0]?.id || ""),
    enabled_features: initial?.enabled_features || [],
    monthly_cap_override_usd: initial?.monthly_cap_override_usd || "",
    rollover_enabled: initial?.rollover_enabled || false,
    is_active: initial?.is_active || false,
    opt_in_signature: initial?.opt_in_signature || "",
    custom_provider: initial?.custom_provider || "",
    custom_api_key: "",
    webhook_outbound_url: initial?.webhook_outbound_url || "",
    webhook_outbound_secret: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  function toggleFeature(code) {
    setForm((f) => ({
      ...f,
      enabled_features: f.enabled_features.includes(code)
        ? f.enabled_features.filter((c) => c !== code)
        : [...f.enabled_features, code],
    }));
  }

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const payload = {
        ...form,
        monthly_cap_override_usd: form.monthly_cap_override_usd === ""
          ? null : Number(form.monthly_cap_override_usd),
        custom_provider: form.custom_provider || null,
      };
      if (!payload.custom_api_key) delete payload.custom_api_key;
      if (!payload.webhook_outbound_secret) delete payload.webhook_outbound_secret;
      await api.put("/admin/ai/client-config", payload);
      onSaved();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <Dialog title={`Configuración IA · ${client.name}`} onClose={onClose} testid="ai-client-dialog">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Bracket" required>
          <select value={form.bracket_id} onChange={(e) => setForm({ ...form, bracket_id: e.target.value })}
                  className={inputCls} data-testid="ai-client-bracket-select">
            {brackets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.bracket_name} · ${b.monthly_fee_usd}/mes · cap ${b.hard_cap_usd_per_month}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Features habilitadas">
          <div className="space-y-1.5 border border-mye-border rounded-md p-3 bg-mye-app/40">
            {features.length === 0 && (
              <div className="text-xs text-mye-ink-muted">Sin features en catálogo.</div>
            )}
            {features.map((f) => (
              <label key={f.id} className="flex items-start gap-2 text-xs cursor-pointer">
                <input type="checkbox" checked={form.enabled_features.includes(f.feature_code)}
                       onChange={() => toggleFeature(f.feature_code)}
                       className="mt-0.5 h-3.5 w-3.5 accent-mye-accent"
                       data-testid={`ai-client-feature-${f.feature_code}`} />
                <div>
                  <div className="font-mono text-[12px]">{f.feature_code}</div>
                  <div className="text-[11px] text-mye-ink-muted">{f.feature_name} · {f.recommended_model}</div>
                </div>
              </label>
            ))}
          </div>
        </Field>

        <Field label="Override de tope mensual USD (opcional · ≤ bracket cap)">
          <input type="number" step="0.01" value={form.monthly_cap_override_usd}
                 onChange={(e) => setForm({ ...form, monthly_cap_override_usd: e.target.value })}
                 placeholder="ej. 25.00 — vacío = usa el cap del bracket"
                 className={inputCls} />
        </Field>

        <div className="rounded-md border border-mye-border bg-mye-app/40 p-3 space-y-2">
          <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
            Override de proveedor (opcional)
          </div>
          <div className="grid grid-cols-2 gap-2">
            <select value={form.custom_provider}
                    onChange={(e) => setForm({ ...form, custom_provider: e.target.value })}
                    className={inputCls} data-testid="ai-client-custom-provider">
              <option value="">Usar universal key</option>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
            </select>
            <input type="password" value={form.custom_api_key}
                   onChange={(e) => setForm({ ...form, custom_api_key: e.target.value })}
                   placeholder={initial?.custom_api_key_present ? "•••• cargada · reemplazar" : "API key"}
                   className={inputCls} data-testid="ai-client-custom-key" />
          </div>
        </div>

        <div className="rounded-md border border-mye-border bg-mye-app/40 p-3 space-y-2">
          <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
            Webhook saliente al aprobar drafts (P1 · opcional)
          </div>
          <input type="url" value={form.webhook_outbound_url}
                 onChange={(e) => setForm({ ...form, webhook_outbound_url: e.target.value })}
                 placeholder="https://tu-app.example.com/hooks/mye-ai"
                 className={inputCls} data-testid="ai-client-webhook-url" />
          <input type="password" value={form.webhook_outbound_secret}
                 onChange={(e) => setForm({ ...form, webhook_outbound_secret: e.target.value })}
                 placeholder="Secreto HMAC SHA-256 (opcional · firma X-MyE-Signature)"
                 className={inputCls} data-testid="ai-client-webhook-secret" />
          <div className="text-[10px] text-mye-ink-muted">
            Cuando un agente aprueba un draft cliente final, MyE postea {"{invocation_id, feature_code, ticket_id, response_hash, approved_by, approved_at}"} a esta URL con 3 reintentos exponenciales.
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.rollover_enabled}
                 onChange={(e) => setForm({ ...form, rollover_enabled: e.target.checked })}
                 className="h-4 w-4 accent-mye-accent" />
          <span>Rollover de tokens no usados</span>
        </label>

        <div className="rounded-md border border-mye-accent/40 bg-mye-accent/5 p-3 space-y-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={form.is_active}
                   onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                   className="mt-0.5 h-4 w-4 accent-mye-accent"
                   data-testid="ai-client-is-active" />
            <span>
              <span className="font-medium">Activar IA para este cliente (R39 · opt-in)</span>
              <br />
              <span className="text-[11px] text-mye-ink-muted">
                Requiere firma del responsable que aceptó política PII y tarifas.
              </span>
            </span>
          </label>
          {form.is_active && (
            <Field label="Firma de opt-in (nombre del responsable + fecha)">
              <input value={form.opt_in_signature}
                     onChange={(e) => setForm({ ...form, opt_in_signature: e.target.value })}
                     required={form.is_active}
                     placeholder="Pedro Lara, 2027-03-15"
                     className={inputCls} data-testid="ai-client-opt-in-signature" />
            </Field>
          )}
        </div>

        {err && <ErrorRow msg={err} />}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className={btnGhost}>Cancelar</button>
          <button type="submit" disabled={busy} className={btnPrimary} data-testid="ai-client-submit">
            {busy ? "Guardando…" : "Guardar configuración"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function OptOutDialog({ client, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      await api.patch(`/admin/ai/client-config/${client.id}/opt-out`, { reason });
      onDone();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <Dialog title={`Opt-out · ${client.name}`} onClose={onClose} testid="ai-optout-dialog">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-mye-ink-muted">
          Esta acción desactiva todas las features de IA para este cliente en menos de 60 segundos.
          Las invocaciones en curso terminan; las nuevas retornan <code>AI_DISABLED</code>.
        </p>
        <Field label="Motivo (queda en log inmutable)" required>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} required
                    rows={3} maxLength={2000}
                    placeholder="Ej. solicitud del área legal de privacidad"
                    className={inputCls + " resize-y"} data-testid="ai-optout-reason" />
        </Field>
        {err && <ErrorRow msg={err} />}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className={btnGhost}>Cancelar</button>
          <button type="submit" disabled={busy || !reason.trim()}
                  className="rounded-md bg-status-escalated text-white px-4 py-1.5 text-sm hover:brightness-110 transition disabled:opacity-60"
                  data-testid="ai-optout-submit">
            {busy ? "Procesando…" : "Confirmar opt-out"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

// ─── Tab 4b: Cost-per-feature trend (30d) ────────────────────────────────
function CostTrendPanel() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [client, setClient] = useState("");
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      const params = { days };
      if (client) params.client_id = client;
      const [cs, t] = await Promise.all([
        api.get("/admin/clients").catch(() => null),
        api.get("/admin/ai/cost-trend", { params }),
      ]);
      setClients(cs?.data?.data?.items || []);
      setData(t.data?.data || null);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh();   }, [days, client]);

  if (loading || !data) {
    return <div className="p-6 text-xs font-mono text-mye-ink-muted">Cargando tendencia…</div>;
  }

  const series = data.series || [];
  const totalsByDay = data.totals_by_day || [];
  const maxDayCost = Math.max(0.0001, ...totalsByDay.map((d) => d.cost_usd));
  // Paleta para features (10 colores soft)
  const palette = [
    "#C2410C", "#1F3A5F", "#0EA5E9", "#A21CAF", "#16A34A",
    "#EAB308", "#DC2626", "#0891B2", "#7C3AED", "#9333EA",
  ];

  return (
    <div className="p-5 space-y-5" data-testid="ai-cost-trend-panel">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <span className="text-xs font-mono text-mye-ink-muted">Días:</span>
          {[7, 14, 30, 60, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)}
                    className={"px-2.5 py-1 rounded-md text-xs font-mono transition border " +
                      (days === d
                        ? "bg-mye-accent text-white border-mye-accent"
                        : "bg-white text-mye-ink-muted border-mye-border hover:bg-mye-primary-soft")}
                    data-testid={`cost-trend-days-${d}`}>
              {d}d
            </button>
          ))}
        </div>
        <select value={client} onChange={(e) => setClient(e.target.value)}
                className="rounded-md border border-mye-border bg-white px-2 py-1 text-xs font-mono"
                data-testid="cost-trend-client-filter">
          <option value="">— Todos los clientes —</option>
          {clients.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <button onClick={refresh}
                className="ml-auto inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1 text-xs hover:bg-mye-primary-soft transition"
                data-testid="cost-trend-refresh">
          <RefreshCw className="h-3.5 w-3.5" /> Refrescar
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card label="Gasto total">
          <span className="font-mono text-2xl" data-testid="cost-trend-total">
            {formatCurrencyMX(data.grand_total_usd, "USD")}
          </span>
        </Card>
        <Card label="Features activos">
          <span className="font-mono text-2xl">{data.features_count}</span>
        </Card>
        <Card label="Período">
          <span className="font-mono text-xs">{data.days}d</span>
        </Card>
        <Card label="Días con tráfico">
          <span className="font-mono text-2xl">{totalsByDay.length}</span>
        </Card>
      </div>

      {/* Barras por día (totales) */}
      <section className="bg-white border border-mye-border rounded-lg p-4">
        <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-3">
          Total diario (USD)
        </div>
        {totalsByDay.length === 0 ? (
          <div className="text-xs text-mye-ink-muted">Sin datos en el rango.</div>
        ) : (
          <div className="flex items-end gap-1 h-40">
            {totalsByDay.map((d) => {
              const h = (d.cost_usd / maxDayCost) * 100;
              return (
                <div key={d.date}
                     className="flex-1 group relative flex flex-col items-center"
                     title={`${d.date}: ${formatCurrencyMX(d.cost_usd, "USD")} · ${d.invocations} llamadas`}
                     data-testid={`cost-trend-bar-${d.date}`}>
                  <div className="w-full bg-mye-accent/70 hover:bg-mye-accent transition rounded-t"
                       style={{ height: `${Math.max(2, h)}%` }} />
                  <span className="text-[9px] font-mono text-mye-ink-muted mt-1 truncate w-full text-center">
                    {d.date.slice(5)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Series por feature */}
      <section className="bg-white border border-mye-border rounded-lg p-4 space-y-3">
        <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
          Desglose por feature (top {series.length})
        </div>
        {series.length === 0 ? (
          <div className="text-xs text-mye-ink-muted">Sin invocaciones IA registradas todavía.</div>
        ) : (
          <ul className="space-y-2" data-testid="cost-trend-feature-list">
            {series.map((s, i) => {
              const pct = data.grand_total_usd > 0
                ? (s.total_cost_usd / data.grand_total_usd) * 100 : 0;
              return (
                <li key={s.feature_code}
                    className="rounded-md border border-mye-border bg-mye-app/40 p-3"
                    data-testid={`cost-trend-feature-${s.feature_code}`}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="h-3 w-3 rounded-sm" style={{ background: palette[i % palette.length] }} />
                    <span className="text-sm font-medium">{s.feature_code}</span>
                    <span className="ml-auto font-mono text-xs">
                      {formatCurrencyMX(s.total_cost_usd, "USD")} · {s.total_invocations} llamadas
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-mye-border overflow-hidden">
                    <div className="h-full transition-all"
                         style={{
                           width: `${pct.toFixed(1)}%`,
                           background: palette[i % palette.length],
                         }} />
                  </div>
                  <div className="text-[10px] font-mono text-mye-ink-muted mt-1.5">
                    {pct.toFixed(1)}% del gasto · {s.points.length} día(s) con tráfico
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function Card({ label, children }) {
  return (
    <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">{label}</div>
      <div>{children}</div>
    </div>
  );
}

// ─── Tab 4: Consumption Dashboard ────────────────────────────────────────
function ConsumptionPanel() {
  const [items, setItems] = useState([]);
  const [logs, setLogs] = useState([]);
  const [filterClient, setFilterClient] = useState("");
  const [clients, setClients] = useState([]);
  const [systemStatus, setSystemStatus] = useState(null);

  async function refresh() {
    const params = filterClient ? { client_id: filterClient } : {};
    const [c, cons, log, sys] = await Promise.all([
      api.get("/admin/clients"),
      api.get("/admin/ai/consumption", { params }),
      api.get("/admin/ai/invocation-log", { params: { limit: 50, ...params } }),
      api.get("/ai/system/status").catch(() => null),
    ]);
    setClients(c.data?.data?.items || []);
    setItems(cons.data?.data?.items || []);
    setLogs(log.data?.data?.items || []);
    setSystemStatus(sys?.data?.data || null);
  }
  useEffect(() => { refresh(); }, [filterClient]);

  const totalUsd = items.reduce((acc, r) => acc + (r.total_cost_usd || 0), 0);
  const totalInv = items.reduce((acc, r) => acc + (r.invocations_count || 0), 0);

  return (
    <div data-testid="ai-consumption-panel" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-mye-border bg-white">
        <div>
          <div className="font-medium text-sm">Dashboard de consumo</div>
          <div className="text-xs text-mye-ink-muted font-mono">{items.length} ventanas mes·cliente</div>
        </div>
        <select value={filterClient} onChange={(e) => setFilterClient(e.target.value)}
                className={inputCls + " ml-auto max-w-xs"} data-testid="ai-consumption-filter">
          <option value="">Todos los clientes</option>
          {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <button onClick={refresh} className={btnGhost + " inline-flex items-center gap-1 text-xs"}>
          <RefreshCw className="h-3.5 w-3.5" /> Refrescar
        </button>
      </div>

      <div className="grid md:grid-cols-3 gap-3 px-5">
        <Stat label="Costo total (mes en curso)" value={formatCurrencyMX(totalUsd, "USD")} />
        <Stat label="Invocaciones totales" value={totalInv} />
        <Stat label="Eventos en log" value={logs.length} />
      </div>

      {systemStatus && (
        <div className="px-5">
          <div className="rounded-md border border-mye-border bg-mye-app/40 p-4" data-testid="ai-system-status">
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-2">
              Estado del sistema (P1) · circuit breaker + cache
            </div>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-xs font-medium mb-1.5">Circuit breaker por proveedor</div>
                {Object.keys(systemStatus.breaker || {}).length === 0 ? (
                  <div className="text-[12px] font-mono text-mye-ink-muted">Sin actividad — todos cerrados.</div>
                ) : (
                  <ul className="text-[12px] space-y-1">
                    {Object.entries(systemStatus.breaker).map(([prov, st]) => (
                      <li key={prov} className="flex items-center gap-2">
                        <span className="font-mono">{prov}</span>
                        <span className={"px-2 py-0.5 rounded-full text-[10px] font-mono " +
                          (st.state === "closed" ? "bg-status-resolved/10 text-status-resolved" :
                           st.state === "open" ? "bg-status-escalated/10 text-status-escalated" :
                           "bg-status-waiting/10 text-status-waiting")}>
                          {st.state}
                        </span>
                        {st.failures_in_window > 0 && (
                          <span className="text-mye-ink-muted">· {st.failures_in_window} fallas</span>
                        )}
                        {st.cooldown_remaining_s > 0 && (
                          <span className="text-mye-ink-muted">· cooldown {st.cooldown_remaining_s}s</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="text-xs font-medium mb-1.5">Cache de prompts</div>
                <div className="grid grid-cols-2 gap-2 text-[12px] font-mono">
                  <div><span className="text-mye-ink-muted">hits</span>: {systemStatus.cache_metrics?.hits || 0}</div>
                  <div><span className="text-mye-ink-muted">misses</span>: {systemStatus.cache_metrics?.misses || 0}</div>
                  <div><span className="text-mye-ink-muted">stores</span>: {systemStatus.cache_metrics?.stores || 0}</div>
                  <div><span className="text-mye-ink-muted">evictions</span>: {systemStatus.cache_metrics?.evictions || 0}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="px-5 overflow-x-auto">
        <h3 className="font-medium text-sm mb-2 mt-2">Consumo por cliente · mes</h3>
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Cliente", "Mes", "Invocations", "Tokens in", "Tokens out", "Costo USD", "Alerta 80%", "Tope 100%"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-3 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-8 text-center text-xs text-mye-ink-muted font-mono">Sin consumo registrado.</td></tr>
            )}
            {items.map((r) => (
              <tr key={r.id} className="border-t border-mye-border" data-testid={`ai-cons-${r.client_id}`}>
                <td className="px-3 py-2 font-mono text-[11px]">{(clients.find((c) => c.id === r.client_id)?.name) || r.client_id.slice(0, 8)}</td>
                <td className="px-3 py-2 font-mono text-[12px]">{r.year_month}</td>
                <td className="px-3 py-2 tabular-nums">{r.invocations_count}</td>
                <td className="px-3 py-2 tabular-nums">{r.total_input_tokens.toLocaleString()}</td>
                <td className="px-3 py-2 tabular-nums">{r.total_output_tokens.toLocaleString()}</td>
                <td className="px-3 py-2 font-mono">{formatCurrencyMX(r.total_cost_usd, "USD")}</td>
                <td className="px-3 py-2 text-[11px] font-mono text-mye-ink-muted">{r.alert_80_sent_at ? "✓" : "—"}</td>
                <td className="px-3 py-2 text-[11px] font-mono">{r.alert_100_sent_at ?
                  <span className="text-mye-accent">CAPPED</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="px-5 overflow-x-auto pb-5">
        <h3 className="font-medium text-sm mb-2 mt-4">Log de invocaciones (últimas 50)</h3>
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Cuándo", "Feature", "Status", "Modelo", "Tokens", "Costo", "PII"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-3 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-xs text-mye-ink-muted font-mono">Sin invocaciones todavía.</td></tr>
            )}
            {logs.map((l) => (
              <tr key={l.id} className="border-t border-mye-border" data-testid={`ai-log-${l.id}`}>
                <td className="px-3 py-2 font-mono text-[10px] text-mye-ink-muted">{l.created_at}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{l.feature_code}</td>
                <td className="px-3 py-2">
                  <StatusPill v={l.status} />
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-mye-ink-muted">{l.model || "—"}</td>
                <td className="px-3 py-2 tabular-nums text-[11px]">{(l.input_tokens || 0)} ↗ {(l.output_tokens || 0)}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{formatCurrencyMX(l.cost_usd, "USD")}</td>
                <td className="px-3 py-2 text-[10px] font-mono">
                  {l.pii_detected ? <span className="text-mye-accent">{l.pii_token_count} tokens</span> : <span className="text-mye-ink-muted">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Tab 5: Benchmark cost-vs-latency (P2) ───────────────────────────────
function BenchmarkPanel({ canRunLive }) {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [samples, setSamples] = useState(3);

  async function refresh() {
    const r = await api.get("/admin/ai/benchmark");
    setItems(r.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  async function runBenchmark(dryRun) {
    setBusy(true); setErr(null);
    try {
      await api.post(`/admin/ai/benchmark/run?dry_run=${dryRun}&samples=${samples}`);
      await refresh();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  const latest = items[0];

  return (
    <div data-testid="ai-benchmark-panel">
      <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-mye-border">
        <div>
          <div className="font-medium">Benchmark cost-vs-latency</div>
          <div className="text-xs text-mye-ink-muted font-mono">
            {items.length} corridas · dry_run estima desde MODEL_PRICING; live usa la universal key
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs">
            <span className="text-mye-ink-muted font-mono">samples</span>
            <input type="number" min={1} max={10} value={samples}
                   onChange={(e) => setSamples(+e.target.value)}
                   className="w-14 rounded-md border border-mye-border bg-white px-2 py-1 text-xs" />
          </label>
          <button onClick={refresh} className={btnGhost + " text-xs inline-flex items-center gap-1"}
                  data-testid="ai-benchmark-refresh">
            <RefreshCw className="h-3.5 w-3.5" /> Refrescar
          </button>
          <button onClick={() => runBenchmark(true)} disabled={busy}
                  className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition inline-flex items-center gap-1 disabled:opacity-60"
                  data-testid="ai-benchmark-run-dry">
            <Play className="h-3.5 w-3.5" /> Dry-run
          </button>
          {canRunLive && (
            <button onClick={() => {
                if (window.confirm("Esta corrida REAL gastará tokens contra los providers configurados. ¿Continuar?")) {
                  runBenchmark(false);
                }
              }}
              disabled={busy}
              className="rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition inline-flex items-center gap-1 disabled:opacity-60"
              data-testid="ai-benchmark-run-live">
              <Play className="h-3.5 w-3.5" /> Live
            </button>
          )}
        </div>
      </div>

      {err && <div className="px-5 pt-4"><ErrorRow msg={err} /></div>}

      {!latest ? (
        <div className="px-5 py-10 text-center text-sm text-mye-ink-muted font-mono">
          Sin corridas todavía. Ejecutá un dry-run para ver estimaciones.
        </div>
      ) : (
        <div className="space-y-4 p-5">
          <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted"
               title={latest.started_at ? new Date(latest.started_at).toLocaleString("es-MX", { timeZone: "America/Mexico_City" }) : ""}
               data-testid="ai-benchmark-last-run">
            Última corrida · {latest.mode === "live" ? "Live (con tokens reales)" : "Dry-run (estimado)"} · ejecutado {fechaRelativa(latest.started_at)} · {fechaCompacta(latest.started_at)} (CDMX)
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-mye-app/60">
                <tr>
                  {["Provider", "Modelo", "Avg cost USD", "Avg in tokens", "Avg out tokens",
                    "p50 latency", "p95 latency", "p99 latency", "Errores"].map((h) => (
                    <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-3 py-2.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {latest.results.map((r, i) => (
                  <tr key={i} className="border-t border-mye-border" data-testid={`ai-benchmark-row-${r.model}`}>
                    <td className="px-3 py-2 font-mono text-[11px] text-mye-ink-muted">{r.provider}</td>
                    <td className="px-3 py-2 font-mono text-[12px]">{r.model}</td>
                    <td className="px-3 py-2 font-mono">${r.avg_cost_usd}</td>
                    <td className="px-3 py-2 tabular-nums">{r.avg_input_tokens}</td>
                    <td className="px-3 py-2 tabular-nums">{r.avg_output_tokens}</td>
                    <td className="px-3 py-2 tabular-nums">{r.p50_latency_ms ?? "—"}</td>
                    <td className="px-3 py-2 tabular-nums">{r.p95_latency_ms ?? "—"}</td>
                    <td className="px-3 py-2 tabular-nums">{r.p99_latency_ms ?? "—"}</td>
                    <td className="px-3 py-2 tabular-nums">{r.errors}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Tab 6: Auditoría externa con CSV firmado (P2) ───────────────────────
function AuditPanel({ canExport }) {
  const [filters, setFilters] = useState({
    date_from: "", date_to: "", client_id: "", feature_code: "", status: "",
  });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [clients, setClients] = useState([]);
  const [features, setFeatures] = useState([]);

  useEffect(() => {
    Promise.all([api.get("/admin/clients"), api.get("/admin/ai/features")]).then(([c, f]) => {
      setClients(c.data?.data?.items || []);
      setFeatures(f.data?.data?.items || []);
    });
  }, []);

  function buildQuery() {
    const p = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v) p.append(k, v); });
    return p.toString();
  }

  async function loadPreview() {
    setBusy(true); setErr(null);
    try {
      const r = await api.get(`/admin/ai/audit/preview?${buildQuery()}`);
      setPreview(r.data?.data || null);
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  async function downloadCsv() {
    if (!canExport) return;
    setBusy(true); setErr(null);
    try {
      const token = localStorage.getItem("mye_access_token");
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/admin/ai/audit/export.csv?${buildQuery()}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        setErr(`HTTP ${res.status}`);
        return;
      }
      const sig = res.headers.get("X-MyE-Audit-Signature") || "";
      const rows = res.headers.get("X-MyE-Audit-Rows") || "0";
      const blob = await res.blob();
      const a = document.createElement("a");
      const link = URL.createObjectURL(blob);
      a.href = link;
      a.download = `ai-audit-${Date.now()}.csv`;
      a.click();
      URL.revokeObjectURL(link);
      setPreview((p) => ({ ...(p || {}), last_download_signature: sig, last_download_rows: rows }));
    } catch (e) {
      setErr(e.message || "Download failed");
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="ai-audit-panel">
      <div className="px-5 py-4 border-b border-mye-border">
        <div className="font-medium">Auditoría externa · export CSV firmado</div>
        <div className="text-xs text-mye-ink-muted font-mono">
          HMAC SHA-256 sobre el body. Auditor verifica con secret = AUDIT_SIGNING_SECRET (header X-MyE-Audit-Signature).
        </div>
      </div>

      <div className="p-5 space-y-4">
        <div className="grid md:grid-cols-3 gap-3">
          <Field label="Desde">
            <input type="date" value={filters.date_from}
                   onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                   className={inputCls} data-testid="ai-audit-date-from" />
          </Field>
          <Field label="Hasta">
            <input type="date" value={filters.date_to}
                   onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                   className={inputCls} data-testid="ai-audit-date-to" />
          </Field>
          <Field label="Status">
            <select value={filters.status}
                    onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                    className={inputCls} data-testid="ai-audit-status">
              <option value="">Todos</option>
              <option value="success">success</option>
              <option value="cache_hit">cache_hit</option>
              <option value="capped">capped</option>
              <option value="error">error</option>
              <option value="provider_unavailable">provider_unavailable</option>
              <option value="opt_out_executed">opt_out_executed</option>
            </select>
          </Field>
          <Field label="Cliente">
            <select value={filters.client_id}
                    onChange={(e) => setFilters({ ...filters, client_id: e.target.value })}
                    className={inputCls}>
              <option value="">Todos</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Feature">
            <select value={filters.feature_code}
                    onChange={(e) => setFilters({ ...filters, feature_code: e.target.value })}
                    className={inputCls}>
              <option value="">Todas</option>
              {features.map((f) => <option key={f.id} value={f.feature_code}>{f.feature_code}</option>)}
            </select>
          </Field>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={loadPreview} disabled={busy}
                  className={btnGhost + " inline-flex items-center gap-1.5 disabled:opacity-60"}
                  data-testid="ai-audit-preview-btn">
            {busy ? "Calculando…" : "Vista previa"}
          </button>
          {canExport && (
            <button onClick={downloadCsv} disabled={busy}
                    className="rounded-md bg-mye-accent text-white px-4 py-1.5 text-sm hover:brightness-110 transition inline-flex items-center gap-1.5 disabled:opacity-60"
                    data-testid="ai-audit-download-btn">
              <Download className="h-3.5 w-3.5" /> Descargar CSV firmado
            </button>
          )}
        </div>

        {err && <ErrorRow msg={err} />}

        {preview && (
          <div className="rounded-md border border-mye-border bg-mye-app/40 p-4 space-y-3" data-testid="ai-audit-preview">
            <div className="grid md:grid-cols-3 gap-3 text-sm">
              <div>
                <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Rows</div>
                <div className="font-mono text-2xl tabular-nums">{preview.rows ?? 0}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Tamaño</div>
                <div className="font-mono">{(preview.size_bytes ?? 0).toLocaleString()} bytes</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Generado</div>
                <div className="font-mono text-[12px]">{preview.exported_at?.slice(0, 19).replace("T", " ")}</div>
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Firma</div>
              <code className="block bg-white border border-mye-border rounded p-2 mt-1 text-[10px] font-mono break-all" data-testid="ai-audit-signature">
                {preview.signature}
              </code>
            </div>
            {preview.last_download_signature && (
              <div className="rounded border border-mye-accent/30 bg-mye-accent/5 p-2 text-[11px] font-mono" data-testid="ai-audit-last-download">
                Última descarga: {preview.last_download_rows} filas · firma {preview.last_download_signature.slice(0, 30)}…
              </div>
            )}
            <div>
              <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Preview (primeras 5 filas)</div>
              <pre className="bg-white border border-mye-border rounded p-2 mt-1 text-[10px] overflow-x-auto whitespace-pre">
{preview.preview_csv || "—"}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// ─── Reusable atoms ──────────────────────────────────────────────────────
const inputCls =
  "w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors";
const btnPrimary =
  "rounded-md bg-mye-accent text-white px-4 py-1.5 text-sm hover:brightness-110 transition disabled:opacity-60";
const btnGhost =
  "rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft transition";

function PanelHeader({ title, subtitle, onRefresh, onCreate, testid }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-mye-border">
      <div>
        <div className="font-medium">{title}</div>
        <div className="text-xs text-mye-ink-muted font-mono">{subtitle}</div>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={onRefresh} className={btnGhost + " inline-flex items-center gap-1 text-xs"} data-testid={`${testid}-refresh`}>
          <RefreshCw className="h-3.5 w-3.5" /> Refrescar
        </button>
        {onCreate && (
          <button onClick={onCreate} className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition" data-testid={`${testid}-create`}>
            <Plus className="h-3.5 w-3.5" /> Nuevo
          </button>
        )}
      </div>
    </div>
  );
}

function Dialog({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" data-testid={testid}>
      <div className="bg-white border border-mye-border rounded-lg shadow-xl w-full max-w-lg animate-fade-in max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border sticky top-0 bg-white">
          <div className="font-medium text-sm">{title}</div>
          <button onClick={onClose} className="text-mye-ink-muted hover:text-mye-ink"><X className="h-4 w-4" /></button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">
        {label}{required && <span className="text-mye-accent ml-0.5">*</span>}
      </span>
      {children}
    </label>
  );
}

function ErrorRow({ msg }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-[13px] text-status-escalated">
      <AlertTriangle className="h-4 w-4 mt-0.5 flex-none" /> {msg}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-md border border-mye-border bg-white p-4">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function DestinatarioBadge({ v }) {
  const map = {
    agent_internal: "bg-status-active/10 text-status-active border-status-active/30",
    client_final:   "bg-status-claim/10 text-status-claim border-status-claim/30",
    both:           "bg-status-pending/10 text-status-pending border-status-pending/30",
  };
  return (
    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono " + (map[v] || "border-mye-border")}>
      {v} {v === "client_final" && <Eye className="h-3 w-3 ml-1" title="R42 → draft" />}
    </span>
  );
}

function StatusPill({ v }) {
  const map = {
    success: "text-status-resolved",
    error: "text-status-escalated",
    capped: "text-mye-accent",
    provider_unavailable: "text-status-waiting",
    opt_out_executed: "text-mye-ink-muted",
  };
  return <span className={"font-mono text-[11px] " + (map[v] || "text-mye-ink-muted")}>{v}</span>;
}
