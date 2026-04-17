export const T = {
    bg: '#f8f7f4', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: 'rgba(0,0,0,0.08)', borderSolid: '#E2E0DB',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    teal: '#1D9E75', tealLt: '#E8F8F1',
    green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#EF9F27', amberLt: '#FFFBEB',
    coral: '#E24B4A', coralLt: '#FEF2F2',
    blue: '#2563EB', blueLt: '#EFF6FF',
    purple: '#3C3489', purpleLt: '#EEEDFE',
    radius: 10, radiusSm: 6,
};

export const PERIODS = [
    { label: 'Hoy', value: 'today' },
    { label: '7 dias', value: '7d' },
    { label: '15 dias', value: '15d' },
    { label: 'Mes actual', value: 'current_month' },
    { label: 'Mes anterior', value: 'prev_month' },
    { label: 'Semana anterior', value: 'prev_week' },
    { label: 'Personalizado', value: 'custom' },
];

export const getDateRange = (preset) => {
    const now = new Date();
    const fmt = (d) => d.toISOString().split('T')[0];
    switch (preset) {
        case 'today': return { from: fmt(now), to: fmt(now) };
        case '7d': { const f = new Date(now); f.setDate(f.getDate() - 6); return { from: fmt(f), to: fmt(now) }; }
        case '15d': { const f = new Date(now); f.setDate(f.getDate() - 14); return { from: fmt(f), to: fmt(now) }; }
        case 'current_month': return { from: fmt(new Date(now.getFullYear(), now.getMonth(), 1)), to: fmt(now) };
        case 'prev_month': { const f = new Date(now.getFullYear(), now.getMonth() - 1, 1); return { from: fmt(f), to: fmt(new Date(now.getFullYear(), now.getMonth(), 0)) }; }
        case 'prev_week': { const s = new Date(now); s.setDate(s.getDate() - s.getDay() - 7); const e = new Date(s); e.setDate(e.getDate() + 6); return { from: fmt(s), to: fmt(e) }; }
        default: return { from: fmt(now), to: fmt(now) };
    }
};

export const getPrevDateRange = (preset) => {
    const now = new Date();
    const fmt = (d) => d.toISOString().split('T')[0];
    switch (preset) {
        case 'today': { const y = new Date(now); y.setDate(y.getDate() - 1); return { from: fmt(y), to: fmt(y) }; }
        case '7d': { const e = new Date(now); e.setDate(e.getDate() - 7); const s = new Date(e); s.setDate(s.getDate() - 6); return { from: fmt(s), to: fmt(e) }; }
        case '15d': { const e = new Date(now); e.setDate(e.getDate() - 15); const s = new Date(e); s.setDate(s.getDate() - 14); return { from: fmt(s), to: fmt(e) }; }
        case 'current_month': { const f = new Date(now.getFullYear(), now.getMonth() - 1, 1); return { from: fmt(f), to: fmt(new Date(now.getFullYear(), now.getMonth(), 0)) }; }
        case 'prev_month': { const f = new Date(now.getFullYear(), now.getMonth() - 2, 1); return { from: fmt(f), to: fmt(new Date(now.getFullYear(), now.getMonth() - 1, 0)) }; }
        default: return null;
    }
};

export const formatDateLabel = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
};
