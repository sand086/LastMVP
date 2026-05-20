/**
 * Detail view of a single ticket inside the 3-column agent layout.
 * Bundle B · R50 — consume `projection.allowed_actions` para deshabilitar /
 * ocultar CTAs en lugar de descubrir las reglas vía 403.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  RefreshCw, Hand, ChevronRight, Loader2, ListTree, CheckCircle2, Lock,
} from "lucide-react";
import StateMachine from "./StateMachine";
import Timeline from "./Timeline";
import Composer from "./Composer";
import { STATUS_COLOR, STATUS_OPTIONS } from "./sla";
import { useRulesContext } from "@/lib/useRulesContext";
import { RuleAwareButton } from "@/components/RuleAwareButton";

const TERMINAL_BANNER_COPY = {
  delivered: "Entregado — confirmado por carrier",
  returned:  "Devuelto al origen",
  cancelled: "Cancelado",
  closed:    "Cerrado",
  resolved:  "Resuelto",
};

export default function TicketDetail({ ticketId, onChanged, onContext }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const r = await api.get(`/agent/tickets/${ticketId}`);
      const d = r.data?.data;
      setData(d);
      onContext?.(d);
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, [ticketId]);

  // Bundle B · R50 — projection-aware helpers
  const rules = useRulesContext(data?.projection);
  const isTerminal = rules.isTerminalForRule("R02");

  async function take() {
    setBusy(true);
    try {
      await api.post(`/agent/tickets/${ticketId}/take`);
      toast.success("Caso asignado a vos");
      await refresh();
      onChanged?.();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }
  async function changeStatus(newStatus) {
    setBusy(true);
    try {
      await api.patch(`/agent/tickets/${ticketId}/status`, { status: newStatus });
      toast.success(`Status → ${newStatus}`);
      await refresh();
      onChanged?.();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }
  async function submitReopen(reason) {
    setBusy(true);
    try {
      await api.post(`/agent/tickets/${ticketId}/request-reopen`, { reason });
      toast.success("Solicitud enviada al supervisor");
      setReopenOpen(false);
      await refresh();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  if (loading || !data) {
    return (
      <div className="flex-1 grid place-items-center">
        <Loader2 className="h-5 w-5 animate-spin text-mye-accent" />
      </div>
    );
  }

  const t = data.ticket;
  const terminalCopy = TERMINAL_BANNER_COPY[(t.status || "").toLowerCase()] || "Terminal";
  const automationDisabled = !rules.isAllowed("execute_solution_automatic");
  const automationReason = rules.reason("execute_solution_automatic");

  return (
    <div className="flex-1 flex flex-col bg-mye-app overflow-hidden"
         data-testid="agent-ticket-detail">
      {/* Head */}
      <div className="border-b border-mye-border bg-white px-5 py-4 space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className={"inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-mono " +
            (STATUS_COLOR[t.status] || "border-mye-border")}
                data-testid="detail-status-badge">
            {t.status}
          </span>
          <h2 className="text-lg font-semibold tracking-tight"
              data-testid="detail-incident-type">
            {t.incident_label || t.incident_type_label || t.incident_type || "Caso sin tipo"}
          </h2>
          <span className="font-mono text-[11px] text-mye-ink-muted">
            #{t.id.slice(0, 12)}
          </span>
          {!isTerminal && automationDisabled && (
            <span
              data-testid="detail-r03-badge"
              title={rules.tooltip("execute_solution_automatic")}
              className="inline-flex items-center gap-1 rounded-full border border-mye-border bg-mye-app/80 px-2 py-0.5 text-[10px] font-mono text-mye-ink-muted">
              <Lock className="h-3 w-3" /> Manual{automationReason ? ` (${automationReason})` : ""}
            </span>
          )}
          <span className="ml-auto flex items-center gap-1 text-[11px] font-mono text-mye-ink-muted">
            <RefreshCw onClick={refresh}
                       className="h-3.5 w-3.5 cursor-pointer hover:text-mye-ink"
                       data-testid="detail-refresh" />
            actualizado · {String(t.updated_at || t.created_at).slice(11, 19)}
          </span>
        </div>
        {/* Bundle B · FIX-B2 — Banner terminal (R02) */}
        {isTerminal && (
          <div
            data-testid="detail-terminal-banner"
            className="rounded-md border border-status-resolved/40 bg-status-resolved/5 px-3 py-2 flex items-center gap-2 text-sm text-status-resolved">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <div className="flex-1">
              {terminalCopy} — {String(t.updated_at || t.created_at).slice(0, 10)}.
              Las comunicaciones quedan registradas en el timeline.
            </div>
          </div>
        )}
        <div className="flex items-center gap-3 flex-wrap">
          <StateMachine status={t.status} isClaim={!!data.active_claim} />
          <div className="ml-auto flex items-center gap-1.5">
            {!t.assigned_agent_id && !isTerminal && (
              <button onClick={take} disabled={busy}
                      className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                      data-testid="detail-take-btn">
                <Hand className="h-3.5 w-3.5" /> Tomar ticket
              </button>
            )}
            {!isTerminal && (
              <select disabled={busy} value={t.status}
                      onChange={(e) => changeStatus(e.target.value)}
                      className="rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs font-mono"
                      data-testid="detail-status-select">
                <option value={t.status}>{t.status}</option>
                {STATUS_OPTIONS.filter((s) => s !== t.status).map((s) =>
                  <option key={s} value={s}>{s}</option>)}
              </select>
            )}
            {isTerminal && (
              <RuleAwareButton
                rules={rules} actionCode="request_reopen"
                onClick={() => setReopenOpen(true)}
                testId="detail-request-reopen"
                variant="secondary"
              >
                Solicitar reapertura (supervisor)
              </RuleAwareButton>
            )}
            <a href={`/admin/tickets/${t.id}`}
               className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2.5 py-1.5 text-xs hover:bg-mye-primary-soft transition"
               data-testid="detail-fullview">
              <ListTree className="h-3 w-3" /> Vista completa <ChevronRight className="h-3 w-3" />
            </a>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto px-5 py-5 space-y-5">
        <section className="bg-white border border-mye-border rounded-lg p-5 space-y-3">
          <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
            Timeline ({data.timeline.length} eventos)
          </div>
          <Timeline events={data.timeline} />
        </section>
        {isTerminal ? (
          <section
            data-testid="detail-composer-locked"
            className="bg-white border border-mye-border rounded-lg p-5 text-sm text-mye-ink-muted text-center">
            Este ticket está cerrado. Las comunicaciones nuevas no aplican —
            quedan registradas en el timeline.
          </section>
        ) : (
          <Composer ticketId={t.id} onPosted={refresh}
                    recipientEmail={data.guia?.recipient?.email}
                    senderEmail={data.guia?.sender?.email} />
        )}
      </div>
      {reopenOpen && (
        <ReopenRequestDialog
          busy={busy}
          onCancel={() => setReopenOpen(false)}
          onConfirm={submitReopen}
        />
      )}
    </div>
  );
}


function ReopenRequestDialog({ busy, onCancel, onConfirm }) {
  const [reason, setReason] = useState("");
  const valid = reason.trim().length >= 10;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/45 backdrop-blur-sm"
         data-testid="reopen-dialog-overlay">
      <div className="w-[min(480px,92vw)] rounded-lg bg-white shadow-xl border border-mye-border p-5"
           data-testid="reopen-dialog">
        <h2 className="text-base font-semibold">Solicitar reapertura</h2>
        <p className="text-sm text-mye-ink-muted mt-2">
          Describí el motivo de la reapertura. El supervisor recibirá la solicitud
          y deberá aprobarla antes de reabrir el caso. (Mínimo 10 caracteres.)
        </p>
        <textarea
          autoFocus rows={4} value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="mt-3 w-full rounded-md border border-mye-border px-3 py-2 text-sm"
          placeholder="Ej. El cliente reportó que la entrega NO se realizó pese al estado 'delivered' del carrier."
          data-testid="reopen-dialog-reason"
        />
        <div className="flex items-center justify-end gap-2 mt-4">
          <button type="button" onClick={onCancel}
                  className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm hover:bg-mye-primary-soft"
                  data-testid="reopen-dialog-cancel">
            Cancelar
          </button>
          <button type="button" disabled={!valid || busy}
                  onClick={() => onConfirm(reason.trim())}
                  className="rounded-md bg-mye-accent text-white px-3 py-1.5 text-sm hover:brightness-110 disabled:opacity-50"
                  data-testid="reopen-dialog-submit">
            {busy ? "Enviando…" : "Enviar solicitud"}
          </button>
        </div>
      </div>
    </div>
  );
}
