import React, { useState, useEffect, useCallback } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Loader2, ChevronLeft, ChevronRight, ExternalLink, Filter, RefreshCw } from 'lucide-react';

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
    const [lastFetch, setLastFetch] = useState(null);
    const [nowTick, setNowTick] = useState(Date.now());

    const fetchEvents = useCallback(async (page = 1, attempt = 1) => {
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
            setLastFetch(Date.now());
        } catch (err) {
            // Cold-start tolerance: retry once on transient 5xx/network without toasting.
            // Toast only after 2 failed attempts so the user doesn't see spurious errors
            // while the pod is warming up.
            const status = err?.response?.status;
            const transient = !status || status >= 500 || status === 0;
            if (transient && attempt < 2) {
                setTimeout(() => fetchEvents(page, attempt + 1), 1500);
                return;
            }
            console.error("Admin component error:", err);
            toast.error('Error al cargar eventos de tokens');
        } finally {
            setLoading(false);
        }
    }, [period, entregable, modelo, clientId, pagination.page_size]);

    useEffect(() => { fetchEvents(1); }, [fetchEvents]);

    // Auto-refresh every 30s to reflect new evaluations live
    useEffect(() => {
        const it = setInterval(() => fetchEvents(pagination.page), 30000);
        return () => clearInterval(it);
    }, [fetchEvents, pagination.page]);

    // Live clock for "actualizado hace Ns" tooltip (re-render every 1s)
    useEffect(() => {
        const it = setInterval(() => setNowTick(Date.now()), 1000);
        return () => clearInterval(it);
    }, []);

    const agoText = (() => {
        if (!lastFetch) return 'Nunca';
        const diffS = Math.max(0, Math.floor((nowTick - lastFetch) / 1000));
        if (diffS < 5) return 'hace un momento';
        if (diffS < 60) return `hace ${diffS}s`;
        const m = Math.floor(diffS / 60);
        const s = diffS % 60;
        return `hace ${m}m ${s}s`;
    })();
    const isFresh = lastFetch && (nowTick - lastFetch) < 35000; // within refresh window

    const ds = detailSummary || { by_entregable: {}, totals: {} };
    const byEnt = ds.by_entregable || {};

    // Derive the ACTUAL model currently in use per entregable from the event list.
    // Falls back to the hardcoded default if no events are visible yet.
    const modelByEntregable = events.reduce((acc, ev) => {
        if (ev.entregable && ev.modelo && !acc[ev.entregable]) {
            acc[ev.entregable] = ev.modelo;
        }
        return acc;
    }, {});

    const entCards = [
        { key: 'evaluacion', label: 'Evaluaciones IA', defaultModel: 'claude-haiku-4-5', color: T.blue, bgColor: T.blueLt },
        { key: 'reporte', label: 'Reportes con IA', defaultModel: 'claude-sonnet-4-5', color: T.teal, bgColor: T.tealLt },
        { key: 'lumi', label: 'Consultas Lumi', defaultModel: 'claude-sonnet-4-5', color: T.purple, bgColor: T.purpleLt },
    ].map(c => ({ ...c, model: modelByEntregable[c.key] || c.defaultModel }));

    // Generate dynamic month labels
    const now = new Date();
    const currentMonthLabel = now.toLocaleString('es-MX', { month: 'long', year: 'numeric' });
    const prevDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const prevMonthLabel = prevDate.toLocaleString('es-MX', { month: 'long', year: 'numeric' });
    const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

    return (
        <div data-testid="token-usage-tab">
            {/* Filters */}
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
                <select value={period} onChange={e => setPeriod(e.target.value)} style={{ padding: '6px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, background: T.surface, color: T.textPri }}>
                    <option value="current_month">{capitalize(currentMonthLabel)}</option>
                    <option value="prev_month">{capitalize(prevMonthLabel)}</option>
                </select>
                <select value={entregable} onChange={e => setEntregable(e.target.value)} style={{ padding: '6px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, background: T.surface }}>
                    <option value="">Todos los entregables</option>
                    <option value="evaluacion">Evaluaciones IA</option>
                    <option value="reporte">Reportes con IA</option>
                    <option value="lumi">Consultas Lumi</option>
                </select>
                <select value={modelo} onChange={e => setModelo(e.target.value)} style={{ padding: '6px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, background: T.surface }} data-testid="filter-modelo">
                    <option value="">Todos los modelos</option>
                    <option value="claude-haiku-4-5">claude-haiku-4-5</option>
                    <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
                    <option value="claude-opus-4-5">claude-opus-4-5</option>
                    <option value="gpt-4o">gpt-4o</option>
                </select>
                <span style={{ fontSize: 11, color: T.textTer, padding: '4px 8px', borderRadius: T.radiusSm, background: T.surface2 }}>
                    TC: <strong>$19.00 MXN/USD</strong>
                </span>
                <button
                    onClick={() => fetchEvents(pagination.page)}
                    disabled={loading}
                    data-testid="refresh-token-usage-btn"
                    title="Actualizar datos (auto cada 30s)"
                    style={{
                        marginLeft: 'auto', padding: '6px 10px', borderRadius: T.radiusSm,
                        border: `1px solid ${T.border}`, background: T.surface, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: T.textSec,
                    }}
                >
                    {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                    Actualizar
                </button>
            </div>

            {/* Shadow cost alert (consumo invisible cuando LLM falla pero ya facturó) */}
            {(ds.shadow?.total_count > 0) && (
                <div
                    data-testid="shadow-cost-banner"
                    style={{
                        padding: '10px 14px', marginBottom: 16,
                        background: T.amberLt, border: `1px solid #F59E0B`,
                        borderRadius: T.radius, display: 'flex',
                        alignItems: 'center', gap: 10,
                    }}
                >
                    <span style={{ fontSize: 18 }}>⚠</span>
                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: '#92400E' }}>
                            Consumo en sombra detectado: ${ds.shadow.total_cost_usd?.toFixed(4)} USD ({ds.totals?.shadow_cost_pct ?? 0}% del total) — {ds.shadow.total_count} eventos
                        </div>
                        <div style={{ fontSize: 11, color: '#78350F', marginTop: 2 }}>
                            Anthropic facturó input tokens (incluyendo imágenes) cuando la respuesta del modelo no se recibió completa (timeout, rate-limit, error de red). Estos cargos ahora quedan auditados con flag <code style={{ background: 'rgba(0,0,0,0.06)', padding: '0 4px', borderRadius: 3 }}>is_shadow_cost</code>.
                            {ds.shadow.by_kind && Object.keys(ds.shadow.by_kind).length > 0 && (
                                <span> Tipos: {Object.entries(ds.shadow.by_kind).map(([k, v]) => `${k}=${v.count}`).join(', ')}.</span>
                            )}
                        </div>
                    </div>
                </div>
            )}

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
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: T.textPri }}>Detalle por evento</span>
                        <LiveIndicator isFresh={isFresh} agoText={agoText} data-testid="tokens-live-indicator" />
                    </div>
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
                                {['Fecha', 'Entregable', 'Modelo', 'Referencia', 'Input', 'Output', 'Prompt', 'Total', 'USD', 'MXN', 'Tipo', 'Cliente'].map(h => (
                                    <th key={h} style={{ padding: '8px 10px', textAlign: h === 'Referencia' ? 'left' : 'center', fontSize: 10, fontWeight: 600, color: T.textTer, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr><td colSpan={12} style={{ padding: 40, textAlign: 'center' }}><Loader2 size={20} className="animate-spin" style={{ margin: '0 auto' }} /></td></tr>
                            ) : events.length === 0 ? (
                                <tr><td colSpan={12} style={{ padding: 40, textAlign: 'center', color: T.textTer }}>No hay eventos registrados para este período</td></tr>
                            ) : events.map(ev => {
                                const color = ENTREGABLE_COLORS[ev.entregable] || T.textSec;
                                const isShadow = !!ev.is_shadow_cost;
                                const rowBg = isShadow ? T.amberLt : 'transparent';
                                return (
                                    <tr key={ev.id} style={{ borderBottom: `1px solid ${T.border}`, background: rowBg }}>
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
                                            {ev.image_count > 0 && (
                                                <span style={{ marginLeft: 6, fontSize: 9, color: T.textTer }}>📷×{ev.image_count}</span>
                                            )}
                                        </td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_input)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_output)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_prompt)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontWeight: 600, fontFamily: "'DM Mono',monospace" }}>{fmtNum(ev.tokens_total)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace", color: T.green }}>${ev.cost_usd?.toFixed(4)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center', fontFamily: "'DM Mono',monospace" }}>${ev.cost_mxn?.toFixed(3)}</td>
                                        <td style={{ padding: '8px 10px', textAlign: 'center' }}>
                                            {isShadow ? (
                                                <span
                                                    title={`Shadow cost (${ev.shadow_kind || 'desconocido'}): Anthropic facturó pero la respuesta no llegó.`}
                                                    style={{ padding: '2px 7px', borderRadius: 8, fontSize: 9.5, fontWeight: 700, background: '#FEF3C7', color: '#92400E', textTransform: 'uppercase' }}
                                                >Shadow</span>
                                            ) : (
                                                <span style={{ padding: '2px 7px', borderRadius: 8, fontSize: 9.5, fontWeight: 600, background: T.greenLt, color: T.green }}>OK</span>
                                            )}
                                        </td>
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

// ═══════════════════ LIVE INDICATOR ═══════════════════
function LiveIndicator({ isFresh, agoText }) {
    const color = isFresh ? '#16A34A' : '#9C9A92';
    const bg = isFresh ? '#F0FDF4' : '#F0EFEC';
    return (
        <div
            data-testid="tokens-live-indicator"
            title={`Actualización automática cada 30s · Última actualización ${agoText}`}
            style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '2px 8px', borderRadius: 999,
                background: bg, fontSize: 10.5, fontWeight: 600,
                color: color, userSelect: 'none', cursor: 'default',
            }}
        >
            <span
                style={{
                    width: 7, height: 7, borderRadius: '50%',
                    background: color,
                    animation: isFresh ? 'tu-live-pulse 1.8s ease-in-out infinite' : 'none',
                    boxShadow: isFresh ? `0 0 0 2px ${bg}` : 'none',
                }}
            />
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{isFresh ? 'LIVE' : 'Sin actualizar'}</span>
            <span style={{ color: '#9C9A92', fontWeight: 500, marginLeft: 2 }}>·</span>
            <span style={{ color: '#6B6960', fontWeight: 500 }}>{agoText}</span>
            <style>{`
                @keyframes tu-live-pulse {
                    0%, 100% { transform: scale(1); opacity: 1; }
                    50% { transform: scale(1.4); opacity: 0.55; }
                }
            `}</style>
        </div>
    );
}

