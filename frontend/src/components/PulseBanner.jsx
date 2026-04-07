import React from 'react';
import { computeFeasibility, PULSE_COLORS, PULSE_BG } from '../lib/pulseUtils';

const T = {
    bg: '#FFFFFF', border: '#E2E0DB', textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    radius: 12,
};

export default function PulseBanner({ journey, pulseConfig }) {
    const data = computeFeasibility(journey, pulseConfig);
    if (!data) return null;

    const { status, label, maxTransit, remaining, delivered, total, failed,
        pctDone, timeLeftStr, estFinish, idealPct, paceDelta, alertMsg,
        departureMin, horaLimite, trasladoMin } = data;

    const color = PULSE_COLORS[status];
    const bgColor = PULSE_BG[status];

    // Timeline bar segments
    const totalWindow = horaLimite - departureMin;
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const trasladoPct = totalWindow > 0 ? Math.min((trasladoMin / totalWindow) * 100, 100) : 0;
    const elapsed = Math.max(0, nowMin - departureMin - trasladoMin);
    const elapsedPct = totalWindow > 0 ? Math.min((elapsed / (totalWindow - trasladoMin)) * 100, 100) : 0;
    const donePct = totalWindow > 0 ? Math.min((pctDone / 100) * (100 - trasladoPct), 100 - trasladoPct) : 0;

    const pad = (n) => String(n).padStart(2, '0');
    const depH = Math.floor(departureMin / 60);
    const depM = departureMin % 60;
    const limH = Math.floor(horaLimite / 60);
    const limM = horaLimite % 60;

    return (
        <div
            data-testid="pulse-banner"
            style={{
                border: `1px solid ${T.border}`, borderRadius: T.radius,
                background: T.bg, padding: 0, overflow: 'hidden', marginBottom: 16,
            }}
        >
            {/* Header */}
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 20px', borderBottom: `1px solid ${T.border}`,
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                        width: 8, height: 8, borderRadius: '50%', background: color,
                        boxShadow: `0 0 6px ${color}80`,
                        animation: 'pulse-dot-banner 2s ease-in-out infinite',
                    }} />
                    <span style={{ fontSize: 14, fontWeight: 700, color: T.textPri }}>
                        Pulse — Monitor de Factibilidad
                    </span>
                </div>
                <span style={{
                    padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                    background: bgColor, color, border: `1px solid ${color}30`,
                }}>
                    {label}
                </span>
            </div>

            {/* Body */}
            <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 0, padding: '16px 20px' }}>
                {/* Left: Hero metric */}
                <div style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    borderRight: `1px solid ${T.border}`, paddingRight: 20,
                }}>
                    <span style={{
                        fontSize: 36, fontWeight: 800, fontFamily: "'DM Mono', monospace",
                        color, lineHeight: 1,
                    }}>{maxTransit}</span>
                    <span style={{ fontSize: 11, color: T.textSec, fontWeight: 600 }}>min max</span>
                    <span style={{ fontSize: 10, color: T.textTer }}>entre puntos</span>
                </div>

                {/* Right: Details */}
                <div style={{ paddingLeft: 20 }}>
                    {/* Detail grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
                        <DetailItem label="Entregados" value={delivered} />
                        <DetailItem label="Restantes" value={remaining} highlight={remaining > 0} />
                        <DetailItem label="Tiempo al cierre" value={timeLeftStr} />
                        <DetailItem label="Hora est. fin" value={estFinish} />
                    </div>

                    {/* Pace bar */}
                    <div style={{ marginBottom: 14 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{ fontSize: 10, color: T.textTer, fontWeight: 600 }}>Ritmo</span>
                            <span style={{
                                fontSize: 11, fontWeight: 700, fontFamily: "'DM Mono', monospace",
                                color: paceDelta >= 0 ? PULSE_COLORS.ok : PULSE_COLORS.danger,
                            }}>
                                {paceDelta >= 0 ? '+' : ''}{paceDelta}% {paceDelta >= 0 ? 'adelantado' : 'rezagado'}
                            </span>
                        </div>
                        <div style={{ position: 'relative', height: 10, background: '#F0EFEC', borderRadius: 5, overflow: 'visible' }}>
                            <div style={{
                                height: '100%', borderRadius: 5, width: `${pctDone}%`,
                                background: color, transition: 'width 0.5s ease',
                            }} />
                            {/* Ideal marker */}
                            <div style={{
                                position: 'absolute', top: -3, left: `${idealPct}%`, transform: 'translateX(-50%)',
                                width: 2, height: 16, background: T.textPri, borderRadius: 1,
                            }} />
                            <span style={{
                                position: 'absolute', top: -16, left: `${idealPct}%`, transform: 'translateX(-50%)',
                                fontSize: 8, color: T.textTer, whiteSpace: 'nowrap',
                            }}>ideal</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                            <span style={{ fontSize: 9, color: T.textTer }}>0%</span>
                            <span style={{ fontSize: 9, color: T.textTer }}>100%</span>
                        </div>
                    </div>

                    {/* Timeline distribution */}
                    <div>
                        <span style={{ fontSize: 10, color: T.textTer, fontWeight: 600, display: 'block', marginBottom: 4 }}>Distribución temporal</span>
                        <div style={{ display: 'flex', height: 10, borderRadius: 5, overflow: 'hidden', background: '#F0EFEC' }}>
                            {/* Transit to first point */}
                            <div style={{ width: `${trasladoPct}%`, background: '#94A3B8', minWidth: trasladoPct > 0 ? 4 : 0 }} title="Traslado" />
                            {/* Delivered */}
                            <div style={{ width: `${donePct}%`, background: color, minWidth: donePct > 0 ? 4 : 0 }} title="Entregados" />
                            {/* Remaining */}
                            <div style={{ flex: 1, background: '#E2E0DB' }} title="Restantes" />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                            <span style={{ fontSize: 9, color: T.textTer }}>{pad(depH)}:{pad(depM)}</span>
                            <span style={{ fontSize: 9, color: T.textTer }}>{pad(limH)}:{pad(limM)}</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Alert footer */}
            <div style={{
                padding: '10px 20px', background: bgColor,
                borderTop: `1px solid ${color}20`,
                fontSize: 12, color, fontWeight: 500,
                display: 'flex', alignItems: 'center', gap: 6,
            }}>
                {status === 'ok' ? '\u2713' : status === 'warn' ? '\u26A0' : '\u2717'} {alertMsg}
            </div>

            <style>{`
                @keyframes pulse-dot-banner {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.5; transform: scale(1.3); }
                }
            `}</style>
        </div>
    );
}

function DetailItem({ label, value, highlight }) {
    return (
        <div>
            <p style={{
                fontSize: 18, fontWeight: 700, fontFamily: "'DM Mono', monospace",
                color: highlight ? '#EF4444' : '#1A1916', margin: 0,
            }}>{value}</p>
            <p style={{ fontSize: 10, color: '#9C9A92', margin: 0 }}>{label}</p>
        </div>
    );
}
