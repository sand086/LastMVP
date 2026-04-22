import React, { useState, useEffect, useCallback } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import { Save, RefreshCw, Loader2, Info, Cpu, Zap, Clock, Layers, Repeat2 } from 'lucide-react';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF',
    green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB',
    purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

const MODEL_INFO = {
    'haiku-4-5': {
        label: 'Haiku 4.5',
        full: 'claude-haiku-4-5-20251001',
        color: T.green,
        bg: T.greenLt,
        cost: '$1 / $5 por M tokens',
        speed: '~ 8s por guía',
        tag: 'Recomendado',
        desc: 'Modelo rápido y económico, ideal para clasificación visual estructurada.',
    },
    'sonnet-4-5': {
        label: 'Sonnet 4.5',
        full: 'claude-sonnet-4-5-20250929',
        color: T.purple,
        bg: T.purpleLt,
        cost: '$3 / $15 por M tokens',
        speed: '~ 30s por guía',
        tag: 'Premium / A-B Test',
        desc: 'Modelo superior en razonamiento. Conviene para casos complejos o A/B testing.',
    },
};

export default function ModelConfigTab({ canEdit }) {
    const [cfg, setCfg] = useState(null);
    const [bounds, setBounds] = useState({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);
    const [draft, setDraft] = useState({});

    const fetchConfig = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get('/ai-evaluation/config');
            setCfg(res.data.config);
            setBounds(res.data.bounds);
            setDraft(res.data.config);
            setDirty(false);
        } catch {
            toast.error('Error al cargar configuración');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchConfig(); }, [fetchConfig]);

    const update = (key, value) => {
        setDraft((d) => ({ ...d, [key]: value }));
        setDirty(true);
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const res = await api.put('/ai-evaluation/config', draft);
            setCfg(res.data.config);
            setDraft(res.data.config);
            setDirty(false);
            toast.success('Configuración guardada. Aplicará al próximo job del worker.');
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        setDraft(cfg);
        setDirty(false);
    };

    if (loading || !cfg) {
        return (
            <div style={{ padding: 32, textAlign: 'center' }}>
                <Loader2 className="animate-spin" style={{ color: T.textSec, margin: '0 auto' }} />
            </div>
        );
    }

    const selectedModel = MODEL_INFO[draft.model] || MODEL_INFO['haiku-4-5'];

    return (
        <div style={{ display: 'grid', gap: 20 }} data-testid="model-config-tab">
            {/* Info banner */}
            <div style={{
                display: 'flex', gap: 12, padding: '12px 14px',
                background: T.blueLt, border: `1px solid ${T.blue}30`,
                borderRadius: T.radius, alignItems: 'flex-start',
            }}>
                <Info size={16} style={{ color: T.blue, marginTop: 2, flexShrink: 0 }} />
                <div style={{ fontSize: 12.5, color: T.textPri, lineHeight: 1.5 }}>
                    Esta configuración aplica <strong>sólo al pipeline de Evaluación IA</strong> (Monitor de procesos → evaluación de evidencias).
                    Lumi y otros módulos conversacionales siguen usando Sonnet 4.5. Los cambios se aplican al próximo job encolado.
                </div>
            </div>

            {/* Model selector */}
            <section style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius, padding: 20 }}>
                <header style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Cpu size={16} style={{ color: T.textSec }} />
                    <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, margin: 0 }}>Modelo de evaluación</h3>
                </header>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    {Object.entries(MODEL_INFO).map(([key, info]) => {
                        const active = draft.model === key;
                        return (
                            <button
                                key={key}
                                onClick={() => canEdit && update('model', key)}
                                disabled={!canEdit}
                                data-testid={`model-option-${key}`}
                                style={{
                                    textAlign: 'left', padding: 16, cursor: canEdit ? 'pointer' : 'default',
                                    border: `2px solid ${active ? info.color : T.border}`,
                                    background: active ? info.bg : T.surface,
                                    borderRadius: T.radius, transition: 'all 0.15s',
                                    display: 'flex', flexDirection: 'column', gap: 8,
                                    opacity: canEdit ? 1 : 0.7,
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span style={{ fontSize: 15, fontWeight: 700, color: T.textPri }}>{info.label}</span>
                                        <span style={{
                                            fontSize: 10, padding: '2px 8px', borderRadius: 999,
                                            background: info.color, color: '#fff', fontWeight: 600,
                                        }}>{info.tag}</span>
                                    </div>
                                    <div style={{
                                        width: 16, height: 16, borderRadius: 999,
                                        border: `2px solid ${active ? info.color : T.borderStrong}`,
                                        background: active ? info.color : 'transparent',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    }}>
                                        {active && <div style={{ width: 6, height: 6, borderRadius: 999, background: '#fff' }} />}
                                    </div>
                                </div>
                                <p style={{ fontSize: 12, color: T.textSec, margin: 0, lineHeight: 1.5 }}>{info.desc}</p>
                                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                                    <span style={{ fontSize: 11, color: T.textTer }}>
                                        <Zap size={10} style={{ marginRight: 3 }} /> {info.speed}
                                    </span>
                                    <span style={{ fontSize: 11, color: T.textTer }}>·</span>
                                    <span style={{ fontSize: 11, color: T.textTer }}>{info.cost}</span>
                                </div>
                                <p style={{ fontSize: 10, color: T.textTer, margin: 0, fontFamily: "'DM Mono',monospace" }}>{info.full}</p>
                            </button>
                        );
                    })}
                </div>
            </section>

            {/* Worker params */}
            <section style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius, padding: 20 }}>
                <header style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Layers size={16} style={{ color: T.textSec }} />
                    <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, margin: 0 }}>Parámetros del worker</h3>
                </header>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 20 }}>
                    <SliderField
                        icon={Clock}
                        label="Timeout por guía"
                        unit="segundos"
                        min={bounds.timeout_per_guia?.[0] ?? 30}
                        max={bounds.timeout_per_guia?.[1] ?? 180}
                        step={5}
                        value={draft.timeout_per_guia}
                        onChange={(v) => update('timeout_per_guia', v)}
                        disabled={!canEdit}
                        testId="cfg-timeout"
                        hint="Tiempo máximo para evaluar una guía antes de marcarla como Error por timeout"
                    />
                    <SliderField
                        icon={Zap}
                        label="Rutas concurrentes"
                        unit="rutas simultáneas"
                        min={bounds.max_routes_concurrent?.[0] ?? 1}
                        max={bounds.max_routes_concurrent?.[1] ?? 5}
                        step={1}
                        value={draft.max_routes_concurrent}
                        onChange={(v) => update('max_routes_concurrent', v)}
                        disabled={!canEdit}
                        testId="cfg-concurrent"
                        hint="Cuántos jobs de distintas rutas se ejecutan al mismo tiempo"
                    />
                    <SliderField
                        icon={Layers}
                        label="Batch por ruta"
                        unit="guías paralelas"
                        min={bounds.batch_size_per_route?.[0] ?? 1}
                        max={bounds.batch_size_per_route?.[1] ?? 10}
                        step={1}
                        value={draft.batch_size_per_route}
                        onChange={(v) => update('batch_size_per_route', v)}
                        disabled={!canEdit}
                        testId="cfg-batch"
                        hint="Cantidad de guías que se evalúan en paralelo dentro de un mismo job"
                    />
                    <SliderField
                        icon={Repeat2}
                        label="Reintentos"
                        unit="reintentos por guía"
                        min={bounds.max_retries?.[0] ?? 0}
                        max={bounds.max_retries?.[1] ?? 5}
                        step={1}
                        value={draft.max_retries}
                        onChange={(v) => update('max_retries', v)}
                        disabled={!canEdit}
                        testId="cfg-retries"
                        hint="Si una guía falla, cuántas veces se reintenta antes de marcarla como Error"
                    />
                </div>
            </section>

            {/* Savings estimate */}
            <section style={{ background: selectedModel.bg, border: `1px solid ${selectedModel.color}30`, borderRadius: T.radius, padding: 16 }}>
                <div style={{ fontSize: 12, color: T.textSec, marginBottom: 6 }}>Estimación mensual (60,000 evaluaciones):</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: selectedModel.color, fontFamily: "'DM Mono',monospace" }}>
                    {draft.model === 'haiku-4-5' ? '~$738 USD/mes' : '~$2,214 USD/mes'}
                </div>
                <div style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>
                    {draft.model === 'haiku-4-5'
                        ? 'Ahorro ≈ $1,476 USD/mes vs Sonnet 4.5'
                        : 'Sonnet es ~3x más caro pero con razonamiento superior'}
                </div>
            </section>

            {/* Action bar */}
            {canEdit && (
                <div style={{
                    position: 'sticky', bottom: 0, background: T.surface,
                    border: `1px solid ${T.border}`, borderRadius: T.radius,
                    padding: 12, display: 'flex', justifyContent: 'flex-end', gap: 8,
                    boxShadow: dirty ? '0 -4px 12px rgba(0,0,0,0.04)' : 'none',
                }}>
                    <button
                        onClick={handleReset}
                        disabled={!dirty || saving}
                        data-testid="cfg-reset-btn"
                        style={{
                            padding: '8px 16px', border: `1px solid ${T.border}`,
                            background: T.surface, color: T.textSec,
                            borderRadius: T.radiusSm, cursor: dirty ? 'pointer' : 'default',
                            fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4,
                            opacity: dirty ? 1 : 0.4,
                        }}
                    >
                        <RefreshCw size={13} />
                        Descartar
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={!dirty || saving}
                        data-testid="cfg-save-btn"
                        style={{
                            padding: '8px 16px', border: `1px solid ${T.blue}`,
                            background: dirty ? T.blue : T.textTer, color: '#fff',
                            borderRadius: T.radiusSm, cursor: dirty ? 'pointer' : 'default',
                            fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
                            opacity: saving ? 0.7 : 1,
                        }}
                    >
                        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                        {saving ? 'Guardando...' : 'Guardar cambios'}
                    </button>
                </div>
            )}
        </div>
    );
}

function SliderField({ icon: Icon, label, unit, min, max, step, value, onChange, disabled, testId, hint }) {
    return (
        <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <Icon size={13} style={{ color: T.textSec }} />
                <label style={{ fontSize: 12.5, fontWeight: 500, color: T.textPri }}>{label}</label>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input
                    type="range"
                    min={min} max={max} step={step}
                    value={value || min}
                    onChange={(e) => onChange(parseInt(e.target.value, 10))}
                    disabled={disabled}
                    data-testid={testId}
                    style={{ flex: 1 }}
                />
                <div style={{
                    minWidth: 56, textAlign: 'right', fontFamily: "'DM Mono',monospace",
                    fontSize: 14, fontWeight: 600, color: T.textPri,
                }}>
                    {value}
                </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
                <span style={{ fontSize: 10, color: T.textTer }}>{min}</span>
                <span style={{ fontSize: 10, color: T.textTer }}>{unit}</span>
                <span style={{ fontSize: 10, color: T.textTer }}>{max}</span>
            </div>
            {hint && <p style={{ fontSize: 10.5, color: T.textTer, marginTop: 4, lineHeight: 1.4 }}>{hint}</p>}
        </div>
    );
}
