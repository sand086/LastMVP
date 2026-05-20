/**
 * StepCatalog — Paso 5 · Catálogo MX estándar (MANDATORIO, no se puede saltar).
 *
 * Llama POST /api/admin/onboarding/seed-mx-catalog para sembrar 12 motivos
 * + 18 soluciones estándar en el tenant. Idempotente — botón puede llamarse
 * múltiples veces sin duplicar.
 */
import { useState } from "react";
import { Loader2, CheckCircle2, BookOpen } from "lucide-react";
import { toast } from "sonner";
import ONBOARDING_COPY from "../copy";

export function StepCatalog({ onAdvance, seedMxCatalog, busy = false }) {
  const c = ONBOARDING_COPY.steps.step_5_catalog;
  const [seeding, setSeeding] = useState(false);
  const [result, setResult] = useState(null);

  async function handleSeed() {
    setSeeding(true);
    try {
      const r = await seedMxCatalog();
      setResult(r);
      const m = (r?.motivos_inserted || 0) + (r?.motivos_skipped || 0);
      const s = (r?.soluciones_inserted || 0) + (r?.soluciones_skipped || 0);
      toast.success(c.success(m, s));
      if ((r?.motivos_skipped || 0) > 0) toast.info(c.partial(r.motivos_skipped));
    } catch (e) {
      toast.error(ONBOARDING_COPY.errors.network);
    } finally {
      setSeeding(false);
    }
  }

  const seeded = !!result;

  return (
    <div className="space-y-4" data-testid="onboarding-step-catalog">
      <div>
        <h2 className="text-base font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>

      <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900">
        ⚠️ {c.mandatory_note}
      </div>

      <div className="rounded-md border border-mye-border p-4 space-y-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-mye-accent" />
          <span className="font-medium text-sm text-mye-ink">12 motivos + 18 soluciones</span>
        </div>
        <p className="text-xs text-mye-ink-muted">{c.cta_primary_help}</p>
        <button
          type="button"
          disabled={busy || seeding}
          onClick={handleSeed}
          data-testid="onboarding-catalog-seed"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {seeding
            ? <><Loader2 className="h-4 w-4 animate-spin" /> Cargando…</>
            : seeded
              ? <><CheckCircle2 className="h-4 w-4" /> Catálogo cargado · volver a cargar</>
              : c.cta_primary}
        </button>
        {seeded && (
          <div className="text-xs text-mye-ink-muted bg-mye-bg rounded p-2 space-y-1"
               data-testid="onboarding-catalog-result">
            <div>Motivos: <span className="font-mono">{result.motivos_inserted}</span> nuevos · <span className="font-mono">{result.motivos_skipped}</span> existentes</div>
            <div>Soluciones: <span className="font-mono">{result.soluciones_inserted}</span> nuevas · <span className="font-mono">{result.soluciones_skipped}</span> existentes</div>
          </div>
        )}
      </div>

      <details className="text-xs text-mye-ink-muted">
        <summary className="cursor-pointer hover:text-mye-ink">{c.cta_secondary}</summary>
        <p className="mt-2 italic">{c.cta_secondary_help}</p>
        <p className="mt-1">Disponible desde /admin/catalogo → Importar CSV.</p>
      </details>

      <div className="pt-2">
        <button
          type="button"
          disabled={busy || !seeded}
          onClick={() => onAdvance({ catalog_seeded: true, ...result })}
          data-testid="onboarding-catalog-continue"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50"
        >
          Continuar →
        </button>
      </div>
    </div>
  );
}

export default StepCatalog;
