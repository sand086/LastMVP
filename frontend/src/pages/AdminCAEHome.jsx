import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity, FileWarning, BookOpen, History, LogOut, FlaskConical,
  Plus, X, Search, ArrowUpRight, AlertTriangle, CheckCircle2, Pencil, Save,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";

export default function AdminCAEHome() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [unmapped, setUnmapped] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [audit, setAudit] = useState([]);
  const [health, setHealth] = useState(null);
  const [tab, setTab] = useState("overview");
  const [editing, setEditing] = useState(null); // Iter59 — fila en edición

  const canEditCatalog = ["admin", "superadmin", "root_dev"].includes(user?.role);

  async function refresh() {
    const [u, c, a, h] = await Promise.all([
      api.get("/admin/cae/unmapped"),
      api.get("/admin/cae/catalog"),
      api.get("/admin/cae/audit-log"),
      api.get("/system/health"),
    ]);
    setUnmapped(u.data?.data?.items || []);
    setCatalog(c.data?.data?.items || []);
    setAudit(a.data?.data?.items || []);
    setHealth(h.data?.data || null);
  }
  useEffect(() => { refresh(); }, []);

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-cae-home">
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">CAE Admin · v2.1-MVP</div>
            </div>
          </div>
          <nav className="hidden md:flex items-center gap-1 ml-6 text-sm" data-testid="cae-header-nav-legacy" aria-hidden>
            {/* Nav links migrated to <AdminSidebar /> in Iter35. Empty placeholder kept to preserve layout flexbox; remove in next refactor. */}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <SaaSHierarchyBreadcrumb className="hidden md:inline-flex mr-2" />
            <span className="hidden sm:inline-flex items-center gap-2 text-xs font-mono text-mye-ink-muted">
              <span className={"h-1.5 w-1.5 rounded-full " + (health?.db === "ok" ? "bg-status-resolved" : "bg-status-escalated")} />
              {health ? `db:${health.db} · ${health.version}` : "checking…"}
            </span>
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 05–07 · Engine + CAE + Adapters
          </div>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight">Carrier Adapter Engine — listo para producción.</h1>
          <p className="mt-2 text-mye-ink-muted max-w-3xl">
            5 adapters ancla en modo mock, normalizer real con catálogo persistente,
            sandbox para simular cualquier raw_code, y monitor de códigos huérfanos con
            promoción al catálogo en un click.
          </p>
        </section>

        <section className="grid md:grid-cols-3 gap-4" data-testid="cae-stats-cards">
          <StatCard label="Mapeos en catálogo" value={catalog.length} sub="carrier_status_catalog" testid="stat-catalog-count" />
          <StatCard label="Códigos sin mapeo" value={unmapped.length} sub="cae_unmapped_codes · R25" highlight testid="stat-unmapped-count" />
          <StatCard label="Eventos auditados" value={audit.length} sub="cae_audit_log · append-only · R27" testid="stat-audit-count" />
        </section>

        <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="cae-tabs">
          {[
            ["overview","Resumen", BookOpen],
            ["sandbox","Sandbox · Probar raw_code", FlaskConical],
            ["unmapped","Sin mapeo (R25)", FileWarning],
            ["audit","Auditoría", History],
          ].map(([k,label,Icon]) => (
            <button key={k} onClick={() => setTab(k)}
                    className={"inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-md transition-colors -mb-px " +
                      (tab === k ? "bg-white border border-mye-border border-b-white text-mye-ink"
                                 : "text-mye-ink-muted hover:text-mye-ink")}
                    data-testid={`cae-tab-${k}`}>
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
        </div>

        <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
          {tab === "overview" && <CatalogTable items={catalog} canEdit={canEditCatalog} onEdit={setEditing} />}
          {tab === "sandbox"  && <Sandbox onRefresh={refresh} />}
          {tab === "unmapped" && <UnmappedPanel items={unmapped} onPromoted={refresh} />}
          {tab === "audit"    && <AuditTable items={audit} />}
        </div>
      </main>

      {editing && (
        <EditCatalogModal
          entry={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => { setEditing(null); await refresh(); }}
        />
      )}
    </div>
  );
}

// ───── Stat card ────────────────────────────────────────────────────────
function StatCard({ label, value, sub, highlight, testid }) {
  return (
    <div className={"rounded-lg border bg-white p-5 transition-all hover:-translate-y-0.5 hover:shadow-sm " +
      (highlight ? "border-mye-accent/40" : "border-mye-border")} data-testid={testid}>
      <div className="text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">{label}</div>
      <div className={"mt-3 text-4xl font-semibold tabular-nums " + (highlight ? "text-mye-accent" : "text-mye-ink")}>{value}</div>
      <div className="mt-1 text-xs font-mono text-mye-ink-muted">{sub}</div>
    </div>
  );
}

// ───── Catalog table ───────────────────────────────────────────────────
function CatalogTable({ items, canEdit, onEdit }) {
  if (items.length === 0) {
    return <div className="px-6 py-10 text-center text-sm text-mye-ink-muted font-mono">Sin mapeos.</div>;
  }
  const headers = ["Carrier", "Raw code", "Canonical", "Display ES", "Conf.", "Terminal", "Acción", "Origen"];
  if (canEdit) headers.push("");
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="cae-catalog-table">
        <thead className="bg-mye-app/60">
          <tr>
            {headers.map((h, i) => (
              <th key={i} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 200).map((r) => (
            <tr key={r.id} className="border-t border-mye-border hover:bg-mye-primary-soft/30 transition"
                data-testid={`cae-catalog-row-${r.carrier_id}-${r.raw_code}`}>
              <td className="px-4 py-2.5 font-mono text-[12px]">{r.carrier_id}</td>
              <td className="px-4 py-2.5 font-mono text-[12px]">{r.raw_code}</td>
              <td className="px-4 py-2.5"><CanonicalPill v={r.canonical_status} /></td>
              <td className="px-4 py-2.5 text-mye-ink-muted">{r.display_label_es}</td>
              <td className="px-4 py-2.5 font-mono text-[12px] text-mye-ink-muted">{r.confidence}%</td>
              <td className="px-4 py-2.5">{r.is_terminal ? "✓" : "—"}</td>
              <td className="px-4 py-2.5">{r.requires_action ? "⚠" : "—"}</td>
              <td className="px-4 py-2.5 font-mono text-[10px] text-mye-ink-muted">{r.source}</td>
              {canEdit && (
                <td className="px-4 py-2.5">
                  <button
                    onClick={() => onEdit?.(r)}
                    className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-primary-soft/40 transition"
                    data-testid={`cae-edit-${r.carrier_id}-${r.raw_code}`}
                    title="Editar homologación"
                  >
                    <Pencil className="h-3 w-3" /> Editar
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CanonicalPill({ v }) {
  const map = {
    in_transit: "bg-status-active/10 text-status-active border-status-active/30",
    delivered:  "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
    returned:   "bg-status-claim/10 text-status-claim border-status-claim/30",
    exception:  "bg-status-escalated/10 text-status-escalated border-status-escalated/30",
    cancelled:  "bg-status-closed/10 text-status-closed border-status-closed/30",
    unknown:    "bg-mye-app text-mye-ink-muted border-mye-border",
  };
  return (
    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono " + (map[v] || "border-mye-border")}>
      {v || "—"}
    </span>
  );
}

// ───── Sandbox simulator ──────────────────────────────────────────────
function Sandbox({ onRefresh }) {
  const [carrier, setCarrier] = useState("fedex");
  const [rawCode, setRawCode] = useState("DL");
  const [apiVersion, setApiVersion] = useState("v1");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [error, setError] = useState(null);

  async function run(e) {
    e?.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await api.post("/admin/cae/sandbox", {
        carrier_id: carrier, raw_code: rawCode, api_version: apiVersion,
      });
      setResult(r.data?.data);
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  async function promoteSuggestion() {
    if (!result?.suggestion) return;
    setPromoting(true); setError(null);
    try {
      await api.post("/admin/cae/promote-unmapped", {
        carrier_id: carrier, raw_code: rawCode, api_version: apiVersion,
        ...result.suggestion,
      });
      await run();
      onRefresh?.();
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setPromoting(false); }
  }

  return (
    <div className="p-6 space-y-5" data-testid="cae-sandbox-panel">
      <div>
        <div className="font-medium text-sm">Simulador del Normalizer</div>
        <div className="text-xs text-mye-ink-muted">
          Aplica las mismas reglas que se usan en producción — sin afectar contadores de unmapped.
        </div>
      </div>

      <form onSubmit={run} className="grid md:grid-cols-4 gap-3 items-end">
        <label className="block">
          <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">Carrier</span>
          <select value={carrier} onChange={(e) => setCarrier(e.target.value)}
                  className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                  data-testid="sandbox-carrier">
            {["fedex", "dhl", "estafeta", "99min", "paqex"].map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">Raw code</span>
          <input value={rawCode} onChange={(e) => setRawCode(e.target.value)}
                 className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                 placeholder="DL" data-testid="sandbox-raw-code" />
        </label>
        <label className="block">
          <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">API version</span>
          <input value={apiVersion} onChange={(e) => setApiVersion(e.target.value)}
                 className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono"
                 data-testid="sandbox-api-version" />
        </label>
        <button type="submit" disabled={busy}
                className="inline-flex items-center justify-center gap-1 rounded-md bg-mye-accent text-white px-4 py-2 text-sm hover:brightness-110 transition disabled:opacity-60"
                data-testid="sandbox-run">
          <Search className="h-3.5 w-3.5" /> {busy ? "Probando…" : "Probar"}
        </button>
      </form>

      {error && (
        <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated">{error}</div>
      )}

      {result && (
        <div className={"rounded-md border p-4 space-y-2 " +
          (result.matched
            ? "border-status-resolved/40 bg-status-resolved/5"
            : "border-status-waiting/40 bg-status-waiting/5")}
             data-testid="sandbox-result">
          {result.matched ? (
            <>
              <div className="flex items-center gap-2 text-sm font-medium text-status-resolved">
                <CheckCircle2 className="h-4 w-4" /> Mapeo encontrado · scope: {result.scope}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                <KvBox k="canonical_status" v={result.canonical_status} pill />
                <KvBox k="incident_type" v={result.incident_type ?? "—"} />
                <KvBox k="is_terminal" v={result.is_terminal ? "✓" : "—"} />
                <KvBox k="requires_action" v={result.requires_action ? "✓" : "—"} />
                <KvBox k="confidence" v={`${result.confidence}%`} />
                <KvBox k="display_label_es" v={result.display_label_es} />
              </div>
              <div className="text-[11px] font-mono text-mye-ink-muted">source: {result.source}</div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm font-medium text-status-waiting">
                <AlertTriangle className="h-4 w-4" /> Sin mapeo en catálogo
              </div>
              {result.suggestion ? (
                <>
                  <div className="text-xs text-mye-ink-muted">Sugerencia del adapter:</div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                    <KvBox k="canonical" v={result.suggestion.canonical_status} pill />
                    <KvBox k="incident" v={result.suggestion.incident_type ?? "—"} />
                    <KvBox k="terminal" v={result.suggestion.is_terminal ? "✓" : "—"} />
                    <KvBox k="action"   v={result.suggestion.requires_action ? "✓" : "—"} />
                    <KvBox k="confidence" v={`${result.suggestion.confidence}%`} />
                    <KvBox k="label" v={result.suggestion.display_label_es} />
                  </div>
                  <button onClick={promoteSuggestion} disabled={promoting}
                          className="mt-2 inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                          data-testid="sandbox-promote-suggestion">
                    <Plus className="h-3.5 w-3.5" /> {promoting ? "Promoviendo…" : "Promover esta sugerencia"}
                  </button>
                </>
              ) : (
                <div className="text-xs text-mye-ink-muted">No hay sugerencia automática — define el mapeo manualmente.</div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function KvBox({ k, v, pill }) {
  return (
    <div className="rounded-md border border-mye-border bg-white px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">{k}</div>
      {pill ? <CanonicalPill v={v} /> : <div className="text-sm">{v}</div>}
    </div>
  );
}

// ───── Unmapped panel with promote button ─────────────────────────────
function UnmappedPanel({ items, onPromoted }) {
  if (items.length === 0) {
    return <div className="px-6 py-10 text-center text-sm text-mye-ink-muted font-mono">Sin alertas — todo está mapeado.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-mye-app/60">
          <tr>
            {["Carrier", "Raw code", "Ocurrencias", "Primera vez", "Última vez", ""].map((h) => (
              <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((u) => (
            <tr key={`${u.carrier_id}|${u.raw_code}|${u.api_version}`} className="border-t border-mye-border">
              <td className="px-4 py-2.5 font-mono text-[12px]">{u.carrier_id}</td>
              <td className="px-4 py-2.5 font-mono text-[12px]">{u.raw_code}</td>
              <td className="px-4 py-2.5 tabular-nums">{u.occurrences}</td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{u.first_seen}</td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{u.last_seen}</td>
              <td className="px-4 py-2.5">
                <a href={`#sandbox-${u.raw_code}`} onClick={(e) => {
                     e.preventDefault();
                     // Cheap UX: just scroll up; full sandbox flow is on the previous tab.
                     window.scrollTo({ top: 0, behavior: "smooth" });
                   }}
                   className="inline-flex items-center gap-1 text-mye-accent text-xs hover:brightness-110">
                  <ArrowUpRight className="h-3.5 w-3.5" /> Probar en sandbox
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditTable({ items }) {
  if (items.length === 0) {
    return <div className="px-6 py-10 text-center text-sm text-mye-ink-muted font-mono">Sin movimientos auditados todavía.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-mye-app/60">
          <tr>
            {["Fecha", "Acción", "Entidad", "Entry", "Usuario"].map((h) => (
              <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id} className="border-t border-mye-border">
              <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{a.created_at}</td>
              <td className="px-4 py-2.5 font-mono text-[12px]">{a.action}</td>
              <td className="px-4 py-2.5 font-mono text-[12px]">{a.entity}</td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{a.entity_id?.slice(0, 8)}…</td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{a.user_id?.slice(0, 8)}…</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


// ───── Iter59 — Modal de edición de homologación ──────────────────────
const CANONICAL_OPTIONS = ["in_transit", "delivered", "returned", "exception", "cancelled", "unknown"];
const INCIDENT_OPTIONS = [
  "", "address_issue", "refused", "recipient_absent", "customs",
  "damage", "lost", "failed", "exception", "returned", "other",
];

function EditCatalogModal({ entry, onClose, onSaved }) {
  const [form, setForm] = useState({
    canonical_status: entry.canonical_status || "unknown",
    display_label_es: entry.display_label_es || "",
    incident_type: entry.incident_type || "",
    is_terminal: !!entry.is_terminal,
    requires_action: !!entry.requires_action,
    confidence: entry.confidence ?? 95,
    active: entry.active !== false,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  // Iter60 — preview + reclasificación retroactiva
  const [preview, setPreview] = useState(null);
  const [reclassifying, setReclassifying] = useState(false);
  const [reclassifyResult, setReclassifyResult] = useState(null);

  function update(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  useEffect(() => {
    api.get(`/admin/cae/catalog/${entry.id}/reclassify-preview`)
      .then((r) => setPreview(r.data?.data))
      .catch(() => {});
  }, [entry.id]);

  async function save() {
    setSaving(true); setError(null);
    try {
      const payload = {
        canonical_status: form.canonical_status,
        display_label_es: form.display_label_es,
        incident_type: form.incident_type || null,
        is_terminal: form.is_terminal,
        requires_action: form.requires_action,
        confidence: Number(form.confidence),
        active: form.active,
      };
      await api.patch(`/admin/cae/catalog/${entry.id}`, payload);
      // Refresca preview con el catálogo actualizado
      const r = await api.get(`/admin/cae/catalog/${entry.id}/reclassify-preview`);
      setPreview(r.data?.data);
    } catch (e) {
      setError(e.response?.data?.errors?.[0]?.message || e.message);
    } finally {
      setSaving(false);
    }
  }

  async function applyToExisting() {
    if (!preview || preview.total_guias === 0) return;
    setReclassifying(true); setError(null); setReclassifyResult(null);
    try {
      const r = await api.post(`/admin/cae/catalog/${entry.id}/reclassify`, {
        dry_run: false, create_tickets: true,
      }, { timeout: 300000 });
      setReclassifyResult(r.data?.data);
      // Refresca preview tras aplicar
      const r2 = await api.get(`/admin/cae/catalog/${entry.id}/reclassify-preview`);
      setPreview(r2.data?.data);
    } catch (e) {
      setError(e.response?.data?.errors?.[0]?.message || e.message);
    } finally {
      setReclassifying(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="cae-edit-modal">
      <div className="bg-white border border-mye-border rounded-lg w-full max-w-xl shadow-xl">
        <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border">
          <div>
            <div className="text-sm font-semibold">Editar homologación</div>
            <div className="text-[11px] font-mono text-mye-ink-muted mt-0.5">
              {entry.carrier_id} · raw_code: <span className="text-mye-ink">{entry.raw_code}</span> · {entry.api_version || "v1"}
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-mye-app rounded" data-testid="cae-edit-close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <Field label="Canonical status">
            <select value={form.canonical_status}
                    onChange={(e) => update("canonical_status", e.target.value)}
                    className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                    data-testid="cae-edit-canonical">
              {CANONICAL_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>

          <Field label="Display label (ES)">
            <input value={form.display_label_es}
                   onChange={(e) => update("display_label_es", e.target.value)}
                   className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                   data-testid="cae-edit-display" />
          </Field>

          <Field label="Incident type (opcional)">
            <select value={form.incident_type}
                    onChange={(e) => update("incident_type", e.target.value)}
                    className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                    data-testid="cae-edit-incident">
              {INCIDENT_OPTIONS.map((c) => <option key={c || "none"} value={c}>{c || "— ninguno —"}</option>)}
            </select>
          </Field>

          <div className="grid grid-cols-3 gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_terminal}
                     onChange={(e) => update("is_terminal", e.target.checked)}
                     data-testid="cae-edit-terminal" />
              <span>Es terminal</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.requires_action}
                     onChange={(e) => update("requires_action", e.target.checked)}
                     data-testid="cae-edit-requires-action" />
              <span>Requiere acción</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.active}
                     onChange={(e) => update("active", e.target.checked)}
                     data-testid="cae-edit-active" />
              <span>Activo</span>
            </label>
          </div>

          <Field label={`Confidence (${form.confidence}%)`}>
            <input type="range" min={0} max={100} value={form.confidence}
                   onChange={(e) => update("confidence", e.target.value)}
                   className="w-full"
                   data-testid="cae-edit-confidence" />
          </Field>

          {error && (
            <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
                 data-testid="cae-edit-error">
              {error}
            </div>
          )}

          {/* Iter60 — Reclasificación retroactiva */}
          {preview && (
            <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-3"
                 data-testid="cae-reclassify-block">
              <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                Aplicar a guías existentes
              </div>
              <div className="text-xs text-mye-ink-muted">
                Hay <span className="font-mono text-mye-ink font-semibold" data-testid="cae-reclassify-total">{preview.total_guias}</span> guía(s)
                con <code className="font-mono text-[11px]">{entry.carrier_id}/{entry.raw_code}</code>
                {preview.needs_change > 0 ? (
                  <> — <span className="text-mye-accent font-semibold" data-testid="cae-reclassify-needs">{preview.needs_change}</span> requieren actualización al nuevo mapeo.</>
                ) : (
                  <> — todas ya están en el estado target.</>
                )}
              </div>
              {reclassifyResult && (
                <div className="mt-2 text-xs rounded-md bg-status-resolved/10 border border-status-resolved/30 px-2 py-1.5"
                     data-testid="cae-reclassify-result">
                  ✓ Procesadas: <b>{reclassifyResult.processed}</b> · actualizadas: <b>{reclassifyResult.updated}</b> · tickets creados: <b>{reclassifyResult.tickets_created}</b>
                  {reclassifyResult.errors?.length > 0 && (
                    <span className="text-status-escalated"> · errores: {reclassifyResult.errors.length}</span>
                  )}
                </div>
              )}
              <button onClick={applyToExisting}
                      disabled={reclassifying || preview.total_guias === 0}
                      className="mt-2 inline-flex items-center gap-1 text-xs rounded-md border border-mye-accent text-mye-accent px-2.5 py-1 hover:bg-mye-accent hover:text-white disabled:opacity-50"
                      data-testid="cae-reclassify-btn">
                {reclassifying ? "Aplicando…" : `Aplicar y crear tickets (${preview.total_guias})`}
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-mye-border bg-mye-app/40">
          <button onClick={onSaved} disabled={saving || reclassifying}
                  className="px-3 py-1.5 text-sm rounded-md border border-mye-border bg-white hover:bg-mye-app">
            Cerrar
          </button>
          <button onClick={save} disabled={saving || reclassifying}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-mye-accent text-white hover:brightness-110 disabled:opacity-60"
                  data-testid="cae-edit-save">
            <Save className="h-3.5 w-3.5" /> {saving ? "Guardando…" : "Guardar mapeo"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">{label}</span>
      {children}
    </label>
  );
}
