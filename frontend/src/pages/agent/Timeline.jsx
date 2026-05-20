/**
 * Append-only timeline view of ticket events.
 *
 * Event types (from timeline_events collection):
 *   - "ticket_created" / similar          → blue dot (system-created)
 *   - "ticket_assigned", "status_changed" → orange dot (action)
 *   - "comm" or anything from agent reply → purple dot (communication)
 *   - "automation_executed", "ai_*"       → cyan dot (system-automated)
 *   - "claim_promoted", carrier-related   → red dot (escalation)
 */
import { useMemo } from "react";
import {
  Inbox, Hand, RotateCw, Send, Sparkles, FileSignature, AlertCircle,
} from "lucide-react";

const EVENT_STYLE = {
  comm: { icon: Send, dot: "bg-status-claim", label: "Comunicación" },
  action: { icon: Hand, dot: "bg-mye-accent", label: "Acción" },
  system: { icon: RotateCw, dot: "bg-status-pending", label: "Sistema" },
  ai: { icon: Sparkles, dot: "bg-status-active", label: "IA" },
  alert: { icon: AlertCircle, dot: "bg-status-escalated", label: "Alerta" },
  claim: { icon: FileSignature, dot: "bg-status-claim", label: "Reclamo" },
  created: { icon: Inbox, dot: "bg-mye-ink", label: "Creado" },
};

function classify(event) {
  const t = (event.event_type || "").toLowerCase();
  if (t.includes("created") || t === "ticket_created") return "created";
  if (t.includes("ai_") || t.includes("automation")) return "ai";
  if (t.includes("claim_")) return "claim";
  if (t.includes("alert") || t.includes("escalated")) return "alert";
  if (t === "comm" || t.includes("notification")) return "comm";
  if (t.includes("status") || t.includes("assigned") || t === "action") return "action";
  return "system";
}

export default function Timeline({ events = [] }) {
  const sorted = useMemo(
    () => [...events].sort((a, b) =>
      String(a.created_at).localeCompare(String(b.created_at))),
    [events],
  );

  if (sorted.length === 0) {
    return (
      <div className="rounded-md border border-mye-border bg-mye-app/40 px-4 py-6 text-center text-xs text-mye-ink-muted"
           data-testid="ticket-timeline-empty">
        Sin eventos todavía.
      </div>
    );
  }

  return (
    <ol className="relative space-y-3 pl-5"
        data-testid="ticket-timeline">
      <span className="absolute left-[7px] top-0 bottom-0 w-px bg-mye-border" />
      {sorted.map((ev) => {
        const klass = classify(ev);
        const meta = EVENT_STYLE[klass] || EVENT_STYLE.system;
        const Icon = meta.icon;
        return (
          <li key={ev.id} className="relative"
              data-testid={`timeline-event-${ev.event_type}`}>
            <span className={"absolute -left-5 top-1 h-3 w-3 rounded-full ring-2 ring-white " + meta.dot} />
            <div className="space-y-0.5">
              <div className="flex items-center gap-2 text-xs">
                <Icon className="h-3.5 w-3.5 text-mye-ink-muted" />
                <span className="font-medium">{ev.event_type}</span>
                <span className="font-mono text-[10px] text-mye-ink-muted ml-auto">
                  {String(ev.created_at).replace("T", " ").slice(0, 19)}
                </span>
              </div>
              {ev.description && (
                <div className="text-[11px] text-mye-ink-muted">
                  {ev.description}
                </div>
              )}
              {ev.payload?.body && (
                <pre className="font-mono text-[11px] text-mye-ink whitespace-pre-wrap rounded-md border border-mye-border bg-white px-2 py-1.5 mt-1">
                  {ev.payload.body}
                </pre>
              )}
              {ev.event_type === "comm" && ev.payload?.email_ok !== undefined && (
                <EmailDeliveryBadge payload={ev.payload} />
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function EmailDeliveryBadge({ payload }) {
  if (payload.email_ok && payload.email_mock) {
    return (
      <div className="inline-flex items-center gap-1 mt-1 rounded-full bg-mye-primary-soft px-2 py-0.5 text-[10px] font-mono text-mye-ink-muted"
           data-testid="timeline-email-mock">
        📧 Email simulado (sin API key)
      </div>
    );
  }
  if (payload.email_ok) {
    return (
      <div className="inline-flex items-center gap-1 mt-1 rounded-full bg-status-resolved/10 px-2 py-0.5 text-[10px] font-mono text-status-resolved"
           data-testid="timeline-email-ok">
        ✓ Email entregado · {payload.email_id || "—"}
      </div>
    );
  }
  return (
    <div className="inline-flex items-center gap-1 mt-1 rounded-full bg-status-escalated/10 px-2 py-0.5 text-[10px] font-mono text-status-escalated"
         data-testid="timeline-email-failed"
         title={payload.email_error || "Sin detalle"}>
      ✗ Email no entregado{payload.email_error ? `: ${payload.email_error.slice(0, 60)}` : ""}
    </div>
  );
}
