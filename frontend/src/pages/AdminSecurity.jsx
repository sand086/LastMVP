/**
 * AdminSecurity — PROMPT 12 · Auditoría de seguridad pre-go-live.
 *
 * Lista checklist con PASS/WARN/FAIL para cada criterio. Sólo lectura.
 * Pensado para correr antes de cada release a producción.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import UserAuditLogSection from "./security/UserAuditLogSection";
import {
  ShieldCheck, ArrowLeft, LogOut, RefreshCw, CheckCircle2,
  AlertTriangle, XCircle, Lock,
} from "lucide-react";

export default function AdminSecurity() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function refresh() {
    setBusy(true); setErr(null);
    try {
      const r = await api.get("/admin/security/audit");
      setData(r.data?.data || null);
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }
  useEffect(() => { refresh(); }, []);

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="security-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1200px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-status-escalated grid place-items-center text-white">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div className="leading-tight">
              <div className="font-semibold text-sm tracking-tight">Auditoría de seguridad</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">PROMPT 12 · pre-go-live checklist</div>
            </div>
          </div>
          <div className="ml-auto" />
        </div>
      </header>

      <main className="max-w-[1200px] mx-auto px-6 py-10 space-y-6 animate-fade-in">
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <span className="h-px w-6 bg-mye-accent" /> PROMPT 12 · Security audit
          </div>
          <h1 className="text-4xl font-semibold tracking-tight">Pre-go-live</h1>
          <p className="text-mye-ink-muted max-w-3xl">
            Checklist de seguridad y configuración. Ejecuta antes de cada release
            a producción. Los criterios marcados <strong>FAIL</strong> deben
            resolverse; los <strong>WARN</strong> son recomendaciones.
          </p>
        </section>

        <button onClick={refresh} disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft transition disabled:opacity-60"
                data-testid="security-refresh">
          <RefreshCw className="h-3.5 w-3.5" /> {busy ? "Auditando…" : "Re-auditar"}
        </button>

        {err && (
          <div className="rounded-md border border-status-escalated/30 bg-status-escalated/5 px-4 py-3 text-sm text-status-escalated">
            {err}
          </div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="security-summary">
              <SummaryCard label="Total checks" value={data.summary.total_checks} />
              <SummaryCard label="Pass" value={data.summary.pass} tone="good" />
              <SummaryCard label="Warn" value={data.summary.warn} tone="warn" />
              <SummaryCard label="Fail" value={data.summary.fail} tone="bad" />
            </div>

            <div className={"rounded-md border p-4 text-sm " +
              (data.summary.ready_for_prod
                ? "border-status-resolved/40 bg-status-resolved/5"
                : "border-status-escalated/40 bg-status-escalated/5")}
                 data-testid="security-verdict">
              <div className="flex items-center gap-2 font-medium">
                {data.summary.ready_for_prod
                  ? <><CheckCircle2 className="h-5 w-5 text-status-resolved" /> Listo para producción</>
                  : <><Lock className="h-5 w-5 text-status-escalated" /> No listo · resolver {data.summary.fail} FAIL</>}
              </div>
              <div className="text-xs text-mye-ink-muted mt-1">
                {data.summary.warn > 0 && `${data.summary.warn} advertencia(s) recomendadas. `}
                Re-ejecuta tras cada cambio de configuración.
              </div>
            </div>

            <div className="bg-white border border-mye-border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-mye-app/60">
                  <tr>
                    {["Severidad", "Criterio", "Detalle", "Remediación"].map((h) => (
                      <th key={h} className="text-left font-mono text-[10px] uppercase tracking-wider text-mye-ink-muted px-4 py-2.5">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data.checks || []).map((c, i) => (
                    <tr key={i} className="border-t border-mye-border align-top" data-testid={`security-row-${c.severity}`}>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <SeverityPill v={c.severity} />
                      </td>
                      <td className="px-4 py-3 font-medium text-sm">{c.name}</td>
                      <td className="px-4 py-3 text-xs text-mye-ink-muted">{c.detail}</td>
                      <td className="px-4 py-3 text-xs text-mye-ink-muted">
                        {c.remediation ? c.remediation : <span className="text-status-resolved/70">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {user?.role === "root_dev" && <UserAuditLogSection />}
          </>
        )}
      </main>
    </div>
  );
}

function SummaryCard({ label, value, tone }) {
  const cls = tone === "good" ? "border-status-resolved/40 bg-status-resolved/5"
            : tone === "warn" ? "border-status-waiting/40 bg-status-waiting/5"
            : tone === "bad" ? "border-status-escalated/40 bg-status-escalated/5"
            : "border-mye-border bg-mye-app/40";
  return (
    <div className={"rounded-md border p-4 " + cls}>
      <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">{label}</div>
      <div className="text-3xl tabular-nums font-mono mt-1">{value}</div>
    </div>
  );
}

function SeverityPill({ v }) {
  const map = {
    pass: { Icon: CheckCircle2, cls: "border-status-resolved/40 bg-status-resolved/10 text-status-resolved" },
    warn: { Icon: AlertTriangle, cls: "border-status-waiting/40 bg-status-waiting/10 text-status-waiting" },
    fail: { Icon: XCircle, cls: "border-status-escalated/40 bg-status-escalated/10 text-status-escalated" },
  };
  const { Icon, cls } = map[v] || map.warn;
  return (
    <span className={"inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase " + cls}>
      <Icon className="h-3 w-3" /> {v}
    </span>
  );
}

