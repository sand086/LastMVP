/**
 * TenantAccessDialog — gestión de whitelist por carrier de plataforma.
 *
 *   PUT    /api/platform/carriers/{code}/access/{tenant_id}
 *   DELETE /api/platform/carriers/{code}/access/{tenant_id}
 *
 * Permite habilitar tenants específicos para heredar las creds, opcionalmente
 * con filtro de project_ids y rate_limit. Sin entries en tenant_access, el
 * carrier es "abierto" (todos los tenants heredan).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Plus, Trash2, X, Users, Power } from "lucide-react";
import { api } from "@/lib/api";


export default function TenantAccessDialog({ code, carrierName, onClose, onChanged }) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [tenants, setTenants] = useState([]);
  const [access, setAccess] = useState({});
  const [showAdd, setShowAdd] = useState(false);
  const [newEntry, setNewEntry] = useState({
    tenant_id: "", project_ids: "", rate_limit_per_min: "",
    enabled: true,
  });

  async function load() {
    setLoading(true);
    try {
      const [cfg, ts] = await Promise.all([
        api.get(`/platform/carriers/${code}`),
        api.get("/admin/tenants"),
      ]);
      setAccess(cfg.data?.data?.tenant_access || {});
      setTenants(ts.data?.data?.items || []);
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error cargando");
    } finally { setLoading(false); }
  }
  useEffect(() => { load();   }, [code]);

  function tenantLabel(tid) {
    const t = tenants.find((x) => x.id === tid);
    return t ? `${t.name} (${t.slug})` : tid;
  }

  async function grant() {
    if (!newEntry.tenant_id) return;
    setBusy(true);
    try {
      const body = {
        project_ids: newEntry.project_ids
          ? newEntry.project_ids.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        rate_limit_per_min: newEntry.rate_limit_per_min
          ? Number(newEntry.rate_limit_per_min) : null,
        enabled: newEntry.enabled,
      };
      await api.put(`/platform/carriers/${code}/access/${newEntry.tenant_id}`, body);
      toast.success("Acceso concedido");
      setNewEntry({ tenant_id: "", project_ids: "", rate_limit_per_min: "", enabled: true });
      setShowAdd(false);
      await load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error otorgando acceso");
    } finally { setBusy(false); }
  }

  async function revoke(tid) {
    if (!window.confirm(`¿Revocar acceso a ${tenantLabel(tid)} sobre ${carrierName}?`)) return;
    setBusy(true);
    try {
      await api.delete(`/platform/carriers/${code}/access/${tid}`);
      toast.success("Acceso revocado");
      await load();
      onChanged && onChanged();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error revocando");
    } finally { setBusy(false); }
  }

  const entries = Object.entries(access);
  const availableTenants = tenants.filter((t) => !access[t.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
         data-testid="tenant-access-dialog">
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-2xl border border-mye-border max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
              Whitelist por tenant
            </div>
            <div className="font-semibold flex items-center gap-2">
              <Users className="h-4 w-4 text-mye-accent" />
              {carrierName}
            </div>
          </div>
          <button onClick={onClose} className="text-mye-ink-muted hover:text-mye-ink"
                  data-testid="tenant-access-close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <p className="text-xs text-mye-ink-muted leading-relaxed">
            Si no agregas ningún tenant, este carrier es <strong>abierto</strong> — todos los tenants heredarán las creds de plataforma. Si agregás aunque sea uno, se vuelve <strong>whitelist</strong> y solo esos tenants tendrán acceso (con sus filtros de project_ids y rate-limit).
          </p>

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-mye-ink-muted">
              <Loader2 className="h-3 w-3 animate-spin" /> Cargando…
            </div>
          ) : entries.length === 0 ? (
            <div className="rounded-md bg-mye-primary-soft/40 border border-mye-border px-4 py-3 text-xs text-mye-ink-muted">
              <strong>Modo abierto</strong>: cualquier tenant que use este carrier heredará las credenciales de plataforma.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="bg-mye-primary-soft/40 text-[10px] uppercase tracking-[0.1em] font-mono">
                <tr>
                  <th className="text-left px-3 py-2">Tenant</th>
                  <th className="text-left px-3 py-2">Projects</th>
                  <th className="text-left px-3 py-2">Rate limit</th>
                  <th className="text-left px-3 py-2">Estado</th>
                  <th className="text-right px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {entries.map(([tid, e]) => (
                  <tr key={tid} className="border-t border-mye-border"
                      data-testid={`tenant-access-row-${tid}`}>
                    <td className="px-3 py-2">
                      <div className="font-medium">{tenantLabel(tid)}</div>
                      <div className="font-mono text-[10px] text-mye-ink-muted">{tid.slice(0, 12)}…</div>
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px]">
                      {(e.project_ids || []).length === 0
                        ? <span className="text-mye-ink-muted">todos</span>
                        : e.project_ids.join(", ")}
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px]">
                      {e.rate_limit_per_min ? `${e.rate_limit_per_min}/min` : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`font-mono text-[10px] ${
                        e.enabled === false ? "text-status-escalated" : "text-status-resolved"
                      }`}>
                        {e.enabled === false ? "DESACTIVADO" : "activo"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => revoke(tid)}
                              disabled={busy}
                              className="text-status-escalated hover:underline text-[10px]"
                              data-testid={`tenant-access-revoke-${tid}`}>
                        Revocar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {showAdd ? (
            <div className="rounded-md border border-mye-accent/30 bg-mye-accent/5 p-4 space-y-3">
              <div className="font-medium text-sm">Otorgar acceso a tenant</div>
              <select value={newEntry.tenant_id}
                      onChange={(e) => setNewEntry({ ...newEntry, tenant_id: e.target.value })}
                      className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm"
                      data-testid="tenant-access-add-tenant">
                <option value="">— Elegir tenant —</option>
                {availableTenants.map((t) => (
                  <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
                ))}
              </select>
              <input value={newEntry.project_ids}
                     onChange={(e) => setNewEntry({ ...newEntry, project_ids: e.target.value })}
                     placeholder="project_ids permitidos (coma-separados, opcional)"
                     className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono"
                     data-testid="tenant-access-add-projects" />
              <input value={newEntry.rate_limit_per_min}
                     onChange={(e) => setNewEntry({ ...newEntry, rate_limit_per_min: e.target.value })}
                     placeholder="rate_limit por minuto (opcional)"
                     type="number"
                     className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono"
                     data-testid="tenant-access-add-rate" />
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input type="checkbox" checked={newEntry.enabled}
                       onChange={(e) => setNewEntry({ ...newEntry, enabled: e.target.checked })} />
                <Power className="h-3 w-3" /> Habilitado
              </label>
              <div className="flex justify-end gap-2">
                <button onClick={() => setShowAdd(false)}
                        className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition">
                  Cancelar
                </button>
                <button onClick={grant} disabled={busy || !newEntry.tenant_id}
                        className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-50"
                        data-testid="tenant-access-add-submit">
                  {busy && <Loader2 className="h-3 w-3 animate-spin" />}
                  Otorgar
                </button>
              </div>
            </div>
          ) : (
            availableTenants.length > 0 && (
              <button onClick={() => setShowAdd(true)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                      data-testid="tenant-access-add-btn">
                <Plus className="h-3 w-3" /> Otorgar acceso a un tenant
              </button>
            )
          )}
        </div>

        <div className="px-5 py-3 border-t border-mye-border flex justify-end bg-mye-primary-soft/30">
          <button onClick={onClose}
                  className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition">
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}
