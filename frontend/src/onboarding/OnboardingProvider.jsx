/**
 * OnboardingProvider — top-level orchestrator for the first-time-login tour.
 *
 * Responsibilities:
 *  - fetch onboarding status on mount
 *  - if not completed, render a discreet "Hacer tour" banner
 *  - drive react-joyride v3 through the appropriate tour preset (agent / admin
 *    / root_dev), navigating via react-router when a step has `pageHint`
 *  - persist completion to backend on finish or skip
 *  - expose window.__myeReplayTour() so the avatar header can re-run the tour
 *
 * react-joyride v3 notes:
 *  - Prop name is `onEvent`, NOT `callback` (v2 → v3 rename).
 *  - `stepIndex` is the INITIAL index only — Joyride manages its own internal
 *    cursor afterwards. To restart from step 0, fully unmount/remount the
 *    component by toggling its `key`.
 *  - Joyride is a NAMED export, not default.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Joyride, EVENTS, STATUS } from "react-joyride";
import { Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { TOUR_REGISTRY } from "./tours";


const BRAND_COLOR = "#C2410C"; // mye-accent

const JOYRIDE_STYLES = {
  options: {
    primaryColor: BRAND_COLOR,
    textColor: "#101010",
    backgroundColor: "#FFFFFF",
    arrowColor: "#FFFFFF",
    overlayColor: "rgba(16,16,16,0.45)",
    zIndex: 10_000,
  },
  buttonNext: {
    backgroundColor: BRAND_COLOR,
    borderRadius: "6px",
    fontSize: "12px",
    padding: "6px 12px",
  },
  buttonBack: { color: "#666", fontSize: "12px" },
  buttonSkip: { color: "#999", fontSize: "12px" },
  tooltipTitle: { fontSize: "14px", fontWeight: 600, marginBottom: "4px" },
  tooltipContent: { fontSize: "12px", padding: "4px 0 8px" },
};


export function OnboardingProvider() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [status, setStatus] = useState(null);
  const [running, setRunning] = useState(false);
  // Bumped on every "replay" → forces full unmount of <Joyride> so it restarts
  // at step 0 cleanly. Joyride v3 keeps an internal cursor, so remount is the
  // safest way to reset.
  const [runId, setRunId] = useState(0);
  const [showBanner, setShowBanner] = useState(false);
  const fetchedRef = useRef(false);

  // ─── Fetch onboarding status once per session ────────────────────────────
  const refresh = useCallback(async () => {
    if (!user) return;
    try {
      const r = await api.get("/users/me/onboarding");
      const data = r.data?.data || {};
      setStatus(data);
      if (!data.completed && TOUR_REGISTRY[data.suggested_tour]) {
        setShowBanner(true);
      }
    } catch { /* swallow */ }
  }, [user]);

  useEffect(() => {
    if (user && !fetchedRef.current) {
      fetchedRef.current = true;
      refresh();
    }
    if (!user) {
      fetchedRef.current = false;
      setStatus(null); setRunning(false); setShowBanner(false);
    }
  }, [user, refresh]);

  // ─── Expose replay() globally so any button can trigger the tour ─────────
  useEffect(() => {
    window.__myeReplayTour = async () => {
      try { await api.post("/users/me/onboarding/reset"); }
      catch { /* ok */ }
      // Pull fresh status (so suggested_tour is up-to-date)
      try {
        const r = await api.get("/users/me/onboarding");
        setStatus(r.data?.data || null);
      } catch { /* ok */ }
      setShowBanner(false);
      setRunning(false);
      // Force Joyride remount on next tick so it restarts from step 0
      setRunId((n) => n + 1);
      setTimeout(() => setRunning(true), 50);
    };
    return () => { delete window.__myeReplayTour; };
  }, []);

  function start() {
    setShowBanner(false);
    setRunId((n) => n + 1);
    setRunning(true);
  }

  const markCompleted = useCallback(async () => {
    setRunning(false);
    setShowBanner(false);
    try { await api.post("/users/me/onboarding/complete"); }
    catch { /* swallow */ }
  }, []);

  // ─── Joyride event handler (v3 prop is onEvent, NOT callback) ────────────
  // Use a ref to avoid stale closures over `steps` and `location.pathname`.
  const ctxRef = useRef({ steps: null, pathname: "/" });
  ctxRef.current = { steps: null, pathname: location.pathname };

  const onEvent = useCallback((data) => {
    const { type, status: jrStatus, index } = data || {};
    if (jrStatus === STATUS.FINISHED || jrStatus === STATUS.SKIPPED) {
      markCompleted();
      return;
    }

    // Bundle E (Iter33) — TARGET_NOT_FOUND robusto:
    //   1) Si el step tiene pageHint distinto a la ruta actual, navegá.
    //   2) Si ya estamos en la ruta correcta y el target sigue ausente,
    //      Joyride avanza automáticamente por su lógica continua.
    if (type === EVENTS.TARGET_NOT_FOUND || type === EVENTS.STEP_AFTER) {
      const all = ctxRef.current.steps;
      if (!all || index == null) return;
      const upcoming = all[index + 1] || all[index];
      if (upcoming?.pageHint && upcoming.pageHint !== ctxRef.current.pathname) {
        navigate(upcoming.pageHint);
      }
    }
  }, [navigate, markCompleted]);

  const tourKey = status?.suggested_tour;
  const rawSteps = useMemo(
    () => (tourKey ? TOUR_REGISTRY[tourKey] : null),
    [tourKey],
  );

  // Bundle E (Iter33) — resolver targets:
  //   * Si target no existe en DOM y fallbackToBody=true, usar "body".
  //   * Si target no existe y fallbackToBody=false → omitir el paso.
  //   * Si requiresWizardCompleted=true y el admin onboarding wizard sigue
  //     en progreso (no completed), omitir el paso (evita duplicar lo que
  //     el wizard ya explicó).
  const steps = useMemo(() => {
    if (!rawSteps) return null;
    const wizardActive = !!status && status?.in_progress; // signal best-effort
    return rawSteps
      .map((s) => {
        if (s.requiresWizardCompleted && wizardActive) return null;
        // No DOM check acá (steps se re-evalúan en cada navegación). Joyride
        // emite TARGET_NOT_FOUND y nuestro onEvent navega vía pageHint.
        return s;
      })
      .filter(Boolean);
  }, [rawSteps, status]);
  // Keep ref in sync — onEvent reads steps from here to avoid stale closures.
  ctxRef.current.steps = steps;

  return (
    <>
      {/* Discreet banner — only on first login */}
      {showBanner && steps && (
        <div className="fixed top-16 right-4 z-40 max-w-[320px] rounded-lg border border-mye-accent/30 bg-white shadow-lg p-3 animate-fade-in"
             data-testid="onboarding-banner">
          <div className="flex items-start gap-2">
            <Sparkles className="h-4 w-4 text-mye-accent shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="text-sm font-medium leading-tight">¿Hacés un tour rápido?</div>
              <div className="text-[11px] text-mye-ink-muted mt-0.5">
                {steps.length} pasos · ~{Math.ceil(steps.length * 0.4)} min · {tourKey}
              </div>
              <div className="flex items-center gap-2 mt-2">
                <button onClick={start}
                        className="rounded-md bg-mye-accent text-white px-3 py-1 text-xs hover:brightness-110 transition"
                        data-testid="onboarding-banner-start">
                  Sí, mostrame
                </button>
                <button onClick={markCompleted}
                        className="rounded-md border border-mye-border bg-white px-3 py-1 text-xs hover:bg-mye-primary-soft transition"
                        data-testid="onboarding-banner-skip">
                  Más tarde
                </button>
              </div>
            </div>
            <button onClick={() => setShowBanner(false)}
                    className="text-mye-ink-muted hover:text-mye-ink"
                    data-testid="onboarding-banner-close"
                    title="Recordarme luego">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      {steps && running && (
        <Joyride
          key={runId}
          steps={steps}
          run
          continuous
          showProgress
          showSkipButton
          disableScrolling={false}
          spotlightClicks={false}
          styles={JOYRIDE_STYLES}
          locale={{
            back: "Anterior", close: "Cerrar", last: "Listo",
            next: "Siguiente", skip: "Saltar tour",
          }}
          onEvent={onEvent}
        />
      )}
    </>
  );
}
