import React, { useState, useEffect, useCallback } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Download, Columns, Loader2, ChevronLeft, ChevronRight, ExternalLink, Filter, X, Check } from 'lucide-react';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF', green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB', coral: '#DC2626',
    teal: '#0D9488', tealLt: '#F0FDFA',
    radius: 10, radiusSm: 6,
};

const ALL_COLUMNS = [
    { key: 'order_id', label: 'ORDER ID', default: true },
    { key: 'fecha', label: 'Fecha', default: true },
    { key: 'driver', label: 'Driver', default: true },
    { key: 'team', label: 'Team', default: true },
    { key: 'tipo_unidad', label: 'Tipo unidad', default: true },
    { key: 'estado', label: 'Estado', default: true },
    { key: 'proveedor', label: 'Proveedor', default: true },
    { key: 'costo', label: 'Costo', default: true },
    { key: 'pv', label: 'PV', default: true },
    { key: 'asistencia_en_tiempo', label: 'Asistencia', default: true },
    { key: 'hora_entrada', label: 'H. Entrada', default: true },
    { key: 'hora_salida', label: 'H. Salida', default: true },
    { key: 'horas_laboradas', label: 'Hrs lab.', default: true },
    { key: 'distancia_km', label: 'KM', default: true },
    { key: 'km_excedente', label: 'KM excedente', default: false },
    { key: 'tipo_tarifa', label: 'Tipo tarifa', default: false },
    { key: 'costo_km_adicional', label: 'Costo km+', default: false },
    { key: 'backup_activado', label: 'Backup?', default: false },
    { key: 'total_paquetes', label: 'Total pkgs', default: true },
    { key: 'completados', label: 'Completados', default: true },
    { key: 'cancelados', label: 'Cancelados', default: true },
    { key: 'pendientes', label: 'Pendientes', default: true },
    { key: 'con_evidencia', label: 'Con evidencia', default: true },
    { key: 'sin_evidencia', label: 'Sin evidencia', default: true },
    { key: 'score_ia', label: 'Score IA', default: true },
    { key: 'comentarios', label: 'Comentarios', default: true },
];

const INITIAL_COLS = (() => {
    try { const s = localStorage.getItem('admin_routes_columns'); return s ? JSON.parse(s) : null; } catch { return null; }
})() || ALL_COLUMNS.filter(c => c.default).map(c => c.key);

const fmtMoney = (n) => n ? `$${Number(n).toLocaleString('es-MX')}` : '—';
const fmtKm = (n) => n ? `${Number(n).toFixed(2)}` : '—';
const fmtHrs = (n) => n ? `${Number(n).toFixed(2)}h` : '—';
const fmtScore = (n) => n != null ? `${n}%` : '—';

export default function RoutesReportTab({ canEdit }) {
    const today = new Date();
    const firstDay = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
    const todayStr = today.toISOString().split('T')[0];

    const [dateFrom, setDateFrom] = useState(firstDay);
    const [dateTo, setDateTo] = useState(todayStr);
    const [driver, setDriver] = useState('');
    const [team, setTeam] = useState('');
    const [providerId, setProviderId] = useState('');
    const [status, setStatus] = useState('');
    const [visibleCols, setVisibleCols] = useState(INITIAL_COLS);
    const [showColSelector, setShowColSelector] = useState(false);
    const [rows, setRows] = useState([]);
    const [totals, setTotals] = useState({});
    const [pagination, setPagination] = useState({ total: 0, page: 1, page_size: 25, total_pages: 1 });
    const [loading, setLoading] = useState(false);
    const [exporting, setExporting] = useState(false);

    const fetchData = useCallback(async (page = 1) => {
        setLoading(true);
        try {
            const params = { date_from: dateFrom, date_to: dateTo, page, page_size: pagination.page_size };
            if (driver) params.driver = driver;
            if (team) params.team = team;
            if (providerId) params.provider_id = providerId;
            if (status) params.status = status;
            const res = await api.get('/admin/routes-report', { params });
            setRows(res.data.rows);
            setTotals(res.data.totals);
            setPagination(res.data.pagination);
        } catch {
            toast.error('Error al cargar reporte de rutas');
        } finally {
            setLoading(false);
        }
    }, [dateFrom, dateTo, driver, team, providerId, status, pagination.page_size]);

    useEffect(() => { fetchData(1); }, [fetchData]);

    const handleExport = async () => {
        setExporting(true);
        try {
            const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo, columns: visibleCols.join(',') });
            if (driver) params.set('driver', driver);
            if (team) params.set('team', team);
            if (providerId) params.set('provider_id', providerId);
            if (status) params.set('status', status);
            const res = await api.get(`/admin/routes-report/export?${params}`, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const a = document.createElement('a');
            a.href = url;
            a.download = `LAYOUT_ADM_Cubbo_${dateFrom}_${dateTo}.xlsx`;
            a.click();
            window.URL.revokeObjectURL(url);
            toast.success('Excel exportado');
        } catch {
            toast.error('Error al exportar');
        } finally {
            setExporting(false);
        }
    };

    const toggleCol = (key) => {
        setVisibleCols(prev => {
            const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key];
            localStorage.setItem('admin_routes_columns', JSON.stringify(next));
            return next;
        });
    };

    const getCellValue = (row, key) => {
        const v = row[key];
        if (key === 'costo' || key === 'pv' || key === 'costo_km_adicional') return fmtMoney(v);
        if (key === 'distancia_km' || key === 'km_excedente') return fmtKm(v);
        if (key === 'horas_laboradas') return fmtHrs(v);
        if (key === 'score_ia') return fmtScore(v);
        if (key === 'backup_activado') return v ? 'Si' : 'No';
        if (v === null || v === undefined || v === '') return '—';
        return v;
    };

    const scoreColor = (s) => s >= 90 ? T.green : s >= 70 ? T.amber : T.coral;
    const activeCols = ALL_COLUMNS.filter(c => visibleCols.includes(c.key));

    return (
        <div data-testid="routes-report-tab">
            {/* Filters */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <label style={{ fontSize: 11, color: T.textTer }}>Período</label>
                    <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ padding: '5px 8px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 11 }} />
                    <span style={{ color: T.textTer }}>—</span>
                    <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ padding: '5px 8px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 11 }} />
                </div>
                <input value={driver} onChange={e => setDriver(e.target.value)} placeholder="Driver" style={{ padding: '5px 10px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 11, width: 140 }} />
                <select value={team} onChange={e => setTeam(e.target.value)} style={{ padding: '5px 8px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 11 }}>
                    <option value="">Todos los teams</option>
                    <option value="CDMX - MYE">CDMX - MYE</option>
                    <option value="PACHUCA - MYE">PACHUCA - MYE</option>
                </select>
                <select value={status} onChange={e => setStatus(e.target.value)} style={{ padding: '5px 8px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 11 }}>
                    <option value="">Todos los status</option>
                    <option value="closed">Cerradas</option>
                    <option value="in_progress">En progreso</option>
                </select>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                    <div style={{ position: 'relative' }}>
                        <button onClick={() => setShowColSelector(!showColSelector)} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, background: T.surface, fontSize: 11, cursor: 'pointer' }} data-testid="columns-selector-btn">
                            <Columns size={12} /> Columnas
                        </button>
                        {showColSelector && (
                            <div style={{ position: 'absolute', right: 0, top: 30, width: 260, background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius, boxShadow: '0 4px 16px rgba(0,0,0,0.1)', zIndex: 50, padding: 12, maxHeight: 360, overflowY: 'auto' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                    <span style={{ fontSize: 12, fontWeight: 600 }}>Columnas visibles</span>
                                    <button onClick={() => setShowColSelector(false)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}><X size={14} /></button>
                                </div>
                                {ALL_COLUMNS.map(c => (
                                    <label key={c.key} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 0', cursor: 'pointer', fontSize: 11 }}>
                                        <input type="checkbox" checked={visibleCols.includes(c.key)} onChange={() => toggleCol(c.key)} style={{ width: 13, height: 13 }} />
                                        {c.label}
                                    </label>
                                ))}
                            </div>
                        )}
                    </div>
                    <button onClick={handleExport} disabled={exporting} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 12px', borderRadius: T.radiusSm, border: 'none', background: T.textPri, color: '#fff', fontSize: 11, cursor: 'pointer', fontWeight: 600 }} data-testid="export-excel-btn">
                        {exporting ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />} Exportar Excel
                    </button>
                </div>
            </div>

            {/* Totals Strip */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                {[
                    { label: 'Rutas', val: totals.total_rutas || 0, color: T.textPri },
                    { label: 'Días op.', val: totals.total_dias || 0, color: T.textPri },
                    { label: 'Total pkgs', val: totals.total_paquetes || 0, color: T.blue },
                    { label: 'Completados', val: totals.completados || 0, color: T.green },
                    { label: 'Con evidencia', val: totals.con_evidencia || 0, color: T.teal },
                    { label: 'Costo total', val: fmtMoney(totals.costo_total || 0), color: T.textPri },
                    { label: 'KM extra', val: fmtMoney(totals.km_excedente_cost || 0), color: T.amber },
                ].map((t, i) => (
                    <div key={i} style={{ padding: '10px 14px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, background: T.surface, flex: 1, textAlign: 'center' }}>
                        <p style={{ fontSize: 10, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', marginBottom: 4 }}>{t.label}</p>
                        <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: t.color }}>{t.val}</span>
                    </div>
                ))}
            </div>

            {/* Table */}
            <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                        <thead>
                            <tr style={{ background: T.surface2, borderBottom: `1px solid ${T.border}` }}>
                                {activeCols.map(c => (
                                    <th key={c.key} style={{ padding: '8px 8px', textAlign: 'center', fontSize: 10, fontWeight: 600, color: T.textTer, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{c.label}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr><td colSpan={activeCols.length} style={{ padding: 40, textAlign: 'center' }}><Loader2 size={20} className="animate-spin" style={{ margin: '0 auto' }} /></td></tr>
                            ) : rows.length === 0 ? (
                                <tr><td colSpan={activeCols.length} style={{ padding: 40, textAlign: 'center', color: T.textTer }}>No hay rutas para este período</td></tr>
                            ) : rows.map((row, idx) => (
                                <tr key={idx} style={{ borderBottom: `1px solid ${T.border}` }}>
                                    {activeCols.map(c => {
                                        const val = getCellValue(row, c.key);
                                        let style = { padding: '7px 8px', textAlign: 'center', whiteSpace: 'nowrap' };
                                        if (c.key === 'order_id') style = { ...style, fontFamily: "'DM Mono',monospace", fontSize: 10, textAlign: 'left' };
                                        if (c.key === 'driver') style = { ...style, textAlign: 'left', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis' };
                                        if (c.key === 'comentarios') style = { ...style, textAlign: 'left', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' };
                                        if (c.key === 'score_ia' && row.score_ia != null) style = { ...style, fontWeight: 700, color: scoreColor(row.score_ia), fontFamily: "'DM Mono',monospace" };
                                        if (c.key === 'asistencia_en_tiempo') style = { ...style, color: val === 'Si' ? T.green : val === 'No' ? T.coral : T.textTer };
                                        return <td key={c.key} style={style}>{val}</td>;
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
                {/* Pagination */}
                {pagination.total_pages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', borderTop: `1px solid ${T.border}` }}>
                        <span style={{ fontSize: 11, color: T.textTer }}>Mostrando {rows.length} de {pagination.total} rutas</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <button onClick={() => fetchData(pagination.page - 1)} disabled={pagination.page <= 1} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 8px', cursor: pagination.page <= 1 ? 'default' : 'pointer', opacity: pagination.page <= 1 ? 0.4 : 1 }}><ChevronLeft size={14} /></button>
                            <span style={{ fontSize: 12, color: T.textSec }}>Página {pagination.page} de {pagination.total_pages}</span>
                            <button onClick={() => fetchData(pagination.page + 1)} disabled={pagination.page >= pagination.total_pages} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 8px', cursor: pagination.page >= pagination.total_pages ? 'default' : 'pointer', opacity: pagination.page >= pagination.total_pages ? 0.4 : 1 }}><ChevronRight size={14} /></button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
