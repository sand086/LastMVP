import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";
import {
  LogOut, BarChart3, Activity, Clock, AlertCircle, Bot, Inbox, Scale,
} from "lucide-react";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [kpis, setKpis] = useState(null);
  const [byType, setByType] = useState([]);
  const [throughput, setThroughput] = useState([]);
  const [claimsOpen, setClaimsOpen] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get("/dashboard/kpis"),
      api.get("/dashboard/incidents-by-type"),
      api.get("/dashboard/throughput-7d"),
      api.get("/dashboard/claims-open").catch(() => ({ data: { data: null } })),
    ]).then(([k, b, t, c]) => {
      setKpis(k.data?.data);
      setByType(b.data?.data?.items || []);
      setThroughput(t.data?.data?.items || []);
      setClaimsOpen(c.data?.data || null);
    });
  }, []);

  const max = Math.max(1, ...throughput.map((r) => r.count));
  const maxBy = Math.max(1, ...byType.map((r) => r.count));

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="dashboard-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Dashboard · 5 KPIs (sec 6.3)</div>
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
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 10 · KPIs
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Donde están las incidencias hoy</h1>
        </section>

        <section className="grid md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="dashboard-kpis">
          <KpiCard icon={Inbox}      label="Tickets abiertos"      value={kpis?.open_tickets ?? "…"}      sub="estado no terminal" />
          <KpiCard icon={Activity}   label="Resueltos hoy"          value={kpis?.resolved_today ?? "…"}    sub="UTC · resolved/closed" />
          <KpiCard icon={AlertCircle} label="Backlog > 24h"          value={kpis?.backlog_aged_24h ?? "…"} sub="sin actualización" highlight />
          <KpiCard icon={Bot}        label="Tasa con solución"      value={(kpis?.automation_rate_30d ?? 0) + "%"}
                                     sub={`${kpis?.tickets_30d ?? 0} tickets · 30d`} />
        </section>

        <section className="grid lg:grid-cols-2 gap-4">
          <Card title="Throughput de los últimos 7 días" icon={BarChart3}>
            <div className="grid grid-cols-7 gap-1 items-end h-40">
              {throughput.map((r) => (
                <div key={r.date} className="flex flex-col items-center gap-1" title={`${r.date} · ${r.count}`} data-testid={`throughput-bar-${r.date}`}>
                  <div className="w-full rounded-t-md bg-mye-accent/60 hover:bg-mye-accent transition-colors"
                       style={{ height: `${(r.count / max) * 130 + 4}px` }} />
                  <div className="text-[10px] font-mono text-mye-ink-muted">{r.date.slice(5)}</div>
                  <div className="text-[10px] tabular-nums">{r.count}</div>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Top tipos de incidencia" icon={AlertCircle}>
            {byType.length === 0 ? (
              <div className="text-sm text-mye-ink-muted">Aún no hay incidencias clasificadas.</div>
            ) : (
              <ul className="space-y-2">
                {byType.map((r) => (
                  <li key={r.incident_type} className="flex items-center gap-3" data-testid={`incident-row-${r.incident_type}`}>
                    <span className="w-32 text-xs font-mono shrink-0">{r.incident_type}</span>
                    <div className="flex-1 h-3 rounded bg-mye-primary-soft overflow-hidden">
                      <div className="h-full bg-mye-accent transition-all"
                           style={{ width: `${(r.count / maxBy) * 100}%` }} />
                    </div>
                    <span className="w-12 text-right tabular-nums font-mono text-xs">{r.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>

        <section className="bg-white border border-mye-border rounded-lg p-5"
                 data-testid="dashboard-claims-section">
          <div className="flex items-center gap-2 mb-3 text-sm font-medium">
            <Scale className="h-4 w-4 text-mye-accent" /> Reclamos · KPI (P1.3)
          </div>
          {!claimsOpen ? (
            <div className="text-xs text-mye-ink-muted font-mono">Cargando…</div>
          ) : (
            <>
              <div className="grid md:grid-cols-3 lg:grid-cols-5 gap-3">
                <ClaimMini label="Abiertos" value={claimsOpen.open_total}
                           highlight />
                <ClaimMini label="En dictamen" value={claimsOpen.in_dictamen} />
                <ClaimMini label=">24h en dictamen"
                           value={claimsOpen.in_dictamen_aging_24h}
                           accent={claimsOpen.in_dictamen_aging_24h > 0} />
                <ClaimMini label="Conciliados hoy"
                           value={claimsOpen.conciliated_today} />
                <ClaimMini label="SLA breaches 24h"
                           value={claimsOpen.sla_breaches_24h}
                           accent={claimsOpen.sla_breaches_24h > 0} />
              </div>
              {claimsOpen.by_estado?.length > 0 && (
                <div className="mt-4">
                  <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-2">
                    Distribución por estado
                  </div>
                  <ul className="space-y-1.5">
                    {claimsOpen.by_estado.map((r) => (
                      <li key={r.estado} className="flex items-center gap-3 text-xs"
                          data-testid={`claim-estado-${r.estado}`}>
                        <span className="w-44 font-mono">{r.estado}</span>
                        <div className="flex-1 h-2 rounded bg-mye-primary-soft overflow-hidden">
                          <div className="h-full bg-mye-accent"
                               style={{ width: `${Math.min(100, (r.count / Math.max(1, claimsOpen.open_total)) * 100)}%` }} />
                        </div>
                        <span className="w-8 text-right tabular-nums font-mono">{r.count}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </section>

        <section className="bg-white border border-mye-border rounded-lg p-5">
          <div className="flex items-center gap-2 mb-2 text-sm font-medium">
            <Clock className="h-4 w-4 text-mye-accent" /> Reporte must-have
          </div>
          <p className="text-sm text-mye-ink-muted">
            En esta MVP sembramos los conteos esenciales. SLA % y tiempo medio de resolución ricos
            aterrizan con el cron de inactividad y los timestamps de cierre — PROMPT_09. Mientras
            tanto, esta vista responde la pregunta operativa más urgente: <span className="text-mye-ink">¿qué carga
            tiene mi equipo y qué tipo de incidente lidera la cola?</span>
          </p>
        </section>
      </main>
    </div>
  );
}

function KpiCard({ icon: Icon, label, value, sub, highlight }) {
  return (
    <div className={"rounded-lg border bg-white p-5 transition-all hover:-translate-y-0.5 hover:shadow-sm " +
      (highlight ? "border-mye-accent/40" : "border-mye-border")}>
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
        <Icon className={"h-3.5 w-3.5 " + (highlight ? "text-mye-accent" : "text-mye-primary")} />
        {label}
      </div>
      <div className={"mt-3 text-4xl font-semibold tabular-nums " + (highlight ? "text-mye-accent" : "text-mye-ink")}>{value}</div>
      <div className="mt-1 text-xs font-mono text-mye-ink-muted">{sub}</div>
    </div>
  );
}

function Card({ title, icon: Icon, children }) {
  return (
    <div className="rounded-lg border border-mye-border bg-white p-5">
      <div className="flex items-center gap-2 mb-3 text-sm font-medium">
        <Icon className="h-4 w-4 text-mye-accent" /> {title}
      </div>
      {children}
    </div>
  );
}

function ClaimMini({ label, value, highlight, accent }) {
  return (
    <div className={"rounded-md border bg-mye-app/40 px-3 py-3 " +
      (highlight ? "border-mye-accent/50" : "border-mye-border") +
      (accent ? " border-status-escalated/40" : "")}>
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">{label}</div>
      <div className={"text-2xl font-semibold tabular-nums " +
        (highlight ? "text-mye-accent" : accent ? "text-status-escalated" : "text-mye-ink")}>
        {value ?? "…"}
      </div>
    </div>
  );
}
