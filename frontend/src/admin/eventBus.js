/**
 * adminEventBus — Bundle C (Mayo 2026).
 *
 * Bus de eventos LOCAL al módulo admin (no global). Permite que un componente
 * notifique a otros que dato administrativo cambió (ej. carrier creado) sin
 * usar stores globales (Vuex/Redux/Pinia).
 *
 * Diseño:
 *   - listeners: Map<eventName, Set<callback>>
 *   - subscribe() retorna función de UNSUBSCRIBE (patrón estándar).
 *   - emit() encapsula cada callback en try/catch para que un listener roto
 *     no rompa los demás.
 *   - En development, console.debug imprime cada emit para inspección.
 *   - clearAll() solo para tests.
 *
 * Memory leaks: cada componente que llama subscribe() DEBE guardar el
 * unsubscribe y llamarlo en el cleanup del useEffect.
 *
 *     const unsub = subscribe(ADMIN_EVENTS.CARRIER_UPDATED, handler);
 *     return () => unsub();
 *
 * NO incluido (por scope deliberado):
 *   - Cross-tab broadcasting (BroadcastChannel/WebSocket).
 *   - Telemetría / analytics integration.
 *   - Persistencia de eventos.
 */
const listeners = new Map();

const IS_DEV = (typeof process !== "undefined"
  && process.env?.NODE_ENV === "development");

export function subscribe(eventName, callback) {
  if (typeof callback !== "function") {
    throw new Error("adminEventBus.subscribe requires a function callback");
  }
  if (!listeners.has(eventName)) {
    listeners.set(eventName, new Set());
  }
  const set = listeners.get(eventName);
  set.add(callback);
  return () => {
    const s = listeners.get(eventName);
    if (!s) return;
    s.delete(callback);
    if (s.size === 0) listeners.delete(eventName);
  };
}

export function emit(eventName, payload) {
  if (IS_DEV) {
    // eslint-disable-next-line no-console
    console.debug("[adminEventBus]", eventName, payload || {});
  }
  const set = listeners.get(eventName);
  if (!set || set.size === 0) return;
  set.forEach((cb) => {
    try { cb(payload); } catch (err) {
      // eslint-disable-next-line no-console
      console.error("[adminEventBus] listener error", eventName, err);
    }
  });
}

/** Solo para tests — limpia TODOS los listeners. NO usar en código de app. */
export function clearAll() {
  listeners.clear();
}

/** Inspección — solo lectura, devuelve total de listeners por evento.
 *  Útil en el leak test (debe volver a 0 tras unmounts). */
export function _stats() {
  const out = {};
  for (const [name, set] of listeners) out[name] = set.size;
  return out;
}
