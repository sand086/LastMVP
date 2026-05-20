/**
 * GuiaCancelButton — dispara POST /api/agent/guias/{id}/cancel.
 *
 * Aparece sólo cuando la guía es Routal y tiene `carrier_meta.routal_project_id`
 * persistido (el ingest multi-proyecto lo deja ahí). Cierra el loop outbound
 * 1:1 garantizando que la cancelación va al proyecto correcto en Routal.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Loader2, XOctagon, CheckCircle2, AlertTriangle, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

// Roles que ven habilitada la acción "Cancelar en Routal".
// Backend hace gating real (RBAC en /agent/guias/{id}/cancel); este es solo
// el gating VISUAL (UX-TICKETS-006) para no dejar el botón "gris sin razón".
const ROLES_ALLOWED = new Set(["agent", "supervisor", "admin", "superadmin", "root_dev"]);


export default function GuiaCancelButton({ guiaId, tracking, projectId, onDone }) {
  const { user } = useAuth();
  const allowed = ROLES_ALLOWED.has(user?.role);
  const [open, setOpen] = useState(false);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      const r = await api.post(`/agent/guias/${guiaId}/cancel`,
        { comments: comments || null });
      const d = r.data?.data || {};
      if (d.received) {
        toast.success(`Cancelación enviada a Routal · ${d.tracking_id}`);
      } else if (d.fallback_to_email) {
        toast.error(`Routal rechazó la cancelación (HTTP ${d.status}). Se sugiere notificar por email.`);
      } else {
        toast.error(`Cancelación no aceptada (HTTP ${d.status}).`);
      }
      setOpen(false);
      setComments("");
      onDone && onDone();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error al enviar cancelación");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button onClick={() => allowed && setOpen(true)}
              disabled={!allowed}
              aria-disabled={!allowed}
              className={
                "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition " +
                (allowed
                  ? "border-status-escalated/40 bg-white text-status-escalated hover:bg-status-escalated/5"
                  : "border-mye-border bg-mye-border/30 text-mye-ink-muted cursor-not-allowed")
              }
              data-testid="guia-cancel-btn"
              title={allowed
                ? "Cancelar entrega en Routal"
                : `Solo agentes, supervisores o admins pueden cancelar en Routal. Tu rol actual es "${user?.role || "—"}".`}>
        {allowed
          ? <><XOctagon className="h-3.5 w-3.5" /> Cancelar en Routal</>
          : <><Lock className="h-3.5 w-3.5" /> Cancelar en Routal</>}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             data-testid="guia-cancel-dialog">
          <div className="w-full max-w-md rounded-lg bg-white shadow-2xl border border-mye-border">
            <div className="px-5 py-3 border-b border-mye-border flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-status-escalated" />
              <div className="font-semibold text-sm">Cancelar entrega en Routal</div>
            </div>
            <div className="px-5 py-4 space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-mye-primary-soft/40 rounded p-2">
                <div><span className="text-mye-ink-muted">tracking:</span> {tracking}</div>
                <div><span className="text-mye-ink-muted">project:</span> {projectId}</div>
              </div>
              <p className="text-xs text-mye-ink-muted leading-relaxed">
                Esta acción enviará una instrucción PUT a Routal contra el stop
                identificado por <code className="font-mono">{tracking}</code> en el
                project <code className="font-mono">{projectId}</code>. El cambio
                es <strong>auditado</strong> en el timeline del ticket.
              </p>
              <div>
                <label className="block text-[10px] uppercase tracking-[0.15em] font-mono text-mye-ink-muted mb-1">
                  Comentario (opcional)
                </label>
                <textarea value={comments} onChange={(e) => setComments(e.target.value)}
                          rows={3}
                          placeholder="ej. Cliente solicitó cancelación tras 3 intentos fallidos"
                          className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-mye-accent/40"
                          data-testid="guia-cancel-comments" />
              </div>
            </div>
            <div className="px-5 py-3 border-t border-mye-border flex items-center justify-end gap-2 bg-mye-primary-soft/30">
              <button onClick={() => { setOpen(false); setComments(""); }}
                      disabled={busy}
                      className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition disabled:opacity-50"
                      data-testid="guia-cancel-cancel">
                Cancelar
              </button>
              <button onClick={confirm}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-md bg-status-escalated text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-50"
                      data-testid="guia-cancel-confirm">
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                Confirmar cancelación
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
