import React from 'react';

const T = {
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    surface: '#FFFFFF', surface2: '#F0EFEC', border: '#E2E0DB',
    radius: '8px', radiusSm: '6px',
};

export const KPICard = ({ title, value, subtitle, icon: Icon, accentColor, accentBg, loading, testId }) => (
    <div
        style={{
            background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius,
            padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
            transition: 'box-shadow 0.2s',
        }}
        className="lm-kpi-card"
        data-testid={testId}
    >
        <div>
            <p style={{ fontSize: 12, fontWeight: 500, color: T.textTer, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                {title}
            </p>
            {loading ? (
                <div style={{ height: 32, width: 80, background: T.surface2, borderRadius: 4, animation: 'pulse 1.5s infinite' }} />
            ) : (
                <p style={{ fontSize: 28, fontWeight: 600, color: T.textPri, fontFamily: "'DM Sans', sans-serif", lineHeight: 1.1 }}>
                    {value}
                </p>
            )}
            <p style={{ fontSize: 13, color: T.textSec, marginTop: 4 }}>{subtitle}</p>
        </div>
        <div style={{ width: 44, height: 44, borderRadius: T.radiusSm, background: accentBg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <Icon style={{ width: 22, height: 22, color: accentColor }} strokeWidth={1.5} />
        </div>
    </div>
);
