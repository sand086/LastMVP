/**
 * Users panel — gestión de usuarios del tenant, gateada por root_dev | superadmin.
 *
 * Acciones CRUD + reset password con banner temporal + soft-delete.
 * Toda mutación queda registrada en `user_audit_log` (visible en /admin/security
 * vía UserAuditLogSection — root_dev only).
 *
 * Extraído de AdminHierarchy.jsx en iter20 para mejorar mantenibilidad.
 */
import { useEffect, useState } from "react";
import {
  Plus, X, RefreshCw, Lock, CheckCircle2, AlertTriangle, Search,
  Pencil, Users, KeyRound, Copy, Trash2,
} from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";


// fmt is duplicated here (also exists in AdminHierarchy) to keep this module
// self-contained without creating a one-line shared utility module.
function fmt(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" }); }
  catch { return iso; }
}


// ─────────────────────────────────────────────────────────────────────────
// Users panel — root_dev | superadmin only
// ─────────────────────────────────────────────────────────────────────────
const ROLE_LABEL = {
  root_dev: "Root Dev", superadmin: "Superadmin", admin: "Admin",
  coordinator: "Coordinator", supervisor: "Supervisor", agent: "Agente",
  client_viewer: "Client Viewer", client_auditor: "Client Auditor",
};

const STATUS_LABEL = {
  active: { l: "Activo", c: "bg-status-resolved/10 text-status-resolved border-status-resolved/30" },
  suspended: { l: "Suspendido", c: "bg-status-waiting/10 text-status-waiting border-status-waiting/30" },
  deleted: { l: "Eliminado", c: "bg-status-closed/10 text-status-closed border-status-closed/30" },
};

export default function UsersPanel({ currentUserId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(null);
  const [tempPwdBanner, setTempPwdBanner] = useState(null); // {email, password}
  const [manageableRoles, setManageableRoles] = useState([]);
  const [assignableRoles, setAssignableRoles] = useState([]);
  const [clients, setClients] = useState([]);

  async function refresh() {
    setLoading(true);
    try {
      const params = {};
      if (search) params.q = search;
      if (filterRole) params.role = filterRole;
      if (filterStatus) params.status = filterStatus;
      const [u, c] = await Promise.all([
        api.get("/admin/users", { params }),
        api.get("/admin/clients").catch(() => null),
      ]);
      const data = u.data?.data || {};
      setItems(data.items || []);
      setManageableRoles(data.manageable_roles || []);
      // Bundle G+ — roles que el actor PUEDE asignar (subset de manageable_roles)
      setAssignableRoles(data.assignable_roles || data.manageable_roles || []);
      setClients(c?.data?.data?.items || []);
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh();   }, [filterRole, filterStatus]);
  // Search debounce
  useEffect(() => {
    const id = setTimeout(refresh, 300);
    return () => clearTimeout(id);
     
  }, [search]);

  async function resetPwd(u) {
    if (!window.confirm(`¿Resetear password de ${u.email}? Se generará una temporal.`)) return;
    try {
      const r = await api.post(`/admin/users/${u.id}/reset-password`);
      const tmp = r.data?.data?.temp_password;
      setTempPwdBanner({ email: u.email, password: tmp });
      toast.success("Password reseteada");
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }
  async function softDelete(u) {
    if (u.id === currentUserId) {
      toast.error("No podés eliminarte a vos mismo.");
      return;
    }
    if (!window.confirm(`¿Eliminar ${u.email}? (soft-delete: status=deleted)`)) return;
    try {
      await api.delete(`/admin/users/${u.id}`);
      toast.success("Usuario marcado como eliminado");
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  return (
    <div className="p-5 space-y-4" data-testid="users-panel">
      {/* Banner de password temporal */}
      {tempPwdBanner && (
        <div className="rounded-lg border border-mye-accent/40 bg-mye-accent/5 p-4 flex items-start gap-3"
             data-testid="users-temp-password-banner">
          <KeyRound className="h-4 w-4 text-mye-accent mt-0.5" />
          <div className="flex-1 space-y-1">
            <div className="text-sm font-medium">
              Password temporal generada para <span className="font-mono">{tempPwdBanner.email}</span>
            </div>
            <div className="text-xs text-mye-ink-muted">
              Compartila por canal seguro · el usuario deberá cambiarla en el primer login. NO se mostrará nuevamente.
            </div>
            <div className="mt-2 flex items-center gap-2">
              <code className="font-mono text-base bg-white border border-mye-border rounded px-3 py-1.5 select-all"
                    data-testid="users-temp-password-value">{tempPwdBanner.password}</code>
              <button onClick={async () => {
                try {
                  await navigator.clipboard?.writeText(tempPwdBanner.password);
                  toast.success("Password copiada al portapapeles");
                } catch {
                  toast.error("No se pudo copiar. Copiala manualmente.");
                }
              }}
                      className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition"
                      data-testid="users-temp-password-copy">
                <Copy className="h-3 w-3" /> Copiar
              </button>
            </div>
          </div>
          <button onClick={() => setTempPwdBanner(null)}
                  className="text-mye-ink-muted hover:text-mye-ink"
                  data-testid="users-temp-password-close">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px] max-w-[360px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mye-ink-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
                 placeholder="Buscar por email…"
                 className="w-full rounded-md border border-mye-border bg-white pl-7 pr-3 py-1.5 text-xs"
                 data-testid="users-search" />
        </div>
        <select value={filterRole} onChange={(e) => setFilterRole(e.target.value)}
                className="rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs font-mono"
                data-testid="users-filter-role">
          <option value="">— Todos los roles —</option>
          {Object.keys(ROLE_LABEL).map((r) =>
            <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}
                className="rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs font-mono"
                data-testid="users-filter-status">
          <option value="">— Todos —</option>
          <option value="active">Activos</option>
          <option value="suspended">Suspendidos</option>
          <option value="deleted">Eliminados</option>
        </select>
        <button onClick={refresh}
                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                data-testid="users-refresh">
          <RefreshCw className={"h-3.5 w-3.5 " + (loading ? "animate-spin" : "")} /> Refrescar
        </button>
        <button onClick={() => setShowCreate(true)}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition"
                data-testid="users-create-btn">
          <Plus className="h-3.5 w-3.5" /> Nuevo usuario
        </button>
      </div>

      {/* Tabla */}
      <div className="bg-white border border-mye-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-mye-app/60">
            <tr>
              {["Email", "Nombre", "Rol", "Status", "Último login", "Creado", ""].map((h) =>
                <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-3 py-2.5">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr><td colSpan={7} className="px-3 py-8 text-center text-xs text-mye-ink-muted">
                Sin usuarios que coincidan con el filtro.
              </td></tr>
            )}
            {items.map((u) => {
              const st = STATUS_LABEL[u.status] || STATUS_LABEL.active;
              const isSelf = u.id === currentUserId;
              const isRoot = u.role === "root_dev";
              return (
                <tr key={u.id} className="border-t border-mye-border hover:bg-mye-primary-soft/30 transition"
                    data-testid={`users-row-${u.id}`}>
                  <td className="px-3 py-2.5 font-mono text-xs">{u.email}</td>
                  <td className="px-3 py-2.5 text-mye-ink-muted">{u.name || "—"}</td>
                  <td className="px-3 py-2.5">
                    <span className="inline-flex items-center rounded-full border border-mye-border bg-mye-app px-2 py-0.5 text-[11px] font-mono">
                      {ROLE_LABEL[u.role] || u.role}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono " + st.c}>
                      {st.l}
                    </span>
                    {u.must_reset_password && (
                      <span className="ml-1 inline-flex items-center gap-1 text-[10px] font-mono text-status-waiting"
                            title="Debe resetear contraseña en próximo login">
                        <KeyRound className="h-2.5 w-2.5" /> reset
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-mye-ink-muted">{fmt(u.last_login_at)}</td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-mye-ink-muted">{fmt(u.created_at)}</td>
                  <td className="px-3 py-2.5 text-right space-x-1">
                    <button onClick={() => setShowEdit(u)} disabled={isRoot}
                            title={isRoot ? "Los usuarios root_dev no pueden modificarse" : "Editar"}
                            className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-primary-soft transition disabled:opacity-40 disabled:cursor-not-allowed"
                            data-testid={`users-edit-${u.id}`}>
                      <Pencil className="h-3 w-3" /> Editar
                    </button>
                    <button onClick={() => resetPwd(u)} disabled={isRoot}
                            title={isRoot ? "No se puede resetear root_dev" : "Generar password temporal"}
                            className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-primary-soft transition disabled:opacity-40 disabled:cursor-not-allowed"
                            data-testid={`users-reset-${u.id}`}>
                      <KeyRound className="h-3 w-3" /> Reset
                    </button>
                    <button onClick={() => softDelete(u)} disabled={isRoot || isSelf || u.status === "deleted"}
                            title={isSelf ? "No te podés eliminar a vos mismo"
                                          : isRoot ? "No se puede eliminar root_dev"
                                          : u.status === "deleted" ? "Ya eliminado" : "Soft-delete"}
                            className="inline-flex items-center gap-1 rounded-md border border-status-escalated/30 bg-white px-2 py-1 text-[11px] text-status-escalated hover:bg-status-escalated/5 transition disabled:opacity-40 disabled:cursor-not-allowed"
                            data-testid={`users-delete-${u.id}`}>
                      <Trash2 className="h-3 w-3" /> Eliminar
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <UserModal mode="create" manageableRoles={assignableRoles} clients={clients}
                   onClose={() => setShowCreate(false)}
                   onSuccess={(temp) => {
                     setShowCreate(false);
                     if (temp) setTempPwdBanner(temp);
                     refresh();
                   }} />
      )}
      {showEdit && (
        <UserModal mode="edit" user={showEdit} manageableRoles={assignableRoles} clients={clients}
                   onClose={() => setShowEdit(null)}
                   onSuccess={() => { setShowEdit(null); refresh(); }} />
      )}
    </div>
  );
}

function UserModal({ mode, user, manageableRoles, clients, onClose, onSuccess }) {
  const [form, setForm] = useState(() => ({
    email: user?.email || "",
    name: user?.name || "",
    role: user?.role || "agent",
    status: user?.status || "active",
    client_id: user?.client_id || "",
  }));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const requiresClientId = ["client_viewer", "client_auditor"].includes(form.role);
  // Iter57 — roles internos que pueden (opcionalmente) limitarse a clientes.
  const supportsClientScopes = [
    "client_viewer", "client_auditor",
    "agent", "supervisor", "coordinator",
  ].includes(form.role);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      if (mode === "create") {
        const payload = { ...form };
        if (!requiresClientId) delete payload.client_id;
        const r = await api.post("/admin/users", payload);
        const data = r.data?.data || {};
        toast.success(`Usuario ${data.email} creado`);
        onSuccess({ email: data.email, password: data.temp_password });
      } else {
        const payload = {};
        ["email", "name", "role", "status", "client_id"].forEach((k) => {
          if (form[k] !== (user[k] ?? "")) payload[k] = form[k];
        });
        if (!requiresClientId) delete payload.client_id;
        if (Object.keys(payload).length === 0) {
          onClose();
          return;
        }
        await api.patch(`/admin/users/${user.id}`, payload);
        toast.success("Usuario actualizado");
        onSuccess();
      }
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-mye-ink/40 backdrop-blur-sm"
         onClick={onClose}
         data-testid={`users-modal-${mode}`}>
      <form onSubmit={submit}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg border border-mye-border w-[440px] max-w-[95vw] p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-mye-accent" />
          <h3 className="font-medium text-sm">
            {mode === "create" ? "Nuevo usuario" : "Editar usuario"}
          </h3>
          <button type="button" onClick={onClose}
                  className="ml-auto text-mye-ink-muted hover:text-mye-ink">
            <X className="h-4 w-4" />
          </button>
        </div>

        <Field label="Email" required>
          <input type="email" required value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })}
                 placeholder="user@example.com"
                 className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                 data-testid={`users-modal-${mode}-email`} />
        </Field>
        <Field label="Nombre" required>
          <input required value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })}
                 placeholder="Juan Pérez"
                 className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
                 data-testid={`users-modal-${mode}-name`} />
        </Field>
        <Field label="Rol" required>
          <select value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono"
                  data-testid={`users-modal-${mode}-role`}>
            {(manageableRoles.length > 0 ? manageableRoles : Object.keys(ROLE_LABEL).filter((r) => r !== "root_dev")).map((r) =>
              <option key={r} value={r}>{ROLE_LABEL[r] || r}</option>)}
          </select>
        </Field>
        {requiresClientId && (
          <Field label="Cliente vinculado" required>
            <select required value={form.client_id}
                    onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                    className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm"
                    data-testid={`users-modal-${mode}-client`}>
              <option value="">— Selecciona un cliente —</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <div className="text-[10px] font-mono text-mye-ink-muted mt-1">
              {mode === "create"
                ? "El usuario externo iniciará con este cliente asignado. Podés añadir más después."
                : "Cliente primario del usuario externo."}
            </div>
          </Field>
        )}
        {mode === "edit" && supportsClientScopes && (
          <ScopesPanel userId={user.id} clients={clients} role={form.role} />
        )}
        <Field label="Status">
          <select value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono"
                  data-testid={`users-modal-${mode}-status`}>
            <option value="active">Activo</option>
            <option value="suspended">Suspendido</option>
            {mode === "edit" && <option value="deleted">Eliminado</option>}
          </select>
        </Field>

        {err && (
          <div className="rounded-md border border-status-escalated/40 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
               data-testid={`users-modal-${mode}-error`}>
            <AlertTriangle className="inline h-3 w-3 mr-1" /> {err}
          </div>
        )}

        {mode === "create" && (
          <div className="rounded-md border border-mye-border bg-mye-app/40 px-3 py-2 text-[11px] text-mye-ink-muted">
            <Lock className="inline h-3 w-3 mr-1" />
            Se generará una password temporal automática. Te la mostraremos una sola vez.
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
                  className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition">
            Cancelar
          </button>
          <button type="submit" disabled={busy}
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                  data-testid={`users-modal-${mode}-submit`}>
            {busy ? "Guardando…" : mode === "create" ? <><Plus className="h-3 w-3" /> Crear usuario</> : <><CheckCircle2 className="h-3 w-3" /> Guardar</>}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, required, children }) {
  return (
    <div className="space-y-1">
      <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
        {label}{required && <span className="text-status-escalated"> *</span>}
      </label>
      {children}
    </div>
  );
}


// ─────────────────────────────────────────────────────────────────────────
// Bundle H · ScopesPanel — gestiona los scopes (clients) de usuarios externos
// ─────────────────────────────────────────────────────────────────────────
function ScopesPanel({ userId, clients, role }) {
  const [scopes, setScopes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState("");
  const [busy, setBusy] = useState(false);
  // Iter57 — para roles internos, scope vacío = visión total del tenant.
  const isInternal = !["client_viewer", "client_auditor"].includes(role);

  async function refresh() {
    setLoading(true);
    try {
      const r = await api.get(`/admin/users/${userId}/scopes`);
      setScopes(r.data?.data?.items || []);
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [userId]);

  async function addScope() {
    if (!adding) return;
    setBusy(true);
    try {
      await api.post(`/admin/users/${userId}/scopes`, { client_id: adding });
      toast.success("Cliente añadido al scope");
      setAdding("");
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  async function removeScope(assignmentId) {
    const msg = isInternal
      ? "¿Quitar este cliente del scope? Si lo quitás todos, el usuario verá todos los clientes del tenant."
      : "¿Quitar este cliente del scope del usuario?";
    if (!window.confirm(msg)) return;
    setBusy(true);
    try {
      await api.delete(`/admin/users/${userId}/scopes/${assignmentId}`);
      toast.success("Scope eliminado");
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  const clientNameById = Object.fromEntries(clients.map((c) => [c.id, c.name]));
  const usedClientIds = new Set(scopes.map((s) => s.client_id));
  const availableClients = clients.filter((c) => !usedClientIds.has(c.id));

  return (
    <div className="border-t border-mye-border pt-3 space-y-2"
         data-testid="scopes-panel">
      <div className="flex items-center gap-2">
        <Users className="h-3.5 w-3.5 text-mye-accent" />
        <span className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
          {isInternal ? "Clientes en scope (opcional)" : "Clientes adicionales en scope"}
        </span>
        <span className="ml-auto text-[10px] font-mono text-mye-ink-muted">
          {scopes.length} {scopes.length === 1 ? "cliente" : "clientes"}
        </span>
      </div>
      {isInternal && (
        <p className="text-[10px] text-mye-ink-muted leading-tight">
          {scopes.length === 0
            ? "Sin scopes: el usuario verá tickets de TODOS los clientes del tenant."
            : "Con scopes: el usuario verá tickets SOLO de los clientes listados."}
        </p>
      )}
      {loading ? (
        <div className="text-xs text-mye-ink-muted">Cargando…</div>
      ) : (
        <ul className="space-y-1">
          {scopes.map((s) => (
            <li key={s.id}
                className="flex items-center gap-2 rounded-md bg-mye-primary-soft/30 px-2 py-1 text-xs"
                data-testid={`scope-row-${s.client_id}`}>
              <span className="font-medium truncate flex-1">
                {clientNameById[s.client_id] || s.client_id}
              </span>
              <button type="button"
                      disabled={busy || (!isInternal && scopes.length <= 1)}
                      onClick={() => removeScope(s.id)}
                      className="text-mye-ink-muted hover:text-status-escalated disabled:opacity-30 disabled:cursor-not-allowed"
                      title={(!isInternal && scopes.length <= 1) ? "No podés borrar el último scope" : "Quitar"}
                      data-testid={`scope-remove-${s.client_id}`}>
                <Trash2 className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {availableClients.length > 0 && (
        <div className="flex gap-2">
          <select value={adding}
                  onChange={(e) => setAdding(e.target.value)}
                  disabled={busy}
                  className="flex-1 rounded-md border border-mye-border bg-white px-2 py-1 text-xs"
                  data-testid="scope-add-select">
            <option value="">— Añadir otro cliente —</option>
            {availableClients.map((c) =>
              <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button type="button"
                  disabled={!adding || busy}
                  onClick={addScope}
                  className="rounded-md bg-mye-accent text-white px-3 py-1 text-xs font-medium hover:bg-mye-accent/90 disabled:opacity-40"
                  data-testid="scope-add-btn">
            <Plus className="h-3 w-3" />
          </button>
        </div>
      )}
    </div>
  );
}
