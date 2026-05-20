/**
 * useAdminOnboarding — hook que orquesta el wizard de onboarding admin
 * (Bundle E · Iter33).
 *
 * Responsabilidades:
 *   - fetch del estado al montar
 *   - exponer { state, advance, skipStep, complete, refresh }
 *   - aplicar pre_completed_by_tenant: si el doc del user todavía no marca
 *     esos pasos pero el tenant ya los tiene, los marcamos silenciosamente
 *     antes de devolver el estado a la UI (caso 2do admin).
 *   - emitir eventos a adminEventBus al avanzar/completar para que otras
 *     pantallas refresquen.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { emit } from "@/admin/eventBus";

const STATE_PATH = "/admin/onboarding/state";
const ADVANCE_PATH = "/admin/onboarding/advance";
const SKIP_PATH = "/admin/onboarding/skip-step";
const COMPLETE_PATH = "/admin/onboarding/complete";
const SEED_CATALOG_PATH = "/admin/onboarding/seed-mx-catalog";
const START_PATH = "/admin/onboarding/start";

export function useAdminOnboarding({ enabled = true } = {}) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const preCompletedAppliedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!enabled) { setLoading(false); return null; }
    try {
      setError(null);
      const r = await api.get(STATE_PATH);
      const data = r.data?.data || null;
      setState(data);
      return data;
    } catch (e) {
      if (e.response?.status === 403) {
        // No es admin/superadmin/root_dev — el wizard simplemente no aplica.
        setState(null);
        return null;
      }
      setError(e);
      return null;
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  // Apply pre_completed silently — solo una vez por sesión por usuario.
  // Marca como completados en el doc del user los pasos que ya están a
  // nivel tenant (caso 2do admin del mismo tenant).
  const applyPreCompletedOnce = useCallback(async (data) => {
    if (preCompletedAppliedRef.current) return;
    if (!data) return;
    const pre = data.pre_completed_by_tenant || [];
    const already = new Set(data.steps_completed || []);
    const toMark = pre.filter((s) => !already.has(s));
    if (toMark.length === 0) {
      preCompletedAppliedRef.current = true;
      return;
    }
    preCompletedAppliedRef.current = true;
    try {
      // Bootstrap el doc primero (start) y luego marca cada step.
      await api.post(START_PATH);
      for (const step of toMark) {
        await api.post(ADVANCE_PATH, { current_step: step, step_data: {} });
      }
      // Reset auto-apply para que el siguiente refresh no lo vuelva a hacer.
      await refresh();
    } catch (_e) { /* silent */ }
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const data = await refresh();
      if (cancelled) return;
      if (data?.pre_completed_by_tenant?.length > 0) {
        await applyPreCompletedOnce(data);
      }
    })();
    return () => { cancelled = true; };
  }, [refresh, applyPreCompletedOnce]);

  const advance = useCallback(async (currentStep, stepData = {}) => {
    const r = await api.post(ADVANCE_PATH, {
      current_step: currentStep, step_data: stepData,
    });
    const next = r.data?.data;
    await refresh();
    emit(`admin.onboarding.step_completed`, {
      step: currentStep, next_step: next?.current_step,
      is_completed: !!next?.is_completed,
    });
    if (next?.is_completed) emit("admin.onboarding.completed", {});
    return next;
  }, [refresh]);

  const skipStep = useCallback(async (currentStep) => {
    const r = await api.post(SKIP_PATH, { current_step: currentStep });
    await refresh();
    emit("admin.onboarding.step_skipped", { step: currentStep });
    return r.data?.data;
  }, [refresh]);

  const complete = useCallback(async () => {
    const r = await api.post(COMPLETE_PATH);
    await refresh();
    emit("admin.onboarding.completed", {});
    return r.data?.data;
  }, [refresh]);

  const seedMxCatalog = useCallback(async () => {
    const r = await api.post(SEED_CATALOG_PATH);
    return r.data?.data;
  }, []);

  return {
    state, loading, error,
    refresh, advance, skipStep, complete, seedMxCatalog,
  };
}

export default useAdminOnboarding;
