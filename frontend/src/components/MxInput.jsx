/**
 * MxInput — Bundle D · Parte 2.
 *
 * Componente input estándar para captura de datos en formato mexicano.
 * Aplica máscara + validación + normalización antes del onChange.
 *
 * Tipos soportados:
 *   - "cp"        — Código postal MX (5 dígitos, normaliza al onBlur).
 *   - "rfc"       — RFC personal o moral (12-13 chars alfanuméricos).
 *   - "telefono"  — +52 o 10 dígitos; normaliza a "+52 55 1234 5678".
 *   - "curp"      — CURP (18 chars, regex SAT).
 *   - "fecha"     — type=date HTML5 con `lang="es-MX"`.
 *
 * Props:
 *   value, onChange (recibe el value normalizado), type, label,
 *   required (bool), error (string), testId, placeholder, name, disabled.
 */
import { useState } from "react";

const VALIDATORS = {
  cp: {
    pattern: /^\d{5}$/,
    mask: (v) => (v || "").replace(/\D/g, "").slice(0, 5),
    error: "El código postal debe tener 5 dígitos.",
    placeholder: "06700",
    inputMode: "numeric",
    maxLength: 5,
  },
  rfc: {
    // Persona física: AAAA######AAA (13). Moral: AAA######AAA (12).
    pattern: /^([A-ZÑ&]{3,4})(\d{2})(\d{2})(\d{2})([A-Z\d]{2})([A\d])$/i,
    mask: (v) => (v || "").toUpperCase().replace(/[^A-ZÑ&0-9]/g, "").slice(0, 13),
    error: "RFC inválido (formato esperado XAXX010101000).",
    placeholder: "XAXX010101000",
    inputMode: "text",
    maxLength: 13,
  },
  telefono: {
    // Acepta +52 prefix o 10 dígitos.
    pattern: /^(\+52\s?)?(\d{2}\s?\d{4}\s?\d{4})$/,
    mask: (v) => {
      const digits = (v || "").replace(/\D/g, "");
      // Conservar +52 si comienza así
      const starts52 = (v || "").trim().startsWith("+52");
      const rest = (digits.startsWith("52") && starts52) ? digits.slice(2) : digits;
      const ten = rest.slice(0, 10);
      const prefix = starts52 ? "+52 " : "";
      if (ten.length <= 2) return prefix + ten;
      if (ten.length <= 6) return `${prefix}${ten.slice(0, 2)} ${ten.slice(2)}`;
      return `${prefix}${ten.slice(0, 2)} ${ten.slice(2, 6)} ${ten.slice(6)}`;
    },
    error: "Teléfono inválido (formato esperado +52 55 1234 5678 o 10 dígitos).",
    placeholder: "+52 55 1234 5678",
    inputMode: "tel",
    maxLength: 18,
  },
  curp: {
    pattern: /^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$/i,
    mask: (v) => (v || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 18),
    error: "CURP inválido (18 caracteres).",
    placeholder: "AAAA000000HDFXXX00",
    inputMode: "text",
    maxLength: 18,
  },
};

export function MxInput({
  type = "telefono",
  value, onChange, label, required = false,
  error: errorProp,
  testId, placeholder, name, disabled = false,
  className = "",
}) {
  const cfg = VALIDATORS[type];
  const [localError, setLocalError] = useState(null);
  const error = errorProp || localError;

  // Fallback para "fecha" → input nativo
  if (type === "fecha") {
    return (
      <label className={`block ${className}`} data-testid={testId ? `${testId}-wrapper` : undefined}>
        {label && (
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            {label}{required && " *"}
          </span>
        )}
        <input
          type="date" lang="es-MX" value={value || ""} disabled={disabled}
          onChange={(e) => onChange?.(e.target.value)}
          name={name} data-testid={testId}
          className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
        />
      </label>
    );
  }

  function handleChange(e) {
    const next = cfg.mask(e.target.value);
    onChange?.(next);
  }

  function handleBlur(e) {
    const v = cfg.mask(e.target.value);
    if (v && !cfg.pattern.test(v)) {
      setLocalError(cfg.error);
    } else {
      setLocalError(null);
    }
  }

  return (
    <label className={`block ${className}`} data-testid={testId ? `${testId}-wrapper` : undefined}>
      {label && (
        <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
          {label}{required && " *"}
        </span>
      )}
      <input
        type="text"
        inputMode={cfg.inputMode}
        maxLength={cfg.maxLength}
        value={value || ""}
        onChange={handleChange}
        onBlur={handleBlur}
        placeholder={placeholder || cfg.placeholder}
        name={name}
        disabled={disabled}
        aria-invalid={!!error}
        data-testid={testId}
        className={[
          "w-full rounded-md border bg-white px-3 py-2 text-sm font-mono",
          error ? "border-status-escalated" : "border-mye-border",
          disabled ? "opacity-50 cursor-not-allowed" : "",
        ].join(" ")}
      />
      {error && (
        <span className="block text-[11px] text-status-escalated mt-1"
              data-testid={testId ? `${testId}-error` : undefined}>
          {error}
        </span>
      )}
    </label>
  );
}
