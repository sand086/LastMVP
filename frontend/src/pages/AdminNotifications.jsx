import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";
import {
  ArrowLeft, LogOut, Mail, MessageCircle, Send, CheckCircle2,
  AlertTriangle, Server, RefreshCw, Clock, Play,
} from "lucide-react";

export default function AdminNotifications() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [waPhone, setWaPhone] = useState("");
  const [waMsg, setWaMsg] = useState("Hola, te escribo por una incidencia con tu envío.");
  const [waUrl, setWaUrl] = useState("");
  const [waErr, setWaErr] = useState(null);
  const [cronStatus, setCronStatus] = useState(null);
  const [cronOutputs, setCronOutputs] = useState({});
  const [cronBusy, setCronBusy] = useState(null);
  // Bundle A · FIX-A3: whitelist + warning modal
  const [whitelistedDomains, setWhitelistedDomains] = useState([]);
  const [pendingExternal, setPendingExternal] = useState(null);

  async function loadConfig() {
    try {
      const r = await api.get("/admin/notifications/config");
      setConfig(r.data?.data);
    } catch (e) { /* ignore */ }
  }
  async function loadCron() {
    try {
      const r = await api.get("/admin/cron/status");
      setCronStatus(r.data?.data);
    } catch (e) { /* ignore */ }
  }
  async function loadWhitelist() {
    try {
      const r = await api.get("/admin/test-domains");
      const globals = r.data?.data?.global_domains || [];
      const tenantDomains = (r.data?.data?.tenant_domains || []).map((d) => d.domain);
      setWhitelistedDomains([...globals, ...tenantDomains].map((d) => d.toLowerCase()));
    } catch (e) {
      // Si falla, dejamos whitelist vacía; el backend reconfirmará y cualquier
      // envío a dominios desconocidos disparará el warning del frontend igualmente.
    }
  }
  useEffect(() => {
    loadConfig(); loadCron(); loadWhitelist();
    setTo(user?.email || "");
  }, [user]);

  async function runCron(job) {
    setCronBusy(job);
    try {
      const r = await api.post(`/admin/cron/run/${job}`);
      setCronOutputs((prev) => ({ ...prev, [job]: r.data?.data || null }));
    } catch (e) {
      setCronOutputs((prev) => ({
        ...prev,
        [job]: { error: e.response?.data?.errors?.[0]?.message || e.message },
      }));
    } finally { setCronBusy(null); }
  }

  async function sendTest(e) {
    e.preventDefault();
    setBusy(true); setResult(null);
    // Bundle A · FIX-A3: pre-check de dominio. Si parece externo,
    // pedir confirmación al usuario antes de enviar.
    const domain = (to || "").split("@").pop()?.trim().toLowerCase() || "";
    const isExternal = !isDomainWhitelisted(domain, whitelistedDomains);
    if (isExternal) {
      setPendingExternal({ to, domain });
      setBusy(false);
      return;
    }
    await actuallySend({ confirmedExternal: false });
  }

  async function actuallySend({ confirmedExternal }) {
    setBusy(true); setResult(null);
    try {
      const r = await api.post("/admin/notifications/test", {
        to: to || undefined,
        confirmed_external: !!confirmedExternal,
      });
      setResult(r.data?.data || null);
    } catch (e) {
      // Resend errors arrive as HTTP 502 con detalle en data.data.result.reason
      setResult(
        e.response?.data?.data
          || { result: { ok: false, reason: e.response?.data?.errors?.[0]?.message || e.message } },
      );
    } finally { setBusy(false); }
  }

  function buildWa(e) {
    e.preventDefault();
    setWaErr(null); setWaUrl("");
    try {
      const cleaned = waPhone.replace(/[\s\-\(\)\.]/g, "").replace(/^\+/, "");
      if (!/^[1-9]\d{6,14}$/.test(cleaned)) throw new Error("Formato E.164 inválido (ej. +5215551234567)");
      const url = `https://wa.me/${cleaned}?text=${encodeURIComponent(waMsg)}`;
      setWaUrl(url);
    } catch (err) {
      setWaErr(err.message);
    }
  }

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-notifications-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1100px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Notificaciones · PROMPT 11</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <SaaSHierarchyBreadcrumb className="hidden md:inline-flex mr-2" />
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1100px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 11 · Notificaciones
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Email + WhatsApp deeplink</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            El AutomationService dispara mensajes a los contactos ops del cliente cuando R03
            lo permite. Aquí puedes validar la integración con Resend y construir un
            deeplink de WhatsApp ad-hoc.
          </p>
        </section>

        <section className="bg-white border border-mye-border rounded-lg p-5 space-y-3" data-testid="notif-config">
          <div className="flex items-center gap-2 font-medium text-sm">
            <Server className="h-4 w-4 text-mye-accent" /> Configuración actual
          </div>
          {config ? (
            <div className="grid grid-cols-3 gap-3 text-xs">
              <Card label="Resend">
                {config.resend_configured ? (
                  <span className="inline-flex items-center gap-1 text-status-resolved">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Configurado
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-status-escalated">
                    <AlertTriangle className="h-3.5 w-3.5" /> Sin API key (modo mock)
                  </span>
                )}
              </Card>
              <Card label="Sender email">
                <span className="font-mono">{config.sender_email}</span>
              </Card>
              <Card label="Canales disponibles">
                <span className="font-mono">{config.channels_available?.join(" · ")}</span>
              </Card>
            </div>
          ) : (
            <div className="text-xs text-mye-ink-muted font-mono">Cargando…</div>
          )}
          <button onClick={loadConfig}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="notif-reload-config">
            <RefreshCw className="h-3.5 w-3.5" /> Recargar
          </button>
        </section>

        <section className="bg-white border border-mye-border rounded-lg p-5 space-y-4" data-testid="cron-card">
          <div className="flex items-center gap-2 font-medium text-sm">
            <Clock className="h-4 w-4 text-mye-accent" /> Cron jobs (PROMPT 11.5)
          </div>
          {cronStatus ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-xs">
                <span className={"inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-mono " +
                  (cronStatus.running
                    ? "bg-status-resolved/10 text-status-resolved border border-status-resolved/30"
                    : "bg-status-escalated/10 text-status-escalated border border-status-escalated/30")}>
                  {cronStatus.running
                    ? <CheckCircle2 className="h-3.5 w-3.5" />
                    : <AlertTriangle className="h-3.5 w-3.5" />}
                  {cronStatus.running ? "running" : "stopped"}
                </span>
                <span className="text-mye-ink-muted">
                  CRON_ENABLED={String(cronStatus.enabled_env)}
                </span>
                <button onClick={loadCron}
                        className="ml-auto inline-flex items-center gap-1 rounded-md border border-mye-border px-2 py-1 text-xs hover:bg-mye-primary-soft transition"
                        data-testid="cron-reload">
                  <RefreshCw className="h-3.5 w-3.5" /> Recargar
                </button>
              </div>
              <table className="w-full text-xs">
                <thead className="text-left">
                  <tr className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
                    <th className="py-1.5">Job</th>
                    <th className="py-1.5">Trigger</th>
                    <th className="py-1.5">Próxima ejecución</th>
                    <th className="py-1.5 text-right">Forzar</th>
                  </tr>
                </thead>
                <tbody>
                  {(["sla", "inactivity", "pulling", "daily_summary"]).map((job) => {
                    const j = (cronStatus.jobs || []).find((x) => x.id === `${job}_scan`)
                            || (cronStatus.jobs || []).find((x) => x.id === job);
                    return (
                      <tr key={job} className="border-t border-mye-border" data-testid={`cron-row-${job}`}>
                        <td className="py-2 font-mono">{job}</td>
                        <td className="py-2 font-mono text-mye-ink-muted">{j?.trigger || "—"}</td>
                        <td className="py-2 font-mono text-mye-ink-muted">{j?.next_run_time || "—"}</td>
                        <td className="py-2 text-right">
                          <button onClick={() => runCron(job)} disabled={cronBusy === job}
                                  data-testid={`cron-run-${job}`}
                                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-2 py-1 text-xs hover:opacity-90 transition disabled:opacity-50">
                            <Play className="h-3 w-3" /> {cronBusy === job ? "…" : "Ejecutar"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {Object.keys(cronOutputs).length > 0 && (
                <div className="space-y-2 pt-2 border-t border-mye-border">
                  <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
                    Última ejecución manual
                  </div>
                  {Object.entries(cronOutputs).map(([job, out]) => (
                    <pre key={job}
                         data-testid={`cron-output-${job}`}
                         className="bg-mye-app rounded px-2 py-1 text-[11px] font-mono text-mye-ink-muted overflow-x-auto">
{`[${job}] ${JSON.stringify(out, null, 2)}`}
                    </pre>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-mye-ink-muted font-mono">Cargando…</div>
          )}
        </section>

        <div className="grid lg:grid-cols-2 gap-6">
          <section className="bg-white border border-mye-border rounded-lg p-5 space-y-4" data-testid="notif-email-card">
            <div className="flex items-center gap-2 font-medium text-sm">
              <Mail className="h-4 w-4 text-mye-accent" /> Email de prueba (Resend)
            </div>
            <p className="text-xs text-mye-ink-muted">
              En modo testing, Resend solo permite enviar al email del owner de la cuenta.
              Para envíos a cualquier destinatario, verifica un dominio en Resend y cambia
              <span className="font-mono"> SENDER_EMAIL</span> en .env.
            </p>
            <form onSubmit={sendTest} className="space-y-3">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                  Para
                </label>
                <input type="email" value={to} onChange={(e) => setTo(e.target.value)}
                       placeholder="ops@cliente.test"
                       data-testid="notif-test-to"
                       className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono" />
              </div>
              <button type="submit" disabled={busy}
                      data-testid="notif-test-submit"
                      className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-50">
                <Send className="h-3.5 w-3.5" /> {busy ? "Enviando…" : "Enviar email de prueba"}
              </button>
            </form>
            {result && (
              <div data-testid="notif-test-result"
                   className={"rounded-md border px-3 py-2 text-xs " +
                     (result.result?.ok
                       ? "border-status-resolved/40 bg-status-resolved/5 text-status-resolved"
                       : "border-status-escalated/40 bg-status-escalated/5 text-status-escalated")}>
                {result.result?.ok ? (
                  <>
                    <div className="font-medium mb-1">Email enviado a {result.to}</div>
                    <div className="font-mono text-[11px]">id: {result.result.id}</div>
                    {result.result.mock && (
                      <div className="font-mono text-[11px] mt-1">⚠️ MOCK (sin API key)</div>
                    )}
                  </>
                ) : (
                  <div>{result.result?.reason || "Error desconocido"}</div>
                )}
              </div>
            )}
          </section>

          <section className="bg-white border border-mye-border rounded-lg p-5 space-y-4" data-testid="notif-wa-card">
            <div className="flex items-center gap-2 font-medium text-sm">
              <MessageCircle className="h-4 w-4 text-mye-accent" /> Constructor de deeplink WhatsApp
            </div>
            <p className="text-xs text-mye-ink-muted">
              El deeplink abre WhatsApp del cliente con el mensaje pre-redactado. Sin API
              externa — sólo URL. La integración con WhatsApp Business API (Twilio) llega
              en PROMPT 20.
            </p>
            <form onSubmit={buildWa} className="space-y-3">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                  Teléfono (E.164)
                </label>
                <input value={waPhone} onChange={(e) => setWaPhone(e.target.value)}
                       placeholder="+52 155 5123 4567"
                       data-testid="notif-wa-phone"
                       className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono" />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                  Mensaje
                </label>
                <textarea value={waMsg} onChange={(e) => setWaMsg(e.target.value)} rows={3}
                          data-testid="notif-wa-msg"
                          className="w-full rounded-md border border-mye-border px-3 py-2 text-sm" />
              </div>
              <button type="submit"
                      data-testid="notif-wa-submit"
                      className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition">
                Generar deeplink
              </button>
            </form>
            {waErr && (
              <div className="rounded-md border border-status-escalated/40 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
                   data-testid="notif-wa-err">
                {waErr}
              </div>
            )}
            {waUrl && (
              <div className="rounded-md border border-mye-border bg-mye-app/40 p-3 space-y-2"
                   data-testid="notif-wa-url">
                <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">URL</div>
                <code className="block break-all text-[11px] font-mono">{waUrl}</code>
                <a href={waUrl} target="_blank" rel="noreferrer"
                   className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition"
                   data-testid="notif-wa-open">
                  Abrir en WhatsApp
                </a>
              </div>
            )}
          </section>
        </div>

        <EmailTemplatesSection />
      </main>
      {pendingExternal && (
        <ExternalDomainWarningDialog
          to={pendingExternal.to}
          domain={pendingExternal.domain}
          onCancel={() => setPendingExternal(null)}
          onConfirm={async () => {
            const target = pendingExternal;
            setPendingExternal(null);
            await actuallySend({ confirmedExternal: true });
            // Re-render result inline ya lo hace actuallySend.
            void target;
          }}
        />
      )}
    </div>
  );
}


// Bundle A · FIX-A3 — Helpers compartidos
function isDomainWhitelisted(domain, list) {
  if (!domain) return false;
  return list.includes(domain.toLowerCase());
}


// Bundle A · FIX-A3 — Modal warning con anti-click-reflejo (1s hover).
function ExternalDomainWarningDialog({ to, domain, onCancel, onConfirm }) {
  const [hoverReady, setHoverReady] = useState(false);
  const hoverTimerRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    };
  }, [onCancel]);

  function startHover() {
    if (hoverReady) return;
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setHoverReady(true);
      hoverTimerRef.current = null;
    }, 1000);
  }
  function cancelHover() {
    if (hoverReady) return;  // ya quedó habilitado, no cancelar
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm"
      data-testid="notif-external-warning-overlay"
    >
      <div
        className="w-[min(480px,92vw)] rounded-lg bg-white shadow-xl border border-mye-border p-5"
        data-testid="notif-external-warning-dialog"
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-status-escalated mt-0.5 shrink-0" />
          <div className="flex-1">
            <h2 className="text-base font-semibold text-mye-ink">
              Atención — destinatario externo
            </h2>
            <p className="text-sm text-mye-ink-muted mt-1.5 leading-relaxed">
              Estás por enviar un mensaje de prueba a{" "}
              <span className="font-mono text-mye-ink">{to}</span> (dominio{" "}
              <span className="font-mono">{domain}</span>).
            </p>
            <p className="text-sm text-mye-ink-muted mt-2 leading-relaxed">
              Si es un email de cliente real, el mensaje contendrá placeholders{" "}
              <code className="font-mono text-[11px] bg-mye-app/50 px-1 rounded">{"{{nombre}}"}</code>{" "}
              y{" "}
              <code className="font-mono text-[11px] bg-mye-app/50 px-1 rounded">{"{{guia}}"}</code>{" "}
              sin reemplazar.
            </p>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 mt-5">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft"
            data-testid="notif-external-cancel"
          >
            Cancelar (Esc)
          </button>
          <button
            type="button"
            onMouseEnter={startHover}
            onMouseLeave={cancelHover}
            onFocus={startHover}
            onBlur={cancelHover}
            aria-disabled={!hoverReady}
            onClick={(e) => {
              if (!hoverReady) {
                e.preventDefault();
                // Iniciar hover programáticamente cuando el usuario hace
                // tap rápido (importante para móviles donde no hay hover).
                startHover();
                return;
              }
              onConfirm();
            }}
            className={
              "rounded-md px-3 py-1.5 text-sm transition " +
              (hoverReady
                ? "bg-status-escalated text-white hover:brightness-110"
                : "bg-status-escalated/50 text-white/80 cursor-not-allowed")
            }
            title={hoverReady ? "" : "Mantén el cursor 1 segundo sobre el botón para habilitarlo"}
            data-testid="notif-external-confirm"
          >
            {hoverReady ? "Enviar de todas formas" : "Mantén hover 1s para habilitar…"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EmailTemplatesSection() {
  const [data, setData] = useState({ items: [], supported_keys: [], variables: {} });
  const [loading, setLoading] = useState(true);
  const [activeKey, setActiveKey] = useState("incident_notice");
  const [form, setForm] = useState({ subject: "", html_body: "", text_body: "" });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get("/admin/email-templates");
      setData(r.data?.data || { items: [], supported_keys: [], variables: {} });
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  // Cargar form desde override existente cuando cambia activeKey
  useEffect(() => {
    const existing = (data.items || []).find((t) => t.key === activeKey);
    if (existing) {
      setForm({
        subject: existing.subject,
        html_body: existing.html_body,
        text_body: existing.text_body || "",
      });
    } else {
      setForm({ subject: "", html_body: "", text_body: "" });
    }
    setPreview(null); setMsg(null);
  }, [activeKey, data.items]);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      await api.put("/admin/email-templates", { key: activeKey, ...form });
      setMsg("Plantilla guardada · usará override en próximos envíos.");
      await load();
    } catch (e) {
      setMsg(`Error: ${e.response?.data?.errors?.[0]?.message || e.message}`);
    } finally { setBusy(false); }
  }
  async function remove() {
    if (!window.confirm("¿Eliminar override? Volverá a usar la plantilla por defecto.")) return;
    setBusy(true); setMsg(null);
    try {
      await api.delete(`/admin/email-templates/${activeKey}`);
      setMsg("Override eliminado · vuelve al default.");
      await load();
    } catch (e) {
      setMsg(`Error: ${e.response?.data?.errors?.[0]?.message || e.message}`);
    } finally { setBusy(false); }
  }
  async function doPreview() {
    setBusy(true); setMsg(null);
    try {
      const r = await api.post("/admin/email-templates/preview", form);
      setPreview(r.data?.data);
    } catch (e) {
      setMsg(`Error: ${e.response?.data?.errors?.[0]?.message || e.message}`);
    } finally { setBusy(false); }
  }

  const vars = data.variables?.[activeKey] || [];
  const hasOverride = (data.items || []).some((t) => t.key === activeKey);

  return (
    <section className="bg-white border border-mye-border rounded-lg p-5 space-y-4 mt-6"
             data-testid="notif-templates-card">
      <div className="flex items-center gap-2 font-medium text-sm">
        <Mail className="h-4 w-4 text-mye-accent" /> Plantillas de email del tenant
        <span className="ml-auto text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
          Sustitución <code className="font-mono">{"{{var}}"}</code>
        </span>
      </div>
      <p className="text-xs text-mye-ink-muted">
        Sobreescribe los emails enviados por MyExcellence a los CxC de tus clientes. Si no
        configuras una plantilla, se usará la por defecto del sistema.
      </p>

      {loading ? (
        <div className="text-xs text-mye-ink-muted font-mono">Cargando…</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 border-b border-mye-border pb-3">
            {(data.supported_keys || []).map((k) => {
              const has = (data.items || []).some((t) => t.key === k);
              return (
                <button key={k} onClick={() => setActiveKey(k)}
                        data-testid={`notif-template-tab-${k}`}
                        className={"px-3 py-1.5 rounded-md text-xs font-mono transition border " +
                          (activeKey === k
                            ? "bg-mye-accent text-white border-mye-accent"
                            : "bg-white text-mye-ink-muted hover:bg-mye-primary-soft border-mye-border")}>
                  {k} {has && <span className="ml-1">●</span>}
                </button>
              );
            })}
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                  Subject
                </label>
                <input value={form.subject}
                       onChange={(e) => setForm({ ...form, subject: e.target.value })}
                       placeholder="[MyExcellence] Incidencia en envío {{tracking_id}}"
                       className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
                       data-testid="notif-template-subject" />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                  HTML body
                </label>
                <textarea value={form.html_body}
                          onChange={(e) => setForm({ ...form, html_body: e.target.value })}
                          rows={10}
                          placeholder="<p>Hola {{recipient_name}}…</p>"
                          className="w-full rounded-md border border-mye-border px-3 py-2 text-xs font-mono"
                          data-testid="notif-template-html" />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
                  Texto plano (fallback)
                </label>
                <textarea value={form.text_body}
                          onChange={(e) => setForm({ ...form, text_body: e.target.value })}
                          rows={4}
                          placeholder="Hola {{recipient_name}}…"
                          className="w-full rounded-md border border-mye-border px-3 py-2 text-xs font-mono"
                          data-testid="notif-template-text" />
              </div>
              <div className="flex items-center gap-2">
                <button onClick={save} disabled={busy || !form.subject || !form.html_body}
                        className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-60"
                        data-testid="notif-template-save">
                  <CheckCircle2 className="h-3.5 w-3.5" /> Guardar override
                </button>
                <button onClick={doPreview} disabled={busy}
                        className="inline-flex items-center gap-1.5 rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition disabled:opacity-60"
                        data-testid="notif-template-preview">
                  <Play className="h-3.5 w-3.5" /> Preview
                </button>
                {hasOverride && (
                  <button onClick={remove} disabled={busy}
                          className="inline-flex items-center gap-1.5 rounded-md border border-status-escalated/40 bg-status-escalated/5 text-status-escalated px-3 py-2 text-xs hover:bg-status-escalated/10 transition disabled:opacity-60"
                          data-testid="notif-template-delete">
                    Restablecer default
                  </button>
                )}
              </div>
              {msg && (
                <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-2 text-xs font-mono"
                     data-testid="notif-template-msg">{msg}</div>
              )}
            </div>

            <div className="space-y-3">
              <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1.5">
                  Variables disponibles
                </div>
                <div className="flex flex-wrap gap-1">
                  {vars.map((v) => (
                    <code key={v} onClick={() => navigator.clipboard?.writeText(`{{${v}}}`)}
                          className="px-1.5 py-0.5 rounded bg-white border border-mye-border text-[11px] font-mono cursor-pointer hover:bg-mye-primary-soft transition"
                          title="Click para copiar"
                          data-testid={`notif-template-var-${v}`}>
                      {"{{"}{v}{"}}"}
                    </code>
                  ))}
                </div>
              </div>
              {preview && (
                <div className="rounded-md border border-mye-border bg-white p-3 space-y-2"
                     data-testid="notif-template-preview-pane">
                  <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
                    Preview con datos demo
                  </div>
                  <div className="rounded border border-mye-border bg-mye-app/40 px-2 py-1.5 text-[11px] font-mono">
                    <strong>Subject:</strong> {preview.subject}
                  </div>
                  <div className="rounded border border-mye-border overflow-auto max-h-80"
                       dangerouslySetInnerHTML={{ __html: preview.html }} />
                  {preview.text && (
                    <pre className="rounded border border-mye-border bg-mye-app/40 px-2 py-1.5 text-[11px] whitespace-pre-wrap max-h-32 overflow-auto">{preview.text}</pre>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Card({ label, children }) {
  return (
    <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}
