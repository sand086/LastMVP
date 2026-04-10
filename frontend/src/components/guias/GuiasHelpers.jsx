import React from 'react';
import { AlertTriangle, Circle, CheckCircle2, XCircle } from 'lucide-react';
import { Card, CardContent } from '../ui/card';

/* ─── Score circle ─── */
export const ScoreCircle = ({ score }) => {
    if (score == null) return <span className="text-xs text-slate-400">—</span>;
    const color = score >= 90 ? 'text-emerald-600 border-emerald-400' :
                  score >= 60 ? 'text-amber-600 border-amber-400' :
                  'text-red-600 border-red-400';
    return (
        <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full border-2 text-xs font-bold font-mono ${color}`}
              data-testid="score-circle">
            {score}
        </span>
    );
};

/* ─── Confidence bar ─── */
export const ConfidenceBar = ({ score }) => {
    if (score == null) return <span className="text-xs text-slate-400">—</span>;
    const color = score >= 70 ? '#10B981' : score >= 30 ? '#D97706' : '#EF4444';
    const textCls = score >= 70 ? 'text-emerald-600' : score >= 30 ? 'text-amber-600' : 'text-red-600';
    return (
        <div className="flex items-center gap-2 min-w-[80px]" data-testid="confidence-bar">
            <div className="flex-1 h-1 bg-slate-200 rounded-full overflow-hidden">
                <div style={{ width: `${score}%`, background: color }} className="h-full rounded-full transition-all" />
            </div>
            <span className={`text-xs font-mono font-bold ${textCls}`}>{score}%</span>
        </div>
    );
};

/* ─── Status pill (with discrepancy support) ─── */
export const StatusPill = ({ status, discrepancy }) => {
    if (discrepancy?.detected) {
        return (
            <span className="text-xs font-medium px-2.5 py-0.5 rounded-full border border-amber-400 bg-amber-50 text-amber-700 inline-flex items-center gap-1"
                  data-testid="status-discrepancy">
                <AlertTriangle className="w-3 h-3" /> Discrepancia
            </span>
        );
    }
    const map = {
        delivered: { label: 'Exitosa', cls: 'bg-emerald-100 text-emerald-700' },
        failed: { label: 'Fallida', cls: 'bg-red-100 text-red-700' },
        returned: { label: 'Devuelta', cls: 'bg-slate-200 text-slate-700' },
        pending: { label: 'Pendiente', cls: 'bg-slate-100 text-slate-500' },
    };
    const { label, cls } = map[status] || map.pending;
    return <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${cls}`}>{label}</span>;
};

/* ─── Review indicator ─── */
export const ReviewIndicator = ({ pkg }) => {
    if (pkg.manually_reviewed) {
        return <CheckCircle2 className="w-4 h-4 text-emerald-500 mx-auto" data-testid={`review-approved-${pkg.id}`} />;
    }
    if (pkg.rejection_reason) {
        return <XCircle className="w-4 h-4 text-red-500 mx-auto" data-testid={`review-rejected-${pkg.id}`} />;
    }
    if (pkg.manual_review?.decision === 'confirm_return') {
        return <XCircle className="w-4 h-4 text-red-500 mx-auto" data-testid={`review-return-${pkg.id}`} />;
    }
    if (pkg.manual_review?.decision === 'mark_valid') {
        return <CheckCircle2 className="w-4 h-4 text-emerald-500 mx-auto" data-testid={`review-valid-${pkg.id}`} />;
    }
    return <Circle className="w-4 h-4 text-slate-300 mx-auto" data-testid={`review-pending-${pkg.id}`} />;
};

/* ─── Severity badge ─── */
export const SeverityBadge = ({ level }) => {
    if (level === 'critical') {
        return (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded bg-red-600 text-white uppercase tracking-wide"
                  data-testid="severity-critical">
                Crítico
            </span>
        );
    }
    if (level === 'warning') {
        return (
            <span className="inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500 text-white uppercase tracking-wide"
                  data-testid="severity-warning">
                Alerta
            </span>
        );
    }
    return null;
};

/* ─── Severity utility functions ─── */
export const getMaxSeverity = (iaSeverity) => {
    if (!iaSeverity || typeof iaSeverity !== 'object') return null;
    const vals = Object.values(iaSeverity);
    if (vals.includes('critical')) return 'critical';
    if (vals.includes('warning')) return 'warning';
    return null;
};

export const getErrorSeverity = (displayError, iaErrorsRaw, iaSeverity) => {
    if (!iaSeverity || !iaErrorsRaw) return null;
    for (const rawKey of iaErrorsRaw) {
        if (iaSeverity[rawKey]) {
            const rawWords = rawKey.replace(/_/g, ' ').toLowerCase();
            const displayWords = displayError.toLowerCase();
            if (displayWords.includes(rawWords) || rawWords.includes(displayWords.slice(0, 10))) {
                return iaSeverity[rawKey];
            }
        }
    }
    if (iaErrorsRaw.length > 0 && Object.keys(iaSeverity).length > 0) {
        return getMaxSeverity(iaSeverity);
    }
    return null;
};

/* ─── KPI Card ─── */
export function KpiCard({ label, value, color, accent, testId }) {
    const colorMap = { emerald: 'text-emerald-600', amber: 'text-amber-600', red: 'text-red-600', blue: 'text-blue-600', violet: 'text-violet-600' };
    const accentMap = { red: 'border-t-[3px] border-red-500' };
    return (
        <Card className={accent ? accentMap[accent] : ''}>
            <CardContent className="p-4 text-center">
                <p className="text-xs text-slate-500 uppercase tracking-wider">{label}</p>
                <p className={`text-2xl font-mono font-bold ${colorMap[color] || 'text-slate-800'}`} data-testid={testId}>{value}</p>
            </CardContent>
        </Card>
    );
}

/* ─── Discrepancy row ─── */
export function DiscRow({ label, value, danger }) {
    return (
        <div className="flex items-center justify-between text-xs py-1 border-b border-amber-200 last:border-0">
            <span className="text-amber-700/70">{label}</span>
            <span className={`font-medium ${danger ? 'text-red-700' : 'text-amber-900'}`}>{value}</span>
        </div>
    );
}

/* ─── Segment filters ─── */
export const SEGMENT_FILTERS = [
    { key: 'all', label: 'Todas' },
    { key: 'alert', label: 'Con alerta' },
    { key: 'discrepancy', label: 'Discrepancia' },
    { key: 'no_evidence', label: 'Sin evidencia' },
    { key: 'pending_review', label: 'Pendiente revisión' },
];
