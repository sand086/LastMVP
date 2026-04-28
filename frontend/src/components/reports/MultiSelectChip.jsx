import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Check, X } from 'lucide-react';

/**
 * Multi-select chip dropdown for filters (clientes, sucursales, proveedores).
 * Pure CSS, mantiene estética del FilterBar de Reports (chip-btn, chip-dropdown-menu).
 * - selected: array<string> (ids).
 * - options: array<{id, name, ...}>
 * - allLabel: texto cuando nada está seleccionado (e.g. "Todos los clientes").
 */
export const MultiSelectChip = ({
    label, allLabel = 'Todos', options, selected, onChange,
    testid, disabled = false, emptyMessage,
}) => {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
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

    const selectedSet = useMemo(() => new Set(selected), [selected]);
    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return options;
        return options.filter(o => (o.name || '').toLowerCase().includes(q));
    }, [options, search]);

    const toggle = (id) => {
        const next = new Set(selectedSet);
        if (next.has(id)) next.delete(id); else next.add(id);
        onChange(Array.from(next));
    };
    const clearAll = (e) => {
        e.stopPropagation();
        onChange([]);
    };

    const summary = selected.length === 0
        ? allLabel
        : selected.length === 1
            ? (options.find(o => o.id === selected[0])?.name || `1 ${label}`)
            : `${selected.length} ${label}`;

    return (
        <div ref={wrapperRef} className="chip-dropdown">
            <button
                type="button"
                className={`chip-btn ${selected.length > 0 ? 'active' : ''}`}
                onClick={() => !disabled && setOpen(o => !o)}
                disabled={disabled}
                data-testid={testid}
            >
                <ChevronDown size={12} />
                <span>{summary}</span>
                {selected.length > 0 && (
                    <span
                        role="button"
                        tabIndex={0}
                        onClick={clearAll}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') clearAll(e); }}
                        style={{ cursor: 'pointer', opacity: 0.6, marginLeft: 2, display: 'inline-flex' }}
                        title={`Limpiar selección`}
                        data-testid={testid ? `${testid}-clear` : undefined}
                    >
                        <X size={11} />
                    </span>
                )}
            </button>
            {open && (
                <div
                    className="chip-dropdown-menu"
                    style={{ minWidth: 220, maxHeight: 320, overflowY: 'auto', padding: 4 }}
                    data-testid={testid ? `${testid}-menu` : undefined}
                >
                    <input
                        type="text"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder={`Buscar ${label}...`}
                        className="w-full text-xs px-2 py-1.5 border-b border-slate-200 outline-none mb-1 sticky top-0 bg-white"
                        autoFocus
                        data-testid={testid ? `${testid}-search` : undefined}
                    />
                    {filtered.length === 0 && (
                        <div className="px-3 py-3 text-xs text-slate-400 italic text-center">
                            {emptyMessage || 'Sin resultados'}
                        </div>
                    )}
                    {filtered.map(o => {
                        const isSel = selectedSet.has(o.id);
                        return (
                            <button
                                key={o.id}
                                type="button"
                                className={`chip-dropdown-item ${isSel ? 'selected' : ''}`}
                                onClick={() => toggle(o.id)}
                                style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                                data-testid={testid ? `${testid}-opt-${o.id}` : undefined}
                            >
                                <span
                                    style={{
                                        width: 14, height: 14, borderRadius: 3,
                                        border: `1px solid ${isSel ? '#10b981' : '#cbd5e1'}`,
                                        background: isSel ? '#10b981' : '#fff',
                                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                        flexShrink: 0,
                                    }}
                                >
                                    {isSel && <Check size={10} color="#fff" strokeWidth={3} />}
                                </span>
                                <span style={{ flex: 1, textAlign: 'left' }}>{o.name}</span>
                                {o.suffix && <span style={{ fontSize: 10, color: '#94a3b8' }}>{o.suffix}</span>}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
};
