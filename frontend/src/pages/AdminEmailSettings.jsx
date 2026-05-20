/**
 * AdminEmailSettings — multi-buzón (FASE 2).
 *
 * 4 tabs: Dominios · Buzones · Ruteo · Salud
 * Reemplaza el panel mono-buzón anterior; los datos legacy ya están migrados
 * por `migrate_all_tenants()`.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Mail, Globe, Inbox, Route as RouteIcon, Activity,
  Plus, Trash2, ShieldCheck, ShieldAlert, Send, Copy, RefreshCw,
  CheckCircle2, AlertTriangle, Eye, EyeOff, ExternalLink, X, Wand2,
} from "lucide-react";

import { api } from "@/lib/api";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";

const WORKFLOWS = [
  { id: "ticket_notification", label: "Notificación de ticket" },
  { id: "claim_communication", label: "Comunicación de reclamo" },
  { id: "sla_alert", label: "Alerta SLA" },
  { id: "admin_notification", label: "Notificación admin" },
  { id: "generic", label: "Genérico (catch-all)" },
];
const TABS = [
  { id: "domains", label: "Dominios", icon: Globe },
  { id: "mailboxes", label: "Buzones", icon: Inbox },
  { id: "routing", label: "Ruteo", icon: RouteIcon },
  { id: "health", label: "Salud", icon: Activity },
];

export default function AdminEmailSettings() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("domains");
  return (
    <div className="min-h-screen bg-mye-app">
      <div className="max-w-5xl mx-auto p-6 space-y-4">
        <SaaSHierarchyBreadcrumb />
        <header className="flex items-center gap-3">
          <div className="rounded-lg bg-mye-accent/10 p-2"><Mail className="h-5 w-5 text-mye-accent" /></div>
          <div>
            <h1 className="text-xl font-semibold">Credenciales de correo</h1>
            <p className="text-sm text-mye-ink-muted">
              Multi-buzón: configura dominios verificados, buzones por cliente
              y reglas de ruteo. Único punto de salida (BP-06).
            </p>
          </div>
        </header>
        <div className="flex gap-1 border-b border-mye-border" data-testid="email-tabs">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                      className={"inline-flex items-center gap-1.5 px-3 py-2 text-xs border-b-2 -mb-px " +
                        (active ? "border-mye-accent text-mye-ink"
                                : "border-transparent text-mye-ink-muted hover:text-mye-ink")}
                      data-testid={`email-tab-${t.id}`}>
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>
        {tab === "domains" && <DomainsTab />}
        {tab === "mailboxes" && <MailboxesTab />}
        {tab === "routing" && <RoutingTab />}
        {tab === "health" && <HealthTab />}
        <button onClick={() => navigate("/dashboard")}
                className="text-xs text-mye-ink-muted hover:text-mye-accent">← Dashboard</button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// DOMAINS TAB
// ─────────────────────────────────────────────────────────────────────────
function DomainsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [adding, setAdding] = useState("");
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get("/admin/email/domains");
      setItems(r.data?.data?.items || []);
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function createDomain() {
    if (!adding.trim()) return;
    setBusy(true);
    try {
      await api.post("/admin/email/domains", { domain: adding.trim().toLowerCase() });
      toast.success("Dominio agregado. Configura los registros DNS y luego verifica.");
      setAdding(""); setShowAdd(false); load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }
  async function verifyDomain(id) {
    try {
      await api.post(`/admin/email/domains/${id}/verify`);
      toast.success("Dominio marcado como verificado");
      load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  async function removeDomain(id) {
    if (!window.confirm("¿Eliminar este dominio? Los buzones asociados deben quedar libres primero.")) return;
    try {
      await api.delete(`/admin/email/domains/${id}`);
      toast.success("Dominio eliminado");
      load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }

  return (
    <section className="bg-white border border-mye-border rounded-lg p-4 space-y-3" data-testid="tab-domains">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Dominios verificados ({items.length})</h2>
        <button onClick={load} className="text-mye-ink-muted hover:text-mye-accent" data-testid="domains-refresh">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => setShowAdd(true)}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110"
                data-testid="domains-add">
          <Plus className="h-3 w-3" /> Agregar dominio
        </button>
      </div>
      {showAdd && (
        <div className="rounded-md border border-mye-accent/30 bg-mye-primary-soft/30 p-3 flex items-center gap-2"
             data-testid="domains-add-form">
          <input value={adding} onChange={(e) => setAdding(e.target.value)}
                 placeholder="mail.tudominio.com"
                 className="flex-1 rounded-md border border-mye-border px-3 py-1.5 text-sm font-mono" />
          <button onClick={createDomain} disabled={busy} data-testid="domains-add-submit"
                  className="rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs">
            {busy ? "Creando…" : "Crear"}
          </button>
          <button onClick={() => { setShowAdd(false); setAdding(""); }}
                  className="text-mye-ink-muted">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {loading ? <div className="text-sm text-mye-ink-muted">Cargando…</div>
        : items.length === 0 ? (
          <div className="text-sm text-mye-ink-muted italic">
            Sin dominios. Agrega el primero para empezar.
          </div>
        ) : (
          <ul className="space-y-2">
            {items.map((d) => (
              <li key={d.id} className="rounded-md border border-mye-border" data-testid={`domain-${d.domain}`}>
                <div className="flex items-center gap-2 p-3">
                  {d.verification_status === "verified" && !d.degraded
                    ? <CheckCircle2 className="h-4 w-4 text-status-resolved" />
                    : <ShieldAlert className="h-4 w-4 text-status-pending" />}
                  <span className="font-mono text-sm flex-1">{d.domain}</span>
                  <StatusPill status={d.verification_status} degraded={d.degraded} />
                  {d.verification_status !== "verified" && (
                    <button onClick={() => verifyDomain(d.id)}
                            className="text-xs text-mye-accent hover:underline"
                            data-testid={`domain-verify-${d.domain}`}>
                      Verificar
                    </button>
                  )}
                  <button onClick={() => setExpanded(expanded === d.id ? null : d.id)}
                          className="text-xs text-mye-ink-muted hover:text-mye-accent">
                    {expanded === d.id ? "Ocultar DNS" : "Ver DNS"}
                  </button>
                  <button onClick={() => removeDomain(d.id)} className="text-mye-ink-muted hover:text-status-escalated">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {expanded === d.id && (
                  <div className="bg-mye-app/40 border-t border-mye-border p-3 space-y-2">
                    <p className="text-[11px] text-mye-ink-muted">
                      Agrega estos registros DNS en tu proveedor (CloudFlare, GoDaddy, etc.) y luego clic en "Verificar".
                    </p>
                    {(d.dns_records || []).map((rec, i) => (
                      <div key={i} className="rounded-md border border-mye-border bg-white p-2 text-[11px] font-mono"
                           data-testid={`domain-dns-${i}`}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="rounded bg-mye-primary-soft px-1.5 py-0.5 text-[10px]">{rec.type}</span>
                          <span className="font-medium">{rec.name}</span>
                          {rec.priority && <span className="text-mye-ink-muted">priority {rec.priority}</span>}
                          <span className="ml-auto text-[10px] text-mye-ink-muted">{rec.purpose}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <code className="flex-1 truncate text-mye-ink-muted">{rec.value}</code>
                          <button onClick={() => navigator.clipboard.writeText(rec.value).then(() => toast.success("Copiado"))}
                                  className="text-mye-accent">
                            <Copy className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
    </section>
  );
}

function StatusPill({ status, degraded }) {
  const map = {
    verified: { color: "bg-status-resolved/10 text-status-resolved", text: degraded ? "verified · degraded" : "verified" },
    pending: { color: "bg-status-pending/10 text-status-pending", text: "pending" },
    failed: { color: "bg-status-escalated/10 text-status-escalated", text: "failed" },
  };
  const m = map[status] || map.pending;
  return <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${m.color}`}>{m.text}</span>;
}

// ─────────────────────────────────────────────────────────────────────────
// MAILBOXES TAB
// ─────────────────────────────────────────────────────────────────────────
function MailboxesTab() {
  const [items, setItems] = useState([]);
  const [domains, setDomains] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [testFor, setTestFor] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [mb, dom, cl] = await Promise.all([
        api.get("/admin/email/mailboxes"),
        api.get("/admin/email/domains"),
        api.get("/admin/hierarchy/clients?limit=100").catch(() => ({ data: { data: { items: [] } } })),
      ]);
      setItems(mb.data?.data?.items || []);
      setDomains(dom.data?.data?.items || []);
      setClients(cl.data?.data?.items || []);
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function toggleActive(mb) {
    try {
      await api.patch(`/admin/email/mailboxes/${mb.id}`, { is_active: !mb.is_active });
      load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  async function remove(mb) {
    if (!window.confirm(`Eliminar buzón "${mb.display_name}"?`)) return;
    try {
      await api.delete(`/admin/email/mailboxes/${mb.id}`);
      toast.success("Buzón eliminado"); load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  const verifiedDomains = useMemo(
    () => domains.filter((d) => d.verification_status === "verified"), [domains]);

  return (
    <section className="bg-white border border-mye-border rounded-lg p-4 space-y-3" data-testid="tab-mailboxes">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Buzones ({items.length})</h2>
        <button onClick={() => setShowWizard(true)}
                disabled={verifiedDomains.length === 0}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 disabled:opacity-50"
                data-testid="mailboxes-add"
                title={verifiedDomains.length === 0 ? "Verifica un dominio primero" : ""}>
          <Wand2 className="h-3 w-3" /> Nuevo buzón
        </button>
      </div>
      {verifiedDomains.length === 0 && (
        <div className="text-xs text-status-pending bg-status-pending/10 rounded-md px-3 py-2 inline-flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5" /> Verifica al menos un dominio para crear buzones.
        </div>
      )}
      {showWizard && (
        <MailboxWizard domains={verifiedDomains} clients={clients}
                       onClose={() => setShowWizard(false)}
                       onCreated={() => { setShowWizard(false); load(); }} />
      )}
      {loading ? <div className="text-sm text-mye-ink-muted">Cargando…</div>
        : items.length === 0 ? (
          <div className="text-sm text-mye-ink-muted italic">Sin buzones. Crea el primero.</div>
        ) : (
          <ul className="space-y-2">
            {items.map((mb) => (
              <li key={mb.id} className="rounded-md border border-mye-border p-3 flex items-center gap-3"
                  data-testid={`mailbox-${mb.id}`}>
                <Inbox className={"h-4 w-4 " + (mb.is_active ? "text-mye-accent" : "text-mye-ink-muted")} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">
                    {mb.display_name}
                    {mb.is_default_for_tenant && <span className="ml-2 rounded-full bg-mye-primary-soft px-2 py-0.5 text-[10px] font-mono">default tenant</span>}
                    {mb.is_default_for_client && <span className="ml-2 rounded-full bg-mye-primary-soft px-2 py-0.5 text-[10px] font-mono">default client</span>}
                    {!mb.is_active && <span className="ml-2 rounded-full bg-status-pending/10 text-status-pending px-2 py-0.5 text-[10px] font-mono">inactivo</span>}
                  </div>
                  <div className="text-[11px] font-mono text-mye-ink-muted truncate">
                    {mb.sender_name} &lt;{mb.sender_email}&gt;
                    {mb.api_key_last4 && <span className="ml-2">· key ****{mb.api_key_last4}</span>}
                    {mb.daily_send_limit && <span className="ml-2">· cuota {mb.daily_send_limit}/día</span>}
                  </div>
                </div>
                <button onClick={() => setTestFor(mb)}
                        className="text-xs text-mye-accent hover:underline" data-testid={`mailbox-test-${mb.id}`}>
                  Probar
                </button>
                <button onClick={() => toggleActive(mb)}
                        className="text-xs text-mye-ink-muted hover:text-mye-accent"
                        data-testid={`mailbox-toggle-${mb.id}`}>
                  {mb.is_active ? "Apagar" : "Encender"}
                </button>
                <button onClick={() => remove(mb)} className="text-mye-ink-muted hover:text-status-escalated">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      {testFor && <TestSendModal mailbox={testFor} onClose={() => setTestFor(null)} />}
    </section>
  );
}

function MailboxWizard({ domains, clients, onClose, onCreated }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    domain_id: domains[0]?.id || "",
    client_id: "",
    display_name: "",
    sender_name: "",
    sender_email: "",
    reply_to_email: "",
    api_key: "",
    daily_send_limit: "",
    is_default_for_tenant: false,
    is_default_for_client: false,
    workflow_types: ["generic"],
  });
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const selectedDomain = domains.find((d) => d.id === form.domain_id);

  async function submit() {
    setBusy(true);
    try {
      const payload = {
        domain_id: form.domain_id,
        client_id: form.client_id || null,
        display_name: form.display_name,
        sender_name: form.sender_name,
        sender_email: form.sender_email,
        reply_to_email: form.reply_to_email || null,
        api_key: form.api_key || null,
        daily_send_limit: form.daily_send_limit ? parseInt(form.daily_send_limit, 10) : null,
        is_default_for_tenant: form.is_default_for_tenant,
        is_default_for_client: !!(form.is_default_for_client && form.client_id),
        workflow_types: form.workflow_types,
      };
      await api.post("/admin/email/mailboxes", payload);
      toast.success("Buzón creado");
      onCreated?.();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" data-testid="mailbox-wizard">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-xl p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Wand2 className="h-4 w-4 text-mye-accent" />
          <h2 className="text-sm font-semibold">Nuevo buzón · Paso {step}/3</h2>
          <button onClick={onClose} className="ml-auto text-mye-ink-muted"><X className="h-4 w-4" /></button>
        </div>
        {step === 1 && (
          <div className="space-y-3" data-testid="wizard-step-1">
            <h3 className="text-xs uppercase tracking-wider text-mye-ink-muted">1. Dominio + alcance</h3>
            <Field label="Dominio verificado" required>
              <select value={form.domain_id} onChange={(e) => setForm({ ...form, domain_id: e.target.value })}
                      className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                      data-testid="wizard-domain">
                {domains.map((d) => <option key={d.id} value={d.id}>{d.domain}</option>)}
              </select>
            </Field>
            <Field label="Cliente (opcional)" hint="Vacío = buzón a nivel tenant. Asignado = buzón exclusivo para ese cliente.">
              <select value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                      className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                      data-testid="wizard-client">
                <option value="">— Sin cliente (tenant-level) —</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-3" data-testid="wizard-step-2">
            <h3 className="text-xs uppercase tracking-wider text-mye-ink-muted">2. Identidad de envío</h3>
            <Field label="Nombre visible" required>
              <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                     placeholder="Soporte Cliente A"
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                     data-testid="wizard-display-name" />
            </Field>
            <Field label="Sender name" required>
              <input value={form.sender_name} onChange={(e) => setForm({ ...form, sender_name: e.target.value })}
                     placeholder="MyExcellence Soporte"
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                     data-testid="wizard-sender-name" />
            </Field>
            <Field label="Sender email" required hint={selectedDomain ? `Debe terminar en @${selectedDomain.domain}` : ""}>
              <input value={form.sender_email} onChange={(e) => setForm({ ...form, sender_email: e.target.value })}
                     placeholder={selectedDomain ? `soporte@${selectedDomain.domain}` : ""}
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
                     data-testid="wizard-sender-email" />
            </Field>
            <Field label="Reply-to (opcional)">
              <input value={form.reply_to_email} onChange={(e) => setForm({ ...form, reply_to_email: e.target.value })}
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
                     data-testid="wizard-reply-to" />
            </Field>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-3" data-testid="wizard-step-3">
            <h3 className="text-xs uppercase tracking-wider text-mye-ink-muted">3. Credenciales + defaults</h3>
            <Field label="API key Resend" required hint="Se guarda cifrada con Fernet. Solo se muestran los últimos 4 chars luego.">
              <div className="relative">
                <input value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                       type={showKey ? "text" : "password"}
                       placeholder="re_..."
                       className="w-full rounded-md border border-mye-border pl-3 pr-10 py-2 text-sm font-mono"
                       data-testid="wizard-api-key" />
                <button type="button" onClick={() => setShowKey(!showKey)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-mye-ink-muted">
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>
            <Field label="Límite diario (opcional)">
              <input value={form.daily_send_limit} type="number"
                     onChange={(e) => setForm({ ...form, daily_send_limit: e.target.value })}
                     placeholder="500"
                     className="w-full rounded-md border border-mye-border px-3 py-2 text-sm" />
            </Field>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input type="checkbox" checked={form.is_default_for_tenant}
                     onChange={(e) => setForm({ ...form, is_default_for_tenant: e.target.checked })}
                     data-testid="wizard-default-tenant" />
              Default del tenant (catch-all)
            </label>
            {form.client_id && (
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input type="checkbox" checked={form.is_default_for_client}
                       onChange={(e) => setForm({ ...form, is_default_for_client: e.target.checked })}
                       data-testid="wizard-default-client" />
                Default del cliente seleccionado
              </label>
            )}
          </div>
        )}
        <div className="flex items-center gap-2 pt-3 border-t border-mye-border">
          {step > 1 && (
            <button onClick={() => setStep(step - 1)} className="text-xs text-mye-ink-muted hover:text-mye-accent"
                    data-testid="wizard-back">← Atrás</button>
          )}
          {step < 3 && (
            <button onClick={() => setStep(step + 1)}
                    className="ml-auto rounded-md bg-mye-accent text-white px-4 py-1.5 text-xs hover:brightness-110"
                    data-testid="wizard-next">Siguiente →</button>
          )}
          {step === 3 && (
            <button onClick={submit} disabled={busy}
                    className="ml-auto rounded-md bg-mye-accent text-white px-4 py-1.5 text-xs hover:brightness-110 disabled:opacity-50"
                    data-testid="wizard-submit">
              {busy ? "Creando…" : "Crear buzón"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function TestSendModal({ mailbox, onClose }) {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  async function run() {
    setBusy(true); setResult(null);
    try {
      const r = await api.post(`/admin/email/mailboxes/${mailbox.id}/test`, { to });
      setResult(r.data?.data);
      if (r.data?.data?.sent) toast.success("Email enviado");
      else toast.error(r.data?.data?.error_message || "Falló");
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" data-testid="test-modal">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Send className="h-4 w-4 text-mye-accent" />
          <h3 className="text-sm font-semibold">Probar buzón · {mailbox.display_name}</h3>
          <button onClick={onClose} className="ml-auto text-mye-ink-muted"><X className="h-4 w-4" /></button>
        </div>
        <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="destino@ejemplo.com"
               className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
               data-testid="test-to" />
        <button onClick={run} disabled={busy || !to.trim()}
                className="w-full rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:brightness-110 disabled:opacity-50"
                data-testid="test-send">
          {busy ? "Enviando…" : "Enviar prueba"}
        </button>
        {result && (
          <div className={"rounded-md px-3 py-2 text-xs " + (result.sent
            ? "bg-status-resolved/10 text-status-resolved"
            : "bg-status-escalated/10 text-status-escalated")}>
            {result.sent
              ? <>✓ Enviado · <span className="font-mono">{result.message_id}</span></>
              : <>✗ [{result.error_code}] {result.error_message}</>}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// ROUTING TAB
// ─────────────────────────────────────────────────────────────────────────
function RoutingTab() {
  const [rules, setRules] = useState([]);
  const [mailboxes, setMailboxes] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    mailbox_id: "", workflow_type: "ticket_notification",
    client_id: "", motivo_id: "", priority: 100, description: "",
  });
  const [explainCtx, setExplainCtx] = useState({
    workflow_type: "ticket_notification", client_id: "", motivo_id: "",
  });
  const [explainResult, setExplainResult] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [r, mb, cl] = await Promise.all([
        api.get("/admin/email/routing"),
        api.get("/admin/email/mailboxes"),
        api.get("/admin/hierarchy/clients?limit=100").catch(() => ({ data: { data: { items: [] } } })),
      ]);
      setRules(r.data?.data?.items || []);
      setMailboxes(mb.data?.data?.items || []);
      setClients(cl.data?.data?.items || []);
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function createRule() {
    if (!form.mailbox_id) { toast.error("Selecciona un buzón"); return; }
    try {
      await api.post("/admin/email/routing", {
        ...form,
        client_id: form.client_id || null,
        motivo_id: form.motivo_id || null,
        priority: parseInt(form.priority, 10) || 100,
      });
      toast.success("Regla creada"); setShowAdd(false); load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  async function removeRule(id) {
    if (!window.confirm("¿Eliminar regla?")) return;
    try {
      await api.delete(`/admin/email/routing/${id}`);
      toast.success("Regla eliminada"); load();
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  async function runExplain() {
    try {
      const r = await api.post("/admin/email/explain", {
        ...explainCtx,
        client_id: explainCtx.client_id || null,
        motivo_id: explainCtx.motivo_id || null,
      });
      setExplainResult(r.data?.data);
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
  }
  const mbName = (id) => mailboxes.find((m) => m.id === id)?.display_name || id?.slice(0, 8);
  const clName = (id) => id ? (clients.find((c) => c.id === id)?.name || id.slice(0, 8)) : "*";

  return (
    <section className="bg-white border border-mye-border rounded-lg p-4 space-y-3" data-testid="tab-routing">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Reglas de ruteo ({rules.length})</h2>
        <button onClick={() => setShowAdd(true)}
                disabled={mailboxes.length === 0}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 disabled:opacity-50"
                data-testid="routing-add">
          <Plus className="h-3 w-3" /> Nueva regla
        </button>
      </div>
      {showAdd && (
        <div className="rounded-md border border-mye-accent/30 bg-mye-primary-soft/30 p-3 space-y-2" data-testid="routing-form">
          <div className="grid grid-cols-2 gap-2">
            <select value={form.workflow_type} onChange={(e) => setForm({ ...form, workflow_type: e.target.value })}
                    className="rounded-md border border-mye-border px-2 py-1.5 text-sm" data-testid="routing-workflow">
              {WORKFLOWS.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
            </select>
            <select value={form.mailbox_id} onChange={(e) => setForm({ ...form, mailbox_id: e.target.value })}
                    className="rounded-md border border-mye-border px-2 py-1.5 text-sm" data-testid="routing-mailbox">
              <option value="">— Buzón —</option>
              {mailboxes.map((m) => <option key={m.id} value={m.id}>{m.display_name}</option>)}
            </select>
            <select value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                    className="rounded-md border border-mye-border px-2 py-1.5 text-sm" data-testid="routing-client">
              <option value="">Cualquier cliente</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <input value={form.motivo_id} onChange={(e) => setForm({ ...form, motivo_id: e.target.value })}
                   placeholder="motivo_id (opcional)"
                   className="rounded-md border border-mye-border px-2 py-1.5 text-sm font-mono" />
            <input value={form.priority} type="number"
                   onChange={(e) => setForm({ ...form, priority: e.target.value })}
                   placeholder="priority" data-testid="routing-priority"
                   className="rounded-md border border-mye-border px-2 py-1.5 text-sm" />
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                   placeholder="descripción"
                   className="rounded-md border border-mye-border px-2 py-1.5 text-sm" />
          </div>
          <div className="flex gap-2">
            <button onClick={createRule} className="rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs"
                    data-testid="routing-submit">Crear</button>
            <button onClick={() => setShowAdd(false)} className="text-mye-ink-muted text-xs">Cancelar</button>
          </div>
        </div>
      )}
      {loading ? <div className="text-sm text-mye-ink-muted">Cargando…</div>
        : rules.length === 0 ? (
          <div className="text-sm text-mye-ink-muted italic">
            Sin reglas. La resolución cae a los defaults del cliente/tenant.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-mye-ink-muted">
              <tr><th className="text-left p-2">Workflow</th><th>Cliente</th><th>Motivo</th><th>Prioridad</th><th>Buzón</th><th></th></tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="border-t border-mye-border" data-testid={`rule-${r.id}`}>
                  <td className="p-2 font-mono">{r.workflow_type}</td>
                  <td className="p-2 text-center">{clName(r.client_id)}</td>
                  <td className="p-2 text-center font-mono">{r.motivo_id?.slice(0, 8) || "*"}</td>
                  <td className="p-2 text-center font-mono">{r.priority}</td>
                  <td className="p-2 font-medium">{mbName(r.mailbox_id)}</td>
                  <td className="p-2 text-right">
                    <button onClick={() => removeRule(r.id)} className="text-mye-ink-muted hover:text-status-escalated">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

      {/* Explain */}
      <div className="border-t border-mye-border pt-3" data-testid="routing-explain">
        <h3 className="text-xs font-semibold uppercase tracking-wider mb-2">Depurar resolución</h3>
        <div className="grid grid-cols-3 gap-2">
          <select value={explainCtx.workflow_type} onChange={(e) => setExplainCtx({ ...explainCtx, workflow_type: e.target.value })}
                  className="rounded-md border border-mye-border px-2 py-1.5 text-xs">
            {WORKFLOWS.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
          </select>
          <select value={explainCtx.client_id} onChange={(e) => setExplainCtx({ ...explainCtx, client_id: e.target.value })}
                  className="rounded-md border border-mye-border px-2 py-1.5 text-xs">
            <option value="">Cualquier cliente</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <input value={explainCtx.motivo_id} onChange={(e) => setExplainCtx({ ...explainCtx, motivo_id: e.target.value })}
                 placeholder="motivo_id"
                 className="rounded-md border border-mye-border px-2 py-1.5 text-xs font-mono" />
        </div>
        <button onClick={runExplain}
                className="mt-2 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs"
                data-testid="explain-run">
          Resolver
        </button>
        {explainResult && (
          <div className="mt-2 rounded-md bg-mye-app/40 p-2 text-xs" data-testid="explain-result">
            {explainResult.resolved_mailbox ? (
              <>Resuelve a <strong>{explainResult.resolved_mailbox.display_name}</strong>
              {" ("}<code className="font-mono">{explainResult.resolved_mailbox.sender_email}</code>{")"}</>
            ) : <span className="text-status-escalated">No resuelve · enviar email fallaría con NO_MAILBOX_RESOLVED</span>}
            <div className="text-[10px] text-mye-ink-muted mt-1">Reglas evaluadas: {explainResult.matched_rules.length}</div>
          </div>
        )}
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// HEALTH TAB
// ─────────────────────────────────────────────────────────────────────────
function HealthTab() {
  const [data, setData] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [h, l] = await Promise.all([
        api.get("/admin/email/health?days=7"),
        api.get("/admin/email/logs?limit=20"),
      ]);
      setData(h.data?.data);
      setLogs(l.data?.data?.items || []);
    } catch (e) { toast.error(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  if (loading) return <div className="text-sm text-mye-ink-muted">Cargando…</div>;
  if (!data) return null;

  return (
    <section className="bg-white border border-mye-border rounded-lg p-4 space-y-3" data-testid="tab-health">
      <h2 className="text-sm font-semibold">Salud · últimos 7 días</h2>
      <div className="grid grid-cols-4 gap-3">
        <Stat label="Total" value={data.total} />
        <Stat label="Enviados" value={data.sent} tone="ok" />
        <Stat label="Fallidos" value={data.failed} tone={data.failed > 0 ? "bad" : "muted"} />
        <Stat label="Tasa entrega"
              value={data.delivery_rate != null ? `${(data.delivery_rate * 100).toFixed(1)}%` : "—"}
              tone={data.delivery_rate > 0.95 ? "ok" : data.delivery_rate > 0.8 ? "warn" : "bad"} />
      </div>
      {data.errors_by_code.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider mt-2">Errores por código</h3>
          <ul className="text-xs space-y-1 mt-1">
            {data.errors_by_code.map((e) => (
              <li key={e.code} className="font-mono flex justify-between rounded-md bg-status-escalated/5 px-2 py-1">
                <span>{e.code}</span><span>{e.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <h3 className="text-xs font-semibold uppercase tracking-wider mt-3">Últimos envíos</h3>
      {logs.length === 0 ? (
        <div className="text-xs text-mye-ink-muted italic">Sin envíos recientes.</div>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-mye-ink-muted">
            <tr><th className="text-left p-1">Cuándo</th><th>Workflow</th><th>Destinatario</th><th>Estado</th></tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-t border-mye-border" data-testid={`log-${l.id}`}>
                <td className="p-1 font-mono text-[10px]">{l.sent_at?.slice(0, 16).replace("T", " ")}</td>
                <td className="p-1 font-mono">{l.workflow_type}</td>
                <td className="p-1 font-mono">{l.to_masked}</td>
                <td className="p-1">
                  {l.status === "sent" ? <span className="text-status-resolved">✓ {l.status}</span>
                    : <span className="text-status-escalated">✗ {l.error_code || l.status}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Stat({ label, value, tone = "muted" }) {
  const colors = {
    ok: "text-status-resolved bg-status-resolved/5",
    warn: "text-status-pending bg-status-pending/5",
    bad: "text-status-escalated bg-status-escalated/5",
    muted: "text-mye-ink bg-mye-app",
  }[tone];
  return (
    <div className={"rounded-md p-3 " + colors}>
      <div className="text-[10px] uppercase tracking-wider text-mye-ink-muted">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}

function Field({ label, required, hint, children }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wider font-mono text-mye-ink-muted">
        {label}{required && <span className="text-status-escalated"> *</span>}
      </span>
      <div className="mt-1">{children}</div>
      {hint && <div className="mt-1 text-[10px] text-mye-ink-muted">{hint}</div>}
    </label>
  );
}
