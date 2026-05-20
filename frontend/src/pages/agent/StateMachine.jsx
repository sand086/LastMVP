/**
 * State Machine progress bar — visual representation of the ticket lifecycle.
 * Shows the path: pending → in_progress → waiting_(client|carrier) → resolved.
 * The "claim" branch is shown only when active.
 */
import { Check, Clock, Loader2, AlertCircle, FileSignature } from "lucide-react";

const STAGES = [
  { key: "pending", label: "Nuevo", icon: AlertCircle },
  { key: "in_progress", label: "En curso", icon: Loader2 },
  { key: "waiting", label: "Esperando", icon: Clock,
    aliases: ["waiting_client", "waiting_carrier"] },
  { key: "resolved", label: "Resuelto", icon: Check },
];

function stageReached(currentStatus, stage) {
  const order = ["pending", "in_progress", "waiting_client", "waiting_carrier",
                  "resolved", "closed"];
  const stageIdx = stage.aliases
    ? Math.max(...stage.aliases.map((a) => order.indexOf(a)))
    : order.indexOf(stage.key);
  const currentIdx = order.indexOf(currentStatus);
  return currentIdx >= stageIdx;
}

function isCurrentStage(currentStatus, stage) {
  if (stage.aliases) return stage.aliases.includes(currentStatus);
  return currentStatus === stage.key;
}

export default function StateMachine({ status, isClaim }) {
  return (
    <div className="flex items-center gap-1.5"
         data-testid="ticket-state-machine">
      {STAGES.map((stage, i) => {
        const reached = stageReached(status, stage);
        const isCurrent = isCurrentStage(status, stage);
        const Icon = stage.icon;
        return (
          <div key={stage.key} className="flex items-center gap-1.5">
            <div className={"inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-mono border transition " +
              (isCurrent
                ? "bg-mye-accent text-white border-mye-accent shadow-sm"
                : reached
                  ? "bg-status-resolved/15 text-status-resolved border-status-resolved/30"
                  : "bg-mye-app text-mye-ink-muted border-mye-border")}>
              <Icon className={"h-3 w-3 " + (isCurrent && stage.key === "in_progress" ? "animate-spin" : "")} />
              {stage.label}
            </div>
            {i < STAGES.length - 1 && (
              <div className={"h-px w-3 " +
                (reached ? "bg-status-resolved/40" : "bg-mye-border")} />
            )}
          </div>
        );
      })}
      {isClaim && (
        <span className="ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-mono border bg-status-claim/15 text-status-claim border-status-claim/30"
              data-testid="state-machine-claim-branch">
          <FileSignature className="h-3 w-3" /> Reclamo
        </span>
      )}
    </div>
  );
}
