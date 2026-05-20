/**
 * StepCarriers — Paso 4 · Configuración de carriers.
 *
 * Lista los carriers conocidos del MVP (FedEx, DHL, 99 Minutos, Estafeta,
 * PaqueteExpress) con su estado visual. La configuración real de
 * credenciales se hace después desde /admin/jerarquia (tab Carriers).
 * Acá solo capturamos cuáles planea operar el tenant.
 */
import { useState } from "react";
import { Truck, CheckCircle2, AlertCircle } from "lucide-react";
import ONBOARDING_COPY from "../copy";

// Listado canónico del MVP (orden de prioridad operativa).
const CARRIERS_CATALOG = [
  { code: "99minutos", name: "99 Minutos", platform_managed: false },
  { code: "fedex", name: "FedEx", platform_managed: false },
  { code: "dhl", name: "DHL", platform_managed: false },
  { code: "estafeta", name: "Estafeta", platform_managed: false },
  { code: "paquetexpress", name: "PaqueteExpress", platform_managed: false },
];

export function StepCarriers({ onAdvance, onSkip, busy = false, initialData = {} }) {
  const c = ONBOARDING_COPY.steps.step_4_carriers;
  const [planned, setPlanned] = useState(
    new Set(initialData.planned_carriers || []),
  );

  function toggle(code) {
    setPlanned((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  }

  function submit() {
    onAdvance({ planned_carriers: Array.from(planned) });
  }

  const hasSelection = planned.size > 0;

  return (
    <div className="space-y-4" data-testid="onboarding-step-carriers">
      <div>
        <h2 className="text-base font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>

      <div className="space-y-2">
        {CARRIERS_CATALOG.map((carrier) => {
          const selected = planned.has(carrier.code);
          return (
            <button
              key={carrier.code}
              type="button"
              disabled={busy}
              onClick={() => toggle(carrier.code)}
              data-testid={`onboarding-carrier-${carrier.code}`}
              className={[
                "w-full flex items-center justify-between rounded-md border px-3 py-2 text-sm transition",
                selected
                  ? "border-mye-accent bg-mye-accent/5"
                  : "border-mye-border bg-white hover:bg-mye-bg",
              ].join(" ")}
            >
              <div className="flex items-center gap-3">
                <Truck className={`h-4 w-4 ${selected ? "text-mye-accent" : "text-mye-ink-muted"}`} />
                <span className="font-medium text-mye-ink">{carrier.name}</span>
              </div>
              <div className="text-xs">
                {selected ? (
                  <span className="inline-flex items-center gap-1 text-mye-accent">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Lo voy a configurar
                  </span>
                ) : (
                  <span className="text-mye-ink-muted">{c.states.unconfigured}</span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {!hasSelection && (
        <div className="flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 p-3 text-xs">
          <AlertCircle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <span className="text-amber-900">{c.banner_skipped}</span>
        </div>
      )}

      <div className="pt-2 space-y-2">
        <button
          type="button"
          disabled={busy || !hasSelection}
          onClick={submit}
          data-testid="onboarding-carriers-continue"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50"
        >
          {c.cta_primary} →
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onSkip}
          data-testid="onboarding-carriers-skip"
          className="w-full text-xs text-mye-ink-muted hover:text-mye-ink py-1"
        >
          {c.cta_skip}
        </button>
      </div>
    </div>
  );
}

export default StepCarriers;
