import React from 'react';
import { Zap } from 'lucide-react';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    green: '#10B981', amber: '#D97706', red: '#EF4444',
    radius: 10, radiusSm: 6,
};

const inputStyle = {
    width: 60, padding: '4px 8px', borderRadius: 4,
    border: `1px solid ${T.border}`, fontSize: 13, fontWeight: 600,
    fontFamily: "'DM Mono', monospace", textAlign: 'center',
};

export default function PulseConfigSection({ pulseConfig, onChange, canEdit }) {
    const cfg = pulseConfig || {};
    const horaH = cfg.hora_limite?.hour ?? 21;
    const horaM = cfg.hora_limite?.minute ?? 30;
    const tiempoEntrega = cfg.tiempo_promedio_entrega ?? 5;
    const umbralOk = cfg.umbral_ok ?? 10;
    const umbralWarn = cfg.umbral_warn ?? 5;

    const update = (key, val) => {
        onChange({ ...cfg, [key]: val });
    };

    const updateHora = (field, val) => {
        const hora = { ...(cfg.hora_limite || { hour: 21, minute: 30 }), [field]: Number(val) };
        onChange({ ...cfg, hora_limite: hora });
    };

    return (
        <div style={{ borderTop: `1px dashed ${T.border}`, marginTop: 20, paddingTop: 20 }} data-testid="pulse-config-section">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Zap size={15} color={T.amber} />
                <h4 style={{ fontSize: 13, fontWeight: 700, color: T.textPri, margin: 0 }}>
                    Pulse — Parametros de factibilidad operativa
                </h4>
            </div>
            <p style={{ fontSize: 11, color: T.textTer, marginBottom: 16 }}>
                Configuracion global del monitor de factibilidad en tiempo real. El traslado al primer punto se configura individualmente al iniciar cada ruta.
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
                border: `1px solid ${T.border}`, background: T.surface,
            }}>
                <p style={{ fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 10 }}>Umbrales del semaforo</p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: T.green }} />
                        <span style={{ fontSize: 11, color: T.textSec, flex: 1 }}>En tiempo: &ge;</span>
                        <input type="number" min={1} max={60} value={umbralOk}
                            onChange={e => update('umbral_ok', Number(e.target.value))}
                            disabled={!canEdit} style={{ ...inputStyle, width: 50 }}
                            data-testid="pulse-umbral-ok" />
                        <span style={{ fontSize: 11, color: T.textTer }}>min</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: T.amber }} />
                        <span style={{ fontSize: 11, color: T.textSec, flex: 1 }}>Ajustada: &ge;</span>
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
