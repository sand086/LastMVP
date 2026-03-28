import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import TokenUsageTab from '../components/admin/TokenUsageTab';
import RoutesReportTab from '../components/admin/RoutesReportTab';
import CostConfigTab from '../components/admin/CostConfigTab';
import api from '../lib/api';
import { toast } from 'sonner';
import { Cpu, FileSpreadsheet, Settings2, AlertTriangle } from 'lucide-react';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF', green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB', coral: '#DC2626', coralLt: '#FEF2F2',
    teal: '#0D9488', tealLt: '#F0FDFA', purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

const TABS = [
    { key: 'tokens', label: 'Consumo de tokens', icon: Cpu },
    { key: 'routes', label: 'Reporte de rutas', sub: 'Cubbo ADM', icon: FileSpreadsheet },
    { key: 'config', label: 'Configuración de costos', icon: Settings2 },
];

export default function AdminPage() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const canEdit = user?.role === 'developer';

    const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'tokens');
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);

    const [period, setPeriod] = useState('current_month');
    const [clientId, setClientId] = useState('');

    useEffect(() => {
        if (user && !['developer', 'ejecutivo', 'executive', 'coordinator'].includes(user.role)) {
            toast.error('Sin permisos para acceder al módulo admin');
            navigate('/dashboard');
        }
    }, [user, navigate]);

    const fetchSummary = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get('/admin/summary', { params: { period, client_id: clientId || undefined } });
            setSummary(res.data);
        } catch {
            toast.error('Error al cargar resumen admin');
        } finally {
            setLoading(false);
        }
    }, [period, clientId]);

    useEffect(() => { fetchSummary(); }, [fetchSummary]);

    const switchTab = (key) => {
        setActiveTab(key);
        setSearchParams({ tab: key });
    };

    const fmtNum = (n) => {
        if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
        if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
        return n?.toLocaleString('es-MX') || '0';
    };

    const s = summary || { totals: {}, by_entregable: {}, evaluaciones_count: 0, lumi_count: 0, reportes_count: 0 };
    const t = s.totals || {};

    return (
        <div style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }} data-testid="admin-page">
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                    <div>
                        <h1 style={{ fontSize: 22, fontWeight: 700, color: T.textPri, fontFamily: "'DM Sans'" }}>Consumo IA & Administración</h1>
                        <p style={{ fontSize: 13, color: T.textTer, marginTop: 2 }}>
                            {period === 'current_month' ? 'Marzo 2026' : period === 'prev_month' ? 'Febrero 2026' : 'Personalizado'} · Cubbo
                        </p>
                    </div>
                </div>

                {/* KPI Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 20 }} data-testid="admin-kpi-cards">
                    {/* Total tokens */}
                    <div style={{ padding: '16px 18px', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface }}>
                        <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Total tokens / mes</p>
                        <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.textPri }}>{fmtNum(t.tokens_total || 0)}</span>
                        {(t.tokens_total || 0) > 0 && (
                            <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 10, border: `1px solid ${T.border}` }}>
                                <div style={{ width: `${t.input_pct}%`, background: T.blue }} title={`Input ${t.input_pct}%`} />
                                <div style={{ width: `${t.output_pct}%`, background: T.green }} title={`Output ${t.output_pct}%`} />
                                <div style={{ width: `${t.prompt_pct}%`, background: T.amber }} title={`Prompt ${t.prompt_pct}%`} />
                            </div>
                        )}
                        <div style={{ display: 'flex', gap: 8, marginTop: 6, fontSize: 10, color: T.textTer }}>
                            <span><span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: 2, background: T.blue, marginRight: 3 }} />Input {t.input_pct || 0}%</span>
                            <span><span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: 2, background: T.green, marginRight: 3 }} />Output {t.output_pct || 0}%</span>
                            <span><span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: 2, background: T.amber, marginRight: 3 }} />Prompt {t.prompt_pct || 0}%</span>
                        </div>
                    </div>
                    {/* Cost USD */}
                    <div style={{ padding: '16px 18px', border: `1px solid ${s.over_budget ? T.coral + '60' : T.border}`, borderRadius: T.radius, background: s.over_budget ? T.coralLt : T.surface }}>
                        <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Costo USD / mes</p>
                        <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: s.over_budget ? T.coral : T.textPri }}>${t.cost_usd || '0.00'}</span>
                        <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>USD · ≈ ${t.cost_mxn || 0} MXN</p>
                        {s.over_budget && <p style={{ fontSize: 10, color: T.coral, marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}><AlertTriangle size={10} /> Excede umbral ${s.budget_threshold}</p>}
                    </div>
                    {/* Evaluaciones */}
                    <div style={{ padding: '16px 18px', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface }}>
                        <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Evaluaciones IA</p>
                        <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.blue }}>{fmtNum(s.evaluaciones_count)}</span>
                        <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>entregas evaluadas este mes</p>
                    </div>
                    {/* Lumi */}
                    <div style={{ padding: '16px 18px', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface }}>
                        <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Consultas Lumi</p>
                        <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.purple }}>{fmtNum(s.lumi_count)}</span>
                        <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>mensajes procesados</p>
                    </div>
                    {/* Reportes */}
                    <div style={{ padding: '16px 18px', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface }}>
                        <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Reportes IA</p>
                        <span style={{ fontSize: 26, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.teal }}>{fmtNum(s.reportes_count)}</span>
                        <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>generados este mes</p>
                    </div>
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: 0, borderBottom: `1px solid ${T.border}`, marginBottom: 20 }}>
                    {TABS.map(tab => {
                        const active = activeTab === tab.key;
                        const Icon = tab.icon;
                        return (
                            <button key={tab.key} onClick={() => switchTab(tab.key)} style={{
                                display: 'flex', alignItems: 'center', gap: 6, padding: '10px 20px',
                                border: 'none', borderBottom: `2px solid ${active ? T.textPri : 'transparent'}`,
                                background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: active ? 600 : 400,
                                color: active ? T.textPri : T.textSec, fontFamily: "'DM Sans'", transition: 'all 0.15s',
                            }} data-testid={`admin-tab-${tab.key}`}>
                                <Icon size={15} />
                                {tab.label}
                                {tab.sub && <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 3, background: T.tealLt, color: T.teal, fontWeight: 600, marginLeft: 4 }}>{tab.sub}</span>}
                            </button>
                        );
                    })}
                </div>

                {/* Tab Content */}
                {activeTab === 'tokens' && <TokenUsageTab summary={s} period={period} setPeriod={setPeriod} clientId={clientId} setClientId={setClientId} />}
                {activeTab === 'routes' && <RoutesReportTab canEdit={canEdit} />}
                {activeTab === 'config' && <CostConfigTab canEdit={canEdit} summary={s} onRefresh={fetchSummary} />}
            </div>
    );
}
