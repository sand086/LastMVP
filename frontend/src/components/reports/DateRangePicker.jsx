import React, { useEffect, useRef, useState } from 'react';
import { Calendar as CalendarIcon, X } from 'lucide-react';
import { Calendar } from '../ui/calendar';
import { es } from 'date-fns/locale';

/* Format a Date as YYYY-MM-DD (local timezone, NOT UTC) */
const fmtIso = (d) => {
    if (!d) return '';
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
};

const fmtDisplay = (iso) => {
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('es-MX', {
        day: 'numeric', month: 'short', year: 'numeric',
    });
};

/**
 * Single-popover calendar para seleccionar rango (Desde - Hasta) en el mismo lugar.
 * Reemplaza los 2 inputs `<input type="date">` antiguos.
 */
export const DateRangePicker = ({ from, to, onChange, testid = 'date-range-picker', disabled = false }) => {
    const [open, setOpen] = useState(false);
    const wrapperRef = useRef(null);

    useEffect(() => {
        const handler = (e) => {
            if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
                setOpen(false);
            }
        };
        if (open) document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    const range = {
        from: from ? new Date(`${from}T00:00:00`) : undefined,
        to:   to   ? new Date(`${to}T00:00:00`)   : undefined,
    };

    const handleSelect = (r) => {
        if (!r) { onChange({ from: '', to: '' }); return; }
        onChange({ from: fmtIso(r.from), to: fmtIso(r.to || r.from) });
    };

    const display = from
        ? (to && to !== from
            ? `${fmtDisplay(from)} → ${fmtDisplay(to)}`
            : fmtDisplay(from))
        : 'Seleccionar fechas';

    const clear = (e) => { e.stopPropagation(); onChange({ from: '', to: '' }); };

    return (
        <div ref={wrapperRef} className="chip-dropdown" style={{ position: 'relative' }}>
            <button
                type="button"
                className={`chip-btn ${from ? 'active' : ''}`}
                onClick={() => !disabled && setOpen(o => !o)}
                disabled={disabled}
                data-testid={testid}
            >
                <CalendarIcon size={13} />
                <span>{display}</span>
                {from && (
                    <span
                        role="button"
                        tabIndex={0}
                        onClick={clear}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') clear(e); }}
                        style={{ cursor: 'pointer', opacity: 0.6, marginLeft: 2, display: 'inline-flex' }}
                        title="Limpiar rango"
                        data-testid={`${testid}-clear`}
                    >
                        <X size={11} />
                    </span>
                )}
            </button>
            {open && (
                <div
                    className="chip-dropdown-menu"
                    style={{ padding: 0, minWidth: 'auto', overflow: 'hidden' }}
                    data-testid={`${testid}-popover`}
                >
                    <Calendar
                        mode="range"
                        defaultMonth={range.from}
                        selected={range}
                        onSelect={handleSelect}
                        numberOfMonths={2}
                        locale={es}
                        weekStartsOn={1}
                    />
                    <div
                        style={{
                            display: 'flex', justifyContent: 'space-between',
                            padding: '6px 12px', borderTop: '1px solid #e2e8f0',
                            background: '#f8fafc',
                        }}
                    >
                        <span style={{ fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>
                            {from || '—'} → {to || '—'}
                        </span>
                        <button
                            type="button"
                            onClick={() => setOpen(false)}
                            className="text-xs font-semibold text-emerald-600 hover:text-emerald-700"
                            data-testid={`${testid}-done`}
                        >
                            Aplicar
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
