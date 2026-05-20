/**
 * SLA computation & display helpers.
 *
 * Convention: a ticket has `sla_deadline` (ISO string) when assigned, or it
 * inherits from its incident_type SLA (e.g. 24h for fresh, 8h for damaged).
 * If neither is present we fall back to a soft 24h SLA from `created_at`.
 */
export function slaInfo(ticket) {
  const deadlineStr = ticket?.sla_deadline
    || _fallbackDeadline(ticket?.created_at);
  if (!deadlineStr) return null;
  const deadline = new Date(deadlineStr);
  const now = new Date();
  const diffMs = deadline - now;
  const totalMs = deadline - new Date(ticket?.created_at || deadline);
  const elapsedRatio = totalMs > 0 ? 1 - diffMs / totalMs : 1;
  const overdue = diffMs < 0;
  let level = "ok";
  if (overdue || elapsedRatio >= 1) level = "risk";
  else if (elapsedRatio >= 0.7) level = "warn";
  return {
    deadline,
    overdue,
    diffMs,
    elapsedRatio: Math.max(0, Math.min(1, elapsedRatio)),
    level,
    label: _humanizeMs(diffMs),
  };
}

function _fallbackDeadline(createdAt) {
  if (!createdAt) return null;
  const d = new Date(createdAt);
  d.setHours(d.getHours() + 24);
  return d.toISOString();
}

function _humanizeMs(ms) {
  const overdue = ms < 0;
  const abs = Math.abs(ms);
  const h = Math.floor(abs / 3_600_000);
  const m = Math.floor((abs % 3_600_000) / 60_000);
  const core = h > 0 ? `${h}h ${m.toString().padStart(2, "0")}m` : `${m}m`;
  return overdue ? `−${core}` : core;
}

export const SLA_COLOR = {
  ok: "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
  warn: "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  risk: "bg-status-escalated/10 text-status-escalated border-status-escalated/40",
};

export const SLA_BAR = {
  ok: "bg-status-resolved",
  warn: "bg-status-waiting",
  risk: "bg-status-escalated",
};

export const PRIORITY_COLOR = {
  low: "bg-status-closed",
  normal: "bg-status-active",
  high: "bg-status-waiting",
  urgent: "bg-status-escalated",
};

export const STATUS_COLOR = {
  pending: "bg-status-pending/10 text-status-pending border-status-pending/30",
  in_progress: "bg-status-active/10 text-status-active border-status-active/30",
  waiting_client: "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  waiting_carrier: "bg-status-waiting/10 text-status-waiting border-status-waiting/30",
  resolved: "bg-status-resolved/10 text-status-resolved border-status-resolved/30",
  closed: "bg-status-closed/10 text-status-closed border-status-closed/30",
  claim: "bg-status-claim/10 text-status-claim border-status-claim/30",
};

/** Status timeline progression for the state machine bar. */
export const STATE_FLOW = [
  "pending", "in_progress", "waiting_client", "waiting_carrier", "resolved",
];

export const STATUS_OPTIONS = [
  "in_progress", "waiting_client", "waiting_carrier", "resolved", "claim",
];
