import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, LogOut, Webhook, FileSpreadsheet, RefreshCw, Copy, CheckCircle2,
  Upload, AlertTriangle, Eye, EyeOff, Download, Activity,
} from "lucide-react";
import { api, API } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";

const TABS = [
  { key: "webhook", label: "Webhook + HMAC", icon: Webhook },
  { key: "layout",  label: "Layout (CSV/XLSX)",   icon: FileSpreadsheet },
  { key: "pulling", label: "Pulling",        icon: RefreshCw },
  { key: "health",  label: "Health",         icon: Activity },
];

export default function AdminIngest() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("webhook");
  const [clients, setClients] = useState([]);
  const [clientId, setClientId] = useState("");

  useEffect(() => {
    api.get("/admin/clients").then((r) => {
      const list = r.data?.data?.items || [];
      setClients(list);
      if (list[0]) setClientId(list[0].id);
    });
  }, []);

  const current = useMemo(() => clients.find((c) => c.id === clientId), [clients, clientId]);

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-ingest-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Admin · Workflow de Ingesta</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <SaaSHierarchyBreadcrumb className="hidden md:inline-flex mr-2" />
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 04 · Workflow de Ingesta
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Tres maneras de meter eventos al sistema</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            Webhook firmado con HMAC SHA-256 · Pulling cron-driven · Layout CSV. Las guías terminales
            (entregadas o devueltas) <span className="text-mye-accent">nunca se sobrescriben</span> (R02).
          </p>
        </section>

        {clients.length === 0 ? (
          <div className="bg-white border border-mye-border rounded-lg p-8 text-center text-mye-ink-muted">
            No hay clientes registrados. Crea uno en
            <button onClick={() => navigate("/admin/jerarquia")}
                    className="ml-1 underline text-mye-accent hover:brightness-110">/admin/jerarquia</button>.
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-xs font-mono text-mye-ink-muted uppercase tracking-wider">Cliente:</span>
              <select className="rounded-md border border-mye-border bg-white px-3 py-2 text-sm outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 min-w-[260px]"
                      value={clientId} onChange={(e) => setClientId(e.target.value)}
                      data-testid="ingest-client-select">
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.name} · {c.ingest_mode}</option>
                ))}
              </select>
              {current && (
                <span className={"inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-mono " +
                  (current.ingest_mode === "webhook"
                    ? "border-status-active/40 bg-status-active/10 text-status-active"
                    : current.ingest_mode === "pulling"
                      ? "border-status-pending/40 bg-status-pending/10 text-status-pending"
                      : "border-status-waiting/40 bg-status-waiting/10 text-status-waiting")}>
                  modo: {current.ingest_mode}
                </span>
              )}
            </div>

            <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="ingest-tabs">
              {TABS.map((t) => {
                const Active = tab === t.key;
                const Icon = t.icon;
                return (
                  <button key={t.key} onClick={() => setTab(t.key)}
                          className={"inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-md transition-colors -mb-px " +
                            (Active ? "bg-white border border-mye-border border-b-white text-mye-ink"
                                    : "text-mye-ink-muted hover:text-mye-ink")}
                          data-testid={`ingest-tab-${t.key}`}>
                    <Icon className="h-3.5 w-3.5" /> {t.label}
                  </button>
                );
              })}
            </div>

            <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
              {tab === "webhook" && current && <WebhookPanel client={current} />}
              {tab === "layout"  && current && <LayoutPanel client={current} />}
              {tab === "pulling" && current && <PullingPanel client={current} />}
              {tab === "health"  && <IngestHealthPanel />}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

// ─── Webhook panel ────────────────────────────────────────────────────────
function WebhookPanel({ client }) {
  const [showToken, setShowToken] = useState(false);
  const [copied, setCopied] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const url = `${API}/guias/ingest/webhook?client_id=${client.id}`;
  const sample = JSON.stringify({
    tracking_id: "FX-001",
    carrier_code: "fedex",
    carrier_status: "IN_TRANSIT",
  });

  // Build a copy-pasteable curl example. We use $WEBHOOK_TOKEN so the user
  // can export the secret themselves rather than literally pasting it.
  const curlExample = [
    "TOKEN=\"" + (client.webhook_token || "<token>") + "\"",
    "BODY='" + sample + "'",
    "SIG=$(printf '%s' \"$BODY\" | openssl dgst -sha256 -hmac \"$TOKEN\" -hex | awk '{print $2}')",
    "",
    "curl -X POST '" + url + "' \\",
    "  -H \"Content-Type: application/json\" \\",
    "  -H \"X-MyE-Signature: $SIG\" \\",
    "  --data-raw \"$BODY\"",
  ].join("\n");

  async function copy(label, value) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      setTimeout(() => setCopied(null), 1500);
    } catch (_e) { /* ignore */ }
  }

  async function runTest() {
    if (!client.webhook_token) return;
    setTesting(true); setTestResult(null);
    try {
      // Compute HMAC in the browser using SubtleCrypto (no extra dep).
      const enc = new TextEncoder();
      const key = await crypto.subtle.importKey(
        "raw", enc.encode(client.webhook_token),
        { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
      );
      const sigBuf = await crypto.subtle.sign("HMAC", key, enc.encode(sample));
      const sig = Array.from(new Uint8Array(sigBuf)).map((b) => b.toString(16).padStart(2, "0")).join("");
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-MyE-Signature": sig },
        body: sample,
      });
      const json = await r.json();
      setTestResult({ ok: r.ok, status: r.status, json });
    } catch (e) { setTestResult({ ok: false, status: 0, json: { errors: [{ message: e.message }] } }); }
    finally { setTesting(false); }
  }

  return (
    <div className="p-6 space-y-6" data-testid="webhook-panel">
      {client.ingest_mode !== "webhook" && (
        <div className="flex items-start gap-2 rounded-md border border-status-waiting/30 bg-status-waiting/5 px-3 py-2 text-[13px] text-status-waiting">
          <AlertTriangle className="h-4 w-4 mt-0.5" />
          <span>Este cliente está configurado en modo <strong>{client.ingest_mode}</strong>. El webhook
          no funcionará hasta que cambies el cliente a <strong>webhook</strong>.</span>
        </div>
      )}

      <KeyValue label="Endpoint" value={url} onCopy={(v) => copy("url", v)} copied={copied === "url"} />
      <KeyValue label="Webhook token (R07 — único, no compartir)"
                value={client.webhook_token || "(no disponible)"}
                masked={!showToken}
                onToggleMask={() => setShowToken((v) => !v)}
                onCopy={(v) => copy("token", v)}
                copied={copied === "token"} />
      <KeyValue label="Header obligatorio" value="X-MyE-Signature: <hex HMAC-SHA256(body, token)>" />
      <KeyValue label="Content-Type" value="application/json" />

      <div>
        <div className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">curl listo para pegar</div>
        <pre className="bg-mye-sidebar text-white/90 rounded-md p-4 text-[12px] font-mono overflow-x-auto whitespace-pre">{curlExample}</pre>
        <button onClick={() => copy("curl", curlExample)}
                className="mt-2 inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                data-testid="webhook-copy-curl">
          <Copy className="h-3.5 w-3.5" /> {copied === "curl" ? "Copiado ✓" : "Copiar curl"}
        </button>
      </div>

      <div className="border-t border-mye-border pt-5 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="font-medium text-sm">Probar el endpoint ahora</div>
            <div className="text-xs text-mye-ink-muted">Genera la firma desde el navegador y dispara una guía de prueba.</div>
          </div>
          <button onClick={runTest} disabled={testing || !client.webhook_token}
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-50"
                  data-testid="webhook-test-button">
            {testing ? "Enviando…" : "Enviar prueba"}
          </button>
        </div>
        {testResult && (
          <div className={"rounded-md border p-3 text-xs font-mono whitespace-pre-wrap " +
            (testResult.ok
              ? "border-status-resolved/40 bg-status-resolved/5 text-status-resolved"
              : "border-status-escalated/40 bg-status-escalated/5 text-status-escalated")}
               data-testid="webhook-test-result">
            HTTP {testResult.status} · {JSON.stringify(testResult.json, null, 2)}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Layout panel ─────────────────────────────────────────────────────────
function LayoutPanel({ client }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setResult(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.post(`/admin/ingest/layout?client_id=${client.id}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(r.data?.data);
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  async function downloadTemplate() {
    try {
      // Endpoint protegido por RBAC; usamos el `api` axios para que adjunte el
      // bearer token automáticamente.
      const resp = await api.get("/admin/ingest/layout/template", {
        responseType: "blob",
      });
      const blob = new Blob([resp.data], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "myexcellence_layout_v2.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError("No se pudo descargar la plantilla.");
    }
  }

  return (
    <div className="p-6 space-y-6" data-testid="layout-panel">
      <div className="grid md:grid-cols-2 gap-3 text-sm">
        <div className="rounded-md border border-mye-border bg-mye-app/40 p-4">
          <div className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-2">Columnas requeridas</div>
          <ul className="space-y-1 font-mono text-[12px]">
            <li>· Tracking</li>
            <li>· Courier (ej: Fedex, DHL, 99 Minutos)</li>
            <li>· Status (ej: Entregado, En tránsito, Recolectado)</li>
          </ul>
        </div>
        <div className="rounded-md border border-mye-border bg-mye-app/40 p-4">
          <div className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-2">Plantilla v2 · 36 columnas</div>
          <ul className="space-y-1 font-mono text-[11px] text-mye-ink-muted">
            <li>· 3 fechas (creación, embarque, entrega) — formato dd/mm/yyyy</li>
            <li>· Remitente y Destinatario (persona, empresa, dirección, CP, tel, email)</li>
            <li>· Servicio, Pesos (real, vol., cobrado), Valor + Seguro Y/N</li>
            <li>· Notas, Incidencia y metadata (contenido, dimensiones, hecho por)</li>
          </ul>
        </div>
      </div>

      <button onClick={downloadTemplate}
              className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition"
              data-testid="layout-download-template">
        <Download className="h-3.5 w-3.5" /> Descargar plantilla v2 (CSV)
      </button>

      <form onSubmit={submit} className="space-y-3">
        <label className="block">
          <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">Archivo .csv o .xlsx (máx. 10 MB)</span>
          <input type="file" accept=".csv,.xlsx,.xlsm"
                 onChange={(e) => setFile(e.target.files?.[0] || null)}
                 className="block w-full text-sm text-mye-ink-muted file:mr-4 file:rounded-md file:border-0 file:bg-mye-primary-soft file:px-4 file:py-2 file:text-sm file:font-medium file:text-mye-primary hover:file:bg-mye-primary-soft/80"
                 data-testid="layout-file-input" />
        </label>
        {error && (
          <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated">{error}</div>
        )}
        <button type="submit" disabled={!file || busy}
                className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-4 py-2 text-sm hover:brightness-110 transition disabled:opacity-60"
                data-testid="layout-submit">
          <Upload className="h-3.5 w-3.5" /> {busy ? "Procesando…" : "Subir y procesar"}
        </button>
      </form>

      {result && (
        <div className="border border-mye-border rounded-md bg-white p-4 space-y-2" data-testid="layout-result">
          <div className="font-medium text-sm flex items-center gap-1">
            <CheckCircle2 className="h-4 w-4 text-status-resolved" /> Procesado
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs font-mono">
            {Object.entries(result.summary).map(([k, v]) => (
              <div key={k} className="rounded-md border border-mye-border px-2 py-1.5">
                <div className="text-[10px] text-mye-ink-muted uppercase tracking-wider">{k}</div>
                <div className="text-sm tabular-nums">{v}</div>
              </div>
            ))}
          </div>
          {result.errors?.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer font-mono text-status-escalated">{result.errors.length} líneas con error</summary>
              <pre className="mt-2 bg-mye-app rounded p-2 overflow-auto">{JSON.stringify(result.errors, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Pulling panel ───────────────────────────────────────────────────────
function PullingPanel({ client }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  // Iter56 — rango por defecto: hoy
  const today = new Date().toISOString().slice(0, 10);
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);

  async function triggerPing() {
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await api.post(`/admin/ingest/pull/${client.id}`);
      setResult(r.data?.data);
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  async function triggerRange() {
    if (!dateFrom || !dateTo) {
      setError("Selecciona fecha inicio y fin");
      return;
    }
    if (dateFrom > dateTo) {
      setError("La fecha de inicio debe ser anterior a la fecha de fin");
      return;
    }
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await api.post(`/admin/ingest/pull/${client.id}`, {
        date_from: dateFrom, date_to: dateTo,
      });
      setResult(r.data?.data);
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  function shortcut(days) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - days);
    setDateFrom(start.toISOString().slice(0, 10));
    setDateTo(end.toISOString().slice(0, 10));
  }

  return (
    <div className="p-6 space-y-6" data-testid="pulling-panel">
      <div className="flex items-start gap-2 rounded-md border border-status-pending/30 bg-status-pending/5 px-3 py-2 text-[13px] text-status-pending">
        <RefreshCw className="h-4 w-4 mt-0.5" />
        <span>El cron-driven pulling se ejecuta cada {client.pulling_freq_min ?? "—"}min.
        Aquí puedes disparar un pull manual (verificación de config) o cargar
        servicios de un rango específico para sincronizar histórico.</span>
      </div>

      <div className="grid md:grid-cols-2 gap-3 text-sm">
        <KvRow label="Modo configurado" value={client.ingest_mode} />
        <KvRow label="API URL" value={client.api_url || "—"} mono />
        <KvRow label="Frecuencia (min)" value={client.pulling_freq_min ?? "—"} />
        <KvRow label="Credenciales" value={client.api_creds_set ? "cifradas ✓" : "no configuradas"} />
      </div>

      {/* Iter56 — Cargar rango */}
      <div className="rounded-lg border border-mye-stroke bg-white p-4 space-y-3"
           data-testid="pull-range-panel">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-sm font-semibold">Cargar servicios por rango</h3>
          <div className="flex gap-1.5">
            <button type="button" onClick={() => shortcut(0)}
                    data-testid="range-shortcut-today"
                    className="text-[11px] px-2 py-1 rounded border border-mye-stroke hover:bg-mye-app">Hoy</button>
            <button type="button" onClick={() => shortcut(7)}
                    data-testid="range-shortcut-7d"
                    className="text-[11px] px-2 py-1 rounded border border-mye-stroke hover:bg-mye-app">7 días</button>
            <button type="button" onClick={() => shortcut(30)}
                    data-testid="range-shortcut-30d"
                    className="text-[11px] px-2 py-1 rounded border border-mye-stroke hover:bg-mye-app">30 días</button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs text-mye-ink-muted">Desde</span>
            <input type="date" value={dateFrom} max={dateTo || undefined}
                   onChange={(e) => setDateFrom(e.target.value)}
                   data-testid="range-date-from"
                   className="mt-1 w-full rounded-md border border-mye-stroke px-3 py-2 text-sm" />
          </label>
          <label className="block">
            <span className="text-xs text-mye-ink-muted">Hasta</span>
            <input type="date" value={dateTo} min={dateFrom || undefined}
                   max={today}
                   onChange={(e) => setDateTo(e.target.value)}
                   data-testid="range-date-to"
                   className="mt-1 w-full rounded-md border border-mye-stroke px-3 py-2 text-sm" />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={triggerRange} disabled={busy}
                  data-testid="pull-range-trigger"
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-4 py-2 text-sm hover:brightness-110 transition disabled:opacity-60">
            <RefreshCw className={"h-3.5 w-3.5 " + (busy ? "animate-spin" : "")} />
            {busy ? "Cargando…" : "Cargar rango"}
          </button>
          <button onClick={triggerPing} disabled={busy}
                  data-testid="pulling-trigger"
                  className="inline-flex items-center gap-1 rounded-md border border-mye-stroke text-mye-ink px-4 py-2 text-sm hover:bg-mye-app transition disabled:opacity-60">
            Probar config (ping)
          </button>
        </div>
        <p className="text-[11px] text-mye-ink-muted">
          El pull en rango lista los planes del carrier creados entre las fechas
          seleccionadas, recorre sus paradas e inserta/actualiza guías. Es
          idempotente: re-ejecutarlo no duplica datos.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
             data-testid="pull-error">{error}</div>
      )}
      {result && (
        <pre className="bg-mye-sidebar text-white/90 rounded-md p-4 text-[12px] font-mono overflow-x-auto" data-testid="pulling-result">
{JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}

// ─── Atoms ───────────────────────────────────────────────────────────────
function KeyValue({ label, value, onCopy, copied, masked, onToggleMask }) {
  const display = masked ? "•".repeat(Math.min(48, (value || "").length)) : (value || "");
  return (
    <div>
      <div className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">{label}</div>
      <div className="flex items-center gap-2 rounded-md border border-mye-border bg-mye-app/40 px-3 py-2">
        <code className="flex-1 text-[12px] font-mono break-all">{display}</code>
        {onToggleMask && (
          <button onClick={onToggleMask} className="text-mye-ink-muted hover:text-mye-ink transition" title="Mostrar/Ocultar">
            {masked ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          </button>
        )}
        {onCopy && (
          <button onClick={() => onCopy(value)}
                  className={"inline-flex items-center gap-1 text-xs " +
                    (copied ? "text-status-resolved" : "text-mye-ink-muted hover:text-mye-ink") + " transition"}>
            {copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copiado" : "Copiar"}
          </button>
        )}
      </div>
    </div>
  );
}

function KvRow({ label, value, mono }) {
  return (
    <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">{label}</div>
      <div className={"text-sm " + (mono ? "font-mono text-[12px]" : "")}>{value}</div>
    </div>
  );
}


// ─── IngestHealthPanel ───────────────────────────────────────────────────
function IngestHealthPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/admin/ingest/health");
      setData(r.data?.data);
    } catch (e) {
      setError(e?.response?.data?.errors?.[0]?.message || e.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  function freshness(iso) {
    if (!iso) return { label: "—", cls: "text-mye-ink-muted" };
    const ageH = (Date.now() - new Date(iso).getTime()) / 3600000;
    if (ageH < 1) return { label: "hace <1h", cls: "text-status-active" };
    if (ageH < 24) return { label: `hace ${ageH.toFixed(0)}h`, cls: "text-status-active" };
    if (ageH < 72) return { label: `hace ${(ageH/24).toFixed(0)}d`, cls: "text-status-waiting" };
    return { label: `hace ${(ageH/24).toFixed(0)}d`, cls: "text-status-escalated" };
  }

  function pct(part, total) {
    if (!total) return 0;
    return Math.round((part / total) * 100);
  }

  if (loading && !data) {
    return <div className="p-6 text-sm text-mye-ink-muted">Cargando health…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-status-escalated" data-testid="health-error">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="p-6 space-y-4" data-testid="ingest-health-panel">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Salud de ingesta por cliente</h3>
          <p className="text-xs text-mye-ink-muted mt-0.5">
            Resumen agregado de guías, distribución de status, tickets abiertos y frescura del último pull.
          </p>
        </div>
        <button onClick={load} disabled={loading}
                data-testid="health-refresh"
                className="text-xs px-3 py-1.5 rounded-md border border-mye-border hover:bg-mye-app">
          <RefreshCw className={"h-3 w-3 inline mr-1 " + (loading ? "animate-spin" : "")} /> Refrescar
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <KvRow label="Clientes" value={data.totals.clients} />
        <KvRow label="Con datos" value={`${data.totals.with_data} / ${data.totals.clients}`} />
        <KvRow label="Total guías" value={data.totals.total_guias.toLocaleString()} />
        <KvRow label="Tickets abiertos" value={data.totals.tickets_open} />
      </div>

      <div className="overflow-x-auto border border-mye-border rounded-md">
        <table className="w-full text-xs" data-testid="health-table">
          <thead className="bg-mye-app">
            <tr className="text-left text-mye-ink-muted uppercase tracking-wider text-[10px]">
              <th className="px-3 py-2">Cliente</th>
              <th className="px-3 py-2">Carrier</th>
              <th className="px-3 py-2 text-right">Guías</th>
              <th className="px-3 py-2">Entregadas</th>
              <th className="px-3 py-2">En tránsito</th>
              <th className="px-3 py-2">Devueltas</th>
              <th className="px-3 py-2">Excepción</th>
              <th className="px-3 py-2 text-right">Tickets</th>
              <th className="px-3 py-2">Último ingest</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((it) => {
              const sb = it.status_breakdown || {};
              const delivered = sb.delivered || 0;
              const inTransit = sb.in_transit || 0;
              const returned = sb.returned || 0;
              const exception = sb.exception || 0;
              const fresh = freshness(it.last_ingest_at);
              return (
                <tr key={it.client_id} className="border-t border-mye-border hover:bg-mye-app/40"
                    data-testid={`health-row-${it.client_id}`}>
                  <td className="px-3 py-2">
                    <div className="font-medium text-mye-ink">{it.client_name}</div>
                    <div className="text-[10px] font-mono text-mye-ink-muted">{it.ingest_mode}{it.pulling_freq_min ? ` · ${it.pulling_freq_min}min` : ""}</div>
                  </td>
                  <td className="px-3 py-2 font-mono">{it.carrier_code}</td>
                  <td className="px-3 py-2 text-right font-mono font-semibold">{it.total_guias.toLocaleString()}</td>
                  <td className="px-3 py-2">
                    <span className="text-status-active">{delivered}</span>{" "}
                    <span className="text-[10px] text-mye-ink-muted">({pct(delivered, it.total_guias)}%)</span>
                  </td>
                  <td className="px-3 py-2">
                    <span>{inTransit}</span>{" "}
                    <span className="text-[10px] text-mye-ink-muted">({pct(inTransit, it.total_guias)}%)</span>
                  </td>
                  <td className="px-3 py-2">
                    {returned > 0 ? (
                      <span className="text-status-waiting">{returned} <span className="text-[10px] text-mye-ink-muted">({pct(returned, it.total_guias)}%)</span></span>
                    ) : <span className="text-mye-ink-muted">0</span>}
                  </td>
                  <td className="px-3 py-2">
                    {exception > 0 ? (
                      <span className="text-status-escalated">{exception} <span className="text-[10px] text-mye-ink-muted">({pct(exception, it.total_guias)}%)</span></span>
                    ) : <span className="text-mye-ink-muted">0</span>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className={it.tickets_open > 0 ? "text-status-escalated font-semibold" : "text-mye-ink-muted"}>
                      {it.tickets_open} / {it.tickets_total}
                    </span>
                  </td>
                  <td className={"px-3 py-2 font-mono text-[11px] " + fresh.cls}>
                    {fresh.label}
                  </td>
                </tr>
              );
            })}
            {data.items.length === 0 && (
              <tr><td colSpan={9} className="px-3 py-6 text-center text-mye-ink-muted">No hay clientes registrados.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
