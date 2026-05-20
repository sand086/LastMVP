/**
 * RuleAwareButton — Bundle B · R50.
 *
 * Botón que consulta una projection del backend (vía useRulesContext) y
 * se renderiza deshabilitado con tooltip cuando la regla no permite la
 * acción. Reemplaza <button> en CTAs gobernados por reglas R01–R49.
 *
 * Props:
 *   rules        — instancia de useRulesContext (obligatoria)
 *   actionCode   — código del action en projection.allowed_actions (p.ej. "send_validation_cta")
 *   onClick      — handler estándar
 *   children     — contenido del botón
 *   className    — Tailwind extra
 *   variant      — "primary" | "secondary" | "danger" (default: primary)
 *   testId       — data-testid (default: `rule-aware-{actionCode}`)
 *   hideWhenDisabled — si true (default), oculta totalmente el botón cuando
 *                      no está enabled (recomendado para R02 terminal — no
 *                      sugerir que podría hacerse). Para R03 conviene
 *                      mostrar deshabilitado con tooltip.
 */
import { Lock } from "lucide-react";

const VARIANTS = {
  primary:   "bg-mye-accent text-white hover:brightness-110",
  secondary: "bg-white border border-mye-border text-mye-ink hover:bg-mye-primary-soft",
  danger:    "bg-status-escalated text-white hover:brightness-110",
};

export function RuleAwareButton({
  rules, actionCode, onClick, children,
  className = "", variant = "primary",
  testId,
  hideWhenDisabled = false,
  type = "button",
  ...rest
}) {
  const allowed = rules.isAllowed(actionCode);
  const reason = rules.reason(actionCode);
  const tooltip = rules.tooltip(actionCode);
  const safeTestId = testId || `rule-aware-${actionCode}`;

  if (!allowed && hideWhenDisabled) return null;

  // Disabled visual sin atributo `disabled` HTML (evitamos el gotcha de
  // que disabled bloquea events — Bundle A · iter28). Hacemos el guard
  // en el onClick para mantener accesibilidad con aria-disabled.
  const isDisabled = !allowed;

  return (
    <button
      type={type}
      onClick={(e) => {
        if (isDisabled) {
          e.preventDefault();
          return;
        }
        if (onClick) onClick(e);
      }}
      aria-disabled={isDisabled}
      title={tooltip || undefined}
      className={[
        "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition",
        isDisabled ? "opacity-50 cursor-not-allowed" : VARIANTS[variant] || VARIANTS.primary,
        !isDisabled && VARIANTS[variant] ? "" : "",
        className,
      ].filter(Boolean).join(" ")}
      data-testid={safeTestId}
      data-rule-reason={reason || ""}
      {...rest}
    >
      {isDisabled && <Lock className="h-3.5 w-3.5" />}
      <span>{children}</span>
      {isDisabled && reason && (
        <span className="text-[10px] font-mono opacity-70">({reason})</span>
      )}
    </button>
  );
}
