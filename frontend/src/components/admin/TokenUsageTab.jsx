import React, { useState, useEffect, useCallback } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Loader2, ChevronLeft, ChevronRight, ExternalLink, Filter } from 'lucide-react';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF', green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB', coral: '#DC2626', coralLt: '#FEF2F2',
    teal: '#0D9488', tealLt: '#F0FDFA', purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

const fmtNum = (n) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n?.toLocaleString('es-MX') || '0';
};

const ENTREGABLE_LABELS = { evaluacion: 'Evaluación IA', reporte: 'Reporte IA', lumi: 'Consulta Lumi' };
const ENTREGABLE_COLORS = { evaluacion: T.blue, reporte: T.teal, lumi: T.purple };

export default function TokenUsageTab({ summary, period, setPeriod, clientId, setClientId }) {
    const [events, setEvents] = useState([]);
    const [pagination, setPagination] = useState({ total: 0, page: 1, page_size: 25, total_pages: 1 });
    const [detailSummary, setDetailSummary] = useState(null);
    const [loading, setLoading] = useState(false);
    const [entregable, setEntregable] = useState('');
    const [modelo, setModelo] = useState('');

    const fetchEvents = useCallback(async (page = 1) => {
        setLoading(true);
        try {
            const params = { period, page, page_size: pagination.page_size };
            if (entregable) params.entregable = entregable;
            if (modelo) params.modelo = modelo;
            if (clientId) params.client_id = clientId;
            const res = await api.get('/admin/token-usage', { params });
            setEvents(res.data.events);
            setPagination(res.data.pagination);
            setDetailSummary(res.data.summary);
        } catch (err) { console.error("Admin component error:", err);
            toast.error('Error al cargar eventos de tokens');
        } finally {
            setLoading(false);
        }
    }, [period, entregable, modelo, clientId, pagination.page_size]);

    useEffect(() => { fetchEvents(1); }, [fetchEvents]);

    const ds = detailSummary || { by_entregable: {}, totals: {} };
    const byEnt = ds.by_entregable || {};

    const entCards = [
        { key: 'evaluacion', label: 'Evaluaciones IA', model: 'claude-opus-4-5', color: T.blue, bgColor: T.blueLt },
        { key: 'reporte', label: 'Reportes con IA', model: 'claude-sonnet-4-5', color: T.teal, bgColor: T.tealLt },
        { key: 'lumi', label: 'Consultas Lumi', model: 'claude-sonnet-4-5', color: T.purple, bgColor: T.purpleLt },
    ];

    return (
        <div data-testid="token-usage-tab">
            {/* Filters */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
                <select value={period} onChange={e => setPeriod(e.target.value)} style={{ padding: '6px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, background: T.surface, color: T.textPri }}>
                    <option value="current_month">Marzo 2026</option>
                    <option value="prev_month">Febrero 2026</option>
                </select>
                <select value={entregable} onChange={e => setEntregable(e.target.value)} style={{ padding: '6px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, background: T.surface }}>
                    <option value="">Todos los entregables</option>
                    <option value="evaluacion">Evaluaciones IA</option>
                    <option value="reporte">Reportes con IA</option>
                    <option value="lumi">Consultas Lumi</option>
                </select>
                <select value={modelo} onChange={e => setModelo(e.target.value)} style={{ padding: '6px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, background: T.surface }}>
                    <option value="">Todos los modelos</option>
                    <option value="claude-opus-4-5">claude-opus-4-5</option>
                    <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
                    <option value="gpt-4o">gpt-4o</option>
                </select>
                <span style={{ fontSize: 11, color: T.textTer, padding: '4px 8px', borderRadius: T.radiusSm, background: T.surface2 }}>
                    TC: <strong>$19.00 MXN/USD</strong>
                </span>
            </div>

            {/* Summary Cards - 3 columns */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
                {entCards.map(card => {
                    const d = byEnt[card.key] || {};
                    const avg = d.avg_per_unit || {};
                    return (
                        <div key={card.key} style={{ padding: '16px 18px', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                                <div>
                                    <span style={{ fontSize: 13, fontWeight: 600, color: T.textPri }}>{card.label}</span>
                                    <span style={{ fontSize: 12, color: T.textTer, marginLeft: 6 }}>{fmtNum(d.count || 0)} {card.key === 'evaluacion' ? 'entregas' : card.key === 'reporte' ? 'generados' : 'mensajes'}</span>
                                </div>
                                <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, background: card.bgColor, color: card.color, fontWeight: 600 }}>{card.model}</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                <div>
                                    <p style={{ fontSize: 10, color: T.textTer, textTransform: 'uppercase', fontWeight: 500, marginBottom: 4 }}>Input</p>
                                    <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.textPri }}>{fmtNum(d.tokens_input || 0)}</span>
                                    <p style={{ fontSize: 10, color: T.textTer }}>~{fmtNum(avg.input || 0)} / unidad</p>
                                </div>
                                <div>
                                    <p style={{ fontSize: 10, color: T.textTer, textTransform: 'uppercase', fontWeight: 500, marginBottom: 4 }}>Output</p>
                                    <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.textPri }}>{fmtNum(d.tokens_output || 0)}</span>
                                    <p style={{ fontSize: 10, color: T.textTer }}>~{fmtNum(avg.output || 0)} / unidad</p>
                                </div>
                                <div>
                                    <p style={{ fontSize: 10, color: T.textTer, textTransform: 'uppercase', fontWeight: 500, marginBottom: 4 }}>Prompt</p>
                                    <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.textPri }}>{fmtNum(d.tokens_prompt || 0)}</span>
                                    <p style={{ fontSize: 10, color: T.textTer }}>~{fmtNum(avg.prompt || 0)} / unidad</p>
                                </div>
                                <div>
                                    <p style={{ fontSize: 10, color: T.textTer, textTransform: 'uppercase', fontWeight: 500, marginBottom: 4 }}>Costo estimado</p>
                                    <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: card.color }}>${d.cost_usd || '0.00'} USD</span>
                                    <p style={{ fontSize: 10, color: T.textTer }}>≈ ${d.cost_mxn || '0.00'} MXN</p>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Events Table */}
            <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, overflow: 'hidden' }}>
                <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: T.textPri }}>Detalle por evento</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 11, color: T.textTer }}>Mostrando {events.length} de {pagination.total} eventos</span>
                        <select value={pagination.page_size} onChange={e => setPagination(prev => ({ ...prev, page_size: Number(e.target.value) }))} style={{ padding: '4px 8px', borderRadius: 4, border: `1px solid ${T.border}`, fontSize: 11 }}>
                            <option value={25}>25 por página</option>
                            <option value={50}>50 por página</option>
                            <option value={100}>100 por página</option>
                        </select>
                    </div>
                </div>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                            <tr style={{ background: T.surface2, borderBottom: `1px solid ${T.border}` }}>
                                {['Fecha', 'Entregable', 'Modelo', 'Referencia', 'Input', 'Output', 'Prompt', 'Total', 'USD', 'MXN', 'Cliente'].map(h => (
                                    <th key={h} style={{ padding: '8px 10px', textAlign: h === 'Referencia' ? 'left' : 'center', fontSize: 10, fontWeight: 600, color: T.textTer, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr><td colSpan={11} style={{ padding: 40, textAlign: 'center' }}><Loader2 size={20} className="animate-spin" style={{ margin: '0 auto' }} /></td></tr>
                            ) : events.length === 0 ? (
                                <tr><td colSpan={11} style={{ padding: 40, textAlign: 'center', color: T.textTer }}>No hay eventos registrados para este período</td></tr>
                            ) : events.map(ev => {
                                const color = ENTREGABLE_COLORS[ev.entregable] || T.textSec;
                                return (
                                    <tr key={ev.id} style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap', fontSize: 11, color: T.textSec }}>
                                            {new Date(ev.timestamp).toLocaleString('es-MX', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                        </td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                            <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 600, background: color + '15', color }}>{ENTREGABLE_LABELS[ev.entregable] || ev.entregable}</span>
                                        </td>
                                        <td style={{ padding: '8px 10px', fontSize: 11, textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{ev.modelo}</td>
                                        <td style={{ padding: '8px 10px', fontSize: 11, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {ev.journey_id && ev.entregable === 'evaluacion' ? (
                                                <a href={`/journeys/${ev.journey_id}`} style={{ color: T.blue, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}>
                                                    {ev.referencia} <ExternalLink size={10} />
                                                </a>
                                            ) : ev.referencia}
                                        </td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_input)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_output)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_prompt)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 600, fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_total)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace", color: T.green }}>${ev.cost_usd?.toFixed(4)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>${ev.cost_mxn?.toFixed(3)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontSize: 11 }}>{ev.client_id ? 'Cubbo' : '—'}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
                {/* Pagination */}
                {pagination.total_pages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '10px 16px', borderTop: `1px solid ${T.border}` }}>
                        <button onClick={() => fetchEvents(pagination.page - 1)} disabled={pagination.page <= 1} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 8px', cursor: pagination.page <= 1 ? 'default' : 'pointer', opacity: pagination.page <= 1 ? 0.4 : 1 }}><ChevronLeft size={14} /></button>
                        <span style={{ fontSize: 12, color: T.textSec }}>Página {pagination.page} de {pagination.total_pages}</span>
                        <button onClick={() => fetchEvents(pagination.page + 1)} disabled={pagination.page >= pagination.total_pages} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 8px', cursor: pagination.page >= pagination.total_pages ? 'default' : 'pointer', opacity: pagination.page >= pagination.total_pages ? 0.4 : 1 }}><ChevronRight size={14} /></button>
                    </div>
                )}
            </div>
        </div>
    );
}
