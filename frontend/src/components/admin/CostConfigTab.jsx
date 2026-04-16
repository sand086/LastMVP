import React, { useState, useEffect, useCallback } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Save, RefreshCw, Loader2, Info, AlertTriangle, DollarSign, Package, Plus, Trash2 } from 'lucide-react';
import PulseConfigSection from './PulseConfigSection';

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

export default function CostConfigTab({ canEdit, summary, onRefresh }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);

    // Local state for editable fields
    const [tcRate, setTcRate] = useState(19);
    const [autoUpdate, setAutoUpdate] = useState(false);
    const [models, setModels] = useState([]);
    const [threshold, setThreshold] = useState(50);
    const [alertEnabled, setAlertEnabled] = useState(true);
    const [weeklyEnabled, setWeeklyEnabled] = useState(false);
    const [weeklyEmail, setWeeklyEmail] = useState('');
    const [defaultSla, setDefaultSla] = useState(40);
    const [providerSlas, setProviderSlas] = useState({});
    const [providers, setProviders] = useState([]);
    const [newSlaProviderId, setNewSlaProviderId] = useState('');
    const [pulseConfig, setPulseConfig] = useState({});

    const fetchConfig = useCallback(async () => {
        setLoading(true);
        try {
            const [configRes, provRes] = await Promise.allSettled([
                api.get('/admin/config'),
                api.get('/providers'),
            ]);
            if (configRes.status === 'fulfilled') {
                const cfg = configRes.value.data;
                setConfig(cfg);
                setTcRate(cfg.exchange_rate?.rate || 19);
                setAutoUpdate(cfg.exchange_rate?.auto_update || false);
                setModels(cfg.ia_cost_config?.models || []);
                setThreshold(cfg.budget_alerts?.monthly_threshold_usd || 50);
                setAlertEnabled(cfg.budget_alerts?.alert_enabled ?? true);
                setWeeklyEnabled(cfg.budget_alerts?.weekly_report_enabled || false);
                setWeeklyEmail(cfg.budget_alerts?.weekly_report_email || '');
                setDefaultSla(cfg.sla_config?.default_sla || 40);
                setProviderSlas(cfg.sla_config?.by_provider || {});
                setPulseConfig(cfg.pulse_config || {});
            }
            if (provRes.status === 'fulfilled') {
                const pData = provRes.value.data;
                setProviders(Array.isArray(pData) ? pData : pData.providers || []);
            }
        } catch (err) { console.error("Admin component error:", err);
            toast.error('Error al cargar configuración');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchConfig(); }, [fetchConfig]);

    const handleSave = async (section, value) => {
        setSaving(true);
        try {
            await api.patch('/admin/config', { section, value });
            toast.success(`Configuración de ${section} guardada`);
            setDirty(false);
            fetchConfig();
            if (onRefresh) onRefresh();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    const saveAll = async () => {
        setSaving(true);
        try {
            await api.patch('/admin/config', { section: 'exchange_rate', value: { rate: tcRate, source: 'manual', auto_update: autoUpdate, last_updated: new Date().toISOString(), history: config?.exchange_rate?.history || [] } });
            await api.patch('/admin/config', { section: 'ia_cost_config', value: { models } });
            await api.patch('/admin/config', { section: 'budget_alerts', value: { monthly_threshold_usd: threshold, alert_enabled: alertEnabled, weekly_report_enabled: weeklyEnabled, weekly_report_email: weeklyEmail } });
            await api.patch('/admin/config', { section: 'sla_config', value: { default_sla: defaultSla, by_provider: providerSlas } });
            await api.patch('/admin/config', { section: 'pulse_config', value: pulseConfig });
            toast.success('Toda la configuración guardada');
            setDirty(false);
            fetchConfig();
            if (onRefresh) onRefresh();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    const updateModelField = (idx, field, val) => {
        setModels(prev => {
            const next = [...prev];
            next[idx] = { ...next[idx], [field]: val };
            return next;
        });
        setDirty(true);
    };

    // Cost preview calculation
    const evalData = React.useMemo(() => (summary?.by_entregable || {}).evaluacion || {}, [summary]);
    const previewModels = React.useMemo(() => {
        const avgTokens = evalData.avg_per_unit || {};
        const count = evalData.count || 0;
        return models.filter(m => m.active).map(m => {
            const avgIn = avgTokens.input || 1400;
            const avgOut = avgTokens.output || 600;
            const costPerEval = ((avgIn * (m.input_per_million || 0)) + (avgOut * (m.output_per_million || 0))) / 1_000_000;
            const totalMonthly = costPerEval * (count || 1842);
            return { name: m.name, costPerEval: costPerEval.toFixed(4), totalMonthly: totalMonthly.toFixed(2), totalMxn: (totalMonthly * tcRate).toFixed(2) };
        });
    }, [models, evalData, tcRate]);

    if (loading) return <div style={{ padding: 60, textAlign: 'center', color: T.textTer }}>Cargando configuración...</div>;

    return (
        <div data-testid="cost-config-tab">
            {/* Info banner */}
            <div style={{ padding: '10px 16px', borderRadius: T.radiusSm, background: T.amberLt, border: `1px solid ${T.amber}30`, marginBottom: 20, fontSize: 12, color: T.textSec, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Info size={14} color={T.amber} />
                Los cambios afectan el cálculo de costos en el tab de Consumo y en los reportes exportados. Guardar después de modificar.
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                {/* LEFT: Exchange Rate + Cost per Model */}
                <div>
                    {/* TC Section */}
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: 20, marginBottom: 16 }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 4 }}>Tipo de cambio USD → MXN</h3>
                        <p style={{ fontSize: 11, color: T.textTer, marginBottom: 16 }}>Se aplica a todos los cálculos de costo MXN</p>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                            <span style={{ fontSize: 16, fontWeight: 700, color: T.textPri }}>$</span>
                            <input
                                type="number" step="0.01" value={tcRate}
                                onChange={e => { setTcRate(Number(e.target.value)); setDirty(true); }}
                                disabled={!canEdit}
                                style={{ width: 100, padding: '8px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", textAlign: 'center' }}
                                data-testid="tc-input"
                            />
                            <span style={{ fontSize: 13, color: T.textSec }}>MXN/USD</span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: T.textSec, cursor: canEdit ? 'pointer' : 'default' }}>
                                <input type="checkbox" checked={autoUpdate} onChange={e => { setAutoUpdate(e.target.checked); setDirty(true); }} disabled={!canEdit} style={{ width: 14, height: 14 }} />
                                Actualización automática (Banxico API)
                            </label>
                        </div>

                        <div style={{ fontSize: 11, color: T.textTer, marginBottom: 8 }}>
                            Última actualización: {config?.exchange_rate?.last_updated ? new Date(config.exchange_rate.last_updated).toLocaleString('es-MX', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                        </div>

                        {/* TC History */}
                        <div style={{ marginTop: 12 }}>
                            <p style={{ fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 6 }}>Historial reciente</p>
                            <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
                                <thead><tr style={{ borderBottom: `1px solid ${T.border}` }}><th style={{ textAlign: 'left', padding: '4px 0', color: T.textTer }}>Fecha</th><th style={{ textAlign: 'right', padding: '4px 0', color: T.textTer }}>TC MXN/USD</th></tr></thead>
                                <tbody>
                                    {(config?.exchange_rate?.history || []).slice(0, 5).map((h, i) => (
                                        <tr key={`rate-${h.date}`} style={{ borderBottom: `1px solid ${T.border}` }}>
                                            <td style={{ padding: '4px 0' }}>{h.date}</td>
                                            <td style={{ padding: '4px 0', textAlign: 'right', fontFamily: "'DM Mono',monospace", fontWeight: 600 }}>${h.rate}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Model Costs */}
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: 20 }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Costo por token según modelo IA</h3>
                        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                    <th style={{ textAlign: 'left', padding: '6px 0', fontSize: 10, color: T.textTer, fontWeight: 600, textTransform: 'uppercase' }}>Modelo</th>
                                    <th style={{ textAlign: 'center', padding: '6px 0', fontSize: 10, color: T.textTer, fontWeight: 600, textTransform: 'uppercase' }}>Input ($/1M tok)</th>
                                    <th style={{ textAlign: 'center', padding: '6px 0', fontSize: 10, color: T.textTer, fontWeight: 600, textTransform: 'uppercase' }}>Output ($/1M tok)</th>
                                    <th style={{ textAlign: 'center', padding: '6px 0', fontSize: 10, color: T.textTer, fontWeight: 600, textTransform: 'uppercase' }}>Activo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {models.map((m, i) => (
                                    <tr key={m.name} style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <td style={{ padding: '8px 0', fontFamily: "'DM Mono',monospace", fontWeight: 500, fontSize: 11 }}>{m.name}</td>
                                        <td style={{ padding: '8px 0', textAlign: 'center' }}>
                                            <input type="number" step="0.01" value={m.input_per_million}
                                                onChange={e => updateModelField(i, 'input_per_million', Number(e.target.value))}
                                                disabled={!canEdit}
                                                style={{ width: 80, padding: '4px 6px', borderRadius: 4, border: `1px solid ${T.border}`, fontSize: 12, textAlign: 'center', fontFamily: "'DM Mono'" }}
                                            />
                                        </td>
                                        <td style={{ padding: '8px 0', textAlign: 'center' }}>
                                            <input type="number" step="0.01" value={m.output_per_million}
                                                onChange={e => updateModelField(i, 'output_per_million', Number(e.target.value))}
                                                disabled={!canEdit}
                                                style={{ width: 80, padding: '4px 6px', borderRadius: 4, border: `1px solid ${T.border}`, fontSize: 12, textAlign: 'center', fontFamily: "'DM Mono'" }}
                                            />
                                        </td>
                                        <td style={{ padding: '8px 0', textAlign: 'center' }}>
                                            <input type="checkbox" checked={m.active}
                                                onChange={e => updateModelField(i, 'active', e.target.checked)}
                                                disabled={!canEdit}
                                                style={{ width: 15, height: 15 }}
                                            />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* RIGHT: Preview + Budget + Reference */}
                <div>
                    {/* Cost Preview */}
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: 20, marginBottom: 16 }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Vista previa: costo por entrega promedio</h3>
                        {previewModels.map(pm => (
                            <div key={pm.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: `1px solid ${T.border}` }}>
                                <span style={{ fontFamily: "'DM Mono',monospace", fontSize: 12, fontWeight: 500 }}>{pm.name}</span>
                                <div style={{ textAlign: 'right' }}>
                                    <span style={{ fontSize: 14, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.green }}>${pm.costPerEval} USD</span>
                                    <p style={{ fontSize: 10, color: T.textTer }}>≈ ${(Number(pm.costPerEval) * tcRate).toFixed(2)} MXN</p>
                                </div>
                            </div>
                        ))}
                        <div style={{ marginTop: 12, padding: '12px 14px', borderRadius: T.radiusSm, background: T.surface2 }}>
                            <p style={{ fontSize: 11, color: T.textSec }}><strong>{fmtNum(evalCount || 1842)}</strong> entregas/mes</p>
                            <p style={{ fontSize: 16, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.textPri, marginTop: 4 }}>
                                ${summary?.totals?.cost_usd || '34.82'} USD
                            </p>
                            <p style={{ fontSize: 12, color: T.textTer }}>≈ ${summary?.totals?.cost_mxn || '661'} MXN / mes</p>
                        </div>
                    </div>

                    {/* Token Reference */}
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: 20, marginBottom: 16 }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 12 }}>Referencia de tokens por entregable</h3>
                        <div style={{ fontSize: 12, color: T.textSec, lineHeight: 2 }}>
                            <p>Input imagen/texto: <strong>800–2,000 tok</strong></p>
                            <p>Prompt instrucción: <strong>200–500 tok</strong></p>
                            <p>JSON salida estructurada: <strong>300–800 tok</strong></p>
                            <p>Total por evaluación: <strong>~1,300–3,300 tok</strong></p>
                        </div>
                    </div>

                    {/* Budget Alerts */}
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: 20 }}>
                        <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, marginBottom: 16 }}>Alertas de presupuesto</h3>

                        <div style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                                <span style={{ fontSize: 12, fontWeight: 500, color: T.textSec }}>Alerta de gasto mensual USD</span>
                                <input type="checkbox" checked={alertEnabled} onChange={e => { setAlertEnabled(e.target.checked); setDirty(true); }} disabled={!canEdit} style={{ width: 15, height: 15 }} />
                            </div>
                            <p style={{ fontSize: 11, color: T.textTer, marginBottom: 8 }}>Notificar cuando el costo mensual supere el umbral</p>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <DollarSign size={14} color={T.textTer} />
                                <input type="number" value={threshold} onChange={e => { setThreshold(Number(e.target.value)); setDirty(true); }} disabled={!canEdit}
                                    style={{ width: 80, padding: '6px 10px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 13, fontFamily: "'DM Mono'" }}
                                    data-testid="budget-threshold-input"
                                />
                                <span style={{ fontSize: 12, color: T.textTer }}>USD</span>
                            </div>
                        </div>

                        <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                                <span style={{ fontSize: 12, fontWeight: 500, color: T.textSec }}>Reporte semanal de consumo</span>
                                <input type="checkbox" checked={weeklyEnabled} onChange={e => { setWeeklyEnabled(e.target.checked); setDirty(true); }} disabled={!canEdit} style={{ width: 15, height: 15 }} />
                            </div>
                            <p style={{ fontSize: 11, color: T.textTer, marginBottom: 8 }}>Resumen de tokens y costos cada lunes</p>
                            <input value={weeklyEmail} onChange={e => { setWeeklyEmail(e.target.value); setDirty(true); }} disabled={!canEdit}
                                placeholder="dev@me.mx"
                                style={{ width: '100%', padding: '6px 10px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12 }}
                            />
                        </div>
                    </div>

                    {/* SLA Configuration */}
                    <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: 20, marginBottom: 16 }} data-testid="sla-config-section">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                            <Package size={16} color={T.teal} />
                            <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri }}>SLA de paquetes por proveedor</h3>
                        </div>
                        <p style={{ fontSize: 11, color: T.textTer, marginBottom: 16 }}>
                            Define cuántos paquetes deben entregarse por ruta. Se usa en el cálculo de "% Efectividad SLA" y "Costo x Pq" en la Liquidación.
                        </p>

                        {/* Default SLA */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, padding: '12px 14px', borderRadius: T.radiusSm, background: T.tealLt, border: `1px solid ${T.teal}20` }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: T.textSec, whiteSpace: 'nowrap' }}>SLA por defecto:</span>
                            <input
                                type="number" min="1" value={defaultSla}
                                onChange={e => { setDefaultSla(Number(e.target.value)); setDirty(true); }}
                                disabled={!canEdit}
                                style={{ width: 70, padding: '6px 10px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 14, fontWeight: 700, fontFamily: "'DM Mono',monospace", textAlign: 'center' }}
                                data-testid="default-sla-input"
                            />
                            <span style={{ fontSize: 12, color: T.textTer }}>paquetes</span>
                        </div>

                        {/* Per-provider SLA overrides */}
                        <p style={{ fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 8 }}>Excepciones por proveedor</p>
                        {Object.entries(providerSlas).length > 0 ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
                                {Object.entries(providerSlas).map(([provId, slaVal]) => {
                                    const prov = providers.find(p => p.id === provId);
                                    return (
                                        <div key={provId} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: T.radiusSm, background: T.surface2 }} data-testid={`sla-override-${provId}`}>
                                            <span style={{ flex: 1, fontSize: 12, fontWeight: 500, color: T.textPri }}>{prov?.name || provId}</span>
                                            <input
                                                type="number" min="1" value={slaVal}
                                                onChange={e => {
                                                    setProviderSlas(prev => ({ ...prev, [provId]: Number(e.target.value) }));
                                                    setDirty(true);
                                                }}
                                                disabled={!canEdit}
                                                style={{ width: 70, padding: '4px 8px', borderRadius: 4, border: `1px solid ${T.border}`, fontSize: 13, fontWeight: 600, fontFamily: "'DM Mono',monospace", textAlign: 'center' }}
                                            />
                                            <span style={{ fontSize: 11, color: T.textTer }}>pq</span>
                                            {canEdit && (
                                                <button onClick={() => {
                                                    setProviderSlas(prev => {
                                                        const next = { ...prev };
                                                        delete next[provId];
                                                        return next;
                                                    });
                                                    setDirty(true);
                                                }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }} data-testid={`sla-remove-${provId}`}>
                                                    <Trash2 size={14} color={T.coral} />
                                                </button>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <p style={{ fontSize: 11, color: T.textTer, marginBottom: 12, fontStyle: 'italic' }}>
                                Todos los proveedores usan el SLA por defecto ({defaultSla}).
                            </p>
                        )}

                        {/* Add new provider override */}
                        {canEdit && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <select
                                    value={newSlaProviderId}
                                    onChange={e => setNewSlaProviderId(e.target.value)}
                                    style={{ flex: 1, padding: '6px 10px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, color: T.textSec, background: T.surface }}
                                    data-testid="sla-provider-select"
                                >
                                    <option value="">Seleccionar proveedor...</option>
                                    {providers.filter(p => !providerSlas[p.id]).map(p => (
                                        <option key={p.id} value={p.id}>{p.name}</option>
                                    ))}
                                </select>
                                <button
                                    onClick={() => {
                                        if (!newSlaProviderId) return;
                                        setProviderSlas(prev => ({ ...prev, [newSlaProviderId]: defaultSla }));
                                        setNewSlaProviderId('');
                                        setDirty(true);
                                    }}
                                    disabled={!newSlaProviderId}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px',
                                        borderRadius: T.radiusSm, border: `1px solid ${T.teal}40`,
                                        background: newSlaProviderId ? T.tealLt : T.surface2,
                                        color: newSlaProviderId ? T.teal : T.textTer,
                                        fontSize: 12, fontWeight: 500, cursor: newSlaProviderId ? 'pointer' : 'default',
                                    }}
                                    data-testid="sla-add-provider-btn"
                                >
                                    <Plus size={13} /> Agregar
                                </button>
                            </div>
                        )}
                    </div>

                    {/* Pulse Config inside SLA section */}
                    <PulseConfigSection
                        pulseConfig={pulseConfig}
                        onChange={(val) => { setPulseConfig(val); setDirty(true); }}
                        canEdit={canEdit}
                    />

                    {/* Save Button */}
                    {canEdit && (
                        <button onClick={saveAll} disabled={saving} style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, width: '100%',
                            padding: '12px', borderRadius: T.radiusSm, border: 'none', marginTop: 16,
                            background: dirty ? T.green : T.textPri, color: '#fff', fontSize: 13, fontWeight: 600,
                            cursor: 'pointer', fontFamily: "'DM Sans'", opacity: saving ? 0.6 : 1,
                        }} data-testid="save-config-btn">
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                            {dirty ? 'Guardar cambios' : 'Guardar configuración'}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
