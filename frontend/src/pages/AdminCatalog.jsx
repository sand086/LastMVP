import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Tag, BookOpen, ShieldCheck, ArrowLeft, LogOut, Plus, X,
  RefreshCw, AlertTriangle, Lock, CheckCircle2, Search, Pencil,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";

const TABS = [
  { key: "motivos",   label: "Motivos",   icon: Tag },
  { key: "soluciones",label: "Soluciones",icon: BookOpen },
  { key: "permisos",  label: "Permisos de automatización", icon: ShieldCheck },
];

export default function AdminCatalog() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("motivos");

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-catalog-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Admin · Catálogo & Automatización</div>
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
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 03 · Catálogo + Permisos
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Motivos, Soluciones y Matriz</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            La automatización <span className="text-mye-accent font-medium">nunca se impone — se contrata</span>:
            cada combinación cliente × solución × canal arranca <span className="font-mono">deny</span>{" "}
            y solo se activa con permiso explícito (R03).
          </p>
        </section>

        <div className="flex flex-wrap gap-1 border-b border-mye-border" data-testid="catalog-tabs">
          {TABS.map((t) => {
            const Active = tab === t.key;
            const Icon = t.icon;
            return (
              <button key={t.key} onClick={() => setTab(t.key)}
                      className={"inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-md transition-colors -mb-px " +
                        (Active ? "bg-white border border-mye-border border-b-white text-mye-ink"
                                : "text-mye-ink-muted hover:text-mye-ink")}
                      data-testid={`catalog-tab-${t.key}`}>
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="bg-white border border-mye-border rounded-b-lg rounded-tr-lg overflow-hidden">
          {tab === "motivos"    && <MotivosPanel />}
          {tab === "soluciones" && <SolucionesPanel />}
          {tab === "permisos"   && <PermisosPanel />}
        </div>
      </main>
    </div>
  );
}

// ─── Motivos ──────────────────────────────────────────────────────────────
function MotivosPanel() {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen]   = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy]   = useState(false);
  const [form, setForm]   = useState({ code: "", name: "", restricted: false, active: true });

  async function refresh() {
    const r = await api.get("/admin/motivos");
    setItems(r.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((m) => (m.code + " " + m.name).toLowerCase().includes(q));
  }, [items, search]);

  function openCreate() {
    setEditingId(null);
    setForm({ code: "", name: "", restricted: false, active: true });
    setOpen(true); setError(null);
  }
  function openEdit(m) {
    setEditingId(m.id);
    setForm({ code: m.code, name: m.name, restricted: !!m.restricted, active: !!m.active });
    setOpen(true); setError(null);
  }

  async function submit(e) {
    e.preventDefault(); setError(null); setBusy(true);
    try {
      if (editingId) {
        await api.patch(`/admin/motivos/${editingId}`, {
          name: form.name, restricted: form.restricted, active: form.active,
        });
      } else {
        await api.post("/admin/motivos", form);
      }
      setOpen(false); setEditingId(null);
      setForm({ code: "", name: "", restricted: false, active: true });
      await refresh();
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  async function toggleRestricted(id, val) {
    await api.patch(`/admin/motivos/${id}`, { restricted: val });
    await refresh();
  }

  return (
    <div data-testid="motivos-panel">
      <PanelHeader title="Motivos" subtitle={`${filtered.length}${search ? ` / ${items.length}` : ""} registros`}
                   onCreate={openCreate} onRefresh={refresh}
                   testid="motivos-panel"
                   search={search} onSearch={setSearch} />
      <table className="w-full text-sm">
        <thead className="bg-mye-app/60">
          <tr>
            {["Código", "Nombre", "Restricted (R03)", "Activo", "ID", "Acciones"].map((h) => (
              <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">
              {items.length === 0 ? "Sin motivos — crea el primero." : `Sin coincidencias para \u201C${search}\u201D.`}
            </td></tr>
          )}
          {filtered.map((m) => (
            <tr key={m.id} className="border-t border-mye-border hover:bg-mye-primary-soft/40 transition" data-testid="motivos-row">
              <td className="px-4 py-2.5 font-mono text-[12px]">{m.code}</td>
              <td className="px-4 py-2.5">{m.name}</td>
              <td className="px-4 py-2.5">
                <button
                  onClick={() => toggleRestricted(m.id, !m.restricted)}
                  className={"inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-mono transition " +
                    (m.restricted
                      ? "border-status-escalated/40 bg-status-escalated/10 text-status-escalated"
                      : "border-mye-border text-mye-ink-muted hover:bg-mye-primary-soft")}
                  data-testid={`motivo-restricted-${m.id}`}>
                  {m.restricted ? <><Lock className="h-3 w-3" /> bloqueado</> : "permitido"}
                </button>
              </td>
              <td className="px-4 py-2.5">{m.active ? "✓" : "—"}</td>
              <td className="px-4 py-2.5 font-mono text-[11px] text-mye-ink-muted">{m.id.slice(0, 8)}…</td>
              <td className="px-4 py-2.5">
                <button onClick={() => openEdit(m)}
                        data-testid={`motivos-edit-${m.id}`}
                        className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline">
                  <Pencil className="h-3 w-3" /> Editar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {open && (
        <Dialog title={editingId ? "Editar motivo" : "Nuevo motivo"} onClose={() => { setOpen(false); setEditingId(null); }} testid="motivos-dialog">
          <form onSubmit={submit} className="space-y-4">
            <Field label="Código (UPPER_SNAKE)" required>
              <input value={form.code}
                     onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                     required disabled={!!editingId}
                     className={inputCls + (editingId ? " opacity-60 cursor-not-allowed" : "")}
                     placeholder="DIR_INSUFICIENTE" data-testid="field-code" />
            </Field>
            <Field label="Nombre" required>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                     required className={inputCls} placeholder="Dirección insuficiente" data-testid="field-name" />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.restricted}
                     onChange={(e) => setForm({ ...form, restricted: e.target.checked })}
                     className="h-4 w-4 accent-mye-accent" data-testid="field-restricted" />
              <span>Motivo restringido (nunca se automatiza · R03)</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.active}
                     onChange={(e) => setForm({ ...form, active: e.target.checked })}
                     className="h-4 w-4 accent-mye-accent" data-testid="field-active" />
              <span>Activo (visible en catálogo)</span>
            </label>
            {error && <ErrorRow msg={error} />}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => { setOpen(false); setEditingId(null); }} className={btnGhost}>Cancelar</button>
              <button type="submit" disabled={busy} className={btnPrimary} data-testid="motivos-submit">
                {busy ? "Guardando…" : (editingId ? "Actualizar" : "Guardar")}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}

// ─── Soluciones ───────────────────────────────────────────────────────────
function SolucionesPanel() {
  const [items, setItems] = useState([]);
  const [motivos, setMotivos] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen]   = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy]   = useState(false);
  const [form, setForm]   = useState({
    motivo_id: "", name: "", template_email: "", template_wa: "", automatable: false,
  });

  async function refresh() {
    const [a, b] = await Promise.all([api.get("/admin/soluciones"), api.get("/admin/motivos")]);
    setItems(a.data?.data?.items || []);
    setMotivos(b.data?.data?.items || []);
  }
  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (motivos.length && !form.motivo_id) setForm((f) => ({ ...f, motivo_id: motivos[0].id }));
  }, [motivos]);   

  const filtered = useMemo(() => {
    if (!search.trim()) return items;
    const q = search.trim().toLowerCase();
    return items.filter((s) => {
      const motivo = motivos.find((m) => m.id === s.motivo_id);
      return (s.name + " " + (motivo?.code || "")).toLowerCase().includes(q);
    });
  }, [items, search, motivos]);

  function openCreate() {
    setEditingId(null);
    setForm({
      motivo_id: motivos[0]?.id || "", name: "",
      template_email: "", template_wa: "", automatable: false,
    });
    setOpen(true); setError(null);
  }
  function openEdit(s) {
    setEditingId(s.id);
    setForm({
      motivo_id: s.motivo_id, name: s.name,
      template_email: s.template_email || "",
      template_wa: s.template_wa || "",
      automatable: !!s.automatable,
    });
    setOpen(true); setError(null);
  }

  async function submit(e) {
    e.preventDefault(); setError(null); setBusy(true);
    try {
      if (editingId) {
        await api.patch(`/admin/soluciones/${editingId}`, {
          name: form.name,
          template_email: form.template_email || null,
          template_wa: form.template_wa || null,
          automatable: form.automatable,
        });
      } else {
        await api.post("/admin/soluciones", { ...form, steps: [] });
      }
      setOpen(false); setEditingId(null);
      setForm({ motivo_id: motivos[0]?.id || "", name: "", template_email: "", template_wa: "", automatable: false });
      await refresh();
    } catch (e) { setError(e.response?.data?.errors?.[0]?.message || e.message); }
    finally { setBusy(false); }
  }

  if (motivos.length === 0) {
    return <div className="px-6 py-10 text-sm text-mye-ink-muted">Crea al menos un motivo antes de registrar soluciones.</div>;
  }

  return (
    <div data-testid="soluciones-panel">
      <PanelHeader title="Soluciones" subtitle={`${filtered.length}${search ? ` / ${items.length}` : ""} registros`}
                   onCreate={openCreate} onRefresh={refresh}
                   testid="soluciones-panel"
                   search={search} onSearch={setSearch} />
      <table className="w-full text-sm">
        <thead className="bg-mye-app/60">
          <tr>
            {["Nombre", "Motivo", "Automatable", "Email tpl", "WhatsApp tpl", "Acciones"].map((h) => (
              <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-mye-ink-muted font-mono">
              {items.length === 0 ? "Sin soluciones todavía." : `Sin coincidencias para \u201C${search}\u201D.`}
            </td></tr>
          )}
          {filtered.map((s) => {
            const motivo = motivos.find((m) => m.id === s.motivo_id);
            return (
              <tr key={s.id} className="border-t border-mye-border hover:bg-mye-primary-soft/40 transition" data-testid="soluciones-row">
                <td className="px-4 py-2.5">{s.name}</td>
                <td className="px-4 py-2.5 font-mono text-[12px]">{motivo?.code || s.motivo_id.slice(0, 8)}</td>
                <td className="px-4 py-2.5">
                  {s.automatable
                    ? <span className="inline-flex items-center gap-1 text-status-resolved font-mono text-[11px]"><CheckCircle2 className="h-3.5 w-3.5" /> sí</span>
                    : <span className="text-mye-ink-muted font-mono text-[11px]">no</span>}
                </td>
                <td className="px-4 py-2.5 text-mye-ink-muted">{s.template_email ? "✓" : "—"}</td>
                <td className="px-4 py-2.5 text-mye-ink-muted">{s.template_wa ? "✓" : "—"}</td>
                <td className="px-4 py-2.5">
                  <button onClick={() => openEdit(s)}
                          data-testid={`soluciones-edit-${s.id}`}
                          className="inline-flex items-center gap-1 text-xs text-mye-accent hover:underline">
                    <Pencil className="h-3 w-3" /> Editar
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {open && (
        <Dialog title={editingId ? "Editar solución" : "Nueva solución"} onClose={() => { setOpen(false); setEditingId(null); }} testid="soluciones-dialog">
          <form onSubmit={submit} className="space-y-4">
            <Field label="Motivo" required>
              <select className={inputCls + (editingId ? " opacity-60 cursor-not-allowed" : "")}
                      value={form.motivo_id} disabled={!!editingId}
                      onChange={(e) => setForm({ ...form, motivo_id: e.target.value })}
                      data-testid="field-motivo">
                {motivos.map((m) => <option key={m.id} value={m.id}>{m.code} — {m.name}</option>)}
              </select>
            </Field>
            <Field label="Nombre" required>
              <input className={inputCls} value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })}
                     placeholder="Confirmar referencias" required data-testid="field-name" />
            </Field>
            <Field label="Plantilla correo (opcional)">
              <textarea className={inputCls + " min-h-[80px] resize-y"} value={form.template_email}
                        onChange={(e) => setForm({ ...form, template_email: e.target.value })}
                        placeholder="Hola {{cliente}}, …" />
            </Field>
            <Field label="Plantilla WhatsApp (opcional)">
              <textarea className={inputCls + " min-h-[60px] resize-y"} value={form.template_wa}
                        onChange={(e) => setForm({ ...form, template_wa: e.target.value })}
                        placeholder="Hola {{cliente}} 📦 …" />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.automatable}
                     onChange={(e) => setForm({ ...form, automatable: e.target.checked })}
                     className="h-4 w-4 accent-mye-accent" data-testid="field-automatable" />
              <span>Automatable (puede ejecutarse sin agente, sujeto a R03)</span>
            </label>
            {error && <ErrorRow msg={error} />}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => { setOpen(false); setEditingId(null); }} className={btnGhost}>Cancelar</button>
              <button type="submit" disabled={busy} className={btnPrimary} data-testid="soluciones-submit">
                {busy ? "Guardando…" : (editingId ? "Actualizar" : "Guardar")}
              </button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
}

// ─── Permisos (matrix) ───────────────────────────────────────────────────
const CHANNELS = ["email", "whatsapp", "api"];

function PermisosPanel() {
  const [clients, setClients] = useState([]);
  const [soluciones, setSoluciones] = useState([]);
  const [motivos, setMotivos] = useState([]);
  const [clientId, setClientId] = useState("");
  const [perms, setPerms] = useState({}); // { "solId|channel": true|false }
  const [busyKey, setBusyKey] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get("/admin/clients"),
      api.get("/admin/soluciones"),
      api.get("/admin/motivos"),
    ]).then(([c, s, m]) => {
      const cl = c.data?.data?.items || [];
      setClients(cl);
      setSoluciones(s.data?.data?.items || []);
      setMotivos(m.data?.data?.items || []);
      if (cl[0]) setClientId(cl[0].id);
    });
  }, []);

  useEffect(() => {
    if (!clientId) return;
    api.get("/admin/automation-permissions", { params: { client_id: clientId } }).then((r) => {
      const map = {};
      (r.data?.data?.items || []).forEach((p) => {
        map[`${p.solucion_id}|${p.channel}`] = !!p.allowed;
      });
      setPerms(map);
    });
  }, [clientId]);

  async function toggle(solId, channel) {
    if (!clientId) return;
    const key = `${solId}|${channel}`;
    setBusyKey(key);
    const next = !perms[key];
    try {
      await api.put("/admin/automation-permissions", {
        client_id: clientId, solucion_id: solId, channel, allowed: next,
      });
      setPerms((p) => ({ ...p, [key]: next }));
    } catch (_e) { /* surface visually below */ }
    finally { setBusyKey(null); }
  }

  if (clients.length === 0) {
    return <div className="px-6 py-10 text-sm text-mye-ink-muted">Registra clientes en la página de Jerarquía antes de configurar permisos.</div>;
  }
  if (soluciones.length === 0) {
    return <div className="px-6 py-10 text-sm text-mye-ink-muted">Crea al menos una solución antes de configurar permisos.</div>;
  }

  return (
    <div data-testid="permisos-panel">
      <div className="flex flex-wrap items-center gap-3 px-5 py-4 border-b border-mye-border">
        <div>
          <div className="font-medium text-sm">Matriz de permisos</div>
          <div className="text-xs text-mye-ink-muted font-mono">Default-deny por R03 · activación queda registrada</div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs font-mono text-mye-ink-muted">Cliente:</span>
          <select className={inputCls + " min-w-[220px]"} value={clientId}
                  onChange={(e) => setClientId(e.target.value)}
                  data-testid="permisos-client-select">
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              <th className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">Solución</th>
              <th className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">Motivo</th>
              {CHANNELS.map((ch) => (
                <th key={ch} className="text-center font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">
                  {ch}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {soluciones.map((s) => {
              const motivo = motivos.find((m) => m.id === s.motivo_id);
              const blockedByMotivo = motivo?.restricted || !s.automatable;
              return (
                <tr key={s.id} className="border-t border-mye-border" data-testid={`permisos-row-${s.id}`}>
                  <td className="px-4 py-2.5">{s.name}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px]">
                    {motivo?.code}{" "}
                    {motivo?.restricted && (
                      <span className="ml-1 inline-flex items-center gap-1 text-status-escalated text-[10px]" title="Motivo bloqueado por R03">
                        <Lock className="h-3 w-3" /> R03
                      </span>
                    )}
                  </td>
                  {CHANNELS.map((ch) => {
                    const key = `${s.id}|${ch}`;
                    const v = perms[key] || false;
                    return (
                      <td key={ch} className="px-4 py-2.5 text-center">
                        <button
                          disabled={blockedByMotivo || busyKey === key}
                          onClick={() => toggle(s.id, ch)}
                          className={
                            "inline-flex items-center gap-1 rounded-full border px-3 py-0.5 text-[11px] font-mono transition " +
                            (blockedByMotivo
                              ? "border-mye-border text-mye-ink-muted opacity-50 cursor-not-allowed"
                              : v
                                ? "border-status-resolved/40 bg-status-resolved/10 text-status-resolved hover:brightness-95"
                                : "border-mye-border text-mye-ink-muted hover:bg-mye-primary-soft")
                          }
                          data-testid={`perm-${s.id}-${ch}`}>
                          {blockedByMotivo ? "n/a" : v ? "permitido" : "denegado"}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="px-5 py-3 border-t border-mye-border bg-mye-app/40 text-xs text-mye-ink-muted font-mono">
        ℹ Cualquier solución cuyo motivo esté marcado como restringido (R03) o que no sea
        automatable queda bloqueada en la matriz. Modifícalas en sus pestañas correspondientes.
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

function PanelHeader({ title, subtitle, onRefresh, onCreate, testid, search, onSearch }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-mye-border flex-wrap">
      <div>
        <div className="font-medium">{title}</div>
        <div className="text-xs text-mye-ink-muted font-mono">{subtitle}</div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {typeof onSearch === "function" && (
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mye-ink-muted" />
            <input
              type="text"
              value={search ?? ""}
              onChange={(e) => onSearch(e.target.value)}
              placeholder="Buscar…"
              className="rounded-md border border-mye-border bg-white pl-7 pr-2 py-1.5 text-xs outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20 transition-colors w-44"
              data-testid={`${testid}-search`}
            />
          </div>
        )}
        <button onClick={onRefresh} className={btnGhost + " inline-flex items-center gap-1 text-xs"} data-testid={`${testid}-refresh`}>
          <RefreshCw className="h-3.5 w-3.5" /> Refrescar
        </button>
        <button onClick={onCreate} className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition" data-testid={`${testid}-create`}>
          <Plus className="h-3.5 w-3.5" /> Nuevo
        </button>
      </div>
    </div>
  );
}

function Dialog({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4" data-testid={testid}>
      <div className="bg-white border border-mye-border rounded-lg shadow-xl w-full max-w-lg animate-fade-in">
        <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border">
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
      <AlertTriangle className="h-4 w-4 mt-0.5 flex-none" />
      <span>{msg}</span>
    </div>
  );
}
