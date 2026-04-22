import React from 'react';
import { computeFeasibility, PULSE_COLORS } from '../lib/pulseUtils';

const T = {
    bg: '#FFFFFF', border: '#E2E0DB', textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    radius: 12,
};

export default function PulseStrip({ journeys, pulseConfig }) {
    // Only compute for in_progress routes
    const activeJourneys = (journeys || []).filter(j => j.status === 'in_progress');
    if (activeJourneys.length === 0) return null;

    const results = activeJourneys
        .map(j => computeFeasibility(j, pulseConfig))
        .filter(Boolean);

    if (results.length === 0) return null;

    const okCount = results.filter(r => r.status === 'ok').length;
    const warnCount = results.filter(r => r.status === 'warn').length;
    const dangerCount = results.filter(r => r.status === 'danger').length;
    const totalDelivered = results.reduce((s, r) => s + r.delivered, 0);
    const totalPkgs = results.reduce((s, r) => s + r.total, 0);

    return (
        <div
            data-testid="pulse-strip"
            style={{
                display: 'flex', alignItems: 'center', gap: 16,
                padding: '14px 24px', background: T.bg,
                border: `1px solid ${T.border}`, borderRadius: T.radius,
                marginBottom: 16, flexWrap: 'wrap',
            }}
        >
            {/* Dot + Title */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 180 }}>
                <span style={{
                    width: 8, height: 8, borderRadius: '50%', background: PULSE_COLORS.ok,
                    boxShadow: `0 0 6px ${PULSE_COLORS.ok}80`,
                    animation: 'pulse-dot 2s ease-in-out infinite',
                }} />
                <div>
                    <span style={{ fontSize: 13, fontWeight: 700, color: T.textPri }}>Pulse Monitor</span>
                    <p style={{ fontSize: 10, color: T.textTer, margin: 0 }}>Factibilidad en tiempo real</p>
                </div>
            </div>

            {/* Divider */}
            <div style={{ width: 1, height: 32, background: T.border }} />

            {/* KPIs */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
                <KPI label="Activas" value={results.length} color="#2563EB" />
                {okCount > 0 && <KPI label="En tiempo" value={okCount} color={PULSE_COLORS.ok} />}
                {warnCount > 0 && <KPI label="Ajustadas" value={warnCount} color={PULSE_COLORS.warn} />}
                {dangerCount > 0 && <KPI label="Criticas" value={dangerCount} color={PULSE_COLORS.danger} />}
                <KPI label="Entregados" value={`${totalDelivered}/${totalPkgs}`} color={T.textSec} />
            </div>

            {/* Mini color blocks */}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 3, alignItems: 'center' }}>
                {results.map((r, i) => (
                    <div
                        key={`pulse-${i}-${r.label || 'x'}`}
                        style={{
                            width: 14, height: 14, borderRadius: 3,
                            background: PULSE_COLORS[r.status],
                            opacity: 0.85,
                        }}
                        title={`${r.label} — ${r.maxTransit} min`}
                    />
                ))}
            </div>

            {/* Pulse animation keyframes */}
            <style>{`
                @keyframes pulse-dot {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.5; transform: scale(1.3); }
                }
            `}</style>
        </div>
    );
}

function KPI({ label, value, color }) {
    return (
        <div style={{ textAlign: 'center', minWidth: 50 }}>
            <p style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono', monospace", color, margin: 0 }}>{value}</p>
            <p style={{ fontSize: 10, color: '#9C9A92', margin: 0 }}>{label}</p>
        </div>
    );
}
