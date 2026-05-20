import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2, Briefcase, Layers, Truck, Globe2, Plus, X, RefreshCw,
  LogOut, Lock, ArrowLeft, CheckCircle2, AlertTriangle, Search, Activity,
  Pencil, Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";
import UsersPanel from "./hierarchy/UsersPanel";
import CarrierConfigDialog from "./hierarchy/CarrierConfigDialog";
import CarrierCellRenderer from "./hierarchy/CarrierCellRenderer";
import { subscribe, emit } from "@/admin/eventBus";
import { ADMIN_EVENTS } from "@/admin/eventCatalog";

const TABS = [
  { key: "projects",   label: "Proyectos",   icon: Briefcase },
  { key: "clients",    label: "Clientes",    icon: Building2 },
  { key: "subclients", label: "Subclientes", icon: Layers },
  { key: "carriers",   label: "Carriers",    icon: Truck },
  { key: "users",      label: "Usuarios",    icon: Users,
    requiresAnyRole: ["root_dev", "superadmin"] },
  { key: "tenants",    label: "Tenants",     icon: Globe2, requiresRole: "root_dev" },
];

export default function AdminHierarchy() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("projects");
  // UX-JERARQUIA-005 — Bundle F: contadores visibles por tab.
  // Single-shot fetch al montar; se refresca cuando el usuario cambia de tab
  // (lightweight: solo counts, no listados).
  const [counts, setCounts] = useState({});
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [p, c, s, ca, u, t] = await Promise.allSettled([
          api.get("/admin/projects"),
          api.get("/admin/clients"),
          api.get("/admin/subclients"),
          api.get("/admin/carriers"),
          api.get("/admin/users"),
          api.get("/admin/tenants"),
        ]);
        if (cancelled) return;
        const ex = (r) => r.status === "fulfilled"
          ? (r.value?.data?.data?.count
              ?? r.value?.data?.data?.total
              ?? r.value?.data?.data?.items?.length
              ?? null)
          : null;
        setCounts({
          projects: ex(p), clients: ex(c), subclients: ex(s),
          carriers: ex(ca), users: ex(u), tenants: ex(t),
        });
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [tab]);

  const visible = useMemo(
    () => TABS.filter((t) => {
      if (t.requiresRole && user?.role !== t.requiresRole) return false;
      if (t.requiresAnyRole && !t.requiresAnyRole.includes(user?.role)) return false;
      return true;
    }),
    [user],
  );

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-hierarchy-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Admin · Jerarquía multi-tenant</div>
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
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 02 · Jerarquía multi-tenant
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">CRUD Admin</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            Tenants → Proyectos → Clientes → Subclientes · Carriers (transversales).
            Toda escritura está aislada por <span className="font-mono">tenant_id</span> (R01).
          </p>
        </section>

        <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="hierarchy-tabs">
          {visible.map((t) => {
            const Active = tab === t.key;
            const Icon = t.icon;
            const cnt = counts[t.key];
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
                data-testid={`hierarchy-tab-${t.key}`}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
                {cnt != null && (
                  <span
                    className={
                      "ml-1 inline-flex items-center justify-center rounded-full px-1.5 text-[10px] font-mono " +
                      (Active
                        ? "bg-mye-accent/10 text-mye-accent"
                        : "bg-mye-border/40 text-mye-ink-muted")
                    }
                    data-testid={`hierarchy-tab-${t.key}-count`}
                  >
                    {cnt}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
          {tab === "projects"   && <ProjectsPanel />}
          {tab === "clients"    && <ClientsPanel />}
          {tab === "subclients" && <SubclientsPanel />}
          {tab === "carriers"   && <CarriersPanel />}
          {tab === "users"      && ["root_dev","superadmin"].includes(user?.role) && <UsersPanel currentUserId={user?.id} />}
          {tab === "tenants"    && user?.role === "root_dev" && <TenantsPanel />}
        </div>
      </main>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Generic CRUD panel
//
// Bundle C (Mayo 2026): refactor con patrón observable.
//   - Nueva prop opcional `refreshSignal` (number|string|Date|null): cuando
//     cambia, el panel re-fetcha la lista.
//   - Método imperativo expuesto vía ref: `panelRef.current.refresh()`.
//   - Nueva prop opcional `onRefreshCompleted({ count, durationMs })`.
//   - Debounce de 500ms para colapsar ráfagas de refresh.
//   - Race-condition guard: descarta resultados de fetchs obsoletos.
//
// Backward compatible al 100%: si no se pasan las nuevas props ni ref,
// el comportamiento es idéntico al previo al refactor.
// ─────────────────────────────────────────────────────────────────────────
const CrudPanel = forwardRef(function CrudPanel({
  title, listEndpoint, columns, formFields, payloadFromForm, testid,
  headerExtra, searchKeys, editPath, editPayloadFromForm, editFromRow,
  // Bundle C — nuevas props (todas opcionales)
  refreshSignal,
  onRefreshCompleted,
  onItemSaved,
}, ref) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const initial = useMemo(() => Object.fromEntries(formFields.map((f) => [f.name, f.default ?? ""])), [formFields]);
  const [form, setForm] = useState(initial);

  // Bundle C — refs para debounce + race-condition guard.
  const debounceTimerRef = useRef(null);
  const lastRequestIdRef = useRef(0);
  const refreshOverlayRef = useRef(false);
  const [overlay, setOverlay] = useState(false);

  async function refresh() {
    // Cancelar timer pendiente — fue solicitado un refresh ya.
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    const requestId = ++lastRequestIdRef.current;
    const t0 = performance.now();
    setLoading(true);
    if (items.length > 0) {
      refreshOverlayRef.current = true;
      setOverlay(true);
    }
    try {
      const r = await api.get(listEndpoint);
      // Race-condition guard: si llegó un fetch posterior, descartar este.
      if (requestId !== lastRequestIdRef.current) return;
      const newItems = r.data?.data?.items || [];
      setItems(newItems);
      if (typeof onRefreshCompleted === "function") {
        try {
          onRefreshCompleted({
            count: newItems.length,
            durationMs: Math.round(performance.now() - t0),
          });
        } catch (_) { /* listener no debe romper refresh */ }
      }
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally {
      if (requestId === lastRequestIdRef.current) {
        setLoading(false);
        refreshOverlayRef.current = false;
        setOverlay(false);
      }
    }
  }

  // Bundle C — debounce: encolar el refresh con 500ms de gracia.
  function scheduleRefresh() {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      refresh();
    }, 500);
  }

  // Exponer refresh() al ref del padre — patrón useImperativeHandle.
  useImperativeHandle(ref, () => ({
    refresh,         // inmediato
    scheduleRefresh, // con debounce
  }), [listEndpoint]);

  useEffect(() => { refresh(); }, [listEndpoint]);

  // Bundle C — observer del refreshSignal con debounce.
  useEffect(() => {
    if (refreshSignal === undefined || refreshSignal === null) return;
    scheduleRefresh();
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  const filtered = useMemo(() => {
    if (!search.trim() || !searchKeys?.length) return items;
    const q = search.trim().toLowerCase();
    return items.filter((row) => searchKeys.some((k) => String(row[k] ?? "").toLowerCase().includes(q)));
  }, [items, search, searchKeys]);

  function openCreate() {
    setForm(initial); setEditingId(null); setOpen(true); setError(null);
  }
  function openEdit(row) {
    if (!editPath) return;
    const seed = editFromRow ? editFromRow(row) : Object.fromEntries(formFields.map((f) => [f.name, row[f.name] ?? f.default ?? ""]));
    setForm({ ...initial, ...seed });
    setEditingId(row.id);
    setOpen(true);
    setError(null);
  }

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    let savedId = null;
    const isNew = !editingId;
    try {
      if (editingId) {
        const buildPayload = editPayloadFromForm || payloadFromForm;
        const resp = await api.patch(`${editPath}/${editingId}`, buildPayload(form));
        savedId = resp.data?.data?.id || editingId;
      } else {
        const resp = await api.post(listEndpoint, payloadFromForm(form));
        savedId = resp.data?.data?.id || null;
      }
      setForm(initial);
      setOpen(false);
      setEditingId(null);
      await refresh();
      // Bundle C — emitir hook de dominio para que el caller publique
      // el evento que corresponda en el bus.
      if (typeof onItemSaved === "function") {
        try { onItemSaved({ id: savedId, isNew }); } catch (_) { /* listener no debe romper submit */ }
      }
    } catch (e) {
      setError(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div data-testid={testid} className="relative">
      {overlay && (
        <div
          className="absolute inset-0 z-10 grid place-items-center bg-white/70 pointer-events-none"
          data-testid={`${testid}-refresh-overlay`}
        >
          <RefreshCw className="h-4 w-4 animate-spin text-mye-accent" />
        </div>
      )}
      <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-mye-border flex-wrap">
        <div>
          <div className="font-medium">{title}</div>
          <div className="text-xs text-mye-ink-muted font-mono">
            {loading ? "Cargando…" : `${filtered.length}${search ? ` / ${items.length}` : ""} registros`}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {searchKeys?.length > 0 && (
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mye-ink-muted" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar…"
                className="rounded-md border border-mye-border bg-white pl-7 pr-2 py-1.5 text-xs outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors w-44"
                data-testid={`${testid}-search`}
              />
            </div>
          )}
          <button
            onClick={scheduleRefresh}
            className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
            data-testid={`${testid}-refresh`}
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refrescar
          </button>
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition"
            data-testid={`${testid}-create`}
          >
            <Plus className="h-3.5 w-3.5" /> Nuevo
          </button>
        </div>
      </div>

      {headerExtra}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">
                  {c.label}
                </th>
              ))}
              {editPath && (
                <th className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">
                  Acciones
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && !loading && (
              <tr>
                <td colSpan={columns.length + (editPath ? 1 : 0)} className="text-center px-4 py-10 text-sm text-mye-ink-muted font-mono">
                  {items.length === 0
                    ? "Sin registros — crea el primero con \u201CNuevo\u201D."
                    : `Sin coincidencias para \u201C${search}\u201D.`}
                </td>
              </tr>
            )}
            {filtered.map((row) => (
              <tr key={row.id} className="border-t border-mye-border hover:bg-mye-primary-soft/40 transition" data-testid={`${testid}-row`}>
                {columns.map((c) => (
                  <td key={c.key} className={"px-4 py-2.5 " + (c.mono ? "font-mono text-[12px]" : "")}>
                    {c.render ? c.render(row) : (row[c.key] ?? "—")}
                  </td>
                ))}
                {editPath && (
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => openEdit(row)}
                      data-testid={`${testid}-edit-${row.id}`}
                      className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline"
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

      {open && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" data-testid={`${testid}-dialog`}>
          <div className="bg-white border border-mye-border rounded-lg shadow-xl w-full max-w-lg animate-fade-in max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border sticky top-0 bg-white">
              <div className="font-medium text-sm">{editingId ? "Editar" : "Crear"} · {title}</div>
              <button onClick={() => { setOpen(false); setEditingId(null); }} className="text-mye-ink-muted hover:text-mye-ink">
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={submit} className="p-5 space-y-4">
              {formFields.filter((f) => !(editingId && f.createOnly)).map((f) => (
                <FieldInput
                  key={f.name}
                  field={f}
                  value={form[f.name]}
                  onChange={(v) => setForm((s) => ({ ...s, [f.name]: v }))}
                />
              ))}
              {error && (
                <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated" data-testid={`${testid}-error`}>
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => { setOpen(false); setEditingId(null); }}
                        className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft transition">
                  Cancelar
                </button>
                <button type="submit" disabled={busy}
                        className="rounded-md bg-mye-accent text-white px-4 py-1.5 text-sm hover:brightness-110 transition disabled:opacity-60"
                        data-testid={`${testid}-submit`}>
                  {busy ? "Guardando…" : (editingId ? "Actualizar" : "Guardar")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
});

function FieldInput({ field, value, onChange }) {
  const baseCls =
    "w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors";
  const label = (
    <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">
      {field.label}{field.required && <span className="text-mye-accent ml-0.5">*</span>}
      {field.secret && <Lock className="inline h-3 w-3 ml-1 text-mye-ink-muted" />}
    </span>
  );
  if (field.options) {
    return (
      <label className="block">
        {label}
        <select className={baseCls} value={value} onChange={(e) => onChange(e.target.value)}
                data-testid={`field-${field.name}`}>
          {field.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
    );
  }
  if (field.type === "checkbox") {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)}
               className="h-4 w-4 accent-mye-accent" data-testid={`field-${field.name}`} />
        <span>{field.label}</span>
      </label>
    );
  }
  return (
    <label className="block">
      {label}
      <input
        type={field.type || "text"}
        value={value ?? ""}
        required={field.required}
        placeholder={field.placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={baseCls}
        data-testid={`field-${field.name}`}
      />
    </label>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Concrete panels
// ─────────────────────────────────────────────────────────────────────────
function ProjectsPanel() {
  return (
    <CrudPanel
      title="Proyectos"
      testid="projects-panel"
      listEndpoint="/admin/projects"
      editPath="/admin/projects"
      searchKeys={["name", "id"]}
      columns={[
        { key: "name", label: "Nombre" },
        { key: "status", label: "Status", render: (r) => <StatusPill v={r.status} /> },
        { key: "id", label: "ID", mono: true, render: (r) => <span className="text-mye-ink-muted">{r.id.slice(0, 8)}…</span> },
        { key: "created_at", label: "Creado", mono: true, render: (r) => fmt(r.created_at) },
      ]}
      formFields={[
        { name: "name", label: "Nombre del proyecto", required: true, placeholder: "Cubbo Anchor" },
        { name: "status", label: "Status", default: "active", options: [
          { value: "active", label: "Activo" }, { value: "inactive", label: "Inactivo" },
        ]},
      ]}
      payloadFromForm={(f) => ({ name: f.name, status: f.status })}
    />
  );
}

function ClientsPanel() {
  const [projects, setProjects] = useState([]);
  const [carrierDialog, setCarrierDialog] = useState(null); // {client, code}
  // Bundle C — ref imperativo + signal observable + suscripción al bus.
  const panelRef = useRef(null);
  const [refreshSignal, setRefreshSignal] = useState(0);
  useEffect(() => {
    api.get("/admin/projects").then((r) => setProjects(r.data?.data?.items || []));
  }, []);
  useEffect(() => {
    // Cuando OTRO componente emite que un carrier cambió, refrescamos.
    // CarrierConfigDialog emite admin.carrier.updated en onSaved.
    const unsubA = subscribe(ADMIN_EVENTS.CARRIER_UPDATED, () => {
      setRefreshSignal((n) => n + 1);
    });
    const unsubB = subscribe(ADMIN_EVENTS.CARRIER_DELETED, () => {
      setRefreshSignal((n) => n + 1);
    });
    return () => { unsubA(); unsubB(); };
  }, []);
  if (projects.length === 0) {
    return (
      <div className="px-6 py-10 text-sm text-mye-ink-muted">
        Crea al menos un proyecto antes de registrar clientes.
      </div>
    );
  }
  return (
    <>
    <CrudPanel
      ref={panelRef}
      refreshSignal={refreshSignal}
      onItemSaved={({ id, isNew }) => {
        emit(
          isNew ? ADMIN_EVENTS.CLIENT_CREATED : ADMIN_EVENTS.CLIENT_UPDATED,
          { client_id: id },
        );
      }}
      title="Clientes"
      testid="clients-panel"
      listEndpoint="/admin/clients"
      editPath="/admin/clients"
      searchKeys={["name", "id"]}
      columns={[
        { key: "name", label: "Nombre" },
        { key: "ingest_mode", label: "Ingesta" },
        { key: "preferred_channel", label: "Canal" },
        { key: "api_creds_set", label: "Credenciales", render: (r) => (
          r.api_creds_set
            ? <span className="font-mono text-[11px] text-status-resolved">cifradas ✓</span>
            : <span className="font-mono text-[11px] text-mye-ink-muted">—</span>
        )},
        { key: "_carriers", label: "Integraciones", render: (r) => (
          <CarrierCellRenderer client={r}
                                onConfigure={(code) => setCarrierDialog({ client: r, code })} />
        )},
        { key: "webhook_token", label: "Webhook token", mono: true, render: (r) => <span className="text-mye-ink-muted">{r.webhook_token?.slice(0, 12)}…</span> },
      ]}
      formFields={[
        { name: "project_id", label: "Proyecto", required: true,
          createOnly: true,
          options: projects.map((p) => ({ value: p.id, label: p.name })),
          default: projects[0]?.id ?? "" },
        { name: "name", label: "Nombre del cliente", required: true, placeholder: "Cubbo" },
        { name: "ingest_mode", label: "Modo de ingesta", default: "webhook", options: [
          { value: "webhook", label: "Webhook" }, { value: "pulling", label: "Pulling" }, { value: "layout", label: "Layout" },
        ]},
        { name: "preferred_channel", label: "Canal preferido", default: "email", options: [
          { value: "email", label: "Correo" }, { value: "whatsapp", label: "WhatsApp" }, { value: "both", label: "Ambos" },
        ]},
        { name: "api_url", label: "API URL (opcional)", placeholder: "https://cliente.example.com" },
        { name: "api_auth_type", label: "Auth", default: "none", options: [
          { value: "none", label: "Ninguno" }, { value: "bearer", label: "Bearer" }, { value: "basic", label: "Basic" }, { value: "apikey", label: "API Key" },
        ]},
        { name: "api_creds", label: "Credenciales API (se cifran)", secret: true, type: "password" },
        { name: "ops_contact_email", label: "Email contacto ops", type: "email", placeholder: "ops@cliente.com" },
        { name: "ops_contact_wa", label: "WhatsApp ops (+521…)", placeholder: "+5215512345678" },
      ]}
      payloadFromForm={(f) => ({
        project_id: f.project_id, name: f.name,
        ingest_mode: f.ingest_mode, preferred_channel: f.preferred_channel,
        api_url: f.api_url || null, api_auth_type: f.api_auth_type,
        api_creds: f.api_creds || null,
        ops_contact_email: f.ops_contact_email || null,
        ops_contact_wa: f.ops_contact_wa || null,
        status_map: {},
      })}
      editPayloadFromForm={(f) => {
        // PATCH: omit project_id (createOnly), only include creds if provided
        const out = {
          name: f.name,
          ingest_mode: f.ingest_mode,
          preferred_channel: f.preferred_channel,
          api_url: f.api_url || null,
          api_auth_type: f.api_auth_type,
          ops_contact_email: f.ops_contact_email || null,
          ops_contact_wa: f.ops_contact_wa || null,
        };
        if (f.api_creds) out.api_creds = f.api_creds;
        return out;
      }}
      editFromRow={(row) => ({
        project_id: row.project_id,
        name: row.name,
        ingest_mode: row.ingest_mode,
        preferred_channel: row.preferred_channel,
        api_url: row.api_url || "",
        api_auth_type: row.api_auth_type || "none",
        api_creds: "", // never seed encrypted creds back
        ops_contact_email: row.ops_contact_email || "",
        ops_contact_wa: row.ops_contact_wa || "",
      })}
    />
    {carrierDialog && (
      <CarrierConfigDialog
        clientId={carrierDialog.client.id}
        clientName={carrierDialog.client.name}
        carrierCode={carrierDialog.code}
        onClose={() => setCarrierDialog(null)}
        onSaved={() => {
          // Bundle C — emitir evento; el panel se refresca vía suscripción.
          // (Anterior workaround documentado en este punto removido.)
          emit(ADMIN_EVENTS.CARRIER_UPDATED, {
            client_id: carrierDialog.client.id,
            carrier_code: carrierDialog.code,
          });
        }}
      />
    )}
    </>
  );
}

function SubclientsPanel() {
  const [clients, setClients] = useState([]);
  // Bundle C — el dropdown de cliente del form depende de /admin/clients;
  // si en otra pestaña del admin se crea un cliente, suscribimos para
  // mantener fresca la lista (zero recarga del browser).
  const [clientsRefreshSignal, setClientsRefreshSignal] = useState(0);
  useEffect(() => {
    api.get("/admin/clients").then((r) => setClients(r.data?.data?.items || []));
  }, [clientsRefreshSignal]);
  useEffect(() => {
    const unsubA = subscribe(ADMIN_EVENTS.CLIENT_CREATED, () => {
      setClientsRefreshSignal((n) => n + 1);
    });
    const unsubB = subscribe(ADMIN_EVENTS.CLIENT_UPDATED, () => {
      setClientsRefreshSignal((n) => n + 1);
    });
    return () => { unsubA(); unsubB(); };
  }, []);
  if (clients.length === 0) {
    return (
      <div className="px-6 py-10 text-sm text-mye-ink-muted">
        Registra al menos un cliente antes de crear subclientes.
      </div>
    );
  }
  return (
    <CrudPanel
      title="Subclientes"
      testid="subclients-panel"
      listEndpoint="/admin/subclients"
      editPath="/admin/subclients"
      searchKeys={["name", "id"]}
      columns={[
        { key: "name", label: "Nombre" },
        { key: "client_id", label: "Cliente", render: (r) => clients.find((c) => c.id === r.client_id)?.name || r.client_id.slice(0, 8) },
        { key: "status", label: "Status", render: (r) => <StatusPill v={r.status} /> },
      ]}
      formFields={[
        { name: "client_id", label: "Cliente", required: true,
          createOnly: true,
          options: clients.map((c) => ({ value: c.id, label: c.name })),
          default: clients[0]?.id ?? "" },
        { name: "name", label: "Nombre del subcliente", required: true, placeholder: "ShopinBaz" },
        { name: "status", label: "Status", default: "active", options: [
          { value: "active", label: "Activo" }, { value: "inactive", label: "Inactivo" },
        ]},
      ]}
      payloadFromForm={(f) => ({ client_id: f.client_id, name: f.name, status: f.status })}
      editPayloadFromForm={(f) => ({ name: f.name, status: f.status })}
    />
  );
}

function CarriersPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({});
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [healthByCode, setHealthByCode] = useState({});
  const [trackOpen, setTrackOpen] = useState(null);  // carrier code/id
  const [trackTid, setTrackTid] = useState("");
  const [trackResult, setTrackResult] = useState(null);
  const [trackBusy, setTrackBusy] = useState(false);
  const [trackErr, setTrackErr] = useState(null);

  async function refresh() {
    setLoading(true);
    try {
      const r = await api.get("/admin/carriers");
      const list = r.data?.data?.items || [];
      setItems(list);
      // Disparar health en paralelo
      const next = {};
      await Promise.all(list.map(async (c) => {
        try {
          const h = await api.get(`/admin/carriers/${c.id}/health`);
          next[c.id] = h.data?.data;
        } catch (_e) { next[c.id] = { has_adapter: false, pingable: false }; }
      }));
      setHealthByCode(next);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((c) => (c.name + " " + c.code).toLowerCase().includes(q));
  }, [items, search]);

  async function ping(carrier) {
    setHealthByCode((s) => ({ ...s, [carrier.id]: { ...(s[carrier.id] || {}), _busy: true } }));
    try {
      const h = await api.get(`/admin/carriers/${carrier.id}/health`);
      setHealthByCode((s) => ({ ...s, [carrier.id]: h.data?.data }));
    } catch (e) {
      setHealthByCode((s) => ({ ...s, [carrier.id]: { has_adapter: false, pingable: false } }));
    }
  }

  async function track(e) {
    e.preventDefault();
    if (!trackTid.trim() || !trackOpen) return;
    setTrackBusy(true); setTrackErr(null); setTrackResult(null);
    try {
      const r = await api.post(`/admin/carriers/${trackOpen}/track`, { tracking_id: trackTid.trim() });
      setTrackResult(r.data?.data);
    } catch (err) {
      setTrackErr(err.response?.data?.errors?.[0]?.message || err.message);
    } finally { setTrackBusy(false); }
  }

  function openCreate() {
    setEditingId(null); setForm({}); setOpen(true); setError(null);
  }
  function openEdit(c) {
    setEditingId(c.id);
    setForm({
      name: c.name, code: c.code,
      has_api: !!c.has_api,
      pulling_supported: !!c.pulling_supported,
      webhook_supported: !!c.webhook_supported,
      api_url: c.api_url || "", api_creds: "",
      status: c.status || "active",
    });
    setOpen(true); setError(null);
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (editingId) {
        const payload = {
          name: form.name,
          has_api: !!form.has_api,
          pulling_supported: !!form.pulling_supported,
          webhook_supported: !!form.webhook_supported,
          api_url: form.api_url || null,
          status: form.status || "active",
        };
        if (form.api_creds) payload.api_creds = form.api_creds;
        await api.patch(`/admin/carriers/${editingId}`, payload);
      } else {
        const payload = {
          name: form.name, code: form.code, has_api: !!form.has_api,
          pulling_supported: !!form.pulling_supported,
          webhook_supported: !!form.webhook_supported,
          api_url: form.api_url || null, api_creds: form.api_creds || null,
          status: "active",
        };
        const r = await api.post("/admin/carriers", payload);
        if (!r.data?.success) {
          setError(r.data?.errors?.[0]?.message || "Error");
          setBusy(false);
          return;
        }
      }
      setOpen(false); setEditingId(null); setForm({});
      await refresh();
    } catch (err) {
      setError(err.response?.data?.errors?.[0]?.message || err.message);
    } finally { setBusy(false); }
  }

  return (
    <div data-testid="carriers-panel">
      <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-mye-border flex-wrap">
        <div>
          <div className="font-medium">Carriers</div>
          <div className="text-xs text-mye-ink-muted font-mono">
            {loading ? "Cargando…" : `${filtered.length}${search ? ` / ${items.length}` : ""} registros · adapters via ADAPTER_REGISTRY`}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mye-ink-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar…"
              className="rounded-md border border-mye-border bg-white pl-7 pr-2 py-1.5 text-xs outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors w-44"
              data-testid="carriers-panel-search"
            />
          </div>
          <button onClick={refresh}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                  data-testid="carriers-panel-refresh">
            <RefreshCw className="h-3.5 w-3.5" /> Refrescar
          </button>
          <button onClick={openCreate}
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition"
                  data-testid="carriers-panel-create">
            <Plus className="h-3.5 w-3.5" /> Nuevo
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Nombre", "Código", "API", "Conexión", "Pulling", "Webhook", "Status", "Acciones"].map((h) => (
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && !loading && (
              <tr><td colSpan={8} className="text-center px-4 py-10 text-sm text-mye-ink-muted font-mono">
                {items.length === 0 ? "Sin carriers — crea el primero con \u201CNuevo\u201D." : `Sin coincidencias para \u201C${search}\u201D.`}
              </td></tr>
            )}
            {filtered.map((c) => {
              const h = healthByCode[c.id] || {};
              return (
                <tr key={c.id} className="border-t border-mye-border" data-testid={`carriers-panel-row-${c.code}`}>
                  <td className="px-4 py-2.5">{c.name}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px]">{c.code}</td>
                  <td className="px-4 py-2.5">{c.has_api ? "✓" : "—"}</td>
                  <td className="px-4 py-2.5">
                    {h.has_adapter == null ? (
                      <span className="text-xs text-mye-ink-muted font-mono">—</span>
                    ) : !h.has_adapter ? (
                      <span className="inline-flex items-center gap-1 text-xs text-mye-ink-muted font-mono">
                        sin adapter
                      </span>
                    ) : h.pingable ? (
                      <span className="inline-flex items-center gap-1 text-xs text-status-resolved font-mono">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {h.is_mock ? "mock" : "real · 200 OK"}
                      </span>
                    ) : h.is_mock ? (
                      <span className="inline-flex items-center gap-1 text-xs text-status-waiting font-mono">
                        <Activity className="h-3.5 w-3.5" /> mock
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-status-escalated font-mono">
                        <AlertTriangle className="h-3.5 w-3.5" /> sin respuesta
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">{c.pulling_supported ? "✓" : "—"}</td>
                  <td className="px-4 py-2.5">{c.webhook_supported ? "✓" : "—"}</td>
                  <td className="px-4 py-2.5"><StatusPill v={c.status} /></td>
                  <td className="px-4 py-2.5 space-x-2">
                    <button onClick={() => openEdit(c)}
                            data-testid={`carrier-edit-${c.code}`}
                            className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline">
                      <Pencil className="h-3 w-3" /> Editar
                    </button>
                    <button onClick={() => ping(c)}
                            data-testid={`carrier-ping-${c.code}`}
                            className="text-xs text-mye-accent hover:underline">
                      Probar
                    </button>
                    <button onClick={() => { setTrackOpen(c.id); setTrackTid(""); setTrackResult(null); setTrackErr(null); }}
                            data-testid={`carrier-track-${c.code}`}
                            className="text-xs text-mye-accent hover:underline">
                      Rastrear
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Create/Edit modal */}
      {open && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" data-testid="carriers-panel-dialog">
          <div className="bg-white border border-mye-border rounded-lg shadow-xl w-full max-w-lg animate-fade-in max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border sticky top-0 bg-white">
              <div className="font-medium text-sm">{editingId ? "Editar" : "Crear"} · Carrier</div>
              <button onClick={() => { setOpen(false); setEditingId(null); }} className="text-mye-ink-muted hover:text-mye-ink">
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={submit} className="p-5 space-y-4">
              {[
                { name: "name", label: "Nombre", required: true, placeholder: "Routal" },
                { name: "code", label: "Código (snake_case)", required: true, placeholder: "routal", createOnly: true },
                { name: "has_api", label: "Tiene API", type: "checkbox" },
                { name: "pulling_supported", label: "Soporta pulling", type: "checkbox" },
                { name: "webhook_supported", label: "Soporta webhook", type: "checkbox" },
                { name: "api_url", label: "API URL (opcional)", placeholder: "https://api.routal.com" },
                { name: "api_creds", label: editingId ? "Credenciales API (deja vacío para conservar)" : "Credenciales API", type: "password", secret: true },
              ].filter((f) => !(editingId && f.createOnly)).map((f) => (
                <FieldInput key={f.name} field={f} value={form[f.name]}
                            onChange={(v) => setForm((s) => ({ ...s, [f.name]: v }))} />
              ))}
              {editingId && (
                <label className="block">
                  <span className="block text-xs font-mono uppercase tracking-wider text-mye-ink-muted mb-1">Status</span>
                  <select value={form.status || "active"}
                          onChange={(e) => setForm((s) => ({ ...s, status: e.target.value }))}
                          className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm">
                    <option value="active">Activo</option>
                    <option value="inactive">Inactivo</option>
                  </select>
                </label>
              )}
              <div className="text-[11px] text-mye-ink-muted">
                Tip: el adapter se busca por <code className="bg-mye-app/50 px-1 rounded">code</code>.
                Routal real está disponible con <code className="bg-mye-app/50 px-1 rounded">routal</code>;
                FedEx/DHL/Estafeta/99Min/Paqex son mocks.
              </div>
              {error && (
                <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated">
                  {error}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => { setOpen(false); setEditingId(null); }}
                        className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft transition">
                  Cancelar
                </button>
                <button type="submit" disabled={busy}
                        className="rounded-md bg-mye-accent text-white px-4 py-1.5 text-sm hover:brightness-110 transition disabled:opacity-60"
                        data-testid="carriers-panel-submit">
                  {busy ? "Guardando…" : (editingId ? "Actualizar" : "Guardar")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Track modal */}
      {trackOpen && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" data-testid="carriers-track-dialog"
             onClick={() => setTrackOpen(null)}>
          <div className="bg-white border border-mye-border rounded-lg shadow-xl w-full max-w-2xl animate-fade-in"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border">
              <div className="font-medium text-sm flex items-center gap-2">
                <Search className="h-4 w-4 text-mye-accent" />
                Rastrear vía adapter — {items.find((i) => i.id === trackOpen)?.name}
              </div>
              <button onClick={() => setTrackOpen(null)} className="text-mye-ink-muted hover:text-mye-ink">
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={track} className="p-5 space-y-3">
              <p className="text-xs text-mye-ink-muted">
                El adapter ejecuta <code className="bg-mye-app/50 px-1 rounded">get_raw_status</code> y la
                CAE normaliza el resultado.
              </p>
              <div className="flex gap-2">
                <input value={trackTid} onChange={(e) => setTrackTid(e.target.value)}
                       placeholder="tracking_id (ej. 16lfgtGFKg2XxT7B)"
                       data-testid="carriers-track-input"
                       className="flex-1 rounded-md border border-mye-border px-3 py-2 text-sm font-mono" />
                <button type="submit" disabled={trackBusy || !trackTid.trim()}
                        data-testid="carriers-track-submit"
                        className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-50">
                  {trackBusy ? "Buscando…" : "Rastrear"}
                </button>
              </div>
              {trackErr && (
                <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated">
                  {trackErr}
                </div>
              )}
              {trackResult && (
                <div className="space-y-3" data-testid="carriers-track-result">
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <Card label="Raw code"><span className="font-mono">{trackResult.raw.raw_code}</span></Card>
                    <Card label="Canonical"><span className="font-mono">{trackResult.normalized.canonical_status}</span></Card>
                    <Card label="Display ES">{trackResult.normalized.display_label_es}</Card>
                    <Card label="Estado">
                      {trackResult.normalized.is_terminal && <span className="text-status-resolved">terminal</span>}
                      {trackResult.normalized.requires_action && <span className="text-status-escalated"> · acción requerida</span>}
                      {!trackResult.normalized.is_terminal && !trackResult.normalized.requires_action && (
                        <span className="text-mye-ink-muted">en seguimiento</span>
                      )}
                    </Card>
                  </div>
                  <details className="text-xs">
                    <summary className="cursor-pointer font-mono text-mye-ink-muted">Raw payload</summary>
                    <pre className="mt-2 bg-mye-app rounded px-2 py-1 text-[11px] font-mono text-mye-ink-muted overflow-x-auto">
{JSON.stringify(trackResult.raw.raw_payload, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </form>
          </div>
        </div>
      )}
    </div>
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

function TenantsPanel() {
  return (
    <CrudPanel
      title="Tenants (root_dev)"
      testid="tenants-panel"
      listEndpoint="/admin/tenants"
      editPath="/admin/tenants"
      searchKeys={["name", "slug", "id"]}
      columns={[
        { key: "name", label: "Nombre" },
        { key: "slug", label: "Slug", mono: true },
        { key: "status", label: "Status", render: (r) => <StatusPill v={r.status} /> },
        { key: "id", label: "ID", mono: true, render: (r) => <span className="text-mye-ink-muted">{r.id.slice(0, 8)}…</span> },
      ]}
      formFields={[
        { name: "name", label: "Nombre", required: true, placeholder: "Mensajería y Estrategias" },
        { name: "slug", label: "Slug (a-z0-9-)", required: true, createOnly: true, placeholder: "m-y-e" },
        { name: "status", label: "Status", default: "active", options: [
          { value: "active", label: "Activo" }, { value: "maintenance", label: "Mantenimiento" }, { value: "suspended", label: "Suspendido" },
        ]},
      ]}
      payloadFromForm={(f) => ({ name: f.name, slug: f.slug, status: f.status })}
      editPayloadFromForm={(f) => ({ name: f.name, status: f.status })}
    />
  );
}

function StatusPill({ v }) {
  const map = {
    active: "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
    inactive: "bg-status-closed/10 text-status-closed border-status-closed/30",
    maintenance: "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
    suspended: "bg-status-escalated/10 text-status-escalated border-status-escalated/30",
  };
  return (
    <span className={"inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-mono " + (map[v] || "border-mye-border text-mye-ink-muted")}>
      {v || "—"}
    </span>
  );
}

function fmt(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" }); }
  catch { return iso; }
}

