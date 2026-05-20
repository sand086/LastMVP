/**
 * OnboardingWizard — Slide-in lateral 480px (NO bloqueante, R51).
 *
 * Renderiza el wizard de 6 pasos + pantalla de completion. Se monta
 * globalmente en App.js y se controla mediante `useAdminOnboarding`.
 *
 * Comportamiento:
 *   - Auto-open si state.should_auto_open && el user no lo cerró manualmente
 *     en esta sesión (sessionStorage key).
 *   - El admin puede cerrar con X o tecla Esc; la confirmación se hace solo
 *     si está a mitad de un paso con cambios sin guardar (heurística simple:
 *     paso > 1 y no completado).
 *   - No bloquea la UI principal — el resto de la app sigue interactiva.
 *
 * Triggers manuales para reabrir:
 *   - window.__myeOpenOnboarding()
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, ChevronLeft } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import useAdminOnboarding from "./useAdminOnboarding";
import ONBOARDING_COPY from "./copy";
import {
  StepWelcome, StepTenantInfo, StepProjectClient, StepCarriers,
  StepCatalog, StepAutomationMatrix, StepCompletion,
} from "./steps";

const STEP_ORDER = [
  "step_1_welcome",
  "step_2_tenant_info",
  "step_3_project_client",
  "step_4_carriers",
  "step_5_catalog",
  "step_6_automation_matrix",
];

const MANDATORY_STEPS = new Set(["step_1_welcome", "step_5_catalog"]);

const SESSION_KEY = "mye_onboarding_dismissed_in_session";

export function OnboardingWizard({ enabled = true }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  // Solo activar el hook si hay user admin/superadmin/root_dev autenticado.
  const role = user?.role;
  const isAdminish = !!role && ["admin", "superadmin", "root_dev"].includes(role);
  const onboarding = useAdminOnboarding({ enabled: enabled && isAdminish });
  const { state, loading, advance, skipStep, complete, seedMxCatalog } = onboarding;
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showCompletion, setShowCompletion] = useState(false);

  // Decisión de auto-open. Una vez decidido, no se sobre-escribe.
  useEffect(() => {
    if (loading || !state) return;
    if (state.is_completed) { setOpen(false); return; }
    const dismissed = sessionStorage.getItem(SESSION_KEY) === "1";
    if (state.should_auto_open && !dismissed) setOpen(true);
  }, [loading, state]);

  // API global para reabrir desde otros componentes (avatar menu, etc.)
  useEffect(() => {
    window.__myeOpenOnboarding = () => {
      sessionStorage.removeItem(SESSION_KEY);
      setOpen(true);
      setShowCompletion(false);
    };
    return () => { delete window.__myeOpenOnboarding; };
  }, []);

  // Calcular cuál es el paso actual a mostrar
  const currentStep = useMemo(() => {
    if (!state) return STEP_ORDER[0];
    if (state.is_completed) return null;
    return state.current_step || STEP_ORDER[0];
  }, [state]);

  const stepIndex = STEP_ORDER.indexOf(currentStep);
  const totalSteps = STEP_ORDER.length;
  const remainingMins = Math.max(2, totalSteps - stepIndex);

  if (!enabled || !state || !open) return null;

  function handleClose() {
    // R51 — siempre permitir cerrar. Mostrar confirmación solo si está
    // a mitad de paso (no en welcome ni en completion).
    if (stepIndex > 0 && !state.is_completed && !showCompletion) {
      if (!window.confirm(ONBOARDING_COPY.header.close_confirm)) return;
    }
    sessionStorage.setItem(SESSION_KEY, "1");
    setOpen(false);
  }

  async function handleAdvance(stepData) {
    if (!currentStep) return;
    setBusy(true);
    try {
      const r = await advance(currentStep, stepData);
      if (r?.is_completed) {
        setShowCompletion(true);
      }
    } catch (e) {
      toast.error(ONBOARDING_COPY.errors.network);
    } finally {
      setBusy(false);
    }
  }

  async function handleSkip() {
    if (!currentStep || MANDATORY_STEPS.has(currentStep)) return;
    setBusy(true);
    try {
      const r = await skipStep(currentStep);
      if (r?.is_completed) setShowCompletion(true);
    } catch (e) {
      toast.error(ONBOARDING_COPY.errors.network);
    } finally {
      setBusy(false);
    }
  }

  async function handleFinalize() {
    setBusy(true);
    try { await complete(); } catch (_e) { /* ok */ }
    setBusy(false);
    setShowCompletion(true);
  }

  function handleGoDashboard() {
    setOpen(false);
    navigate("/dashboard");
  }

  function handleTakeTour() {
    setOpen(false);
    if (typeof window.__myeReplayTour === "function") {
      window.__myeReplayTour();
    }
  }

  const allStepsCompleted = STEP_ORDER.every(
    (s) => state?.steps_completed?.includes(s),
  );

  // Render del step actual
  function renderStep() {
    if (showCompletion || state.is_completed || !currentStep) {
      const summary = {
        tenant_name: state?.step_data?.step_2_tenant_info?.name,
        project_name: state?.step_data?.step_3_project_client?.project_name,
        client_name: state?.step_data?.step_3_project_client?.client_name,
        planned_carriers: state?.step_data?.step_4_carriers?.planned_carriers,
        catalog_seeded: !!state?.step_data?.step_5_catalog?.catalog_seeded,
        matrix_count_automated: state?.step_data?.step_6_automation_matrix?.count_automated,
      };
      return (
        <StepCompletion
          summary={summary}
          onGoDashboard={handleGoDashboard}
          onTakeTour={handleTakeTour}
        />
      );
    }
    const initialData = state?.step_data?.[currentStep] || {};
    switch (currentStep) {
      case "step_1_welcome":
        return <StepWelcome onAdvance={handleAdvance} busy={busy} />;
      case "step_2_tenant_info":
        return <StepTenantInfo onAdvance={handleAdvance} busy={busy} initialData={initialData} />;
      case "step_3_project_client":
        return <StepProjectClient onAdvance={handleAdvance} busy={busy} initialData={initialData} />;
      case "step_4_carriers":
        return <StepCarriers onAdvance={handleAdvance} onSkip={handleSkip} busy={busy} initialData={initialData} />;
      case "step_5_catalog":
        return <StepCatalog onAdvance={handleAdvance} seedMxCatalog={seedMxCatalog} busy={busy} />;
      case "step_6_automation_matrix":
        return <StepAutomationMatrix onAdvance={handleAdvance} onSkip={handleSkip} busy={busy} initialData={initialData} />;
      default:
        return null;
    }
  }

  const isFinalScreen = showCompletion || state.is_completed;
  const showSkip = currentStep && !MANDATORY_STEPS.has(currentStep) && !isFinalScreen;

  return (
    <aside
      data-testid="onboarding-wizard"
      role="complementary"
      aria-label="Asistente de configuración"
      className="fixed top-0 right-0 h-screen w-full sm:w-[480px] bg-white border-l border-mye-border shadow-2xl z-[9000] flex flex-col"
    >
      {/* Header */}
      <header className="flex items-start justify-between p-4 border-b border-mye-border bg-mye-bg">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
            Asistente · {ONBOARDING_COPY.header.title}
          </div>
          {!isFinalScreen && stepIndex >= 0 && (
            <div className="text-xs text-mye-ink-muted mt-1 flex items-center gap-2">
              <span data-testid="onboarding-progress-label">
                {ONBOARDING_COPY.header.progress_label(stepIndex + 1, totalSteps)}
              </span>
              <span>·</span>
              <span data-testid="onboarding-time-remaining">
                {ONBOARDING_COPY.header.estimated_time(remainingMins)}
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1">
          {showSkip && (
            <button
              type="button"
              onClick={handleSkip}
              disabled={busy}
              data-testid="onboarding-header-skip"
              className="text-xs text-mye-ink-muted hover:text-mye-ink px-2 py-1 rounded hover:bg-white"
            >
              {ONBOARDING_COPY.header.skip_button}
            </button>
          )}
          <button
            type="button"
            onClick={handleClose}
            data-testid="onboarding-close-button"
            aria-label={ONBOARDING_COPY.header.close_button}
            className="p-1.5 rounded hover:bg-white text-mye-ink-muted hover:text-mye-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Progress bar */}
      {!isFinalScreen && stepIndex >= 0 && (
        <div className="h-1 bg-mye-border" data-testid="onboarding-progress-bar">
          <div
            className="h-full bg-mye-accent transition-all"
            style={{ width: `${((stepIndex + 1) / totalSteps) * 100}%` }}
          />
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {renderStep()}
      </div>

      {/* Footer — solo en pasos no finales y cuando hay paso anterior */}
      {!isFinalScreen && stepIndex > 0 && (
        <footer className="border-t border-mye-border p-3 flex items-center justify-between bg-mye-bg">
          <button
            type="button"
            disabled={busy}
            data-testid="onboarding-back-button"
            className="text-xs text-mye-ink-muted hover:text-mye-ink inline-flex items-center gap-1"
            onClick={() => { /* Volver atrás recargando paso previo: out of scope simple */
              toast.info("Para volver atrás, modificá el dato en el paso siguiente o cerrá y reabrí el wizard.");
            }}
          >
            <ChevronLeft className="h-3 w-3" /> {ONBOARDING_COPY.header.back_button}
          </button>
          {allStepsCompleted && (
            <button
              type="button"
              disabled={busy}
              onClick={handleFinalize}
              data-testid="onboarding-finalize-button"
              className="text-xs bg-emerald-600 text-white rounded px-3 py-1 hover:bg-emerald-700"
            >
              {ONBOARDING_COPY.header.finish_button}
            </button>
          )}
        </footer>
      )}
    </aside>
  );
}

export default OnboardingWizard;
