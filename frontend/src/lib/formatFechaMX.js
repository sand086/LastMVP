/**
 * formatFechaMX — Bundle D · Parte 2 (Mayo 2026).
 *
 * Single Source of Truth para formato de fecha/hora en español MX.
 * Construido sobre Intl nativo (NO dependencias de moment.js/date-fns).
 *
 * Convenciones aplicadas:
 *   - Fechas: 24h en CSA operativo. dd/mes/yy en compactas, dd de mes de yyyy en largas.
 *   - Zona horaria: convertir SIEMPRE a "America/Mexico_City" al mostrar
 *     (BD almacena UTC — R20).
 *   - null/undefined → "" (no throw).
 *   - Input acepta Date | string ISO | timestamp number.
 *
 * Reglas BP-05 (Localización México como default).
 */

const TZ = "America/Mexico_City";
const LOCALE = "es-MX";

function toDate(input) {
  if (input == null) return null;
  if (input instanceof Date) return isNaN(input.getTime()) ? null : input;
  if (typeof input === "number") {
    // Heurística: si el valor es < año 3000 en segundos, asumir segundos.
    const ms = input < 1e12 ? input * 1000 : input;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? null : d;
  }
  if (typeof input === "string") {
    const d = new Date(input);
    return isNaN(d.getTime()) ? null : d;
  }
  return null;
}

// "15/oct/26 14:23"
export function fechaCompacta(input) {
  const d = toDate(input);
  if (!d) return "";
  const datePart = new Intl.DateTimeFormat(LOCALE, {
    day: "2-digit", month: "short", year: "2-digit", timeZone: TZ,
  }).format(d).replace(/\./g, "").replace(/ de /g, "/");
  const timePart = new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ,
  }).format(d);
  return `${datePart} ${timePart}`;
}

// "15 de octubre de 2026, 14:23 hrs CDMX"
export function fechaCompleta(input) {
  const d = toDate(input);
  if (!d) return "";
  const datePart = new Intl.DateTimeFormat(LOCALE, {
    day: "numeric", month: "long", year: "numeric", timeZone: TZ,
  }).format(d);
  const timePart = new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ,
  }).format(d);
  return `${datePart}, ${timePart} hrs CDMX`;
}

// "hace 30 min" / "hace 2 días" / "en 3 días" / "ahora"
export function fechaRelativa(input) {
  const d = toDate(input);
  if (!d) return "";
  const diffMs = d.getTime() - Date.now();
  const absSeconds = Math.abs(Math.round(diffMs / 1000));
  const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });
  if (absSeconds < 45) return "ahora";
  if (absSeconds < 90) return rtf.format(Math.sign(diffMs) * 1, "minute");
  const minutes = Math.round(diffMs / 60000);
  if (Math.abs(minutes) < 45) return rtf.format(minutes, "minute");
  const hours = Math.round(diffMs / 3_600_000);
  if (Math.abs(hours) < 22) return rtf.format(hours, "hour");
  const days = Math.round(diffMs / 86_400_000);
  if (Math.abs(days) < 26) return rtf.format(days, "day");
  const months = Math.round(diffMs / (86_400_000 * 30));
  if (Math.abs(months) < 11) return rtf.format(months, "month");
  return rtf.format(Math.round(diffMs / (86_400_000 * 365)), "year");
}

// "Entregado el 15 oct, 14:23 hrs CDMX"
export function fechaBanner(input, accion = "Entregado") {
  const d = toDate(input);
  if (!d) return accion;
  const datePart = new Intl.DateTimeFormat(LOCALE, {
    day: "numeric", month: "short", timeZone: TZ,
  }).format(d).replace(/\./g, "");
  const timePart = new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ,
  }).format(d);
  return `${accion} el ${datePart}, ${timePart} hrs CDMX`;
}

// "15 de octubre de 2026"
export function fechaLarga(input) {
  const d = toDate(input);
  if (!d) return "";
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric", month: "long", year: "numeric", timeZone: TZ,
  }).format(d);
}

// "14:23 hrs"
export function horaSola(input) {
  const d = toDate(input);
  if (!d) return "";
  const timePart = new Intl.DateTimeFormat(LOCALE, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ,
  }).format(d);
  return `${timePart} hrs`;
}

// "2026-10-15" — para inputs HTML5 type=date.
export function fechaParaInput(input) {
  const d = toDate(input);
  if (!d) return "";
  // ISO en TZ de CDMX (no UTC) para que el input no salte un día.
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: TZ,
  }).format(d);
  return parts;
}

// "$1,234.56 MXN" — formato MX para currency
export function formatCurrencyMX(amount, currency = "MXN") {
  if (amount == null) return "—";
  const num = Number(amount);
  if (Number.isNaN(num)) return "—";
  const formatted = new Intl.NumberFormat(LOCALE, {
    style: "currency", currency, minimumFractionDigits: 2,
  }).format(num);
  // Intl ya prefija $ + sufija MXN. Para USD el output es "US$1,234.56".
  return formatted;
}
