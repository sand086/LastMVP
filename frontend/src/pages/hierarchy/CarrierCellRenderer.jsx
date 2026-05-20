/**
 * CarrierCellRenderer — celda compacta para la tabla de clientes
 * que muestra qué carriers están configurados y permite agregar nuevos.
 *
 * Renderiza:
 *   - Badge por cada carrier ya configurado (clic → reabre el modal)
 *   - Dropdown "+ Configurar" para agregar los carriers que aún no están
 */
import { useState, useRef, useEffect } from "react";
import { Plus, KeyRound } from "lucide-react";
import { CARRIER_SCHEMAS } from "./carrierSchemas";


export default function CarrierCellRenderer({ client, onConfigure }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handler(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const carriers = client.carriers || {};
  const configured = Object.entries(carriers)
    .filter(([code]) => CARRIER_SCHEMAS[code])
    .map(([code, cfg]) => ({ code, cfg }));
  const available = Object.keys(CARRIER_SCHEMAS)
    .filter((code) => !carriers[code]);

  return (
    <div className="flex items-center gap-1.5 flex-wrap" data-testid={`client-carriers-cell-${client.id}`}>
      {configured.map(({ code, cfg }) => {
        const schema = CARRIER_SCHEMAS[code];
        const ready = !!cfg.api_key_set;
        return (
          <button key={code}
                  onClick={(e) => { e.stopPropagation(); onConfigure(code); }}
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-mono transition ${
                    ready
                      ? "border-status-resolved/40 bg-status-resolved/5 text-status-resolved hover:bg-status-resolved/10"
                      : "border-mye-border bg-white text-mye-ink-muted hover:bg-mye-primary-soft"
                  }`}
                  data-testid={`client-carrier-btn-${code}-${client.id}`}>
            <KeyRound className="h-3 w-3" />
            {schema.label}
            {cfg.project_ids?.length > 0 && (
              <span className="text-[10px] opacity-70">· {cfg.project_ids.length}</span>
            )}
          </button>
        );
      })}

      {available.length > 0 && (
        <div ref={ref} className="relative">
          <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
                  className="inline-flex items-center gap-1 rounded-md border border-dashed border-mye-border bg-white px-2 py-1 text-[11px] text-mye-ink-muted hover:bg-mye-primary-soft hover:border-mye-accent hover:text-mye-ink transition"
                  data-testid={`client-carriers-add-${client.id}`}>
            <Plus className="h-3 w-3" /> Configurar
          </button>
          {open && (
            <div className="absolute right-0 top-7 z-20 min-w-[180px] rounded-md border border-mye-border bg-white shadow-lg py-1"
                 data-testid={`client-carriers-menu-${client.id}`}>
              {available.map((code) => (
                <button key={code}
                        onClick={(e) => { e.stopPropagation(); setOpen(false); onConfigure(code); }}
                        className="w-full text-left px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                        data-testid={`client-carriers-menu-item-${code}`}>
                  <KeyRound className="h-3 w-3 inline mr-1.5 text-mye-accent" />
                  {CARRIER_SCHEMAS[code].label}
                  <span className="block text-[10px] text-mye-ink-muted ml-5">
                    {CARRIER_SCHEMAS[code].description}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {configured.length === 0 && available.length === 0 && (
        <span className="text-[11px] font-mono text-mye-ink-muted">—</span>
      )}
    </div>
  );
}
