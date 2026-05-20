/**
 * StepCompletion — Pantalla de finalización del wizard.
 *
 * Resume lo configurado y ofrece CTAs: ir al Dashboard o tomar el tour.
 */
import { CheckCircle2, Sparkles } from "lucide-react";
import ONBOARDING_COPY from "../copy";

export function StepCompletion({ summary = {}, onGoDashboard, onTakeTour }) {
  const c = ONBOARDING_COPY.steps.completion;
  const lines = [];
  if (summary.tenant_name) lines.push(`Tenant: ${summary.tenant_name}`);
  if (summary.project_name) lines.push(`Proyecto: ${summary.project_name}`);
  if (summary.client_name) lines.push(`Primer cliente: ${summary.client_name}`);
  if (summary.planned_carriers?.length) lines.push(`${summary.planned_carriers.length} carrier(s) planeados`);
  if (summary.catalog_seeded) lines.push("Catálogo MX estándar cargado");
  if (summary.matrix_count_automated != null) {
    lines.push(`Matriz de automatización: ${summary.matrix_count_automated} celdas automáticas`);
  }

  return (
    <div className="space-y-5 text-center py-4" data-testid="onboarding-step-completion">
      <div className="inline-flex items-center justify-center h-14 w-14 rounded-full bg-emerald-50 border border-emerald-200 mx-auto">
        <CheckCircle2 className="h-7 w-7 text-emerald-600" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>
      {lines.length > 0 && (
        <div className="rounded-md border border-mye-border bg-mye-bg p-3 text-xs text-mye-ink text-left">
          <div className="font-medium mb-2">{c.summary_lead}</div>
          <ul className="space-y-1 list-disc pl-5">
            {lines.map((l, i) => (<li key={i}>{l}</li>))}
          </ul>
        </div>
      )}
      <div className="space-y-2 pt-2">
        <button
          type="button"
          onClick={onGoDashboard}
          data-testid="onboarding-completion-dashboard"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover"
        >
          {c.cta_primary} →
        </button>
        <button
          type="button"
          onClick={onTakeTour}
          data-testid="onboarding-completion-tour"
          className="w-full rounded-md border border-mye-border text-mye-ink text-sm py-2 hover:bg-mye-bg inline-flex items-center justify-center gap-2"
        >
          <Sparkles className="h-3.5 w-3.5" /> {c.cta_secondary}
        </button>
      </div>
    </div>
  );
}

export default StepCompletion;
