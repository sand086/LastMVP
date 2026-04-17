import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Info, Check } from 'lucide-react';

export const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF', green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB', coral: '#DC2626', coralLt: '#FEF2F2',
    teal: '#0D9488', tealLt: '#F0FDFA', purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

export const scoreColor = (s) => s >= 90 ? T.green : s >= 70 ? T.amber : T.coral;
export const confColor = (c) => c >= 80 ? T.green : c >= 60 ? T.amber : T.coral;
export const attemptColor = (n) => n === 1 ? T.green : n === 2 ? T.amber : T.coral;
export const attemptLabel = (n) => n === 1 ? '1er' : n === 2 ? '2do' : '3er';

export const ScoreCircle = ({ score }) => {
    const c = scoreColor(score);
    return (
        <div data-testid="score-circle" style={{ width: 36, height: 36, borderRadius: '50%', background: c + '18', border: `2px solid ${c}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: c }}>{score}</span>
        </div>
    );
};

export const ConfidenceBar = ({ confidence }) => {
    const pct = Math.round((confidence || 0) * 100);
    const c = confColor(pct);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, fontFamily: "'DM Mono',monospace", fontWeight: 600, color: c, minWidth: 32 }}>{pct}%</span>
            <div style={{ width: 50, height: 6, borderRadius: 3, background: T.surface2 }}>
                <div style={{ height: '100%', borderRadius: 3, width: `${pct}%`, background: c, transition: 'width 0.3s' }} />
            </div>
        </div>
    );
};

export const IntentBadge = ({ n }) => {
    const c = attemptColor(n);
    return (
        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: c + '18', color: c }}>{attemptLabel(n)}</span>
    );
};

export const ReviewStatus = ({ status }) => {
    if (status === 'approved') return <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.green }}><CheckCircle2 size={14} /> Aprobada</span>;
    if (status === 'rejected') return <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.coral }}><XCircle size={14} /> Rechazada</span>;
    return <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.textTer }}><div style={{ width: 12, height: 12, borderRadius: '50%', border: `2px solid ${T.borderStrong}` }} /> Pendiente</span>;
};

export const ErrorChip = ({ errKey, severity, label }) => {
    const isCrit = severity === 'critical';
    const bg = isCrit ? T.coralLt : T.amberLt;
    const border = isCrit ? T.coral + '40' : T.amber + '40';
    const color = isCrit ? T.coral : T.amber;
    return (
        <span data-testid={`error-chip-${errKey}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500, background: bg, border: `1px solid ${border}`, color, whiteSpace: 'nowrap' }}>
            {isCrit ? <AlertTriangle size={10} /> : <Info size={10} />}
            {label}
        </span>
    );
};

export const OkChip = () => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500, background: T.greenLt, border: `1px solid ${T.green}30`, color: T.green }}>
        <Check size={10} /> Todas correctas
    </span>
);
