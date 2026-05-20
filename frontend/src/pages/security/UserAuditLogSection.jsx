/**
 * UserAuditLogSection — append-only log de operaciones de usuarios,
 * visible solo para root_dev. Renderiza filtros + tabla con expandible JSON
 * diff before/after.
 *
 * Extraído de AdminSecurity.jsx en iter20.
 */
import { useCallback, useEffect, useState, Fragment } from "react";
import { Activity, ChevronRight, RefreshCw, Search } from "lucide-react";
import { api } from "@/lib/api";



const ACTION_META = {
  "user.create":         { l: "Usuario creado",      c: "bg-status-resolved/10 text-status-resolved border-status-resolved/30" },
  "user.update":         { l: "Usuario editado",     c: "bg-status-active/10 text-status-active border-status-active/30" },
  "user.reset_password": { l: "Password reseteada", c: "bg-status-waiting/10 text-status-waiting border-status-waiting/30" },
  "user.delete":         { l: "Usuario eliminado",   c: "bg-status-escalated/10 text-status-escalated border-status-escalated/30" },
};

export default function UserAuditLogSection() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState("");
  const [target, setTarget] = useState("");
  const [expanded, setExpanded] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (action) params.action = action;
      if (target) params.target_email = target;
      const r = await api.get("/admin/security/user-audit-log", { params });
      setData(r.data?.data);
    } finally { setLoading(false); }
  }, [action, target]);

  // Fire when action changes (immediate).
  useEffect(() => { refresh(); }, [refresh, action]);

  // Debounce 300ms for free-text search.
  useEffect(() => {
    const id = setTimeout(refresh, 300);
    return () => clearTimeout(id);
  }, [refresh, target]);

  return (
    <section className="bg-white border border-mye-border rounded-lg overflow-hidden"
             data-testid="user-audit-log-section">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-mye-border">
        <Activity className="h-4 w-4 text-mye-accent" />
        <h3 className="font-medium text-sm">Audit log · operaciones de usuarios</h3>
        <span className="text-[10px] font-mono text-mye-ink-muted ml-auto">
          Visible solo para <code className="font-mono">root_dev</code> · append-only
        </span>
      </div>

      <div className="px-5 py-3 border-b border-mye-border flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px] max-w-[320px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mye-ink-muted" />
          <input value={target} onChange={(e) => setTarget(e.target.value)}
                 placeholder="Buscar por email del usuario afectado…"
                 className="w-full rounded-md border border-mye-border bg-white pl-7 pr-3 py-1.5 text-xs"
                 data-testid="audit-log-search-target" />
        </div>
        <select value={action} onChange={(e) => setAction(e.target.value)}
                className="rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs font-mono"
                data-testid="audit-log-filter-action">
          <option value="">— Todas las acciones —</option>
          {(data?.available_actions || []).map((a) => (
            <option key={a} value={a}>
              {ACTION_META[a]?.l || a}{data?.counts_by_action?.[a] ? ` (${data.counts_by_action[a]})` : ""}
            </option>
          ))}
        </select>
        <button onClick={refresh}
                className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                data-testid="audit-log-refresh">
          <RefreshCw className={"h-3.5 w-3.5 " + (loading ? "animate-spin" : "")} /> Refrescar
        </button>
        <span className="ml-auto text-[10px] font-mono text-mye-ink-muted"
              data-testid="audit-log-count">
          {data?.count || 0} eventos
        </span>
      </div>

      <table className="w-full text-sm">
        <thead className="bg-mye-app/60">
          <tr>
            {["Cuándo", "Acción", "Actor", "Usuario afectado", "Diff", "IP"].map((h) =>
              <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {(data?.items || []).length === 0 && !loading && (
            <tr><td colSpan={6} className="px-4 py-8 text-center text-xs text-mye-ink-muted">
              Sin eventos que coincidan.
            </td></tr>
          )}
          {(data?.items || []).map((ev) => {
            const meta = ACTION_META[ev.action] || { l: ev.action, c: "border-mye-border" };
            const open = expanded === ev.id;
            const hasDiff = ev.before || ev.after;
            return (
              <Fragment key={ev.id}>
                <tr className="border-t border-mye-border align-top hover:bg-mye-primary-soft/30 transition"
                    data-testid={`audit-row-${ev.id}`}>
                  <td className="px-4 py-2 font-mono text-[11px] text-mye-ink-muted whitespace-nowrap">
                    {String(ev.created_at).replace("T", " ").slice(0, 19)}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap">
                    <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono " + meta.c}>
                      {meta.l}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs">
                    <div className="font-mono">{ev.actor_email}</div>
                    <div className="text-[10px] text-mye-ink-muted">{ev.actor_role}</div>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{ev.target_email}</td>
                  <td className="px-4 py-2 text-xs">
                    {hasDiff ? (
                      <button onClick={() => setExpanded(open ? null : ev.id)}
                              className="inline-flex items-center gap-1 text-mye-accent hover:underline"
                              data-testid={`audit-row-toggle-${ev.id}`}>
                        <ChevronRight className={"h-3 w-3 transition " + (open ? "rotate-90" : "")} />
                        {open ? "Ocultar" : "Ver diff"}
                      </button>
                    ) : <span className="text-mye-ink-muted">—</span>}
                  </td>
                  <td className="px-4 py-2 font-mono text-[10px] text-mye-ink-muted">{ev.ip || "—"}</td>
                </tr>
                {open && hasDiff && (
                  <tr className="bg-mye-app/40">
                    <td colSpan={6} className="px-4 py-3">
                      <div className="grid grid-cols-2 gap-4">
                        <Diff label="Antes" data={ev.before} testId={`audit-diff-before-${ev.id}`} />
                        <Diff label="Después" data={ev.after} testId={`audit-diff-after-${ev.id}`} />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function Diff({ label, data, testId }) {
  return (
    <div data-testid={testId}>
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">{label}</div>
      {data ? (
        <pre className="rounded-md border border-mye-border bg-white px-2 py-1.5 text-[11px] font-mono whitespace-pre-wrap">
{JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <div className="rounded-md border border-mye-border bg-white px-2 py-1.5 text-[11px] font-mono text-mye-ink-muted italic">
          (sin datos · estado vacío)
        </div>
      )}
    </div>
  );
}
