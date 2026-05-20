/**
 * StepAutomationMatrix — Paso 6 · Matriz de permisos de automatización (R03).
 *
 * Permite definir, para cada motivo restringido vs. no, qué canales pueden
 * ejecutar acciones automáticamente. Default seguro: TODO en manual.
 *
 * El payload se guarda en step_data; la matriz real se materializa en /admin/catalogo
 * (tab Permisos) cuando el admin la confirma desde ahí — Bundle E solo captura
 * la intención inicial.
 */
import { useState } from "react";
import { Lock, AlertTriangle } from "lucide-react";
import ONBOARDING_COPY from "../copy";

// Default motivos del catálogo MX para la matriz inicial.
const DEFAULT_MOTIVOS = [
  { code: "DIR_INSUF", name: "Dirección insuficiente", restricted: false },
  { code: "DESTI_AUS", name: "Destinatario ausente", restricted: false },
  { code: "REAGENDA_CLI", name: "Reagendado por cliente", restricted: false },
  { code: "CARRIER_DELAY", name: "Retraso del carrier", restricted: false },
  { code: "AUTORIDAD", name: "Acceso restringido por autoridad", restricted: true },
  { code: "PERDIDA", name: "Pérdida o robo", restricted: true },
];

const CHANNELS = ["email", "whatsapp", "carrier_api"];

export function StepAutomationMatrix({ onAdvance, onSkip, busy = false, initialData = {} }) {
  const c = ONBOARDING_COPY.steps.step_6_automation_matrix;
  // matrix[motivo_code][channel] = "manual" | "automatic"
  const [matrix, setMatrix] = useState(() => {
    const init = initialData.matrix || {};
    const fresh = {};
    for (const m of DEFAULT_MOTIVOS) {
      fresh[m.code] = {};
      for (const ch of CHANNELS) {
        fresh[m.code][ch] = init?.[m.code]?.[ch] || "manual";
      }
    }
    return fresh;
  });

  function setMode(motivoCode, channel, mode) {
    setMatrix((prev) => ({
      ...prev,
      [motivoCode]: { ...prev[motivoCode], [channel]: mode },
    }));
  }

  const automatedCount = Object.values(matrix).reduce(
    (acc, row) => acc + Object.values(row).filter((v) => v === "automatic").length,
    0,
  );

  function submit() {
    if (automatedCount > 0 && !window.confirm(c.confirm_activation)) return;
    onAdvance({ matrix, count_automated: automatedCount });
  }

  return (
    <div className="space-y-4" data-testid="onboarding-step-automation-matrix">
      <div>
        <h2 className="text-base font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>

      <div className="rounded-md bg-mye-bg border border-mye-border p-3 text-xs text-mye-ink">
        🛡️ {c.default_note}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs" data-testid="onboarding-matrix-table">
          <thead>
            <tr className="border-b border-mye-border">
              <th className="text-left py-2 px-1 font-medium text-mye-ink-muted">Motivo</th>
              {CHANNELS.map((ch) => (
                <th key={ch} className="text-center py-2 px-1 font-medium text-mye-ink-muted">
                  {c.channels[ch]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DEFAULT_MOTIVOS.map((m) => (
              <tr key={m.code} className="border-b border-mye-border/50">
                <td className="py-2 px-1">
                  <div className="flex items-center gap-1">
                    {m.restricted && (
                      <span title={c.restricted_tooltip}>
                        <Lock className="h-3 w-3 text-mye-ink-muted" />
                      </span>
                    )}
                    <span className="text-mye-ink">{m.name}</span>
                  </div>
                </td>
                {CHANNELS.map((ch) => (
                  <td key={ch} className="text-center py-1 px-1">
                    {m.restricted ? (
                      <span className="text-[10px] text-mye-ink-muted italic">
                        Manual
                      </span>
                    ) : (
                      <select
                        value={matrix[m.code][ch]}
                        disabled={busy}
                        onChange={(e) => setMode(m.code, ch, e.target.value)}
                        data-testid={`onboarding-matrix-${m.code}-${ch}`}
                        className="rounded border border-mye-border text-xs px-1 py-0.5 bg-white"
                      >
                        <option value="manual">{c.modes.manual}</option>
                        <option value="automatic">{c.modes.automatic}</option>
                      </select>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {automatedCount > 0 && (
        <div className="flex items-start gap-2 rounded-md bg-amber-50 border border-amber-200 p-3 text-xs">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <span className="text-amber-900">
            Tenés <b>{automatedCount}</b> celdas configuradas como automáticas. Confirmá que tu equipo conoce el flujo antes de continuar.
          </span>
        </div>
      )}

      <div className="pt-2 space-y-2">
        <button
          type="button"
          disabled={busy}
          onClick={submit}
          data-testid="onboarding-matrix-save"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50"
        >
          {c.cta_primary}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onSkip}
          data-testid="onboarding-matrix-skip"
          className="w-full text-xs text-mye-ink-muted hover:text-mye-ink py-1"
        >
          {c.cta_skip}
        </button>
      </div>
    </div>
  );
}

export default StepAutomationMatrix;
