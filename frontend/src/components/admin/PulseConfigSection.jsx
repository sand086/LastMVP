import React from 'react';
import { Plus, Trash2, Clock, Zap } from 'lucide-react';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    green: '#10B981', greenLt: '#ECFDF5', amber: '#D97706', amberLt: '#FFFBEB',
    red: '#EF4444', redLt: '#FEF2F2', blue: '#2563EB',
    radius: 10, radiusSm: 6,
};

const inputStyle = {
    width: 60, padding: '4px 8px', borderRadius: 4,
    border: `1px solid ${T.border}`, fontSize: 13, fontWeight: 600,
    fontFamily: "'DM Mono', monospace", textAlign: 'center',
};

export default function PulseConfigSection({ pulseConfig, onChange, canEdit, providers }) {
    const cfg = pulseConfig || {};
    const horaH = cfg.hora_limite?.hour ?? 21;
    const horaM = cfg.hora_limite?.minute ?? 30;
    const trasladoDefault = cfg.traslado_primer_punto_default ?? 40;
    const tiempoEntrega = cfg.tiempo_promedio_entrega ?? 5;
    const umbralOk = cfg.umbral_ok ?? 10;
    const umbralWarn = cfg.umbral_warn ?? 5;
    const excepciones = cfg.excepciones_traslado_por_proveedor || [];

    const update = (key, val) => {
        onChange({ ...cfg, [key]: val });
    };

    const updateHora = (field, val) => {
        const hora = { ...(cfg.hora_limite || { hour: 21, minute: 30 }), [field]: Number(val) };
        onChange({ ...cfg, hora_limite: hora });
    };

    const addExcepcion = (providerId) => {
        if (!providerId) return;
        const next = [...excepciones, { provider_id: providerId, traslado_primer_punto: trasladoDefault }];
        onChange({ ...cfg, excepciones_traslado_por_proveedor: next });
    };

    const removeExcepcion = (idx) => {
        const next = excepciones.filter((_, i) => i !== idx);
        onChange({ ...cfg, excepciones_traslado_por_proveedor: next });
    };

    const updateExcepcion = (idx, val) => {
        const next = [...excepciones];
        next[idx] = { ...next[idx], traslado_primer_punto: Number(val) };
        onChange({ ...cfg, excepciones_traslado_por_proveedor: next });
    };

    const usedProviderIds = new Set(excepciones.map(e => e.provider_id));
    const availableProviders = (providers || []).filter(p => !usedProviderIds.has(p.id));

    return (
        <div style={{ borderTop: `1px dashed ${T.border}`, marginTop: 20, paddingTop: 20 }} data-testid="pulse-config-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Zap size={15} color={T.amber} />
                <h4 style={{ fontSize: 13, fontWeight: 700, color: T.textPri, margin: 0 }}>
                    Pulse — Parametros de factibilidad operativa
                </h4>
            </div>
            <p style={{ fontSize: 11, color: T.textTer, marginBottom: 16 }}>
                Configuracion del monitor de factibilidad en tiempo real. Estos valores se usan para calcular si una ruta activa puede completar sus entregas dentro de la ventana operativa.
            </p>

            {/* Ventana operativa */}
            <div style={{
                padding: 14, borderRadius: T.radiusSm,
                border: `1px solid ${T.border}`, background: T.surface, marginBottom: 12,
            }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 10 }}>Ventana operativa</p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <Row label="Hora limite de entrega">
                        <input type="number" min={12} max={23} value={horaH}
                            onChange={e => updateHora('hour', e.target.value)}
                            disabled={!canEdit} style={inputStyle}
                            data-testid="pulse-hora-h" />
                        <span style={{ fontWeight: 700, color: T.textSec }}>:</span>
                        <input type="number" min={0} max={59} value={horaM}
                            onChange={e => updateHora('minute', e.target.value)}
                            disabled={!canEdit} style={inputStyle}
                            data-testid="pulse-hora-m" />
                    </Row>

                    <Row label="Tiempo traslado a 1er punto">
                        <input type="number" min={1} max={240} value={trasladoDefault}
                            onChange={e => update('traslado_primer_punto_default', Number(e.target.value))}
                            disabled={!canEdit} style={inputStyle}
                            data-testid="pulse-traslado" />
                        <span style={{ fontSize: 11, color: T.textTer }}>min</span>
                    </Row>

                    <Row label="Tiempo promedio por entrega">
                        <input type="number" min={1} max={60} value={tiempoEntrega}
                            onChange={e => update('tiempo_promedio_entrega', Number(e.target.value))}
                            disabled={!canEdit} style={inputStyle}
                            data-testid="pulse-tiempo-entrega" />
                        <span style={{ fontSize: 11, color: T.textTer }}>min</span>
                    </Row>
                </div>
            </div>

            {/* Umbrales del semaforo */}
            <div style={{
                padding: 14, borderRadius: T.radiusSm,
                border: `1px solid ${T.border}`, background: T.surface, marginBottom: 12,
            }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 10 }}>Umbrales del semaforo</p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: T.green }} />
                        <span style={{ fontSize: 11, color: T.textSec, flex: 1 }}>En tiempo: ≥</span>
                        <input type="number" min={1} max={60} value={umbralOk}
                            onChange={e => update('umbral_ok', Number(e.target.value))}
                            disabled={!canEdit} style={{ ...inputStyle, width: 50 }}
                            data-testid="pulse-umbral-ok" />
                        <span style={{ fontSize: 11, color: T.textTer }}>min</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: T.amber }} />
                        <span style={{ fontSize: 11, color: T.textSec, flex: 1 }}>Ajustada: ≥</span>
                        <input type="number" min={1} max={60} value={umbralWarn}
                            onChange={e => update('umbral_warn', Number(e.target.value))}
                            disabled={!canEdit} style={{ ...inputStyle, width: 50 }}
                            data-testid="pulse-umbral-warn" />
                        <span style={{ fontSize: 11, color: T.textTer }}>min</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: T.red }} />
                        <span style={{ fontSize: 11, color: T.textTer, flex: 1 }}>Critica: &lt; {umbralWarn} min (auto)</span>
                    </div>
                </div>
            </div>

            {/* Excepciones de traslado por proveedor */}
            <div style={{
                padding: 14, borderRadius: T.radiusSm,
                border: `1px solid ${T.border}`, background: T.surface,
            }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 8 }}>Excepciones por proveedor (traslado)</p>

                {excepciones.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                        {excepciones.map((exc, i) => {
                            const prov = (providers || []).find(p => p.id === exc.provider_id);
                            return (
                                <div key={exc.provider_id} style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    padding: '6px 10px', borderRadius: 4, background: T.surface2,
                                }} data-testid={`pulse-exc-${exc.provider_id}`}>
                                    <span style={{ flex: 1, fontSize: 11, fontWeight: 500, color: T.textPri }}>
                                        {prov?.name || exc.provider_id}
                                    </span>
                                    <input type="number" min={1} max={240} value={exc.traslado_primer_punto}
                                        onChange={e => updateExcepcion(i, e.target.value)}
                                        disabled={!canEdit} style={{ ...inputStyle, width: 55 }} />
                                    <span style={{ fontSize: 10, color: T.textTer }}>min</span>
                                    {canEdit && (
                                        <button onClick={() => removeExcepcion(i)}
                                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}>
                                            <Trash2 size={13} color={T.red} />
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p style={{ fontSize: 11, color: T.textTer, fontStyle: 'italic', marginBottom: 10 }}>
                        Todos usan el default de {trasladoDefault} min.
                    </p>
                )}

                {canEdit && availableProviders.length > 0 && (
                    <ProviderAdder providers={availableProviders} onAdd={addExcepcion} />
                )}
            </div>
        </div>
    );
}

function Row({ label, children }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: '#6B6960', flex: 1, minWidth: 170 }}>{label}</span>
            {children}
        </div>
    );
}

function ProviderAdder({ providers, onAdd }) {
    const [sel, setSel] = React.useState('');
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <select value={sel} onChange={e => setSel(e.target.value)} data-testid="pulse-exc-select"
                style={{ flex: 1, padding: '5px 8px', borderRadius: 4, border: `1px solid #E2E0DB`, fontSize: 11, color: '#6B6960' }}>
                <option value="">Seleccionar proveedor...</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button onClick={() => { if (sel) { onAdd(sel); setSel(''); } }} disabled={!sel}
                data-testid="pulse-exc-add-btn"
                style={{
                    display: 'flex', alignItems: 'center', gap: 3, padding: '5px 10px', borderRadius: 4,
                    border: `1px solid ${sel ? '#D97706' : '#E2E0DB'}40`,
                    background: sel ? '#FFFBEB' : '#F0EFEC', color: sel ? '#D97706' : '#9C9A92',
                    fontSize: 11, fontWeight: 500, cursor: sel ? 'pointer' : 'default',
                }}>
                <Plus size={12} /> Agregar
            </button>
        </div>
    );
}
