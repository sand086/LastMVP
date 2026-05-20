/**
 * useRulesContext — Bundle B · R50.
 *
 * Hook React que consume la proyección devuelta por el backend en
 * GET /api/agent/tickets/{id} o /api/reclamos/{id} (campo `projection`).
 *
 * Expone helpers para que cada componente pueda decidir si renderiza un
 * CTA y con qué tooltip — eliminando la fricción del descubrir-vía-403.
 *
 * Uso:
 *   const r = useRulesContext(detail?.projection);
 *   r.isAllowed("send_validation_cta")            // bool
 *   r.tooltip("send_validation_cta")              // string
 *   r.reason("send_validation_cta")               // "R02" | null
 *   r.isTerminalForRule("R02")                    // bool (any disabled override of R02)
 *
 * NOTA: el frontend es OPTIMISTA. Si el backend revalida y la regla
 * cambió en runtime, el submit retornará 403 → el componente debe
 * refetchar la projection (ver R50.d).
 */
export function useRulesContext(projection) {
  const actionsByCode = new Map();
  (projection?.allowed_actions || []).forEach((a) => actionsByCode.set(a.code, a));
  const applied = new Set(projection?.applied_rules || []);

  function isAllowed(code) {
    const action = actionsByCode.get(code);
    if (!action) return true;  // no proyectada = enabled por defecto
    return action.enabled === true;
  }
  function reason(code) {
    const action = actionsByCode.get(code);
    return action?.reason || null;
  }
  function tooltip(code) {
    const action = actionsByCode.get(code);
    return action?.tooltip || "";
  }
  function category(code) {
    return actionsByCode.get(code)?.category || "other";
  }
  function isTerminalForRule(ruleId) {
    return applied.has(ruleId);
  }
  function allActions() {
    return Array.from(actionsByCode.values());
  }

  return {
    isAllowed, reason, tooltip, category,
    isTerminalForRule, allActions,
    computedAt: projection?.computed_at || null,
    ttlSeconds: projection?.ttl_seconds || 0,
    appliedRules: Array.from(applied),
  };
}
