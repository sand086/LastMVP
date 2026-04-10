import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import DOMPurify from 'dompurify';
import { useAuth } from '../contexts/AuthContext';
import { useSortableTable } from '../lib/useSortableTable';
import {
    generateReport, generateReportExcel,
    getQualityReport, getClients, getProviders,
    getReportAttempts, getReportSla, updateSlaTargets, generateAiReport,
} from '../lib/api';
import { downloadFile } from '../lib/utils';
import {
    FileText, Download, Loader2, Truck, Users, AlertTriangle,
    Sparkles, ShieldCheck, Target, BarChart3, ChevronDown, ChevronUp,
    TrendingUp, TrendingDown, RefreshCw, CheckCircle2, Clock,
    Calendar, X, FileDown, Filter,
} from 'lucide-react';
import { toast } from 'sonner';
import {
    ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis,
    CartesianGrid, Tooltip as RechartsTooltip, Legend,
    PieChart, Pie, Cell,
} from 'recharts';

/* ─── Design tokens (from prompt spec) ─── */
const T = {
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

const PERIODS = [
    { label: 'Hoy', value: 'today' },
    { label: '7 días', value: '7d' },
    { label: '15 días', value: '15d' },
    { label: 'Mes actual', value: 'current_month' },
    { label: 'Mes anterior', value: 'prev_month' },
    { label: 'Semana anterior', value: 'prev_week' },
    { label: 'Personalizado', value: 'custom' },
];

const getDateRange = (preset) => {
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

const getPrevDateRange = (preset) => {
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

const formatDateLabel = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
};

/* ─── Health bar color ─── */
const healthColor = (val) => val >= 90 ? T.green : val >= 75 ? T.amber : T.coral;
const healthBg = (val) => val >= 90 ? T.greenLt : val >= 75 ? T.amberLt : T.coralLt;

/* ─── Rate pill with bar ─── */
const RateCell = ({ value }) => {
    const n = parseFloat(value) || 0;
    const color = healthColor(n);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 110 }}>
            <div style={{ flex: 1, height: 6, borderRadius: 3, background: T.surface2, overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(n, 100)}%`, background: color, transition: 'width 0.4s' }} />
            </div>
            <span style={{ fontSize: 12, fontWeight: 600, fontFamily: "'DM Mono', monospace", color, minWidth: 42, textAlign: 'right' }}>{n.toFixed(1)}%</span>
        </div>
    );
};

/* ─── SLA Badge ─── */
const SlaBadge = ({ actual, target }) => {
    const diff = (actual || 0) - (target || 75);
    if (diff >= 0) return <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10, background: T.greenLt, color: T.green }} data-testid="sla-on-target">On target</span>;
    if (diff >= -5) return <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10, background: T.amberLt, color: T.amber }} data-testid="sla-at-risk">At risk</span>;
    return <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 10, background: T.coralLt, color: T.coral }} data-testid="sla-breach">Breach</span>;
};

/* ─── Activity dot ─── */
const ActivityDot = ({ active }) => (
    <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: active ? T.green : T.textTer, marginRight: 8, flexShrink: 0 }} />
);

/* ─── Severity pill ─── */
const severityPill = (sev) => {
    const map = { alta: T.coral, media: T.amber, baja: T.green };
    return <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500, background: map[sev?.toLowerCase()] ? `${map[sev.toLowerCase()]}20` : T.surface2, color: map[sev?.toLowerCase()] || T.textSec }}>{sev || 'N/A'}</span>;
};

/* ─── KPI Card ─── */
const KpiCard = ({ label, value, delta, sub, healthVal, borderRight }) => {
    const hc = healthColor(parseFloat(value) || 0);
    return (
        <div style={{ padding: '18px 22px', borderRight: borderRight ? `1px solid ${T.borderSolid}` : 'none', position: 'relative' }}>
            <p style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', color: T.textTer, marginBottom: 6 }}>{label}</p>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'DM Sans', sans-serif", color: T.textPri }}>{value}</span>
                {delta !== null && delta !== undefined && (
                    <span style={{ fontSize: 12, fontWeight: 600, color: delta >= 0 ? T.green : T.coral, display: 'flex', alignItems: 'center', gap: 2 }}>
                        {delta >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                        {delta >= 0 ? '+' : ''}{delta.toFixed(1)}pp
                    </span>
                )}
            </div>
            {sub && <p style={{ fontSize: 11, color: T.textTer, marginTop: 3 }}>{sub}</p>}
            <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 3, background: healthVal != null ? hc : T.borderSolid }} />
        </div>
    );
};

/* ─── KPI Strip ─── */
const KPIStrip = ({ reportData, slaData, qualityData, prevData }) => {
    const delivery = reportData?.delivery_rate || 0;
    const totalPkg = reportData?.total_packages || 1;
    const totalDelivered = reportData?.total_delivered || 0;
    const totalFailed = reportData?.total_failed || 0;
    const visitRate = totalPkg > 0 ? Math.round((totalDelivered + totalFailed) / totalPkg * 100 * 10) / 10 : 0;
    const qualityAvg = qualityData?.summary?.avg_score || 0;
    const sla = slaData?.consolidated?.actual || delivery;
    const slaTarget = slaData?.consolidated?.target || 75;

    const prevDelivery = prevData?.delivery_rate || null;
    const prevPkg = prevData?.total_packages || 1;
    const prevDelivered = prevData?.total_delivered || 0;
    const prevFailed = prevData?.total_failed || 0;
    const prevVisit = prevPkg > 0 ? Math.round((prevDelivered + prevFailed) / prevPkg * 100 * 10) / 10 : null;

    const deliveryDelta = prevDelivery != null ? delivery - prevDelivery : null;
    const visitDelta = prevVisit != null ? visitRate - prevVisit : null;

    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', border: `1px solid ${T.borderSolid}`, borderRadius: T.radius, background: T.surface, overflow: 'hidden' }} data-testid="kpi-strip">
            <KpiCard label="Tasa de entrega" value={`${delivery}%`} delta={deliveryDelta} healthVal={delivery} borderRight />
            <KpiCard label="Tasa de visita" value={`${visitRate}%`} delta={visitDelta} healthVal={visitRate} borderRight />
            <KpiCard label="Calidad evidencias" value={`${qualityAvg}%`} delta={null} healthVal={qualityAvg} sub={qualityAvg === 0 ? 'Sin evaluaciones' : undefined} borderRight />
            <KpiCard label="SLA vs Target" value={`${sla}%`} delta={sla - slaTarget} sub={`Target: ${slaTarget}%`} healthVal={sla} />
        </div>
    );
};

/* ─── Charts Section ─── */
const DONUT_COLORS = [T.coral, T.amber, T.teal, T.blue, T.purple, T.green];

const ChartsSection = ({ reportData, journeyChartData }) => {
    const incidentData = useMemo(() => {
        if (!reportData?.incidents_by_type) return [];
        return Object.entries(reportData.incidents_by_type).map(([name, value]) => ({ name, value }));
    }, [reportData]);
    const totalIncidents = incidentData.reduce((s, d) => s + d.value, 0);

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 16 }} data-testid="charts-section">
            {/* Combo chart */}
            <div style={{ background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radius, padding: '20px 20px 12px' }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Ordenes asignadas vs Tiempo promedio de entrega</h3>
                {journeyChartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={240}>
                        <ComposedChart data={journeyChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke={T.borderSolid} />
                            <XAxis dataKey="date" tick={{ fontSize: 11, fill: T.textTer }} />
                            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: T.textTer }} />
                            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: T.textTer }} unit=" min" />
                            <RechartsTooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: `1px solid ${T.borderSolid}` }} />
                            <Legend wrapperStyle={{ fontSize: 11 }} />
                            <Bar yAxisId="left" dataKey="ordenes" name="Ordenes" fill={T.teal} radius={[3, 3, 0, 0]} barSize={28} />
                            <Line yAxisId="right" type="monotone" dataKey="tiempo_min" name="Tiempo (min)" stroke={T.amber} strokeWidth={2} dot={{ r: 3 }} />
                        </ComposedChart>
                    </ResponsiveContainer>
                ) : (
                    <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: T.textTer, fontSize: 13 }}>Sin datos para graficar en este periodo</div>
                )}
            </div>
            {/* Donut chart */}
            <div style={{ background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radius, padding: '20px' }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Desglose de incidencias</h3>
                {incidentData.length > 0 ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                        <ResponsiveContainer width={160} height={160}>
                            <PieChart>
                                <Pie data={incidentData} cx="50%" cy="50%" innerRadius={42} outerRadius={70} dataKey="value" paddingAngle={2}>
                                    {incidentData.map((_, i) => <Cell key={`cell-${i}`} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
                                </Pie>
                                <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle" style={{ fontSize: 22, fontWeight: 700, fill: T.textPri }}>{totalIncidents}</text>
                            </PieChart>
                        </ResponsiveContainer>
                        <div style={{ flex: 1 }}>
                            {incidentData.map((d, i) => (
                                <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                                    <span style={{ width: 10, height: 10, borderRadius: 2, background: DONUT_COLORS[i % DONUT_COLORS.length], flexShrink: 0 }} />
                                    <span style={{ flex: 1, fontSize: 12, color: T.textSec, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
                                    <span style={{ fontSize: 12, fontWeight: 600, fontFamily: "'DM Mono', monospace", color: T.textPri }}>{d.value}</span>
                                    <span style={{ fontSize: 10, color: T.textTer }}>{totalIncidents > 0 ? Math.round(d.value / totalIncidents * 100) : 0}%</span>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center', color: T.textTer, fontSize: 13 }}>Sin incidencias registradas</div>
                )}
            </div>
        </div>
    );
};

/* ─── Safe markdown-to-HTML renderer (sanitized via DOMPurify) ─── */
const renderMarkdown = (text) => {
    const html = text
        .replace(/## /g, '<h3 style="font-size:15px;font-weight:700;color:#1A1916;margin:18px 0 8px">')
        .replace(/\n/g, '<br/>')
        .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#1A1916">$1</strong>');
    return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['h3', 'br', 'strong', 'p', 'em', 'ul', 'li', 'ol'], ALLOWED_ATTR: ['style'] });
};

/* ─── AI Insights Cards ─── */
const CARD_COLORS = {
    alerta: { bg: '#FEF2F2', border: 'rgba(226,75,74,0.15)', text: '#E24B4A', icon: AlertTriangle },
    tendencia: { bg: '#EFF6FF', border: 'rgba(37,99,235,0.15)', text: '#2563EB', icon: TrendingUp },
    logro: { bg: '#F0FDF4', border: 'rgba(22,163,74,0.15)', text: '#16A34A', icon: CheckCircle2 },
};

const AiInsightsBar = ({ narrative, cards, generating, stale, onRegenerate }) => {
    if (!narrative && !cards?.length && !generating) return null;

    return (
        <div data-testid="ai-insights-bar" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {stale && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: T.radiusSm, background: T.amberLt, fontSize: 12, color: T.amber }}>
                    <AlertTriangle size={14} />
                    Los filtros cambiaron desde la ultima generacion.
                    <button onClick={onRegenerate} style={{ marginLeft: 'auto', padding: '4px 10px', borderRadius: 4, border: `1px solid ${T.amber}`, background: 'transparent', color: T.amber, fontSize: 11, fontWeight: 600, cursor: 'pointer' }} data-testid="regenerate-ai-btn">Regenerar IA</button>
                </div>
            )}
            {generating ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 20, borderRadius: T.radius, background: T.purpleLt, color: T.purple, fontSize: 13 }}>
                    <Loader2 size={16} className="animate-spin" /> Generando analisis inteligente...
                </div>
            ) : (
                <>
                    {/* Dynamic Cards */}
                    {cards && cards.length > 0 && (
                        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(cards.length, 3)}, 1fr)`, gap: 12 }}>
                            {cards.map((card, i) => {
                                const ct = CARD_COLORS[card.tipo] || CARD_COLORS.tendencia;
                                const CardIcon = ct.icon;
                                return (
                                    <div key={`card-${i}`} style={{ padding: '16px 18px', borderRadius: T.radius, background: ct.bg, border: `1px solid ${ct.border}` }} data-testid={`ai-card-${card.tipo}`}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                                            <CardIcon size={14} color={ct.text} />
                                            <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: ct.text }}>{card.tipo}</span>
                                            {card.metrica && <span style={{ marginLeft: 'auto', fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono', monospace", color: ct.text }}>{card.metrica}</span>}
                                        </div>
                                        <p style={{ fontSize: 13, fontWeight: 600, color: T.textPri, margin: '0 0 4px' }}>{card.titulo}</p>
                                        <p style={{ fontSize: 12, lineHeight: 1.5, color: T.textSec, margin: 0 }}>{card.cuerpo}</p>
                                        {card.variacion && card.variacion !== 'N/A' && (
                                            <span style={{ display: 'inline-block', marginTop: 6, fontSize: 11, fontWeight: 600, color: card.variacion?.startsWith('+') ? T.green : T.coral, fontFamily: "'DM Mono', monospace" }}>{card.variacion}</span>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                    {/* Markdown Report */}
                    {narrative && (
                        <div style={{ padding: '20px 24px', borderRadius: T.radius, background: T.surface, border: `1px solid ${T.borderSolid}` }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                                <Sparkles size={16} color={T.purple} />
                                <span style={{ fontSize: 14, fontWeight: 600, color: T.textPri }}>Reporte ejecutivo IA</span>
                                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: T.purpleLt, color: T.purple, fontWeight: 500 }}>Auto-generado</span>
                            </div>
                            <div style={{ fontSize: 13, lineHeight: 1.7, color: T.textSec }} dangerouslySetInnerHTML={{ __html: renderMarkdown(narrative) }} />
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

/* ─── Tab: Providers ─── */
const ProvidersTab = ({ data, slaData }) => {
    const rows = useMemo(() => {
        if (!data?.provider_metrics) return [];
        const slaMap = {};
        if (slaData?.by_provider) {
            for (const p of slaData.by_provider) {
                slaMap[p.provider_name] = p;
            }
        }
        return Object.entries(data.provider_metrics).map(([name, m]) => ({
            name, ...m,
            visit_rate: m.packages_loaded > 0 ? Math.round((m.delivered + m.failed) / m.packages_loaded * 100 * 10) / 10 : 0,
            sla_actual: slaMap[name]?.sla_actual || m.delivery_rate || 0,
            sla_target: slaMap[name]?.target || 75,
            active_today: m.days_operated > 0,
        }));
    }, [data, slaData]);
    const { sortedData, SortHeader } = useSortableTable(rows, 'delivery_rate', 'desc');

    if (!rows.length) return <EmptyState message="Sin datos de proveedores para este periodo." />;

    return (
        <div className="overflow-x-auto">
            <table className="lm-table" style={{ width: '100%' }}>
                <thead><tr>
                    <SortHeader field="name">Proveedor</SortHeader>
                    <SortHeader field="days_operated">Dias op.</SortHeader>
                    <SortHeader field="routes">Rutas</SortHeader>
                    <SortHeader field="packages_loaded">Paquetes</SortHeader>
                    <SortHeader field="delivered">Entregados</SortHeader>
                    <SortHeader field="delivery_rate">Entrega%</SortHeader>
                    <SortHeader field="visit_rate">Visita%</SortHeader>
                    <SortHeader field="km_total">Km totales</SortHeader>
                    <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 500, fontSize: 12, color: T.textTer, textTransform: 'uppercase', letterSpacing: '0.04em', borderBottom: `1px solid ${T.borderSolid}`, background: T.surface2 }}>SLA</th>
                </tr></thead>
                <tbody>
                    {sortedData.map(r => (
                        <tr key={r.name}>
                            <td style={{ fontWeight: 500 }}><ActivityDot active={r.active_today} />{r.name}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.days_operated}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.routes}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.packages_loaded}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.delivered}</td>
                            <td><RateCell value={r.delivery_rate} /></td>
                            <td><RateCell value={r.visit_rate} /></td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{(r.km_total || 0).toLocaleString()}</td>
                            <td><SlaBadge actual={r.sla_actual} target={r.sla_target} /></td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

/* ─── Tab: Drivers ─── */
const DriversTab = ({ data }) => {
    const rows = useMemo(() => {
        if (!data?.driver_metrics) return [];
        return Object.entries(data.driver_metrics).map(([name, m]) => ({ name, ...m }));
    }, [data]);
    const { sortedData, SortHeader } = useSortableTable(rows, 'delivery_rate', 'desc');

    if (!rows.length) return <EmptyState message="Sin datos de drivers para este periodo." />;

    return (
        <>
            <div className="overflow-x-auto">
                <table className="lm-table" style={{ width: '100%' }}>
                    <thead><tr>
                        <SortHeader field="name">Driver</SortHeader>
                        <SortHeader field="days_operated">Dias op.</SortHeader>
                        <SortHeader field="routes">Rutas</SortHeader>
                        <SortHeader field="packages_loaded">Paquetes</SortHeader>
                        <SortHeader field="delivered">Entregados</SortHeader>
                        <SortHeader field="delivery_rate">SLA individual</SortHeader>
                        <SortHeader field="km_total">Km</SortHeader>
                    </tr></thead>
                    <tbody>
                        {sortedData.map(r => (
                            <tr key={r.name} style={r.delivery_rate < 60 ? { background: T.amberLt } : {}}>
                                <td style={{ fontWeight: 500 }}><ActivityDot active={r.days_operated > 0} />{r.name}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.days_operated}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.routes}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.packages_loaded}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.delivered}</td>
                                <td><RateCell value={r.delivery_rate} /></td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{(r.km_total || 0).toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.borderSolid}`, fontSize: 12, color: T.textTer }}>
                Politica de strikes: 1er aviso - 2do descanso operativo - 3ro baja. Filas con fondo ambar: SLA individual &lt;60%.
            </div>
        </>
    );
};

/* ─── Tab: Incidents ─── */
const IncidentsTab = ({ data }) => {
    const rows = useMemo(() => {
        if (!data?.incidents_by_type) return [];
        return Object.entries(data.incidents_by_type).map(([type, count]) => ({ type, total: count }));
    }, [data]);
    const { sortedData, SortHeader } = useSortableTable(rows, 'total', 'desc');

    if (!rows.length) return <EmptyState message="Sin incidencias registradas. Buen desempeno!" icon={CheckCircle2} />;

    return (
        <>
            <div className="overflow-x-auto">
                <table className="lm-table" style={{ width: '100%' }}>
                    <thead><tr>
                        <SortHeader field="type">Tipo de incidencia</SortHeader>
                        <SortHeader field="total">Total</SortHeader>
                    </tr></thead>
                    <tbody>
                        {sortedData.map(r => (
                            <tr key={r.type}>
                                <td style={{ fontWeight: 500 }}>{r.type}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.total}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.borderSolid}`, fontSize: 12, color: T.textTer }}>
                Incidencias de zona (accesibilidad) NO penalizan el SLA del driver.
            </div>
        </>
    );
};

/* ─── Tab: Attempts ─── */
const AttemptsTab = ({ attempts }) => {
    if (!attempts) return <EmptyState message="Sin datos de intentos para este periodo." />;
    const bars = [
        { label: '1er intento', ...attempts.first_attempt, color: T.green },
        { label: '2do intento', ...attempts.second_attempt, color: T.amber },
        { label: '3er+ intento', ...attempts.third_attempt, color: T.coral },
    ];
    const causes = [
        { label: 'Gestion del driver', key: 'driver_management', color: T.coral },
        { label: 'Cliente ausente', key: 'client_absent', color: T.amber },
        { label: 'Direccion erronea', key: 'wrong_address', color: T.blue },
        { label: 'Zona sin acceso', key: 'zone_no_access', color: T.teal },
    ];
    const maxBar = Math.max(1, ...bars.map(b => b.pct));
    return (
        <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, padding: 24 }}>
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Distribucion de intentos</h4>
                    {bars.map(b => (
                        <div key={b.label} style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <span style={{ fontSize: 13, color: T.textSec }}>{b.label}</span>
                                <span style={{ fontSize: 13, fontFamily: "'DM Mono', monospace", fontWeight: 500 }}>{b.count} ({b.pct}%)</span>
                            </div>
                            <div style={{ height: 10, borderRadius: 5, background: T.surface2 }}>
                                <div style={{ height: '100%', borderRadius: 5, width: `${(b.pct / maxBar) * 100}%`, background: b.color, transition: 'width 0.4s' }} />
                            </div>
                        </div>
                    ))}
                </div>
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Causa de reintento (2do+)</h4>
                    {causes.map(c => {
                        const d = attempts.retry_causes?.[c.key] || { count: 0, pct: 0 };
                        return (
                            <div key={c.key} style={{ marginBottom: 14 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                    <span style={{ fontSize: 13, color: T.textSec }}>{c.label}</span>
                                    <span style={{ fontSize: 13, fontFamily: "'DM Mono', monospace", fontWeight: 500 }}>{d.count} ({d.pct}%)</span>
                                </div>
                                <div style={{ height: 10, borderRadius: 5, background: T.surface2 }}>
                                    <div style={{ height: '100%', borderRadius: 5, width: `${d.pct}%`, background: c.color, transition: 'width 0.4s' }} />
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.borderSolid}`, fontSize: 12, color: T.textTer }}>
                Total de paquetes en periodo: {attempts.total_packages || 0}. Reintentos impactan directamente el costo operativo.
            </div>
        </>
    );
};

/* ─── Tab: Quality ─── */
const QualityTab = ({ data }) => {
    const qd = data?.quality_report;
    const summary = qd?.summary || {};
    const avg = summary.avg_score || 0;
    const total = summary.total_evaluated || 0;
    const complete = summary.complete || 0;
    const incomplete = summary.incomplete || 0;
    const byProvider = qd?.by_provider || [];
    const byType = qd?.by_type || [];
    if (!total && !byProvider.length) return <EmptyState message="Sin evidencias registradas para este periodo." />;
    return (
        <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 0 }}>
            <div style={{ padding: 24, borderRight: `1px solid ${T.borderSolid}` }}>
                <div style={{ textAlign: 'center', marginBottom: 16 }}>
                    <div style={{ fontSize: 48, fontWeight: 700, fontFamily: "'DM Sans', sans-serif", color: avg >= 90 ? T.green : avg >= 70 ? T.amber : T.coral }}>{avg.toFixed(1)}</div>
                    <div style={{ fontSize: 12, color: T.textTer }}>Score global</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8 }}>
                    <span style={{ color: T.textSec }}>Completas</span>
                    <span style={{ fontFamily: "'DM Mono', monospace", color: T.green, fontWeight: 600 }}>{complete}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 12 }}>
                    <span style={{ color: T.textSec }}>Incompletas</span>
                    <span style={{ fontFamily: "'DM Mono', monospace", color: T.coral, fontWeight: 600 }}>{incomplete}</span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: T.surface2, marginBottom: 4 }}>
                    <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(avg / 90 * 100, 100)}%`, background: avg >= 90 ? T.green : T.amber }} />
                </div>
                <div style={{ fontSize: 11, color: T.textTer, textAlign: 'center' }}>Target: 90%</div>
            </div>
            <div style={{ padding: 24 }}>
                {byType.length > 0 && (
                    <div style={{ marginBottom: 20 }}>
                        <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Por tipo de evidencia</h4>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            {byType.map(t => (
                                <span key={t.type || t._id} style={{ padding: '4px 10px', borderRadius: 4, fontSize: 12, background: T.surface2, color: T.textPri, fontWeight: 500 }}>
                                    {t.type || t._id}: {t.count} ({t.avg_score ? t.avg_score.toFixed(0) : 0}%)
                                </span>
                            ))}
                        </div>
                    </div>
                )}
                {byProvider.length > 0 && (
                    <div>
                        <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Por proveedor</h4>
                        {byProvider.map(p => (
                            <div key={p.provider || p._id} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
                                <span style={{ width: 120, fontSize: 13, color: T.textSec, flexShrink: 0 }}>{p.provider || p._id}</span>
                                <div style={{ flex: 1, height: 8, borderRadius: 4, background: T.surface2 }}>
                                    <div style={{ height: '100%', borderRadius: 4, width: `${p.avg_score || 0}%`, background: (p.avg_score || 0) >= 85 ? T.green : (p.avg_score || 0) >= 70 ? T.amber : T.coral }} />
                                </div>
                                <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 13, fontWeight: 500, width: 44, textAlign: 'right' }}>{(p.avg_score || 0).toFixed(0)}%</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

/* ─── Tab: SLA ─── */
const SLATab = ({ slaData, canEditBrackets }) => {
    const [brackets, setBrackets] = useState([]);
    const [saving, setSaving] = useState(false);
    useEffect(() => { if (slaData?.brackets) setBrackets(slaData.brackets.map(b => ({ ...b }))); }, [slaData]);
    if (!slaData) return <EmptyState message="Cargando SLA..." />;
    const { consolidated, by_provider, by_driver } = slaData;
    const statusIcon = (s) => s === 'above' ? <CheckCircle2 size={14} color={T.green} /> : <AlertTriangle size={14} color={T.coral} />;
    const bracketStatusLabel = { exceeded: 'Superado', active: 'En curso', pending: 'Pendiente' };
    const bracketStatusColor = { exceeded: T.green, active: T.amber, pending: T.textTer };
    const saveBrackets = async () => { setSaving(true); try { await updateSlaTargets(brackets); toast.success('SLA targets actualizados'); } catch { toast.error('Error al guardar'); } setSaving(false); };

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
            <div style={{ padding: 24, borderRight: `1px solid ${T.borderSolid}` }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>SLA Consolidado ME - Cubbo</h4>
                <div style={{ textAlign: 'center', marginBottom: 20 }}>
                    <div style={{ fontSize: 48, fontWeight: 700, fontFamily: "'DM Sans', sans-serif", color: consolidated.actual >= consolidated.target ? T.green : T.coral }}>{consolidated.actual}%</div>
                    <div style={{ height: 8, borderRadius: 4, background: T.surface2, marginTop: 8 }}>
                        <div style={{ height: '100%', borderRadius: 4, width: `${Math.min(consolidated.actual / consolidated.target * 100, 100)}%`, background: consolidated.actual >= consolidated.target ? T.green : T.amber }} />
                    </div>
                    <div style={{ fontSize: 12, color: T.textTer, marginTop: 4 }}>Target actual: {consolidated.target}%</div>
                </div>
                <h5 style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Brackets de escalamiento</h5>
                {brackets.map((b, i) => (
                    <div key={`bracket-${b.label}`} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, padding: '8px 12px', borderRadius: T.radiusSm, background: T.surface2 }}>
                        <span style={{ fontSize: 13, fontWeight: 500, width: 80, flexShrink: 0 }}>{b.label}</span>
                        {canEditBrackets ? (
                            <input type="number" value={b.target} onChange={e => { const u = [...brackets]; u[i] = { ...u[i], target: Number(e.target.value) }; setBrackets(u); }} onBlur={saveBrackets} style={{ width: 60, padding: '4px 8px', border: `1px solid ${T.borderSolid}`, borderRadius: 4, fontSize: 13, fontFamily: "'DM Mono', monospace", textAlign: 'center' }} data-testid={`sla-bracket-input-${i}`} />
                        ) : (<span style={{ fontFamily: "'DM Mono', monospace", fontSize: 13, fontWeight: 600 }}>{b.target}%</span>)}
                        <div style={{ flex: 1, height: 6, borderRadius: 3, background: '#E5E5E0' }}>
                            <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(consolidated.actual / b.target * 100, 100)}%`, background: bracketStatusColor[b.status] || T.textTer }} />
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 500, color: bracketStatusColor[b.status] || T.textTer, whiteSpace: 'nowrap' }}>{bracketStatusLabel[b.status] || b.status}</span>
                    </div>
                ))}
            </div>
            <div style={{ padding: 24 }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Por proveedor</h4>
                <table className="lm-table" style={{ width: '100%', marginBottom: 24 }}>
                    <thead><tr><th>Proveedor</th><th>SLA actual</th><th>Target</th><th>Brecha</th><th></th></tr></thead>
                    <tbody>
                        {by_provider?.map(p => (
                            <tr key={p.provider_name} style={p.status === 'below' ? { background: T.coralLt } : {}}>
                                <td style={{ fontWeight: 500 }}>{p.provider_name}</td>
                                <td><RateCell value={p.sla_actual} /></td>
                                <td style={{ fontFamily: "'DM Mono', monospace", fontSize: 13 }}>{p.target}%</td>
                                <td style={{ fontFamily: "'DM Mono', monospace", fontSize: 13, color: p.gap_pp >= 0 ? T.green : T.coral }}>{p.gap_pp >= 0 ? '+' : ''}{p.gap_pp}pp</td>
                                <td>{statusIcon(p.status)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Top drivers</h4>
                <table className="lm-table" style={{ width: '100%' }}>
                    <thead><tr><th>Driver</th><th>SLA</th><th>vs Target</th><th></th></tr></thead>
                    <tbody>
                        {by_driver?.slice(0, 8).map(d => (
                            <tr key={d.driver_name} style={d.status === 'below' ? { background: T.coralLt } : {}}>
                                <td style={{ fontWeight: 500, fontSize: 13 }}>{d.driver_name}</td>
                                <td><RateCell value={d.sla_actual} /></td>
                                <td style={{ fontFamily: "'DM Mono', monospace", fontSize: 13, color: d.gap_pp >= 0 ? T.green : T.coral }}>{d.gap_pp >= 0 ? '+' : ''}{d.gap_pp}pp</td>
                                <td>{statusIcon(d.status)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

/* ─── Empty State ─── */
const EmptyState = ({ message, icon: Icon = FileText, onPeriodChange }) => (
    <div style={{ padding: '48px 24px', textAlign: 'center' }} data-testid="empty-state">
        <Icon size={32} color={T.textTer} style={{ marginBottom: 12 }} />
        <p style={{ fontSize: 14, color: T.textSec, marginBottom: 16 }}>{message}</p>
        {onPeriodChange && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
                {['Ayer', 'Ultimos 7 dias', 'Semana anterior'].map(label => {
                    const val = label === 'Ayer' ? 'today' : label.includes('7') ? '7d' : 'prev_week';
                    return (
                        <button key={label} onClick={() => onPeriodChange(val === 'today' ? '7d' : val)} style={{ padding: '6px 14px', borderRadius: 14, border: `1px solid ${T.borderSolid}`, background: T.surface, fontSize: 12, cursor: 'pointer', color: T.textPri }} data-testid={`quick-period-${val}`}>{label}</button>
                    );
                })}
            </div>
        )}
    </div>
);


/* ═══════════════════════════════════════════════════════════════════ */
/*                          REPORTS PAGE                              */
/* ═══════════════════════════════════════════════════════════════════ */

const Reports = () => {
    const { user, canEdit } = useAuth();
    const canEditBrackets = ['coordinator', 'developer'].includes(user?.role);
    const isProvider = user?.role === 'proveedor';

    // Global state
    const [period, setPeriod] = useState('today');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [clientId, setClientId] = useState('');
    const [providerId, setProviderId] = useState('');
    const sections = useMemo(() => ['providers', 'drivers', 'incidents', 'attempts', 'quality', 'sla'], []);

    // Data
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [reportData, setReportData] = useState(null);
    const [prevReportData, setPrevReportData] = useState(null);
    const [qualityData, setQualityData] = useState(null);
    const [attemptsData, setAttemptsData] = useState(null);
    const [slaData, setSlaData] = useState(null);
    const [aiNarrative, setAiNarrative] = useState(null);
    const [aiCards, setAiCards] = useState([]);
    const [aiStale, setAiStale] = useState(false);
    const [journeyChartData, setJourneyChartData] = useState([]);

    // UI state
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [exportingPdf, setExportingPdf] = useState(false);
    const [activeTab, setActiveTab] = useState('providers');
    const [showClientDrop, setShowClientDrop] = useState(false);
    const [showProviderDrop, setShowProviderDrop] = useState(false);
    const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

    const effectiveDates = useMemo(() => {
        if (period === 'custom' && dateFrom && dateTo) return { from: dateFrom, to: dateTo };
        return getDateRange(period);
    }, [period, dateFrom, dateTo]);

    const prevDates = useMemo(() => getPrevDateRange(period), [period]);

    // Load clients/providers once
    useEffect(() => {
        Promise.all([getClients(), getProviders()]).then(([c, p]) => {
            setClients(c.data || []);
            setProviders(p.data || []);
        }).catch(() => {});
    }, []);

    const selectedClientName = useMemo(() => clients.find(c => c.id === clientId)?.name || 'Todos los clientes', [clients, clientId]);
    const selectedProviderName = useMemo(() => providers.find(p => p.id === providerId)?.name || 'Todos los proveedores', [providers, providerId]);

    // Fetch data
    const fetchData = useCallback(async () => {
        setLoading(true);
        if (aiNarrative) setAiStale(true);
        try {
            const params = { date_from: effectiveDates.from, date_to: effectiveDates.to };
            if (clientId) params.client_id = clientId;
            if (providerId) params.provider_id = providerId;

            const [report, quality, attempts, sla] = await Promise.allSettled([
                generateReport({ ...params, sections }),
                getQualityReport(params),
                getReportAttempts(params),
                getReportSla(params),
            ]);

            setReportData(report.status === 'fulfilled' ? report.value.data : null);
            setQualityData(quality.status === 'fulfilled' ? quality.value.data : null);
            setAttemptsData(attempts.status === 'fulfilled' ? attempts.value.data : null);
            setSlaData(sla.status === 'fulfilled' ? sla.value.data : null);

            // Build chart data from report
            const rd = report.status === 'fulfilled' ? report.value.data : null;
            if (rd?.daily_stats) {
                setJourneyChartData(rd.daily_stats.map(d => ({
                    date: d.date ? d.date.slice(5, 10) : '',
                    ordenes: d.packages || 0,
                    tiempo_min: d.avg_delivery_time || 0,
                })));
            } else {
                setJourneyChartData([]);
            }

            // Fetch prev period for delta comparison
            if (prevDates) {
                try {
                    const prevParams = { date_from: prevDates.from, date_to: prevDates.to };
                    if (clientId) prevParams.client_id = clientId;
                    if (providerId) prevParams.provider_id = providerId;
                    const prevRes = await generateReport({ ...prevParams, sections: ['providers'] });
                    setPrevReportData(prevRes.data);
                } catch { setPrevReportData(null); }
            }
        } catch {
            toast.error('Error al cargar datos');
        } finally {
            setLoading(false);
        }
    }, [effectiveDates, clientId, providerId, sections, prevDates, aiNarrative]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleGenerateAI = async () => {
        setGenerating(true);
        setAiStale(false);
        try {
            const res = await generateAiReport({
                date_from: effectiveDates.from, date_to: effectiveDates.to,
                client_id: clientId || undefined, provider_id: providerId || undefined,
            });
            setAiNarrative(res.data.narrative || '');
            setAiCards(res.data.cards || []);
        } catch {
            setAiNarrative('Error al generar el reporte con IA.');
            setAiCards([]);
        } finally {
            setGenerating(false);
        }
    };

    const handleExport = async () => {
        setExporting(true);
        try {
            const res = await generateReportExcel({
                date_from: effectiveDates.from, date_to: effectiveDates.to,
                sections, client_id: clientId || undefined, provider_id: providerId || undefined,
            });
            downloadFile(res.data, `reporte_${effectiveDates.from}_${effectiveDates.to}.xlsx`);
            toast.success('Reporte Excel exportado');
        } catch { toast.error('Error al exportar'); }
        setExporting(false);
    };

    const handleExportPDF = async () => {
        setExportingPdf(true);
        try {
            const { generateMultiPagePDF } = await import('../lib/pdfReportGenerator');
            const filters = [];
            if (clientId) filters.push(`Cliente: ${selectedClientName}`);
            if (providerId) filters.push(`Proveedor: ${selectedProviderName}`);

            await generateMultiPagePDF({
                reportData,
                prevReportData: prevReportData,
                qualityData,
                attemptsData,
                slaData,
                aiNarrative,
                aiCards,
                meta: {
                    dateFrom: effectiveDates.from,
                    dateTo: effectiveDates.to,
                    filters,
                    userName: user?.name || user?.email || 'Sistema',
                },
            });
            toast.success('Reporte PDF exportado (multi-pagina)');
        } catch (e) {
            console.error('PDF generation error:', e);
            toast.error('Error al generar PDF');
        }
        setExportingPdf(false);
    };

    const hasData = reportData && (reportData.total_packages > 0 || Object.keys(reportData.provider_metrics || {}).length > 0);

    const TABS = [
        { id: 'providers', label: 'Proveedores', icon: Truck },
        { id: 'drivers', label: 'Drivers', icon: Users },
        { id: 'incidents', label: 'Incidencias', icon: AlertTriangle },
        { id: 'attempts', label: 'Intentos', icon: RefreshCw, isNew: true },
        { id: 'quality', label: 'Evidencias', icon: ShieldCheck },
        { id: 'sla', label: 'SLA', icon: Target, isNew: true },
    ];

    return (
        <div className="lm-dashboard" data-testid="reports-page">
            <style>{`
                .lm-dashboard { font-family: 'DM Sans', sans-serif; display: flex; flex-direction: column; gap: 16px; }
                .lm-card { background: ${T.surface}; border: 1px solid ${T.borderSolid}; border-radius: ${T.radius}px; overflow: hidden; }
                .lm-table { border-collapse: collapse; font-size: 13px; }
                .lm-table thead th { padding: 10px 14px; text-align: left; font-weight: 500; font-size: 12px; color: ${T.textTer}; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid ${T.borderSolid}; background: ${T.surface2}; cursor: pointer; white-space: nowrap; }
                .lm-table tbody td { padding: 10px 14px; border-bottom: 1px solid ${T.borderSolid}; color: ${T.textPri}; }
                .lm-table tbody tr:hover { background: ${T.surface2}; }
                .chip-btn { display: inline-flex; align-items: center; gap: 5px; padding: 6px 14px; border-radius: 16px; font-size: 12px; font-weight: 500; border: 1px solid ${T.borderSolid}; background: ${T.surface}; cursor: pointer; font-family: 'DM Sans', sans-serif; color: ${T.textPri}; transition: all 0.15s; white-space: nowrap; }
                .chip-btn:hover { background: ${T.surface2}; }
                .chip-btn.active { background: ${T.textPri}; color: #fff; border-color: ${T.textPri}; }
                .chip-dropdown { position: relative; }
                .chip-dropdown-menu { position: absolute; top: calc(100% + 4px); left: 0; z-index: 20; background: ${T.surface}; border: 1px solid ${T.borderSolid}; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); min-width: 180px; max-height: 280px; overflow-y: auto; }
                .chip-dropdown-item { padding: 8px 14px; font-size: 13px; cursor: pointer; display: block; width: 100%; text-align: left; border: none; background: none; color: ${T.textPri}; font-family: 'DM Sans', sans-serif; }
                .chip-dropdown-item:hover { background: ${T.surface2}; }
                .chip-dropdown-item.selected { background: ${T.tealLt}; font-weight: 600; }
                @media (max-width: 768px) {
                    .filter-bar-desktop { display: none !important; }
                    .filter-bar-mobile { display: flex !important; }
                    .kpi-grid-4 { grid-template-columns: 1fr 1fr !important; }
                    .charts-grid { grid-template-columns: 1fr !important; }
                }
                @media (min-width: 769px) {
                    .filter-bar-mobile { display: none !important; }
                }
                .skeleton { background: linear-gradient(90deg, ${T.surface2} 25%, #E8E7E3 50%, ${T.surface2} 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 6px; }
                @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
            `}</style>

            {/* ─── TOP BAR ─── */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: T.textPri, margin: 0 }}>Reportes</h1>
                    <p style={{ fontSize: 13, color: T.textTer, marginTop: 2 }}>Desempeno operativo consolidado</p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={handleExport} disabled={exporting || loading} className="chip-btn" data-testid="export-excel-btn">
                        {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                        Excel
                    </button>
                    <button onClick={handleExportPDF} disabled={exportingPdf || loading} className="chip-btn" data-testid="export-pdf-btn">
                        {exportingPdf ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
                        PDF
                    </button>
                    <button onClick={handleGenerateAI} disabled={generating || loading} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 16, border: 'none', background: T.purple, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: "'DM Sans', sans-serif" }} data-testid="generate-ai-btn">
                        {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                        Generar IA
                    </button>
                </div>
            </div>

            {/* ─── FILTER BAR (desktop) ─── */}
            <div className="filter-bar-desktop" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '12px 16px', background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radius }} data-testid="filter-bar">
                {/* Date chip */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 14, background: T.tealLt, color: T.teal, fontSize: 12, fontWeight: 600, marginRight: 4 }}>
                    <Calendar size={13} />
                    {formatDateLabel(effectiveDates.from)}{effectiveDates.from !== effectiveDates.to ? ` — ${formatDateLabel(effectiveDates.to)}` : ''}
                </div>

                <div style={{ width: 1, height: 24, background: T.borderSolid, margin: '0 4px' }} />

                {/* Period chips */}
                {PERIODS.map(p => (
                    <button key={p.value} onClick={() => setPeriod(p.value)} className={`chip-btn ${period === p.value ? 'active' : ''}`} data-testid={`period-${p.value}`}>
                        {p.label}
                    </button>
                ))}

                {period === 'custom' && (
                    <>
                        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${T.borderSolid}`, fontSize: 12 }} data-testid="custom-date-from" />
                        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ padding: '5px 8px', borderRadius: 6, border: `1px solid ${T.borderSolid}`, fontSize: 12 }} data-testid="custom-date-to" />
                    </>
                )}

                <div style={{ width: 1, height: 24, background: T.borderSolid, margin: '0 4px' }} />

                {/* Client dropdown */}
                <div className="chip-dropdown">
                    <button className="chip-btn" onClick={() => { setShowClientDrop(!showClientDrop); setShowProviderDrop(false); }} data-testid="report-client-filter">
                        <ChevronDown size={12} /> {selectedClientName}
                    </button>
                    {showClientDrop && (
                        <div className="chip-dropdown-menu">
                            <button className={`chip-dropdown-item ${!clientId ? 'selected' : ''}`} onClick={() => { setClientId(''); setShowClientDrop(false); }}>Todos los clientes</button>
                            {clients.map(c => (
                                <button key={c.id} className={`chip-dropdown-item ${clientId === c.id ? 'selected' : ''}`} onClick={() => { setClientId(c.id); setShowClientDrop(false); }}>{c.name}</button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Provider dropdown (hidden for provider role) */}
                {!isProvider && (
                    <div className="chip-dropdown">
                        <button className="chip-btn" onClick={() => { setShowProviderDrop(!showProviderDrop); setShowClientDrop(false); }} data-testid="report-provider-filter">
                            <ChevronDown size={12} /> {selectedProviderName}
                        </button>
                        {showProviderDrop && (
                            <div className="chip-dropdown-menu">
                                <button className={`chip-dropdown-item ${!providerId ? 'selected' : ''}`} onClick={() => { setProviderId(''); setShowProviderDrop(false); }}>Todos los proveedores</button>
                                {providers.map(p => (
                                    <button key={p.id} className={`chip-dropdown-item ${providerId === p.id ? 'selected' : ''}`} onClick={() => { setProviderId(p.id); setShowProviderDrop(false); }}>{p.name}</button>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ─── FILTER BAR (mobile) ─── */}
            <div className="filter-bar-mobile" style={{ display: 'none' }}>
                <button onClick={() => setMobileFiltersOpen(!mobileFiltersOpen)} className="chip-btn" style={{ width: '100%', justifyContent: 'center' }}>
                    <Filter size={14} /> Filtros: {PERIODS.find(p => p.value === period)?.label} {mobileFiltersOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
                {mobileFiltersOpen && (
                    <div style={{ padding: 12, background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radius, marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {PERIODS.map(p => (
                            <button key={p.value} onClick={() => setPeriod(p.value)} className={`chip-btn ${period === p.value ? 'active' : ''}`}>{p.label}</button>
                        ))}
                    </div>
                )}
            </div>

            {/* ─── CONTENT (captured for PDF) ─── */}
            <div id="reports-content" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

                {/* ─── AI INSIGHTS ─── */}
                <AiInsightsBar narrative={aiNarrative} cards={aiCards} generating={generating} stale={aiStale} onRegenerate={handleGenerateAI} />

                {/* ─── KPI STRIP ─── */}
                {loading ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1, border: `1px solid ${T.borderSolid}`, borderRadius: T.radius, overflow: 'hidden' }} className="kpi-grid-4">
                        {[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 90 }} />)}
                    </div>
                ) : (
                    <div className="kpi-grid-4">
                        <KPIStrip reportData={reportData} slaData={slaData} qualityData={qualityData} prevData={prevReportData} />
                    </div>
                )}

                {/* ─── CHARTS ─── */}
                {!loading && hasData && (
                    <div className="charts-grid">
                        <ChartsSection reportData={reportData} journeyChartData={journeyChartData} />
                    </div>
                )}

                {/* ─── EMPTY STATE ─── */}
                {!loading && !hasData && (
                    <div className="lm-card">
                        <EmptyState message="Sin operaciones registradas para este periodo. Selecciona otro periodo para ver datos historicos." icon={Calendar} onPeriodChange={(p) => setPeriod(p)} />
                    </div>
                )}

                {/* ─── TABS ─── */}
                {hasData && (
                    <div className="lm-card">
                        <div style={{ display: 'flex', borderBottom: `1px solid ${T.borderSolid}`, background: T.surface2, overflow: 'auto' }}>
                            {TABS.map(t => {
                                const Icon = t.icon;
                                const isActive = activeTab === t.id;
                                return (
                                    <button key={t.id} onClick={() => setActiveTab(t.id)} data-testid={`tab-${t.id}`}
                                        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '12px 20px', fontSize: 13, fontWeight: isActive ? 600 : 400, color: isActive ? T.textPri : T.textSec, background: isActive ? T.surface : 'transparent', border: 'none', borderBottom: isActive ? `2px solid ${T.teal}` : '2px solid transparent', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", whiteSpace: 'nowrap', transition: 'all 0.15s' }}>
                                        <Icon size={14} />
                                        {t.label}
                                        {t.isNew && <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 3, background: T.tealLt, color: T.teal }}>Nuevo</span>}
                                    </button>
                                );
                            })}
                        </div>
                        <div style={{ minHeight: 200 }}>
                            {loading ? (
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60, gap: 8, color: T.textSec, fontSize: 14 }}>
                                    <Loader2 size={20} className="animate-spin" /> Cargando datos...
                                </div>
                            ) : (
                                <>
                                    {activeTab === 'providers' && <ProvidersTab data={reportData} slaData={slaData} />}
                                    {activeTab === 'drivers' && <DriversTab data={reportData} />}
                                    {activeTab === 'incidents' && <IncidentsTab data={reportData} />}
                                    {activeTab === 'attempts' && <AttemptsTab attempts={attemptsData} />}
                                    {activeTab === 'quality' && <QualityTab data={{ quality_report: qualityData }} />}
                                    {activeTab === 'sla' && <SLATab slaData={slaData} canEditBrackets={canEditBrackets} />}
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Reports;
