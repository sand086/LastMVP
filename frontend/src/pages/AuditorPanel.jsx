/**
 * AuditorPanel — PROMPT_27 · Vista read-only para `client_auditor`.
 *
 * Solo muestra auditoría externa de IA (CSV firmado HMAC SHA-256) +
 * log de invocaciones + dashboard de consumo. No permite mutaciones.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import {
  FileSignature, BarChart3, Eye, Download, LogOut, AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import { formatCurrencyMX } from "@/lib/formatFechaMX";

const TABS = [
  { key: "audit",       label: "Auditoría externa", icon: FileSignature, requires: ["client_auditor", "root_dev", "superadmin"] },
  { key: "log",         label: "Log de invocaciones", icon: Eye },
  { key: "consumption", label: "Consumo", icon: BarChart3 },
];

export default function AuditorPanel() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  // Bundle G · G-02 — client_viewer no puede ver la pestaña de export firmado.
  const visibleTabs = TABS.filter(t => !t.requires || t.requires.includes(user?.role));
  const [tab, setTab] = useState(visibleTabs[0]?.key || "log");

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="auditor-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Auditor externo · solo lectura</div>
            </div>
          </div>
          <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-mye-accent/40 bg-mye-accent/10 px-2.5 py-0.5 text-[11px] font-mono text-mye-accent">
            <ShieldCheck className="h-3 w-3" /> {user?.role || "external"}
          </span>
          <span className="text-xs font-mono text-mye-ink-muted hidden sm:inline">{user?.email}</span>
          <button
            onClick={async () => { await logout(); navigate("/login"); }}
            className="inline-flex items-center gap-1.5 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition-colors"
            data-testid="auditor-logout"
          >
            <LogOut className="h-3.5 w-3.5" /> Salir
          </button>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 27 · Auditor externo
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Auditoría de IA</h1>
          <p className="text-mye-ink-muted max-w-3xl">
            Verificación externa del log inmutable (R37) firmado con HMAC SHA-256.
            Acceso de solo lectura — el auditor no puede mutar configuración ni invocar IA.
          </p>
        </section>

        <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="auditor-tabs">
          {visibleTabs.map((t) => {
            const Icon = t.icon;
            const Active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={
                  "inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-md transition-colors -mb-px " +
                  (Active
                    ? "bg-white border border-mye-border border-b-white text-mye-ink"
                    : "text-mye-ink-muted hover:text-mye-ink")
                }
                data-testid={`auditor-tab-${t.key}`}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
          {tab === "audit" && <AuditExportPanel />}
          {tab === "log" && <InvocationLogPanel />}
          {tab === "consumption" && <ConsumptionViewPanel />}
        </div>
      </main>
    </div>
  );
}

// ═════ Tab 1 — Auditoría firmada ═════════════════════════════════════════
function AuditExportPanel() {
  const [filters, setFilters] = useState({
    date_from: "", date_to: "", status: "",
  });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

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
    setBusy(true); setErr(null);
    try {
      const token = localStorage.getItem("mye_access_token");
      const url = `${process.env.REACT_APP_BACKEND_URL}/api/admin/ai/audit/export.csv?${buildQuery()}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) { setErr(`HTTP ${res.status}`); return; }
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
    <div className="p-5 space-y-4" data-testid="auditor-audit-panel">
      <div className="rounded-md border border-mye-accent/30 bg-mye-accent/5 px-4 py-3 text-sm">
        <div className="font-medium mb-1 inline-flex items-center gap-1">
          <FileSignature className="h-3.5 w-3.5" />
          Verificación externa
        </div>
        <p className="text-xs text-mye-ink-muted leading-relaxed">
          El CSV se firma con HMAC SHA-256 sobre el body. Para verificarlo, recomputa{" "}
          <code className="bg-white px-1 rounded">sha256=hmac(AUDIT_SIGNING_SECRET, body)</code>{" "}
          y compara contra el header <code className="bg-white px-1 rounded">X-MyE-Audit-Signature</code>.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        <Field label="Desde">
          <input type="date" value={filters.date_from}
                 onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                 className={inputCls} data-testid="auditor-date-from" />
        </Field>
        <Field label="Hasta">
          <input type="date" value={filters.date_to}
                 onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                 className={inputCls} data-testid="auditor-date-to" />
        </Field>
        <Field label="Status">
          <select value={filters.status}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                  className={inputCls} data-testid="auditor-status">
            <option value="">Todos</option>
            <option value="success">success</option>
            <option value="cache_hit">cache_hit</option>
            <option value="capped">capped</option>
            <option value="error">error</option>
            <option value="provider_unavailable">provider_unavailable</option>
            <option value="opt_out_executed">opt_out_executed</option>
          </select>
        </Field>
      </div>

      <div className="flex items-center gap-2">
        <button onClick={loadPreview} disabled={busy}
                className={btnGhost + " inline-flex items-center gap-1.5 disabled:opacity-60"}
                data-testid="auditor-preview-btn">
          {busy ? "Calculando…" : "Vista previa"}
        </button>
        <button onClick={downloadCsv} disabled={busy}
                className="rounded-md bg-mye-accent text-white px-4 py-1.5 text-sm hover:brightness-110 transition inline-flex items-center gap-1.5 disabled:opacity-60"
                data-testid="auditor-download-btn">
          <Download className="h-3.5 w-3.5" /> Descargar CSV firmado
        </button>
      </div>

      {err && (
        <div className="flex items-start gap-2 rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-[13px] text-status-escalated">
          <AlertTriangle className="h-4 w-4 mt-0.5 flex-none" /> <span>{err}</span>
        </div>
      )}

      {preview && (
        <div className="rounded-md border border-mye-border bg-mye-app/40 p-4 space-y-3" data-testid="auditor-preview">
          <div className="grid md:grid-cols-3 gap-3 text-sm">
            <Stat label="Filas" value={preview.rows ?? 0} mono />
            <Stat label="Tamaño (bytes)" value={(preview.size_bytes ?? 0).toLocaleString()} />
            <Stat label="Generado" value={preview.exported_at?.slice(0, 19).replace("T", " ")} />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Firma HMAC SHA-256</div>
            <code className="block bg-white border border-mye-border rounded p-2 mt-1 text-[10px] font-mono break-all" data-testid="auditor-signature">
              {preview.signature}
            </code>
          </div>
          {preview.last_download_signature && (
            <div className="rounded border border-mye-accent/30 bg-mye-accent/5 p-2 text-[11px] font-mono" data-testid="auditor-last-download">
              Última descarga · {preview.last_download_rows} filas · firma {preview.last_download_signature.slice(0, 30)}…
            </div>
          )}
          <AttestPanel preview={preview} filters={filters} />
          <div>
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">Preview (primeras 5 filas)</div>
            <pre className="bg-white border border-mye-border rounded p-2 mt-1 text-[10px] overflow-x-auto whitespace-pre">
{preview.preview_csv || "—"}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

// ═════ Tab 2 — Log de invocaciones ═══════════════════════════════════════
function InvocationLogPanel() {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ status: "", feature_code: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function refresh() {
    setBusy(true); setErr(null);
    try {
      const p = new URLSearchParams({ limit: "200" });
      if (filters.status) p.append("status", filters.status);
      if (filters.feature_code) p.append("feature_code", filters.feature_code);
      const r = await api.get(`/admin/ai/invocation-log?${p.toString()}`);
      setItems(r.data?.data?.items || []);
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }
  useEffect(() => { refresh();   }, []);

  return (
    <div data-testid="auditor-log-panel">
      <div className="px-5 py-4 border-b border-mye-border flex flex-wrap items-end gap-3">
        <Field label="Status">
          <select value={filters.status}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                  className={inputCls} data-testid="auditor-log-status">
            <option value="">Todos</option>
            <option value="success">success</option>
            <option value="cache_hit">cache_hit</option>
            <option value="capped">capped</option>
            <option value="error">error</option>
            <option value="opt_out_executed">opt_out_executed</option>
          </select>
        </Field>
        <Field label="Feature code">
          <input value={filters.feature_code}
                 onChange={(e) => setFilters({ ...filters, feature_code: e.target.value })}
                 placeholder="classify_motivo"
                 className={inputCls} data-testid="auditor-log-feature" />
        </Field>
        <button onClick={refresh} disabled={busy}
                className={btnGhost + " text-xs disabled:opacity-60"}
                data-testid="auditor-log-refresh">
          {busy ? "Cargando…" : "Aplicar"}
        </button>
        <span className="ml-auto text-xs text-mye-ink-muted font-mono">
          {items.length} registros · cap 200
        </span>
      </div>

      {err && <div className="px-5 py-3 text-xs text-status-escalated">{err}</div>}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Fecha", "Feature", "Cliente", "Status", "Modelo", "Tokens in/out", "Costo USD", "Latencia"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !busy && (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">
                Sin registros que coincidan con el filtro.
              </td></tr>
            )}
            {items.map((row) => (
              <tr key={row.id} className="border-t border-mye-border" data-testid="auditor-log-row">
                <td className="px-4 py-2 font-mono text-[11px] text-mye-ink-muted">{row.created_at?.slice(0, 19).replace("T", " ")}</td>
                <td className="px-4 py-2 font-mono text-[12px]">{row.feature_code}</td>
                <td className="px-4 py-2 font-mono text-[11px] text-mye-ink-muted">{row.client_id?.slice(0, 8)}…</td>
                <td className="px-4 py-2"><StatusPill v={row.status} /></td>
                <td className="px-4 py-2 font-mono text-[11px]">{row.model || "—"}</td>
                <td className="px-4 py-2 font-mono text-[11px] tabular-nums">{row.input_tokens || 0} / {row.output_tokens || 0}</td>
                <td className="px-4 py-2 font-mono text-[11px] tabular-nums">{formatCurrencyMX(row.cost_usd, "USD")}</td>
                <td className="px-4 py-2 font-mono text-[11px] tabular-nums">{row.latency_ms ?? 0} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═════ Tab 3 — Consumo ════════════════════════════════════════════════════
function ConsumptionViewPanel() {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    api.get("/admin/ai/consumption").then((r) => {
      if (!alive) return;
      setItems(r.data?.data?.items || []);
    }).catch((e) => {
      if (alive) setErr(e.response?.data?.errors?.[0]?.message || e.message);
    }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, []);

  const totals = useMemo(() => {
    let usd = 0, calls = 0;
    items.forEach((it) => { usd += it.cost_usd_total || 0; calls += it.invocation_count || 0; });
    return { usd, calls };
  }, [items]);

  return (
    <div className="p-5 space-y-4" data-testid="auditor-consumption-panel">
      <div className="grid md:grid-cols-3 gap-4">
        <Stat label="Periodos" value={items.length} mono />
        <Stat label="Costo acumulado" value={formatCurrencyMX(totals.usd, "USD")} mono />
        <Stat label="Invocaciones acumuladas" value={totals.calls.toLocaleString()} mono />
      </div>

      {err && <div className="text-xs text-status-escalated">{err}</div>}

      <div className="overflow-x-auto rounded-md border border-mye-border">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Periodo (YYYY-MM)", "Cliente", "Invocaciones", "Tokens in", "Tokens out", "Costo USD"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!busy && items.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">Sin consumo registrado.</td></tr>
            )}
            {items.map((it) => (
              <tr key={`${it.client_id}-${it.year_month}`} className="border-t border-mye-border" data-testid="auditor-consumption-row">
                <td className="px-4 py-2 font-mono">{it.year_month}</td>
                <td className="px-4 py-2 font-mono text-[11px] text-mye-ink-muted">{it.client_id?.slice(0, 8)}…</td>
                <td className="px-4 py-2 font-mono tabular-nums">{(it.invocation_count || 0).toLocaleString()}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{(it.input_tokens_total || 0).toLocaleString()}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{(it.output_tokens_total || 0).toLocaleString()}</td>
                <td className="px-4 py-2 font-mono tabular-nums">{formatCurrencyMX(it.cost_usd_total, "USD")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═════ Atestación voluntaria del auditor (PROMPT 26 V2 backlog) ═════════
function AttestPanel({ preview, filters }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState(null);

  async function attest(e) {
    e.preventDefault();
    if (!comment.trim()) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.post("/admin/ai/audit/attest", {
        signature: preview.signature,
        rows: preview.rows,
        filters,
        comment: comment.trim(),
      });
      setDone(r.data?.data);
      setComment("");
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={attest} className="rounded-md border border-mye-accent/30 bg-white p-3 space-y-2"
          data-testid="auditor-attest-form">
      <div className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted">
        Atestación · "He revisado este lote"
      </div>
      <p className="text-[11px] text-mye-ink-muted">
        Firma una atestación voluntaria appendable al log de auditoría
        para evidencia legal de revisión por un auditor humano.
      </p>
      <textarea value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Comentario obligatorio (≤500 chars). Ej: 'Revisado completo, sin observaciones.'"
                className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-xs min-h-[60px] resize-y outline-none focus:border-mye-accent"
                maxLength={500}
                data-testid="auditor-attest-comment" />
      <div className="flex items-center gap-2">
        <button type="submit" disabled={busy || !comment.trim()}
                className="rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-50"
                data-testid="auditor-attest-submit">
          {busy ? "Firmando…" : "Firmar atestación"}
        </button>
        {done && (
          <span className="text-[10px] font-mono text-status-resolved"
                data-testid="auditor-attest-done">
            ✓ atestación {done.attestation_id?.slice(0, 8)}… registrada
          </span>
        )}
        {err && <span className="text-[10px] text-status-escalated">{err}</span>}
      </div>
    </form>
  );
}


// ═════ Atoms ══════════════════════════════════════════════════════════════
const inputCls =
  "w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors";
const btnGhost =
  "rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft transition";

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}

function Stat({ label, value, mono }) {
  return (
    <div className="rounded-md border border-mye-border bg-mye-app/40 px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">{label}</div>
      <div className={"text-2xl tabular-nums " + (mono ? "font-mono" : "")}>{value}</div>
    </div>
  );
}

function StatusPill({ v }) {
  const map = {
    success: "border-status-resolved/40 bg-status-resolved/10 text-status-resolved",
    cache_hit: "border-mye-accent/40 bg-mye-accent/10 text-mye-accent",
    capped: "border-status-waiting/40 bg-status-waiting/10 text-status-waiting",
    error: "border-status-escalated/40 bg-status-escalated/10 text-status-escalated",
    provider_unavailable: "border-status-escalated/40 bg-status-escalated/10 text-status-escalated",
    opt_out_executed: "border-mye-border text-mye-ink-muted",
  };
  return (
    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono " + (map[v] || "border-mye-border text-mye-ink-muted")}>
      {v || "—"}
    </span>
  );
}
