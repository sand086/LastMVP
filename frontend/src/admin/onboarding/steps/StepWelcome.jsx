/**
 * StepWelcome — Paso 1 del wizard de onboarding admin (Bundle E).
 *
 * Pantalla informativa SIN captura. Solo da contexto + checklist + CTA.
 */
import { CheckCircle2 } from "lucide-react";
import ONBOARDING_COPY from "../copy";

export function StepWelcome({ onAdvance, busy = false }) {
  const c = ONBOARDING_COPY.steps.step_1_welcome;
  return (
    <div className="space-y-4" data-testid="onboarding-step-welcome">
      <div>
        <h2 className="text-base font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>
      <div className="space-y-3 text-sm leading-relaxed text-mye-ink">
        {c.body.map((p, i) => (<p key={i}>{p}</p>))}
      </div>
      <ul className="space-y-2">
        {c.checklist.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <CheckCircle2 className="h-4 w-4 mt-0.5 text-mye-accent shrink-0" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
      <div className="rounded-md bg-mye-bg border border-mye-border p-3 text-xs text-mye-ink-muted">
        💡 {c.recommendation}
      </div>
      <div className="pt-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => onAdvance({})}
          data-testid="onboarding-welcome-continue"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50"
        >
          {c.cta_primary} →
        </button>
      </div>
    </div>
  );
}

export default StepWelcome;
