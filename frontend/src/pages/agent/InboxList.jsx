/**
 * Dense single-line list of tickets — Inbox view inspired by the v2 mockup.
 * Used in both the standalone "Bandeja" mode and the left rail of the
 * 3-column detail mode.
 */
import { Hand, AlertTriangle } from "lucide-react";
import { slaInfo, SLA_BAR, PRIORITY_COLOR, STATUS_COLOR } from "./sla";

export default function InboxList({
  rows, selected, focusedId, onToggle, onOpen, onTake,
  selectable = true, compact = false,
}) {
  if (rows.length === 0) {
    return (
      <div className="bg-white border border-mye-border rounded-lg px-6 py-10 text-center text-sm text-mye-ink-muted">
        Sin tickets.
      </div>
    );
  }
  return (
    <ul className="bg-white border border-mye-border rounded-lg overflow-hidden divide-y divide-mye-border"
        data-testid="agent-inbox-list">
      {rows.map((t) => {
        const sla = slaInfo(t);
        const priority = t.priority || "normal";
        const isSelected = selected?.has(t.id);
        const isFocused = focusedId === t.id;
        return (
          <li key={t.id}
              onClick={() => onOpen?.(t)}
              className={"relative flex items-stretch gap-3 cursor-pointer transition group " +
                (isFocused
                  ? "bg-mye-primary-soft/60"
                  : "hover:bg-mye-primary-soft/30")}
              data-testid={`inbox-row-${t.id}`}>
            {/* Priority stripe */}
            <span className={"w-1 flex-shrink-0 " + PRIORITY_COLOR[priority]}
                  title={`Prioridad ${priority}`} />
            {/* Checkbox */}
            {selectable && (
              <span className="flex items-center pl-2"
                    onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" checked={isSelected || false}
                       onChange={() => onToggle?.(t.id)}
                       className="h-4 w-4 accent-mye-accent"
                       data-testid={`inbox-row-select-${t.id}`} />
              </span>
            )}
            {/* Main content */}
            <div className={"flex-1 min-w-0 py-2.5 pr-3 " + (compact ? "" : "sm:py-3")}>
              <div className="flex items-center gap-2">
                <span className={"inline-flex shrink-0 items-center rounded-full border px-1.5 py-0 text-[10px] font-mono " +
                  (STATUS_COLOR[t.status] || "border-mye-border")}>
                  {t.status}
                </span>
                <span className="text-sm font-medium truncate"
                      data-testid={`inbox-row-incident-${t.id}`}>
                  {t.incident_label || t.incident_type_label || t.incident_type || "Sin tipo"}
                </span>
                <span className="font-mono text-[10px] text-mye-ink-muted shrink-0">
                  #{t.id.slice(0, 6)}
                </span>
                {sla && (
                  <span className={"ml-auto inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-mono shrink-0 " +
                    (sla.level === "risk" ? "bg-status-escalated/10 text-status-escalated"
                      : sla.level === "warn" ? "bg-status-waiting/10 text-status-waiting"
                      : "bg-status-resolved/10 text-status-resolved")}
                        data-testid={`inbox-sla-${t.id}`}>
                    {sla.level === "risk" && <AlertTriangle className="h-2.5 w-2.5" />}
                    {sla.label}
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-mye-ink-muted truncate">
                <span className="font-mono shrink-0">{t.tracking_id || "—"}</span>
                <span>·</span>
                <span className="truncate">{t.carrier_status_raw || t.motivo_codigo || "—"}</span>
                <span>·</span>
                <span className="font-mono shrink-0">{String(t.created_at || "").slice(5, 16).replace("T", " ")}</span>
              </div>
              {/* SLA mini-bar */}
              {sla && (
                <div className="mt-1.5 h-0.5 rounded-full bg-mye-border overflow-hidden">
                  <div className={"h-full transition-all " + SLA_BAR[sla.level]}
                       style={{ width: `${Math.min(100, sla.elapsedRatio * 100)}%` }} />
                </div>
              )}
            </div>
            {/* Quick action: Take button when ticket is in the pool */}
            {!t.assigned_agent_id && onTake && (
              <span className="flex items-center pr-3"
                    onClick={(e) => e.stopPropagation()}>
                <button onClick={() => onTake(t)}
                        className="opacity-0 group-hover:opacity-100 inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-2 py-1 text-[11px] hover:brightness-110 transition"
                        data-testid={`inbox-take-${t.id}`}>
                  <Hand className="h-3 w-3" /> Tomar
                </button>
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
