/**
 * Bundle A · FIX-A2 — Auto-save de borrador en Reclamos.
 *
 * Clave de localStorage incluye tenant_id, claim_id y user_id para evitar
 * cross-tenant / cross-user leakage en terminales compartidas (caso
 * detectado por la auditoría UX v1).
 *
 * Comportamiento:
 *   - Hidrata al montar si existe borrador < 24h.
 *   - Auto-guarda cada `debounceMs` ms (default 5_000) cuando el valor cambia.
 *   - Borradores ≥ 24h se eliminan silenciosamente al cargar.
 *   - Si localStorage falla (quota), expone `quotaError` para mostrar warning.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const DRAFT_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

export function buildDraftKey({ tenantId, claimId, userId }) {
  return `mye_reclamo_draft_${tenantId || "anon"}_${claimId || "new"}_${userId || "anon"}`;
}

export function readDraft({ tenantId, claimId, userId }) {
  try {
    const key = buildDraftKey({ tenantId, claimId, userId });
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.saved_at) return null;
    const age = Date.now() - new Date(parsed.saved_at).getTime();
    if (Number.isNaN(age) || age >= DRAFT_MAX_AGE_MS) {
      // Caducó: limpiar silenciosamente.
      window.localStorage.removeItem(key);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearDraft({ tenantId, claimId, userId }) {
  try {
    window.localStorage.removeItem(buildDraftKey({ tenantId, claimId, userId }));
  } catch {
    /* noop */
  }
}

/**
 * useReclamoDraft — auto-save controlado de un objeto `value`.
 *
 * Retorna `{ savedAt, quotaError, flush, hydrated }`:
 *   - `savedAt`: timestamp del último guardado exitoso (Date|null).
 *   - `quotaError`: bool, true si localStorage rechazó el último write.
 *   - `flush()`: fuerza un save inmediato (útil al hacer submit).
 *   - `hydrated`: bool, true tras intentar leer el borrador inicial.
 */
export function useReclamoDraft({
  tenantId, claimId, userId, value, debounceMs = 5_000, enabled = true,
}) {
  const [savedAt, setSavedAt] = useState(null);
  const [quotaError, setQuotaError] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  // UX-AGENTE-007 (Bundle F) — indicador "guardando…" en tiempo real.
  // true entre el último cambio del valor y el flush real al localStorage.
  const [isSaving, setIsSaving] = useState(false);
  const timerRef = useRef(null);

  // Marcar hidratado tras el primer render para que el banner se decida
  // una sola vez (el componente padre llama readDraft directo).
  useEffect(() => { setHydrated(true); }, []);

  const persist = useCallback((toSave) => {
    if (!enabled) return;
    try {
      const key = buildDraftKey({ tenantId, claimId, userId });
      const payload = { ...toSave, saved_at: new Date().toISOString() };
      window.localStorage.setItem(key, JSON.stringify(payload));
      setSavedAt(new Date());
      setQuotaError(false);
    } catch {
      setQuotaError(true);
    } finally {
      setIsSaving(false);
    }
  }, [tenantId, claimId, userId, enabled]);

  // Debounce de guardado
  useEffect(() => {
    if (!enabled || !hydrated) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    setIsSaving(true);  // se mostrará "guardando…" hasta que persist termine
    timerRef.current = setTimeout(() => persist(value), debounceMs);
    return () => clearTimeout(timerRef.current);
  }, [value, persist, debounceMs, enabled, hydrated]);

  const flush = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    persist(value);
  }, [persist, value]);

  return { savedAt, quotaError, flush, hydrated, isSaving };
}
