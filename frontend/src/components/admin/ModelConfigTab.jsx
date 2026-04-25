import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../../lib/api';
import { toast } from 'sonner';
import {
    Save, RefreshCw, Loader2, Info, Cpu, Zap, Clock, Layers, Repeat2,
    Pause, Play, CalendarClock, PlusCircle, X, AlertTriangle,
} from 'lucide-react';

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
    const [pauseState, setPauseState] = useState({ is_paused: false, reason: null, paused_until: null });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);
    const [draft, setDraft] = useState({});
    const [pauseBusy, setPauseBusy] = useState(false);
    const [tick, setTick] = useState(0);
    const refetchTimer = useRef(null);

    const fetchConfig = useCallback(async () => {
        try {
            const res = await api.get('/ai-evaluation/config');
            setCfg(res.data.config);
            setBounds(res.data.bounds);
            setPauseState(res.data.pause_state || { is_paused: false });
            setDraft(res.data.config);
            setDirty(false);
        } catch {
            toast.error('Error al cargar configuración');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchConfig(); }, [fetchConfig]);

    // Refetch pause state every 20s + countdown tick every second
    useEffect(() => {
        refetchTimer.current = setInterval(fetchConfig, 20000);
        const tickTimer = setInterval(() => setTick((t) => t + 1), 1000);
        return () => {
            clearInterval(refetchTimer.current);
            clearInterval(tickTimer);
        };
    }, [fetchConfig]);

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

    // ── Pause / Resume ───────────────────────────────────────────
    const handlePause = async (minutes, reason) => {
        setPauseBusy(true);
        try {
            const res = await api.post('/ai-evaluation/pause', { duration_minutes: minutes, reason });
            toast.success(res.data.message || 'Worker pausado');
            fetchConfig();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al pausar');
        } finally {
            setPauseBusy(false);
        }
    };

    const handleResume = async () => {
        setPauseBusy(true);
        try {
            await api.post('/ai-evaluation/resume');
            toast.success('Worker reanudado');
            fetchConfig();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al reanudar');
        } finally {
            setPauseBusy(false);
        }
    };

    // ── Schedule windows ─────────────────────────────────────────
    const scheduleEnabled = draft.schedule_enabled || false;
    const windows = draft.schedule_windows || [];

    const setScheduleEnabled = (v) => {
        setDraft((d) => ({ ...d, schedule_enabled: v }));
        setDirty(true);
    };

    const addWindow = () => {
        const w = { name: 'Horario pico', days: [0, 1, 2, 3, 4], from: '09:00', to: '13:00', tz: 'America/Mexico_City' };
        setDraft((d) => ({ ...d, schedule_windows: [...(d.schedule_windows || []), w] }));
        setDirty(true);
    };

    const updateWindow = (idx, patch) => {
        setDraft((d) => ({
            ...d,
            schedule_windows: (d.schedule_windows || []).map((w, i) => (i === idx ? { ...w, ...patch } : w)),
        }));
        setDirty(true);
    };

    const removeWindow = (idx) => {
        setDraft((d) => ({
            ...d,
            schedule_windows: (d.schedule_windows || []).filter((_, i) => i !== idx),
        }));
        setDirty(true);
    };

    const saveSchedule = async () => {
        setSaving(true);
        try {
            await api.put('/ai-evaluation/schedule', { enabled: scheduleEnabled, windows });
            toast.success('Agenda guardada. Worker verifica cada 10s.');
            fetchConfig();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error');
        } finally {
            setSaving(false);
        }
    };

    // ── Countdown for paused_until ──────────────────────────────
    const countdownText = (() => {
        if (!pauseState.paused_until) return null;
        const until = new Date(pauseState.paused_until);
        const ms = until - new Date();
        if (ms <= 0) return null;
        const totalSec = Math.floor(ms / 1000);
        const h = Math.floor(totalSec / 3600);
        const m = Math.floor((totalSec % 3600) / 60);
        const s = totalSec % 60;
        return h > 0 ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
    })();
    void tick; // Force re-render every second for countdown

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
            {/* Pause status (big banner) */}
            <PauseBanner
                pauseState={pauseState}
                countdownText={countdownText}
                pauseBusy={pauseBusy}
                canEdit={canEdit}
                onPause={handlePause}
                onResume={handleResume}
            />

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

            {/* Schedule windows */}
            <ScheduleSection
                enabled={scheduleEnabled}
                windows={windows}
                canEdit={canEdit}
                onToggle={setScheduleEnabled}
                onAdd={addWindow}
                onUpdate={updateWindow}
                onRemove={removeWindow}
                onSave={saveSchedule}
                saving={saving}
                dirty={dirty}
            />

            {/* Smart Autopause (P09) */}
            <ShadowAutopauseSection
                draft={draft}
                update={update}
                bounds={bounds}
                canEdit={canEdit}
                saving={saving}
                dirty={dirty}
                onSave={handleSave}
            />

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


// ═══════════════════ PAUSE BANNER ═══════════════════

const PAUSE_PRESETS = [
    { label: '1h', minutes: 60 },
    { label: '4h', minutes: 240 },
    { label: '24h', minutes: 1440 },
];

function PauseBanner({ pauseState, countdownText, pauseBusy, canEdit, onPause, onResume }) {
    const paused = pauseState.is_paused;
    const bg = paused ? '#FEF2F2' : '#F0FDF4';
    const border = paused ? '#DC2626' : '#16A34A';
    const icon = paused ? Pause : Play;
    const Icon = icon;
    return (
        <section
            data-testid="pause-banner"
            style={{
                background: bg, border: `1px solid ${border}40`,
                borderRadius: T.radius, padding: 18,
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
                flexWrap: 'wrap',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0, flex: 1 }}>
                <div style={{
                    width: 44, height: 44, borderRadius: '50%', background: border,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                    <Icon size={22} color="#fff" />
                </div>
                <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 16, fontWeight: 700, color: border, display: 'flex', alignItems: 'center', gap: 8 }}>
                        {paused ? 'Worker pausado' : 'Worker activo'}
                        {countdownText && (
                            <span style={{
                                fontSize: 12, padding: '2px 8px', borderRadius: 4, background: border,
                                color: '#fff', fontFamily: "'DM Mono',monospace", fontWeight: 600,
                            }} data-testid="pause-countdown">
                                {countdownText}
                            </span>
                        )}
                    </div>
                    <p style={{ fontSize: 12.5, color: T.textSec, margin: '4px 0 0 0' }}>
                        {paused
                            ? (pauseState.reason || 'Pausado')
                            : 'Tomando jobs de la cola cada 10 segundos.'}
                    </p>
                </div>
            </div>
            {canEdit && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {!paused && PAUSE_PRESETS.map((p) => (
                        <button
                            key={p.label}
                            onClick={() => onPause(p.minutes, `Pausa manual ${p.label}`)}
                            disabled={pauseBusy}
                            data-testid={`pause-preset-${p.label}`}
                            style={{
                                padding: '8px 14px', border: `1px solid ${T.borderStrong}`,
                                background: T.surface, color: T.textPri, borderRadius: T.radiusSm,
                                cursor: pauseBusy ? 'default' : 'pointer',
                                fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
                                opacity: pauseBusy ? 0.5 : 1,
                            }}
                        >
                            <Pause size={13} />
                            Pausar {p.label}
                        </button>
                    ))}
                    {!paused && (
                        <CustomPauseButton onPause={onPause} disabled={pauseBusy} />
                    )}
                    {paused && (
                        <button
                            onClick={onResume}
                            disabled={pauseBusy}
                            data-testid="resume-btn"
                            style={{
                                padding: '10px 20px', border: 'none',
                                background: '#16A34A', color: '#fff', borderRadius: T.radiusSm,
                                cursor: pauseBusy ? 'default' : 'pointer',
                                fontSize: 13.5, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6,
                                opacity: pauseBusy ? 0.6 : 1,
                            }}
                        >
                            {pauseBusy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                            Reanudar ahora
                        </button>
                    )}
                </div>
            )}
        </section>
    );
}

function CustomPauseButton({ onPause, disabled }) {
    const [open, setOpen] = useState(false);
    const [mins, setMins] = useState(30);
    if (!open) {
        return (
            <button
                onClick={() => setOpen(true)}
                disabled={disabled}
                data-testid="pause-custom-btn"
                style={{
                    padding: '8px 14px', border: `1px solid ${T.borderStrong}`,
                    background: T.surface, color: T.textPri, borderRadius: T.radiusSm,
                    cursor: disabled ? 'default' : 'pointer',
                    fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4,
                }}
            >
                <Clock size={13} />
                Personalizado
            </button>
        );
    }
    return (
        <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: 4, border: `1px solid ${T.borderStrong}`, borderRadius: T.radiusSm, background: T.surface,
        }}>
            <input
                type="number"
                min={1} max={2880}
                value={mins}
                onChange={(e) => setMins(parseInt(e.target.value, 10) || 0)}
                style={{
                    width: 60, padding: '4px 6px', fontSize: 13, border: `1px solid ${T.border}`,
                    borderRadius: 4, fontFamily: "'DM Mono',monospace",
                }}
                data-testid="pause-custom-input"
            />
            <span style={{ fontSize: 11, color: T.textSec }}>min</span>
            <button
                onClick={() => { onPause(mins, `Pausa manual ${mins}min`); setOpen(false); }}
                disabled={mins < 1 || mins > 2880 || disabled}
                data-testid="pause-custom-confirm"
                style={{
                    padding: '5px 10px', border: 'none',
                    background: T.blue, color: '#fff', borderRadius: 4,
                    fontSize: 12, fontWeight: 600, cursor: 'pointer',
                }}
            >
                Pausar
            </button>
            <button onClick={() => setOpen(false)} style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 2 }}>
                <X size={14} color={T.textTer} />
            </button>
        </div>
    );
}

// ═══════════════════ SCHEDULE SECTION ═══════════════════

const DAYS_LABEL = ['L', 'M', 'X', 'J', 'V', 'S', 'D']; // Monday=0 ... Sunday=6

function ScheduleSection({ enabled, windows, canEdit, onToggle, onAdd, onUpdate, onRemove, onSave, saving, dirty }) {
    return (
        <section style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius, padding: 20 }} data-testid="schedule-section">
            <header style={{ marginBottom: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CalendarClock size={16} style={{ color: T.textSec }} />
                    <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, margin: 0 }}>Ventanas programadas</h3>
                    <span style={{ fontSize: 11, color: T.textTer }}>(hora CDMX)</span>
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: canEdit ? 'pointer' : 'default', fontSize: 12.5 }}>
                    <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(e) => canEdit && onToggle(e.target.checked)}
                        disabled={!canEdit}
                        data-testid="schedule-enabled-toggle"
                    />
                    <span style={{ color: enabled ? T.textPri : T.textTer, fontWeight: enabled ? 600 : 400 }}>
                        {enabled ? 'Agenda activa' : 'Agenda inactiva'}
                    </span>
                </label>
            </header>

            <p style={{ fontSize: 12, color: T.textSec, margin: '0 0 14px 0', lineHeight: 1.5 }}>
                Durante estas ventanas el worker NO toma nuevos jobs y ABORTA los que estén en curso (kill switch).
                Los jobs ya evaluados conservan su score.
            </p>

            <div style={{ display: 'grid', gap: 10 }} data-testid="schedule-windows">
                {windows.length === 0 && (
                    <div style={{
                        padding: 20, textAlign: 'center', color: T.textTer, fontSize: 12.5,
                        border: `1px dashed ${T.border}`, borderRadius: T.radiusSm,
                    }}>
                        No hay ventanas programadas. Agrega una para bloquear horarios pico.
                    </div>
                )}
                {windows.map((w, idx) => (
                    <WindowRow
                        key={idx}
                        idx={idx}
                        window={w}
                        disabled={!canEdit}
                        onUpdate={(patch) => onUpdate(idx, patch)}
                        onRemove={() => onRemove(idx)}
                    />
                ))}
            </div>

            {canEdit && (
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button
                        onClick={onAdd}
                        data-testid="add-window-btn"
                        style={{
                            padding: '6px 12px', border: `1px dashed ${T.borderStrong}`,
                            background: 'transparent', color: T.textSec, borderRadius: T.radiusSm,
                            fontSize: 12.5, fontWeight: 500, cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: 4,
                        }}
                    >
                        <PlusCircle size={13} />
                        Agregar ventana
                    </button>
                    <button
                        onClick={onSave}
                        disabled={saving || !dirty}
                        data-testid="save-schedule-btn"
                        style={{
                            marginLeft: 'auto',
                            padding: '6px 14px', border: 'none',
                            background: dirty ? T.blue : T.textTer, color: '#fff',
                            borderRadius: T.radiusSm, fontSize: 12.5, fontWeight: 600,
                            cursor: dirty ? 'pointer' : 'default',
                            display: 'flex', alignItems: 'center', gap: 4,
                            opacity: saving ? 0.6 : 1,
                        }}
                    >
                        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                        Guardar agenda
                    </button>
                </div>
            )}
        </section>
    );
}

function WindowRow({ idx, window: w, disabled, onUpdate, onRemove }) {
    const toggleDay = (d) => {
        const days = w.days.includes(d) ? w.days.filter((x) => x !== d) : [...w.days, d].sort();
        onUpdate({ days });
    };
    return (
        <div
            data-testid={`window-row-${idx}`}
            style={{
                padding: 12, border: `1px solid ${T.border}`, borderRadius: T.radiusSm,
                background: T.bg, display: 'grid',
                gridTemplateColumns: '1.5fr 2fr 1fr auto', gap: 12, alignItems: 'center',
            }}
        >
            <input
                type="text"
                value={w.name || ''}
                onChange={(e) => onUpdate({ name: e.target.value })}
                placeholder="Nombre"
                disabled={disabled}
                data-testid={`window-name-${idx}`}
                style={{
                    padding: '6px 8px', fontSize: 13, border: `1px solid ${T.border}`,
                    borderRadius: 4, background: T.surface,
                }}
            />
            <div style={{ display: 'flex', gap: 4 }}>
                {DAYS_LABEL.map((d, i) => (
                    <button
                        key={i}
                        onClick={() => !disabled && toggleDay(i)}
                        disabled={disabled}
                        data-testid={`window-day-${idx}-${i}`}
                        style={{
                            width: 28, height: 28, border: `1px solid ${T.border}`,
                            background: w.days?.includes(i) ? T.blue : T.surface,
                            color: w.days?.includes(i) ? '#fff' : T.textSec,
                            borderRadius: 4, cursor: disabled ? 'default' : 'pointer',
                            fontSize: 11, fontWeight: 600,
                        }}
                    >{d}</button>
                ))}
            </div>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <input
                    type="time"
                    value={w.from || '09:00'}
                    onChange={(e) => onUpdate({ from: e.target.value })}
                    disabled={disabled}
                    data-testid={`window-from-${idx}`}
                    style={{ padding: '4px 6px', fontSize: 12, border: `1px solid ${T.border}`, borderRadius: 4, fontFamily: "'DM Mono',monospace" }}
                />
                <span style={{ fontSize: 11, color: T.textTer }}>→</span>
                <input
                    type="time"
                    value={w.to || '13:00'}
                    onChange={(e) => onUpdate({ to: e.target.value })}
                    disabled={disabled}
                    data-testid={`window-to-${idx}`}
                    style={{ padding: '4px 6px', fontSize: 12, border: `1px solid ${T.border}`, borderRadius: 4, fontFamily: "'DM Mono',monospace" }}
                />
            </div>
            {!disabled && (
                <button
                    onClick={onRemove}
                    data-testid={`window-remove-${idx}`}
                    style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: 4 }}
                    title="Eliminar ventana"
                >
                    <X size={14} color={T.textTer} />
                </button>
            )}
        </div>
    );
}



/* ────────────────────────────────────────────────────────────────
 * Shadow Autopause Section (P09)
 *   Pausa automática del worker cuando el shadow_cost_pct excede el
 *   umbral en una ventana reciente. Previene drenaje de saldo en
 *   cascadas de fallos de Anthropic (timeouts/rate-limits).
 * ──────────────────────────────────────────────────────────────── */
function ShadowAutopauseSection({ draft, update, bounds, canEdit, saving, dirty, onSave }) {
    const enabled = draft.shadow_autopause_enabled !== false; // default true
    return (
        <section
            data-testid="shadow-autopause-section"
            style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius, padding: 20 }}
        >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div>
                    <h3 style={{ fontSize: 14, fontWeight: 600, color: T.textPri, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <AlertTriangle size={16} color={T.amber} />
                        Autopause inteligente (shadow cost)
                    </h3>
                    <p style={{ fontSize: 11, color: T.textTer, margin: '4px 0 0 0' }}>
                        Pausa el worker automáticamente cuando Anthropic factura sin entregar respuesta (timeouts/rate-limits) por encima de un umbral.
                    </p>
                </div>
                <label
                    style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: canEdit ? 'pointer' : 'not-allowed', fontSize: 12, fontWeight: 600, color: enabled ? T.green : T.textTer }}
                >
                    <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(e) => update('shadow_autopause_enabled', e.target.checked)}
                        disabled={!canEdit}
                        data-testid="shadow-autopause-toggle"
                    />
                    {enabled ? 'Activado' : 'Desactivado'}
                </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, opacity: enabled ? 1 : 0.45 }}>
                <ShadowNumField
                    label="Umbral shadow %"
                    hint="Pausar si shadow ≥ X% del costo en la ventana"
                    icon={AlertTriangle}
                    min={bounds.shadow_threshold_pct?.[0] ?? 1}
                    max={bounds.shadow_threshold_pct?.[1] ?? 100}
                    value={draft.shadow_threshold_pct ?? 10}
                    onChange={(v) => update('shadow_threshold_pct', v)}
                    disabled={!canEdit || !enabled}
                    suffix="%"
                    testid="shadow-threshold-pct"
                />
                <ShadowNumField
                    label="Ventana de medición"
                    hint="Minutos hacia atrás para calcular el %"
                    icon={Clock}
                    min={bounds.shadow_window_minutes?.[0] ?? 5}
                    max={bounds.shadow_window_minutes?.[1] ?? 60}
                    value={draft.shadow_window_minutes ?? 15}
                    onChange={(v) => update('shadow_window_minutes', v)}
                    disabled={!canEdit || !enabled}
                    suffix="min"
                    testid="shadow-window-minutes"
                />
                <ShadowNumField
                    label="Eventos mínimos"
                    hint="Baseline para evitar disparar con 1-2 fallos"
                    icon={Layers}
                    min={bounds.shadow_min_events?.[0] ?? 1}
                    max={bounds.shadow_min_events?.[1] ?? 100}
                    value={draft.shadow_min_events ?? 10}
                    onChange={(v) => update('shadow_min_events', v)}
                    disabled={!canEdit || !enabled}
                    testid="shadow-min-events"
                />
                <ShadowNumField
                    label="Duración de pausa"
                    hint="Cuánto tiempo pausar al disparar"
                    icon={Pause}
                    min={bounds.shadow_autopause_minutes?.[0] ?? 5}
                    max={bounds.shadow_autopause_minutes?.[1] ?? 240}
                    value={draft.shadow_autopause_minutes ?? 20}
                    onChange={(v) => update('shadow_autopause_minutes', v)}
                    disabled={!canEdit || !enabled}
                    suffix="min"
                    testid="shadow-autopause-minutes"
                />
            </div>

            {dirty && canEdit && (
                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                    <button
                        onClick={onSave}
                        disabled={saving}
                        data-testid="save-shadow-autopause-btn"
                        style={{
                            padding: '8px 14px', fontSize: 12, fontWeight: 600,
                            background: T.amber, color: '#fff', border: 'none', borderRadius: 6,
                            cursor: saving ? 'not-allowed' : 'pointer',
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                        }}
                    >
                        {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                        Guardar autopause
                    </button>
                </div>
            )}

            <div style={{ marginTop: 12, padding: 10, background: T.amberLt, borderRadius: 6, fontSize: 11, color: '#92400E', lineHeight: 1.5 }}>
                <strong>Cómo funciona:</strong> cada 60s mientras el worker procesa,
                consulta los últimos {draft.shadow_window_minutes ?? 15} min de evaluaciones IA.
                Si <strong>≥{draft.shadow_threshold_pct ?? 10}%</strong> del costo proviene de eventos shadow
                (Anthropic facturó pero la respuesta falló) y hubo al menos <strong>{draft.shadow_min_events ?? 10}</strong> eventos,
                pausa el worker por <strong>{draft.shadow_autopause_minutes ?? 20} min</strong> con un mensaje claro al operador.
                Para reanudar antes, usa <strong>Reanudar</strong> en la sección superior.
            </div>
        </section>
    );
}

function ShadowNumField({ label, hint, icon: Icon, min, max, value, onChange, disabled, suffix, testid }) {
    return (
        <div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 600, color: T.textSec, marginBottom: 4 }}>
                {Icon && <Icon size={12} color={T.textTer} />}
                {label}
            </label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <input
                    type="number"
                    min={min}
                    max={max}
                    value={value}
                    onChange={(e) => {
                        const v = parseInt(e.target.value || '0', 10);
                        if (!isNaN(v)) onChange(Math.max(min, Math.min(max, v)));
                    }}
                    disabled={disabled}
                    data-testid={testid}
                    style={{
                        flex: 1, padding: '8px 10px', fontSize: 13,
                        border: `1px solid ${T.border}`, borderRadius: T.radiusSm,
                        background: disabled ? T.bg : T.surface, color: T.textPri,
                        fontFamily: "'DM Mono', monospace",
                    }}
                />
                {suffix && (
                    <span style={{ fontSize: 12, color: T.textTer, fontWeight: 600, minWidth: 28 }}>{suffix}</span>
                )}
            </div>
            {hint && (
                <p style={{ fontSize: 10.5, color: T.textTer, margin: '3px 0 0 0' }}>{hint}</p>
            )}
        </div>
    );
}
