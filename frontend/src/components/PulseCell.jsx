import React from 'react';
import { computeFeasibility, PULSE_COLORS } from '../lib/pulseUtils';

export default function PulseCell({ journey, pulseConfig }) {
    const data = computeFeasibility(journey, pulseConfig);

    if (!data) {
        return <span style={{ color: '#C4C2BA', fontSize: 13 }}>—</span>;
    }

    const { status, label, maxTransit, pctDone } = data;
    const color = PULSE_COLORS[status];
    const r = 11;
    const circ = 2 * Math.PI * r;
    const offset = circ - (pctDone / 100) * circ;

    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }} data-testid="pulse-cell">
            {/* Mini SVG ring */}
            <svg width={28} height={28} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
                <circle cx={14} cy={14} r={r} fill="none" stroke="#E2E0DB" strokeWidth={3} />
                <circle cx={14} cy={14} r={r} fill="none" stroke={color} strokeWidth={3}
                    strokeDasharray={circ} strokeDashoffset={offset}
                    strokeLinecap="round" />
            </svg>
            <div>
                <p style={{
                    fontSize: 12, fontWeight: 700, fontFamily: "'DM Mono', monospace",
                    color, margin: 0, lineHeight: 1.2,
                }}>{maxTransit} min</p>
                <p style={{ fontSize: 9, color: '#9C9A92', margin: 0 }}>{label}</p>
            </div>
        </div>
    );
}
