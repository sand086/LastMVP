/**
 * MxAddressInput — Bundle D · Mejora.
 *
 * Captura dirección estructurada mexicana con autocomplete por CP.
 * El user escribe los 5 dígitos del CP y el componente:
 *   1. Llama `GET /api/util/cp-lookup/{cp}`.
 *   2. Auto-rellena `estado` y `ciudad`.
 *   3. Convierte el input de `colonia` en un `<select>` con las colonias
 *      del CP (pueden ser varias). Si no encuentra el CP, fallback a input.
 *
 * Props:
 *   value: { calle, numero_exterior, numero_interior, colonia, codigo_postal,
 *            ciudad, estado, referencias, country } | null
 *   onChange(newValue)
 *   disabled, testIdPrefix
 *
 * Diseño operativo: 4 columnas (Calle, Núm Ext, Núm Int, CP), 2 columnas
 * (Colonia, Ciudad, Estado), 1 fila (Referencias). En móvil colapsa a 1 col.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, MapPin, AlertTriangle } from "lucide-react";
import { MxInput } from "./MxInput";

const EMPTY = {
  calle: "", numero_exterior: "", numero_interior: "",
  colonia: "", codigo_postal: "",
  ciudad: "", estado: "", referencias: "",
  country: "MX",
};

export function MxAddressInput({
  value, onChange, disabled = false, testIdPrefix = "mxaddress",
}) {
  const v = { ...EMPTY, ...(value || {}) };
  const [coloniaOptions, setColoniaOptions] = useState([]);
  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookupError, setLookupError] = useState(null);
  const lastCpLookupRef = useRef(null);

  function update(patch) {
    onChange?.({ ...v, ...patch });
  }

  // Lookup automático cuando CP llega a 5 dígitos
  useEffect(() => {
    const cp = (v.codigo_postal || "").trim();
    if (cp.length !== 5 || !/^\d{5}$/.test(cp)) {
      setColoniaOptions([]);
      return;
    }
    if (lastCpLookupRef.current === cp) return; // ya lo procesamos
    lastCpLookupRef.current = cp;
    let cancelled = false;
    setLookupBusy(true);
    setLookupError(null);
    api.get(`/util/cp-lookup/${cp}`)
      .then((r) => {
        if (cancelled) return;
        const data = r.data?.data?.data;
        if (!data) {
          setLookupError("No se encontró el código postal.");
          setColoniaOptions([]);
          return;
        }
        const cols = data.colonias || [];
        setColoniaOptions(cols);
        // Auto-fill estado/ciudad si vienen vacíos
        const patch = {};
        if (!v.estado && data.estado) patch.estado = data.estado;
        if (!v.ciudad && data.ciudad) patch.ciudad = data.ciudad;
        // Si solo hay 1 colonia y la actual está vacía, pre-seleccionar
        if (cols.length === 1 && !v.colonia) patch.colonia = cols[0].colonia;
        if (Object.keys(patch).length > 0) update(patch);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e.response?.data?.errors?.[0]?.message || "Error al consultar el CP.";
        setLookupError(msg);
        setColoniaOptions([]);
      })
      .finally(() => { if (!cancelled) setLookupBusy(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [v.codigo_postal]);

  return (
    <div className="space-y-2" data-testid={`${testIdPrefix}-wrapper`}>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <label className="block md:col-span-2">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Calle
          </span>
          <input
            type="text" value={v.calle} disabled={disabled}
            onChange={(e) => update({ calle: e.target.value })}
            placeholder="Av. Insurgentes"
            data-testid={`${testIdPrefix}-calle`}
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Núm ext.
          </span>
          <input
            type="text" value={v.numero_exterior} disabled={disabled}
            onChange={(e) => update({ numero_exterior: e.target.value })}
            placeholder="1234"
            data-testid={`${testIdPrefix}-numext`}
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
          />
        </label>
        <label className="block">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Núm int.
          </span>
          <input
            type="text" value={v.numero_interior} disabled={disabled}
            onChange={(e) => update({ numero_interior: e.target.value })}
            placeholder="A-3 (opcional)"
            data-testid={`${testIdPrefix}-numint`}
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
          />
        </label>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <div className="md:col-span-1">
          <MxInput
            type="cp" label="CP"
            value={v.codigo_postal} disabled={disabled}
            onChange={(val) => update({ codigo_postal: val })}
            testId={`${testIdPrefix}-cp`}
          />
        </div>
        <label className="block md:col-span-2">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1 flex items-center gap-1">
            Colonia
            {lookupBusy && <Loader2 className="h-3 w-3 animate-spin text-mye-accent" />}
            {lookupError && (
              <span className="text-status-escalated inline-flex items-center gap-1" title={lookupError}>
                <AlertTriangle className="h-3 w-3" />
              </span>
            )}
            {!lookupBusy && coloniaOptions.length > 0 && (
              <span className="text-mye-ink-muted normal-case" data-testid={`${testIdPrefix}-colonias-count`}>
                ({coloniaOptions.length} colonia{coloniaOptions.length !== 1 ? "s" : ""} para este CP)
              </span>
            )}
          </span>
          {coloniaOptions.length > 0 ? (
            <select
              value={v.colonia} disabled={disabled}
              onChange={(e) => update({ colonia: e.target.value })}
              data-testid={`${testIdPrefix}-colonia-select`}
              className="w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm"
            >
              <option value="">— Selecciona —</option>
              {coloniaOptions.map((c, i) => (
                <option key={`${c.colonia}-${i}`} value={c.colonia}>{c.colonia}</option>
              ))}
              <option value="__OTRA__">Otra (escribir manual)</option>
            </select>
          ) : (
            <input
              type="text" value={v.colonia} disabled={disabled}
              onChange={(e) => update({ colonia: e.target.value })}
              placeholder="Roma Norte"
              data-testid={`${testIdPrefix}-colonia-input`}
              className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
            />
          )}
        </label>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="block">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Ciudad / Municipio
          </span>
          <input
            type="text" value={v.ciudad} disabled={disabled}
            onChange={(e) => update({ ciudad: e.target.value })}
            placeholder="Ciudad de México"
            data-testid={`${testIdPrefix}-ciudad`}
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            Estado
          </span>
          <input
            type="text" value={v.estado} disabled={disabled}
            onChange={(e) => update({ estado: e.target.value })}
            placeholder="CDMX"
            data-testid={`${testIdPrefix}-estado`}
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
          />
        </label>
      </div>

      <label className="block">
        <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1 flex items-center gap-1">
          <MapPin className="h-3 w-3" /> Referencias
        </span>
        <textarea
          rows={2} value={v.referencias} disabled={disabled} maxLength={500}
          onChange={(e) => update({ referencias: e.target.value })}
          placeholder="Esquina con Av. Reforma. Edificio gris, piso 5."
          data-testid={`${testIdPrefix}-referencias`}
          className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
        />
      </label>
    </div>
  );
}
