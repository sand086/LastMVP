import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
} from 'lucide-react';
import { toast } from 'sonner';

/* ─── Design tokens ─── */
const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', green: '#16A34A', amber: '#D97706', coral: '#DC2626', teal: '#0D9488',
    greenLt: '#F0FDF4', amberLt: '#FFFBEB', coralLt: '#FEF2F2', tealLt: '#F0FDFA',
    radius: 10, radiusSm: 6,
};

const PERIODS = [
    { label: 'Últimos 7 días', value: '7d' },
    { label: 'Últimos 15 días', value: '15d' },
    { label: 'Mes actual', value: 'current_month' },
    { label: 'Mes anterior', value: 'prev_month' },
    { label: 'Semana anterior', value: 'prev_week' },
    { label: 'Personalizado', value: 'custom' },
];

const SECTIONS = [
    { id: 'providers', title: 'Métricas por proveedor', desc: 'Días operados, rutas, paquetes, tasa entrega, visita%, km', icon: Truck, defaultOn: true },
    { id: 'drivers', title: 'Métricas por driver', desc: 'Desempeño individual por mensajero', icon: Users, defaultOn: true },
    { id: 'incidents', title: 'Desglose de incidencias', desc: 'Conteo por tipo e imputabilidad', icon: AlertTriangle, defaultOn: true },
    { id: 'attempts', title: 'Intentos de entrega', desc: '1°, 2°, 3er intento y causa de reintento', icon: RefreshCw, defaultOn: false, isNew: true },
    { id: 'quality', title: 'Calidad de evidencias', desc: 'Score, errores por tipo, distribución', icon: ShieldCheck, defaultOn: true },
    { id: 'sla', title: 'SLA vs Target', desc: 'Cumplimiento por nivel: driver, proveedor, ME→Cubbo', icon: Target, defaultOn: false, isNew: true },
];

const getDateRange = (preset) => {
    const now = new Date();
    const fmt = (d) => d.toISOString().split('T')[0];
    switch (preset) {
        case '7d': { const f = new Date(now); f.setDate(f.getDate() - 6); return { from: fmt(f), to: fmt(now) }; }
        case '15d': { const f = new Date(now); f.setDate(f.getDate() - 14); return { from: fmt(f), to: fmt(now) }; }
        case 'current_month': return { from: fmt(new Date(now.getFullYear(), now.getMonth(), 1)), to: fmt(now) };
        case 'prev_month': { const f = new Date(now.getFullYear(), now.getMonth() - 1, 1); return { from: fmt(f), to: fmt(new Date(now.getFullYear(), now.getMonth(), 0)) }; }
        case 'prev_week': { const s = new Date(now); s.setDate(s.getDate() - s.getDay() - 7); const e = new Date(s); e.setDate(e.getDate() + 6); return { from: fmt(s), to: fmt(e) }; }
        default: return { from: fmt(now), to: fmt(now) };
    }
};

const ratePill = (val) => {
    const n = parseFloat(val) || 0;
    const bg = n >= 85 ? T.greenLt : n >= 70 ? T.amberLt : T.coralLt;
    const color = n >= 85 ? T.green : n >= 70 ? T.amber : T.coral;
    return <span style={{ padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, fontFamily: "'DM Mono', monospace", background: bg, color }}>{n.toFixed(1)}%</span>;
};

const severityPill = (sev) => {
    const map = { alta: T.coral, media: T.amber, baja: T.green };
    return <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500, background: map[sev?.toLowerCase()] ? `${map[sev.toLowerCase()]}20` : T.surface2, color: map[sev?.toLowerCase()] || T.textSec }}>{sev || 'N/A'}</span>;
};

/* ─── KPI Strip ─── */
const KPIStrip = ({ reportData, slaData, qualityData }) => {
    const delivery = reportData?.delivery_rate || 0;
    const totalPkg = reportData?.total_packages || 1;
    const totalDelivered = reportData?.total_delivered || 0;
    const totalFailed = reportData?.total_failed || 0;
    const visitRate = totalPkg > 0 ? Math.round((totalDelivered + totalFailed) / totalPkg * 100 * 10) / 10 : 0;
    const qualityAvg = qualityData?.summary?.avg_score || 0;
    const sla = slaData?.consolidated?.actual || delivery;
    const slaTarget = slaData?.consolidated?.target || 75;

    const items = [
        { label: 'Tasa de entrega', value: `${delivery}%`, delta: null },
        { label: 'Tasa de visita', value: `${visitRate}%`, delta: null },
        { label: 'Calidad evidencias', value: `${qualityAvg}%`, delta: null },
        { label: 'SLA vs target', value: `${sla}%`, sub: `Target: ${slaTarget}%`, delta: sla - slaTarget },
    ];

    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, overflow: 'hidden' }} data-testid="kpi-strip">
            {items.map((item, i) => (
                <div key={`kpi-${item.label}`} style={{ padding: '16px 20px', borderRight: i < 3 ? `1px solid ${T.border}` : 'none' }}>
                    <p style={{ fontSize: 11, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', color: T.textTer, marginBottom: 4 }}>{item.label}</p>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                        <span style={{ fontSize: 24, fontWeight: 600, fontFamily: "'DM Sans', sans-serif", color: T.textPri }}>{item.value}</span>
                        {item.delta !== null && (
                            <span style={{ fontSize: 12, fontWeight: 500, color: item.delta >= 0 ? T.green : T.amber, display: 'flex', alignItems: 'center', gap: 2 }}>
                                {item.delta >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                                {item.delta >= 0 ? '+' : ''}{item.delta.toFixed(1)}pp
                            </span>
                        )}
                    </div>
                    {item.sub && <p style={{ fontSize: 11, color: T.textTer, marginTop: 2 }}>{item.sub}</p>}
                </div>
            ))}
        </div>
    );
};

/* ─── Tab: Providers ─── */
const ProvidersTab = ({ data }) => {
    const rows = useMemo(() => {
        if (!data?.provider_metrics) return [];
        return Object.entries(data.provider_metrics).map(([name, m]) => ({
            name, ...m,
            visit_rate: m.packages_loaded > 0 ? Math.round((m.delivered + m.failed) / m.packages_loaded * 100 * 10) / 10 : 0,
        }));
    }, [data]);
    const { sortedData, SortHeader } = useSortableTable(rows, 'delivery_rate', 'desc');
    if (!rows.length) return <div style={{ padding: 40, textAlign: 'center', color: T.textTer }}>Sin datos de proveedores</div>;
    return (
        <div className="overflow-x-auto">
            <table className="lm-table" style={{ width: '100%' }}>
                <thead><tr>
                    <SortHeader field="name">Proveedor</SortHeader>
                    <SortHeader field="days_operated">Días op.</SortHeader>
                    <SortHeader field="routes">Rutas</SortHeader>
                    <SortHeader field="packages_loaded">Paquetes</SortHeader>
                    <SortHeader field="delivered">Entregados</SortHeader>
                    <SortHeader field="delivery_rate">Entrega%</SortHeader>
                    <SortHeader field="visit_rate">Visita%</SortHeader>
                    <SortHeader field="km_total">Km totales</SortHeader>
                </tr></thead>
                <tbody>
                    {sortedData.map(r => (
                        <tr key={r.name}>
                            <td style={{ fontWeight: 500 }}><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: r.delivery_rate >= 85 ? T.green : r.delivery_rate >= 70 ? T.amber : T.coral, marginRight: 8 }} />{r.name}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.days_operated}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.routes}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.packages_loaded}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.delivered}</td>
                            <td>{ratePill(r.delivery_rate)}</td>
                            <td>{ratePill(r.visit_rate)}</td>
                            <td style={{ fontFamily: "'DM Mono', monospace" }}>{(r.km_total || 0).toLocaleString()}</td>
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
    if (!rows.length) return <div style={{ padding: 40, textAlign: 'center', color: T.textTer }}>Sin datos de drivers</div>;
    return (
        <>
            <div className="overflow-x-auto">
                <table className="lm-table" style={{ width: '100%' }}>
                    <thead><tr>
                        <SortHeader field="name">Driver</SortHeader>
                        <SortHeader field="days_operated">Días op.</SortHeader>
                        <SortHeader field="routes">Rutas</SortHeader>
                        <SortHeader field="packages_loaded">Paquetes</SortHeader>
                        <SortHeader field="delivered">Entregados</SortHeader>
                        <SortHeader field="delivery_rate">SLA individual</SortHeader>
                        <SortHeader field="km_total">Km</SortHeader>
                    </tr></thead>
                    <tbody>
                        {sortedData.map(r => (
                            <tr key={r.name} style={r.delivery_rate < 60 ? { background: T.amberLt } : {}}>
                                <td style={{ fontWeight: 500 }}>{r.name}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.days_operated}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.routes}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.packages_loaded}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{r.delivered}</td>
                                <td>{ratePill(r.delivery_rate)}</td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{(r.km_total || 0).toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.textTer }}>
                Política de strikes: 1° aviso → 2° descanso operativo → 3° baja. Filas con fondo ámbar: SLA individual &lt;60%.
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
    if (!rows.length) return <div style={{ padding: 40, textAlign: 'center', color: T.textTer }}>Sin incidencias en el período</div>;
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
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.textTer }}>
                Incidencias de zona (accesibilidad) NO penalizan el SLA del driver.
            </div>
        </>
    );
};

/* ─── Tab: Attempts ─── */
const AttemptsTab = ({ attempts }) => {
    if (!attempts) return <div style={{ padding: 40, textAlign: 'center', color: T.textTer }}>Cargando...</div>;
    const bars = [
        { label: '1er intento', ...attempts.first_attempt, color: T.green },
        { label: '2do intento', ...attempts.second_attempt, color: T.amber },
        { label: '3er+ intento', ...attempts.third_attempt, color: T.coral },
    ];
    const causes = [
        { label: 'Gestión del driver', key: 'driver_management', color: T.coral },
        { label: 'Cliente ausente', key: 'client_absent', color: T.amber },
        { label: 'Dirección errónea', key: 'wrong_address', color: T.blue },
        { label: 'Zona sin acceso', key: 'zone_no_access', color: T.teal },
    ];
    const maxBar = Math.max(1, ...bars.map(b => b.pct));

    return (
        <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, padding: 24 }}>
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Distribución de intentos</h4>
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
                    <h4 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Causa de reintento (2°+)</h4>
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
            <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.textTer }}>
                Total de paquetes en período: {attempts.total_packages || 0}. Reintentos impactan directamente el costo operativo.
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

    if (!total && !byProvider.length) return <div style={{ padding: 40, textAlign: 'center', color: T.textTer }}>Sin datos de calidad en el período</div>;

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr', gap: 0 }}>
            <div style={{ padding: 24, borderRight: `1px solid ${T.border}` }}>
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
                <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: T.radiusSm, background: T.surface2, fontSize: 12, color: T.textTer }}>
                    Evaluación automática sobre entregas del período. Modelo Claude Vision.
                </div>
            </div>
        </div>
    );
};

/* ─── Tab: SLA ─── */
const SLATab = ({ slaData, canEditBrackets }) => {
    const [brackets, setBrackets] = useState([]);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (slaData?.brackets) setBrackets(slaData.brackets.map(b => ({ ...b })));
    }, [slaData]);

    if (!slaData) return <div style={{ padding: 40, textAlign: 'center', color: T.textTer }}>Cargando SLA...</div>;

    const { consolidated, by_provider, by_driver } = slaData;
    const statusIcon = (s) => s === 'above' ? <CheckCircle2 size={14} color={T.green} /> : <AlertTriangle size={14} color={T.coral} />;
    const bracketStatusLabel = { exceeded: 'Superado', active: 'En curso', pending: 'Pendiente' };
    const bracketStatusColor = { exceeded: T.green, active: T.amber, pending: T.textTer };

    const saveBrackets = async () => {
        setSaving(true);
        try {
            await updateSlaTargets(brackets);
            toast.success('SLA targets actualizados');
        } catch { toast.error('Error al guardar'); }
        setSaving(false);
    };

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
            {/* Left: Consolidated */}
            <div style={{ padding: 24, borderRight: `1px solid ${T.border}` }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>SLA Consolidado ME → Cubbo</h4>
                <div style={{ textAlign: 'center', marginBottom: 20 }}>
                    <div style={{ fontSize: 48, fontWeight: 700, fontFamily: "'DM Sans', sans-serif", color: consolidated.actual >= consolidated.target ? T.green : T.coral }}>
                        {consolidated.actual}%
                    </div>
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
                            <input
                                type="number"
                                value={b.target}
                                onChange={e => {
                                    const updated = [...brackets];
                                    updated[i] = { ...updated[i], target: Number(e.target.value) };
                                    setBrackets(updated);
                                }}
                                onBlur={saveBrackets}
                                style={{ width: 60, padding: '4px 8px', border: `1px solid ${T.border}`, borderRadius: 4, fontSize: 13, fontFamily: "'DM Mono', monospace", textAlign: 'center' }}
                                data-testid={`sla-bracket-input-${i}`}
                            />
                        ) : (
                            <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 13, fontWeight: 600 }}>{b.target}%</span>
                        )}
                        <div style={{ flex: 1, height: 6, borderRadius: 3, background: '#E5E5E0' }}>
                            <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(consolidated.actual / b.target * 100, 100)}%`, background: bracketStatusColor[b.status] || T.textTer }} />
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 500, color: bracketStatusColor[b.status] || T.textTer, whiteSpace: 'nowrap' }}>
                            {bracketStatusLabel[b.status] || b.status}
                        </span>
                    </div>
                ))}
            </div>

            {/* Right: By provider + driver */}
            <div style={{ padding: 24 }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Por proveedor</h4>
                <table className="lm-table" style={{ width: '100%', marginBottom: 24 }}>
                    <thead><tr><th>Proveedor</th><th>SLA actual</th><th>Target</th><th>Brecha</th><th></th></tr></thead>
                    <tbody>
                        {by_provider?.map(p => (
                            <tr key={p.provider_name} style={p.status === 'below' ? { background: T.coralLt } : {}}>
                                <td style={{ fontWeight: 500 }}>{p.provider_name}</td>
                                <td>{ratePill(p.sla_actual)}</td>
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
                                <td>{ratePill(d.sla_actual)}</td>
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


/* ═════════════════════════════════════════════════════════════════ */
/*                        REPORTS PAGE                              */
/* ═════════════════════════════════════════════════════════════════ */

const Reports = () => {
    const { user, canEdit } = useAuth();
    const canEditBrackets = ['coordinator', 'developer'].includes(user?.role);

    // Global state
    const [period, setPeriod] = useState('current_month');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [clientId, setClientId] = useState('');
    const [providerId, setProviderId] = useState('');
    const [sections, setSections] = useState(['providers', 'drivers', 'incidents', 'quality']);

    // Data
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [reportData, setReportData] = useState(null);
    const [qualityData, setQualityData] = useState(null);
    const [attemptsData, setAttemptsData] = useState(null);
    const [slaData, setSlaData] = useState(null);
    const [aiNarrative, setAiNarrative] = useState(null);
    const [aiPeriod, setAiPeriod] = useState('');

    // UI state
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [activeTab, setActiveTab] = useState('providers');
    const [showAI, setShowAI] = useState(false);

    const effectiveDates = useMemo(() => {
        if (period === 'custom' && dateFrom && dateTo) return { from: dateFrom, to: dateTo };
        return getDateRange(period);
    }, [period, dateFrom, dateTo]);

    // Load clients/providers once
    useEffect(() => {
        Promise.all([getClients(), getProviders()]).then(([c, p]) => {
            setClients(c.data || []);
            setProviders(p.data || []);
        }).catch(() => {});
    }, []);

    // Fetch report data when filters change
    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const params = { date_from: effectiveDates.from, date_to: effectiveDates.to };
            if (clientId) params.client_id = clientId;
            if (providerId) params.provider_id = providerId;

            const promises = [
                generateReport({ ...params, sections }),
            ];
            if (sections.includes('quality')) promises.push(getQualityReport(params).catch(() => ({ data: null })));
            else promises.push(Promise.resolve({ data: null }));

            if (sections.includes('attempts')) promises.push(getReportAttempts(params).catch(() => ({ data: null })));
            else promises.push(Promise.resolve({ data: null }));

            if (sections.includes('sla')) promises.push(getReportSla(params).catch(() => ({ data: null })));
            else promises.push(Promise.resolve({ data: null }));

            const [report, quality, attempts, sla] = await Promise.all(promises);
            setReportData(report.data);
            setQualityData(quality.data);
            setAttemptsData(attempts.data);
            setSlaData(sla.data);
        } catch (e) {
            toast.error('Error al cargar datos');
        } finally {
            setLoading(false);
        }
    }, [effectiveDates, clientId, providerId, sections]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleGenerateAI = async () => {
        if (showAI && aiNarrative) { setShowAI(false); return; }
        setGenerating(true);
        setShowAI(true);
        try {
            const res = await generateAiReport({
                period, date_from: effectiveDates.from, date_to: effectiveDates.to,
                client_id: clientId || undefined, provider_id: providerId || undefined, sections,
            });
            setAiNarrative(res.data.narrative);
            setAiPeriod(res.data.period);
        } catch {
            setAiNarrative('Error al generar el reporte con IA.');
        } finally {
            setGenerating(false);
        }
    };

    const handleExport = async () => {
        setExporting(true);
        try {
            const res = await generateReportExcel({
                date_from: effectiveDates.from,
                date_to: effectiveDates.to,
                sections,
                client_id: clientId || undefined,
                provider_id: providerId || undefined,
            });
            downloadFile(res.data, `reporte_${effectiveDates.from}_${effectiveDates.to}.xlsx`);
            toast.success('Reporte exportado');
        } catch { toast.error('Error al exportar'); }
        setExporting(false);
    };

    const toggleSection = (id) => setSections(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);

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
                .lm-dashboard { font-family: 'DM Sans', sans-serif; display: flex; flex-direction: column; gap: 20px; }
                :root { --bg: #F5F4F1; --surface: #FFFFFF; --surface-2: #F0EFEC; --border: #E2E0DB; --text-primary: #1A1916; --text-secondary: #6B6960; --text-tertiary: #9C9A92; }
                .lm-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
                .lm-table { border-collapse: collapse; font-size: 13px; }
                .lm-table thead th { padding: 10px 14px; text-align: left; font-weight: 500; font-size: 12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--border); background: var(--surface-2); cursor: pointer; white-space: nowrap; }
                .lm-table tbody td { padding: 10px 14px; border-bottom: 1px solid var(--border); color: var(--text-primary); }
                .lm-table tbody tr:hover { background: var(--surface-2); }
                .lm-select { font-size: 13px; padding: 6px 28px 6px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B6960' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") no-repeat right 8px center; appearance: none; color: var(--text-primary); font-family: 'DM Sans', sans-serif; outline: none; }
                .lm-select:focus { border-color: #2563EB; box-shadow: 0 0 0 2px rgba(37,99,235,0.12); }
            `}</style>

            {/* ─── TOPBAR ─── */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 600, color: T.textPri, margin: 0 }}>Reportes</h1>
                    <p style={{ fontSize: 13, color: T.textTer, marginTop: 2 }}>{effectiveDates.from} — {effectiveDates.to}</p>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={handleExport} disabled={exporting || loading} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, background: T.surface, fontSize: 13, cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", color: T.textPri }} data-testid="export-excel-btn">
                        {exporting ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                        Descargar Excel
                    </button>
                    <button onClick={handleGenerateAI} disabled={generating || loading} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', border: 'none', borderRadius: T.radiusSm, background: T.textPri, color: '#fff', fontSize: 13, cursor: 'pointer', fontFamily: "'DM Sans', sans-serif" }} data-testid="generate-ai-btn">
                        {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                        Generar IA
                    </button>
                </div>
            </div>

            {/* ─── ROW 1: Period + Sections ─── */}
            <div style={{ display: 'flex', gap: 20 }}>
                {/* Period card */}
                <div className="lm-card" style={{ width: 320, flexShrink: 0, padding: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Período</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 12 }}>
                        {PERIODS.map(p => (
                            <button key={p.value} onClick={() => setPeriod(p.value)} data-testid={`period-${p.value}`}
                                style={{ padding: '7px 6px', fontSize: 12, borderRadius: T.radiusSm, border: `1px solid ${period === p.value ? T.textPri : T.border}`, background: period === p.value ? T.textPri : T.surface, color: period === p.value ? '#fff' : T.textPri, cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", transition: 'all 0.15s' }}>
                                {p.label}
                            </button>
                        ))}
                    </div>
                    {period === 'custom' && (
                        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ flex: 1, padding: '6px 8px', border: `1px solid ${T.border}`, borderRadius: 4, fontSize: 13 }} data-testid="custom-date-from" />
                            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ flex: 1, padding: '6px 8px', border: `1px solid ${T.border}`, borderRadius: 4, fontSize: 13 }} data-testid="custom-date-to" />
                        </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        <select className="lm-select" style={{ width: '100%' }} value={clientId} onChange={e => setClientId(e.target.value)} data-testid="report-client-filter">
                            <option value="">Todos los clientes</option>
                            {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                        <select className="lm-select" style={{ width: '100%' }} value={providerId} onChange={e => setProviderId(e.target.value)} data-testid="report-provider-filter">
                            <option value="">Todos los proveedores</option>
                            {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                    </div>
                </div>

                {/* Sections card */}
                <div className="lm-card" style={{ flex: 1, padding: 20 }}>
                    <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Secciones del reporte</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                        {SECTIONS.map(s => {
                            const active = sections.includes(s.id);
                            const Icon = s.icon;
                            return (
                                <div key={s.id} onClick={() => toggleSection(s.id)} data-testid={`section-${s.id}`}
                                    style={{ padding: '12px 14px', borderRadius: T.radiusSm, border: `1.5px solid ${active ? T.textPri : T.border}`, background: active ? '#F8F8F6' : T.surface, cursor: 'pointer', transition: 'all 0.15s', position: 'relative' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <div style={{ width: 16, height: 16, borderRadius: 3, border: `2px solid ${active ? T.textPri : T.borderStrong}`, background: active ? T.textPri : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                            {active && <CheckCircle2 size={10} color="#fff" />}
                                        </div>
                                        <Icon size={15} color={T.textSec} />
                                        <span style={{ fontSize: 13, fontWeight: 500, color: T.textPri }}>{s.title}</span>
                                    </div>
                                    <p style={{ fontSize: 11, color: T.textTer, margin: 0, paddingLeft: 24 }}>{s.desc}</p>
                                    {s.isNew && (
                                        <span style={{ position: 'absolute', top: 8, right: 8, fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 3, background: T.tealLt, color: T.teal }}>Nuevo</span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* ─── AI OUTPUT (collapsible) ─── */}
            {showAI && (
                <div className="lm-card" style={{ padding: 20, borderLeft: `3px solid ${T.textPri}` }} data-testid="ai-output">
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Sparkles size={16} color={T.textPri} />
                            <span style={{ fontSize: 14, fontWeight: 600, color: T.textPri }}>Análisis generado por IA</span>
                        </div>
                        <button onClick={() => setShowAI(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textTer, padding: 4 }}>
                            <ChevronUp size={16} />
                        </button>
                    </div>
                    {aiPeriod && <p style={{ fontSize: 12, color: T.textTer, marginBottom: 12 }}>{aiPeriod}</p>}
                    {generating ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: T.textSec, fontSize: 13 }}>
                            <Loader2 size={16} className="animate-spin" />Generando análisis...
                        </div>
                    ) : (
                        <div style={{ fontSize: 13, lineHeight: 1.7, color: T.textPri }}
                            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize((aiNarrative || '').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>')) }} />
                    )}
                </div>
            )}

            {/* ─── KPI STRIP ─── */}
            <KPIStrip reportData={reportData} slaData={slaData} qualityData={qualityData} />

            {/* ─── TABS ─── */}
            <div className="lm-card">
                {/* Tab bar */}
                <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}`, background: T.surface2, overflow: 'auto' }}>
                    {TABS.filter(t => sections.includes(t.id)).map(t => {
                        const Icon = t.icon;
                        const isActive = activeTab === t.id;
                        return (
                            <button key={t.id} onClick={() => setActiveTab(t.id)} data-testid={`tab-${t.id}`}
                                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '12px 20px', fontSize: 13, fontWeight: isActive ? 600 : 400, color: isActive ? T.textPri : T.textSec, background: isActive ? T.surface : 'transparent', border: 'none', borderBottom: isActive ? `2px solid ${T.textPri}` : '2px solid transparent', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", whiteSpace: 'nowrap', transition: 'all 0.15s' }}>
                                <Icon size={14} />
                                {t.label}
                                {t.isNew && <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 3, background: T.tealLt, color: T.teal }}>Nuevo</span>}
                            </button>
                        );
                    })}
                </div>
                {/* Tab content */}
                <div style={{ minHeight: 200 }}>
                    {loading ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60, gap: 8, color: T.textSec, fontSize: 14 }}>
                            <Loader2 size={20} className="animate-spin" />Cargando datos...
                        </div>
                    ) : (
                        <>
                            {activeTab === 'providers' && <ProvidersTab data={reportData} />}
                            {activeTab === 'drivers' && <DriversTab data={reportData} />}
                            {activeTab === 'incidents' && <IncidentsTab data={reportData} />}
                            {activeTab === 'attempts' && <AttemptsTab attempts={attemptsData} />}
                            {activeTab === 'quality' && <QualityTab data={{ quality_report: qualityData }} />}
                            {activeTab === 'sla' && <SLATab slaData={slaData} canEditBrackets={canEditBrackets} />}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Reports;
