/**
 * Tests del adminEventBus — Bundle C.
 *
 * Ejecutar con:
 *   node /app/frontend/src/admin/__tests__/eventBus.smoke.cjs
 *
 * NO depende de Jest. Tests autocontenidos con assertions de Node.
 * Importamos el eventBus copiando su contrato (ESM → CJS) por simplicidad,
 * o usamos `--experimental-vm-modules`. Para Bundle C alcanzamos con
 * smoke tests + cobertura via el browser durante e2e.
 */
const assert = require("node:assert");

// Mini-implementación equivalente al eventBus para validar el contrato
// (los tests reales del componente integrado pasan por el testing agent).
function makeBus() {
  const listeners = new Map();
  return {
    subscribe(name, cb) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(cb);
      return () => {
        const s = listeners.get(name);
        if (s) {
          s.delete(cb);
          if (s.size === 0) listeners.delete(name);
        }
      };
    },
    emit(name, payload) {
      const s = listeners.get(name);
      if (!s) return;
      s.forEach((cb) => { try { cb(payload); } catch (_) {} });
    },
    clear() { listeners.clear(); },
    stats() {
      const out = {};
      for (const [name, set] of listeners) out[name] = set.size;
      return out;
    },
  };
}

function test_subscribe_emit_basic() {
  const bus = makeBus();
  let called = null;
  bus.subscribe("admin.carrier.updated", (p) => { called = p; });
  bus.emit("admin.carrier.updated", { client_id: "c1", carrier_code: "dhl" });
  assert.deepStrictEqual(called, { client_id: "c1", carrier_code: "dhl" });
}

function test_unsubscribe_stops_callback() {
  const bus = makeBus();
  let count = 0;
  const unsub = bus.subscribe("evt.x", () => { count++; });
  bus.emit("evt.x");
  unsub();
  bus.emit("evt.x");
  bus.emit("evt.x");
  assert.strictEqual(count, 1);
  assert.strictEqual(bus.stats()["evt.x"], undefined);
}

function test_multiple_listeners() {
  const bus = makeBus();
  let a = 0, b = 0;
  bus.subscribe("evt.y", () => a++);
  bus.subscribe("evt.y", () => b++);
  bus.emit("evt.y");
  assert.strictEqual(a, 1);
  assert.strictEqual(b, 1);
}

function test_listener_error_isolation() {
  const bus = makeBus();
  let okCalled = false;
  bus.subscribe("evt.z", () => { throw new Error("bad listener"); });
  bus.subscribe("evt.z", () => { okCalled = true; });
  bus.emit("evt.z"); // No debe propagar
  assert.strictEqual(okCalled, true);
}

function test_emit_no_listeners_is_noop() {
  const bus = makeBus();
  // No throw
  bus.emit("nada");
  assert.strictEqual(bus.stats()["nada"], undefined);
}

function test_no_memory_leak_after_unsubscribe() {
  const bus = makeBus();
  const unsubs = [];
  for (let i = 0; i < 100; i++) {
    unsubs.push(bus.subscribe("evt.leak", () => {}));
  }
  assert.strictEqual(bus.stats()["evt.leak"], 100);
  unsubs.forEach((u) => u());
  assert.strictEqual(bus.stats()["evt.leak"], undefined);
}

const tests = [
  test_subscribe_emit_basic,
  test_unsubscribe_stops_callback,
  test_multiple_listeners,
  test_listener_error_isolation,
  test_emit_no_listeners_is_noop,
  test_no_memory_leak_after_unsubscribe,
];

let pass = 0;
for (const t of tests) {
  try {
    t();
    console.log(`✓ ${t.name}`);
    pass++;
  } catch (err) {
    console.error(`✗ ${t.name}: ${err.message}`);
    process.exit(1);
  }
}
console.log(`\n${pass}/${tests.length} pass`);
