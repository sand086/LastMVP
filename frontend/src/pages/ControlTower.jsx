import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { ArrowLeft, LogOut, Clock, RefreshCw, AlertTriangle, Users } from "lucide-react";
import { fechaRelativa } from "@/lib/formatFechaMX";

export default function ControlTower() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [byAgent, setByAgent] = useState([]);
  const [inactive, setInactive] = useState([]);
  const [threshold, setThreshold] = useState(30);
  const [loading, setLoading] = useState(true);
  const [lastRefreshAt, setLastRefreshAt] = useState(null);
  const [now, setNow] = useState(Date.now());

  async function refresh() {
    setLoading(true);
    try {
      const [a, b] = await Promise.all([
        api.get("/supervisor/tickets-by-agent"),
        api.get(`/supervisor/inactive-agents?threshold_minutes=${threshold}`),
      ]);
      setByAgent(a.data?.data?.items || []);
      setInactive(b.data?.data?.items || []);
      setLastRefreshAt(new Date().toISOString());
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, [threshold]);
  // Tick para que el indicador "hace X" se actualice cada 15s sin re-fetch
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="control-tower-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Torre de Control</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-10 space-y-8 animate-fade-in">
        <section>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 09 · Supervisor
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Casos por agente</h1>
          <p className="text-mye-ink-muted max-w-2xl">
            R15 — el reloj se pausa cuando un caso está en <span className="font-mono">waiting_*</span>.
            La métrica de inactividad excluye esos casos.
          </p>
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <button onClick={refresh} className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition">
            <RefreshCw className={"h-3.5 w-3.5 " + (loading ? "animate-spin" : "")} /> Refrescar
          </button>
          <label className="flex items-center gap-2 text-xs">
            <Clock className="h-3.5 w-3.5 text-mye-accent" /> Inactivo si pasaron
            <input type="number" min="1" max="480" value={threshold}
                   onChange={(e) => setThreshold(Number(e.target.value) || 30)}
                   className="w-16 rounded-md border border-mye-border bg-white px-2 py-1 text-xs text-center"
                   data-testid="tower-threshold" /> minutos
          </label>
          {lastRefreshAt && (
            <span
              data-testid="tower-last-update"
              title={new Date(lastRefreshAt).toLocaleString("es-MX", { timeZone: "America/Mexico_City", dateStyle: "medium", timeStyle: "medium" })}
              className="text-[11px] text-mye-ink-muted ml-auto inline-flex items-center gap-1 font-mono"
              key={now /* re-evaluar etiqueta cada tick */}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Última actualización: {fechaRelativa(lastRefreshAt)} (CDMX)
            </span>
          )}
        </div>

        {inactive.length > 0 && (
          <div className="rounded-lg border border-status-escalated/40 bg-status-escalated/5 p-4 space-y-2" data-testid="tower-inactive">
            <div className="flex items-center gap-2 font-medium text-status-escalated text-sm">
              <AlertTriangle className="h-4 w-4" /> {inactive.length} agente(s) inactivo(s) {">"} {threshold} min
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {inactive.map((i) => (
                <div key={i.agent_id} className="rounded-md border border-status-escalated/30 bg-white px-3 py-2 text-xs">
                  <div className="font-medium">{i.name}</div>
                  <div className="font-mono text-[11px] text-mye-ink-muted">{i.email}</div>
                  <div className="font-mono text-[11px] text-mye-ink-muted">
                    Last update: {i.last_update}
                  </div>
                  <div className="font-mono text-[11px] text-status-escalated">
                    {i.open_actionable} ticket(s) accionables sin tocar
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="bg-white border border-mye-border rounded-lg overflow-hidden" data-testid="tower-table">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-mye-border">
            <Users className="h-4 w-4 text-mye-accent" />
            <div className="font-medium text-sm">Carga por agente</div>
            <span className="text-xs font-mono text-mye-ink-muted">· {byAgent.length}</span>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-mye-app/60">
              <tr>
                {["Agente", "Email", "Open", "In progress", "Pending", "Waiting (R15)", "Claim"].map((h) => (
                  <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {byAgent.map((row) => (
                <tr key={row.agent_id || "_unassigned"} className="border-t border-mye-border hover:bg-mye-primary-soft/30 transition">
                  <td className="px-4 py-2.5">
                    {row.agent_id == null ? <span className="text-mye-ink-muted italic">Sin asignar</span> : row.name}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-mye-ink-muted">{row.email || "—"}</td>
                  <td className="px-4 py-2.5 tabular-nums font-medium">{row.open}</td>
                  <td className="px-4 py-2.5 tabular-nums">{row.in_progress}</td>
                  <td className="px-4 py-2.5 tabular-nums">{row.pending}</td>
                  <td className="px-4 py-2.5 tabular-nums text-status-waiting">{row.waiting}</td>
                  <td className="px-4 py-2.5 tabular-nums text-status-claim">{row.claim}</td>
                </tr>
              ))}
              {byAgent.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-mye-ink-muted">Sin agentes registrados.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
