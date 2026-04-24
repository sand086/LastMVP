import React, { useState, useEffect, useMemo } from 'react';
import { getReportKpis } from '../../lib/api';
import { T } from './ReportsHelpers';
import {
    ResponsiveContainer, ComposedChart, Line, Bar, Area, XAxis, YAxis,
    CartesianGrid, Tooltip as RechartsTooltip, Legend, LineChart,
} from 'recharts';
import { Loader2, TrendingUp, TrendingDown, Minus, Calendar } from 'lucide-react';

const fmtLabel = (key, groupBy) => {
    if (!key) return '—';
    if (groupBy === 'month') return key;
    if (groupBy === 'week') return key;
    // day: YYYY-MM-DD → DD MMM
    try {
        const d = new Date(key + 'T12:00:00');
        if (!isNaN(d.getTime())) return d.toLocaleDateString('es-MX', { day: '2-digit', month: 'short' });
    } catch { /* ignore */ }
    return key;
};

const TrendChip = ({ value, inverted = false }) => {
    if (value === null || value === undefined || isNaN(value)) {
        return <span style={{ color: T.textTer, fontSize: 12 }}><Minus size={12} style={{ display: 'inline', marginRight: 3 }} />—</span>;
    }
    const positive = inverted ? value < 0 : value > 0;
    const neutral = value === 0;
    const color = neutral ? T.textTer : (positive ? T.green : T.coral);
    const Icon = neutral ? Minus : (value > 0 ? TrendingUp : TrendingDown);
    const sign = value > 0 ? '+' : '';
    return (
        <span style={{ color, fontSize: 12, fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
            <Icon size={13} /> {sign}{Math.abs(value).toFixed(1)}pp
        </span>
    );
};

const MiniKpi = ({ label, value, suffix = '', trend }) => (
    <div style={{ padding: '12px 16px', background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radiusSm, minWidth: 140 }}>
        <div style={{ fontSize: 11, color: T.textTer, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>{label}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 22, fontWeight: 700, color: T.textPri, fontFamily: "'DM Sans', sans-serif" }}>
                {value}{suffix}
            </span>
            {trend !== undefined && <TrendChip value={trend} />}
        </div>
    </div>
);

const TrendsTab = ({ dateFrom, dateTo }) => {
    const [loading, setLoading] = useState(true);
    const [groupBy, setGroupBy] = useState('day');
    const [data, setData] = useState([]);
    const [summary, setSummary] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!dateFrom || !dateTo) return;
        let active = true;
        setLoading(true);
        setError(null);
        getReportKpis({ date_from: dateFrom, date_to: dateTo, group_by: groupBy })
            .then(res => {
                if (!active) return;
                setData(res.data?.data || []);
                setSummary(res.data?.summary || null);
            })
            .catch(err => {
                if (!active) return;
                setError(err.response?.data?.detail || 'Error al cargar tendencias');
            })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [dateFrom, dateTo, groupBy]);

    const chartData = useMemo(() =>
        data.map(d => ({
            ...d,
            label: fmtLabel(d.group, groupBy),
            delivered_rate: parseFloat(d.delivery_rate) || 0,
            pending: Math.max(0, (d.packages_total || 0) - (d.packages_delivered || 0) - (d.packages_failed || 0)),
        })), [data, groupBy]);

    // Trend = last point vs first point of delivery_rate
    const rateTrend = useMemo(() => {
        if (chartData.length < 2) return null;
        const first = chartData[0].delivered_rate;
        const last = chartData[chartData.length - 1].delivered_rate;
        return last - first;
    }, [chartData]);

    const hasData = !loading && chartData.length > 0;

    return (
        <div style={{ padding: 20 }}>
            {/* Header controls */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
                <div>
                    <h3 style={{ fontSize: 15, fontWeight: 600, color: T.textPri, marginBottom: 2 }}>
                        Tendencias históricas
                    </h3>
                    <p style={{ fontSize: 12, color: T.textTer, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <Calendar size={12} /> {dateFrom} → {dateTo}
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 4, background: T.surface2, padding: 4, borderRadius: T.radiusSm }}>
                    {[
                        { id: 'day', label: 'Día' },
                        { id: 'week', label: 'Semana' },
                        { id: 'month', label: 'Mes' },
                    ].map(opt => (
                        <button
                            key={opt.id}
                            onClick={() => setGroupBy(opt.id)}
                            data-testid={`trends-groupby-${opt.id}`}
                            style={{
                                padding: '6px 14px', fontSize: 12, fontWeight: 500,
                                borderRadius: 4, border: 'none', cursor: 'pointer',
                                background: groupBy === opt.id ? T.surface : 'transparent',
                                color: groupBy === opt.id ? T.textPri : T.textSec,
                                boxShadow: groupBy === opt.id ? '0 1px 2px rgba(0,0,0,0.06)' : 'none',
                                transition: 'all 0.15s',
                            }}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </div>

            {loading && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60, gap: 8, color: T.textSec, fontSize: 14 }}>
                    <Loader2 size={20} className="animate-spin" /> Cargando tendencias...
                </div>
            )}

            {error && !loading && (
                <div style={{ padding: 20, background: T.coralLt, color: T.coral, borderRadius: T.radiusSm, fontSize: 13 }}>
                    {error}
                </div>
            )}

            {!loading && !error && !hasData && (
                <div style={{ padding: 60, textAlign: 'center', color: T.textTer }}>
                    <TrendingUp size={32} style={{ margin: '0 auto 8px', opacity: 0.3 }} />
                    <p style={{ fontSize: 14 }}>Sin datos históricos en el periodo seleccionado.</p>
                    <p style={{ fontSize: 12, marginTop: 4 }}>Amplia el rango para ver tendencias.</p>
                </div>
            )}

            {hasData && summary && (
                <>
                    {/* Summary KPIs */}
                    <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                        <MiniKpi label="Rutas totales" value={summary.total_journeys} />
                        <MiniKpi label="Paquetes totales" value={summary.total_packages} />
                        <MiniKpi label="Entregados" value={summary.total_delivered} />
                        <MiniKpi label="Delivery rate promedio" value={Number(summary.delivery_rate).toFixed(1)} suffix="%" trend={rateTrend} />
                    </div>

                    {/* Delivery rate line chart */}
                    <div style={{ background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radiusSm, padding: 16, marginBottom: 16 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: T.textPri, marginBottom: 12 }}>
                            Tasa de entrega a lo largo del tiempo
                        </div>
                        <ResponsiveContainer width="100%" height={260}>
                            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                <CartesianGrid stroke={T.borderSolid} strokeDasharray="2 4" vertical={false} />
                                <XAxis dataKey="label" stroke={T.textTer} tick={{ fontSize: 11 }} />
                                <YAxis stroke={T.textTer} tick={{ fontSize: 11 }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                                <RechartsTooltip
                                    formatter={(v) => [`${Number(v).toFixed(1)}%`, 'Delivery rate']}
                                    contentStyle={{ background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: 4, fontSize: 12 }}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="delivered_rate"
                                    name="Delivery rate"
                                    stroke={T.teal}
                                    strokeWidth={2.5}
                                    dot={{ r: 3, fill: T.teal }}
                                    activeDot={{ r: 5 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Volume composed chart (bars = packages, line = rate) */}
                    <div style={{ background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: T.radiusSm, padding: 16 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: T.textPri, marginBottom: 12 }}>
                            Volumen de paquetes por período
                        </div>
                        <ResponsiveContainer width="100%" height={280}>
                            <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                <CartesianGrid stroke={T.borderSolid} strokeDasharray="2 4" vertical={false} />
                                <XAxis dataKey="label" stroke={T.textTer} tick={{ fontSize: 11 }} />
                                <YAxis yAxisId="left" stroke={T.textTer} tick={{ fontSize: 11 }} />
                                <YAxis yAxisId="right" orientation="right" stroke={T.textTer} tick={{ fontSize: 11 }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                                <RechartsTooltip contentStyle={{ background: T.surface, border: `1px solid ${T.borderSolid}`, borderRadius: 4, fontSize: 12 }} />
                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                <Bar yAxisId="left" dataKey="packages_delivered" name="Entregados" stackId="a" fill={T.green} />
                                <Bar yAxisId="left" dataKey="packages_failed" name="Fallidos" stackId="a" fill={T.coral} />
                                <Bar yAxisId="left" dataKey="pending" name="Pendientes" stackId="a" fill={T.amber} />
                                <Line yAxisId="right" type="monotone" dataKey="delivered_rate" name="Delivery rate %" stroke={T.purple} strokeWidth={2} dot={{ r: 2 }} />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>
                </>
            )}
        </div>
    );
};

export default TrendsTab;
