/**
 * /captacion — Centro de control de la cohorte de auditoría por paquetes (RTV2).
 *
 * Objetivo: dar transparencia operativa al flujo "rotación de drivers para auditoría
 * de evidencias", pero con la variable principal en PAQUETES (no rutas):
 *   - target_packages_daily / min / max
 *   - target_packages_weekly (calendar Mon–Sun)
 *   - ingest_cutoff_time (hora de corte CDMX)
 *   - ingest_eligibility_states (default: solo planes Routal in_progress)
 *
 * Layout:
 *   ┌────────────────────────────────────────────────┐
 *   │ Header + selector cliente + última corrida     │
 *   ├──────────────────┬─────────────────────────────┤
 *   │ Card "Hoy"       │ Card "Semana" (Mon–Sun)     │
 *   │ + gauge          │ + barra progreso + banda    │
 *   ├──────────────────┴─────────────────────────────┤
 *   │ Sparkline 28 días                              │
 *   ├────────────────────────────────────────────────┤
 *   │ Form de configuración (modal/aside) UX amigable│
 *   └────────────────────────────────────────────────┘
 */
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { DashboardLayout } from '../components/DashboardLayout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Slider } from '../components/ui/slider';
import { Switch } from '../components/ui/switch';
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '../components/ui/dialog';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import api from '../lib/api';
import {
    Target, Calendar, Settings, Sparkles, AlertCircle, CheckCircle2,
    TrendingUp, TrendingDown, Activity, Clock,
} from 'lucide-react';

const PLAN_STATE_OPTIONS = [
    { value: 'in_progress', label: 'En operación (in_progress)', recommended: true },
    { value: 'created', label: 'Creado (sin iniciar)' },
    { value: 'completed', label: 'Completado' },
    { value: 'cancelled', label: 'Cancelado' },
];

const Captacion = () => {
    const [clients, setClients] = useState([]);
    const [clientId, setClientId] = useState(null);
    const [stats, setStats] = useState(null);
    const [cfg, setCfg] = useState(null);
    const [loading, setLoading] = useState(true);
    const [configOpen, setConfigOpen] = useState(false);
    const [saving, setSaving] = useState(false);

    // ─── Load clients
    useEffect(() => {
        api.get('/clients').then((r) => {
            const items = r.data || [];
            setClients(items);
            const first = items.find((c) => c.active) || items[0];
            if (first) setClientId(first.id);
        }).catch(() => toast.error('No se pudo cargar lista de clientes'));
    }, []);

    // ─── Load stats + cfg
    const refresh = useCallback(async () => {
        if (!clientId) return;
        setLoading(true);
        try {
            const [statsRes, cfgRes] = await Promise.all([
                api.get(`/captacion/stats/${clientId}?days=28`),
                api.get(`/client-config/${clientId}`),
            ]);
            setStats(statsRes.data);
            setCfg(cfgRes.data);
        } catch (e) {
            const detail = e?.response?.data?.detail;
            toast.error(`Error cargando datos: ${detail || e.message}`);
        } finally {
            setLoading(false);
        }
    }, [clientId]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    if (loading || !stats || !cfg) {
        return (
            <DashboardLayout>
                <div className="p-6">
                    <div className="text-sm text-gray-500">Cargando captación...</div>
                </div>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <div className="p-6 space-y-6 max-w-7xl mx-auto" data-testid="captacion-page">
                <Header
                    clients={clients}
                    clientId={clientId}
                    onClientChange={setClientId}
                    stats={stats}
                    cfg={cfg}
                    onConfigClick={() => setConfigOpen(true)}
                />

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <TodayCard stats={stats} />
                    <WeekCard stats={stats} />
                </div>

                <SparklineCard stats={stats} />

                <LastRunCard stats={stats} />

                <ConfigDialog
                    open={configOpen}
                    onOpenChange={setConfigOpen}
                    cfg={cfg}
                    saving={saving}
                    onSave={async (patch) => {
                        setSaving(true);
                        try {
                            await api.patch(`/client-config/${clientId}`, patch);
                            toast.success('Configuración actualizada');
                            setConfigOpen(false);
                            await refresh();
                        } catch (e) {
                            toast.error(`Error: ${e?.response?.data?.detail || e.message}`);
                        } finally {
                            setSaving(false);
                        }
                    }}
                />
            </div>
        </DashboardLayout>
    );
};

const Header = ({ clients, clientId, onClientChange, stats, cfg, onConfigClick }) => (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
            <div className="flex items-center gap-2 text-amber-600 text-xs font-semibold uppercase tracking-wide">
                <Target className="w-4 h-4" /> Captación · Cohorte por paquetes
            </div>
            <h1 className="text-3xl font-bold mt-1">Centro de captación</h1>
            <p className="text-sm text-gray-600 mt-1">
                Auditoría orientada a paquetes con rotación de drivers preservada.
                Corte diario a las <strong>{cfg.ingest_cutoff_time || '16:00'}</strong>{' '}
                ({cfg.ingest_cutoff_timezone?.split('/').pop()?.replace('_', ' ') || 'CDMX'}).
            </p>
        </div>
        <div className="flex items-center gap-2">
            <Select value={clientId} onValueChange={onClientChange}>
                <SelectTrigger className="w-[200px]" data-testid="captacion-client-select">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    {clients.map((c) => (
                        <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
            <Button onClick={onConfigClick} variant="outline" data-testid="captacion-config-btn">
                <Settings className="w-4 h-4 mr-2" /> Configurar
            </Button>
        </div>
    </div>
);

const TodayCard = ({ stats }) => {
    const t = stats.today;
    const pct = Math.min(100, t.pct_of_target);
    const barColor = pct >= 90 ? 'bg-emerald-500'
        : pct >= 60 ? 'bg-amber-500'
        : 'bg-red-500';
    const status = pct >= 90 ? { icon: CheckCircle2, label: 'En target', cls: 'text-emerald-600' }
        : pct >= 60 ? { icon: TrendingUp, label: 'Avanzando', cls: 'text-amber-600' }
        : { icon: TrendingDown, label: 'Por debajo', cls: 'text-red-600' };
    const StatusIcon = status.icon;

    return (
        <Card data-testid="captacion-today-card">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-gray-500" /> Hoy ({t.date})
                    </CardTitle>
                    <Badge className={`${status.cls} bg-transparent border-current`}>
                        <StatusIcon className="w-3 h-3 mr-1" /> {status.label}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="space-y-3">
                <div>
                    <div className="flex items-baseline justify-between mb-1">
                        <span className="text-3xl font-bold tabular-nums">{t.packages_audited.toLocaleString()}</span>
                        <span className="text-sm text-gray-500">
                            / {t.adjusted_target.toLocaleString()} ajustado
                        </span>
                    </div>
                    <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden relative">
                        <div className={`h-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
                        {/* Target line */}
                        <div
                            className="absolute top-0 h-full border-r-2 border-gray-700"
                            style={{ left: `${Math.min(100, (t.target_daily / t.adjusted_target) * (pct / 100) * 100)}%` }}
                            title={`Target base ${t.target_daily}`}
                        />
                    </div>
                    <div className="flex justify-between text-xs text-gray-500 mt-1">
                        <span>Mín {t.min_daily.toLocaleString()}</span>
                        <span>Target {t.target_daily.toLocaleString()}</span>
                        <span>Máx {t.max_daily.toLocaleString()}</span>
                    </div>
                </div>
                <div className="text-xs text-gray-500 pt-1 border-t">
                    <strong>{pct}%</strong> del target del día. El target ajustado se recalcula automáticamente
                    según el acumulado semanal (estrategia adaptive).
                </div>
            </CardContent>
        </Card>
    );
};

const WeekCard = ({ stats }) => {
    const w = stats.week;
    const pct = Math.min(100, w.pct_of_weekly_target);
    const projectedPct = Math.min(150, (w.projected / w.target_weekly) * 100);
    const projOk = projectedPct >= 95 && projectedPct <= 110;
    const days = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
    const daysElapsed = 7 - w.days_remaining_incl_today;

    return (
        <Card data-testid="captacion-week-card">
            <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Activity className="w-4 h-4 text-gray-500" /> Semana ({w.monday} → {w.sunday})
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                <div>
                    <div className="flex items-baseline justify-between mb-1">
                        <span className="text-3xl font-bold tabular-nums">{w.accumulated.toLocaleString()}</span>
                        <span className="text-sm text-gray-500">
                            / {w.target_weekly.toLocaleString()} semanal
                        </span>
                    </div>
                    {/* Day-by-day bar */}
                    <div className="grid grid-cols-7 gap-1 mb-2">
                        {days.map((d, i) => (
                            <div key={d} className="flex flex-col items-center gap-1">
                                <div className={`h-8 w-full rounded ${
                                    i < daysElapsed ? 'bg-blue-500' :
                                    i === daysElapsed ? 'bg-amber-400' :
                                    'bg-gray-200'
                                }`} />
                                <span className="text-[10px] text-gray-500">{d}</span>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="rounded-md bg-gray-50 p-3 text-sm space-y-1">
                    <div className="flex justify-between">
                        <span className="text-gray-600">Días restantes (incl. hoy):</span>
                        <strong>{w.days_remaining_incl_today}</strong>
                    </div>
                    <div className="flex justify-between">
                        <span className="text-gray-600">Proyección semanal:</span>
                        <strong className={projOk ? 'text-emerald-600' : projectedPct < 95 ? 'text-amber-600' : 'text-red-600'}>
                            {w.projected.toLocaleString()} ({projectedPct.toFixed(0)}%)
                        </strong>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
};

const SparklineCard = ({ stats }) => {
    const data = stats.sparkline || [];
    const target = stats.today.target_daily;
    const max = Math.max(target, ...data.map((d) => d.packages_audited));
    const points = data.map((d, i) => {
        const x = (i / Math.max(1, data.length - 1)) * 100;
        const y = max === 0 ? 100 : 100 - (d.packages_audited / max) * 100;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');

    const targetY = max === 0 ? 100 : 100 - (target / max) * 100;
    const minY = max === 0 ? 100 : 100 - (stats.today.min_daily / max) * 100;
    const maxY = max === 0 ? 100 : 100 - (stats.today.max_daily / max) * 100;

    return (
        <Card data-testid="captacion-sparkline-card">
            <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold">Últimos {data.length} días</CardTitle>
            </CardHeader>
            <CardContent>
                <svg viewBox="0 0 100 100" className="w-full h-32" preserveAspectRatio="none">
                    {/* Band min-max */}
                    <rect x="0" y={maxY} width="100" height={minY - maxY} fill="rgba(34,197,94,0.06)" />
                    {/* Target line */}
                    <line x1="0" y1={targetY} x2="100" y2={targetY} stroke="rgba(34,197,94,0.45)" strokeDasharray="1,1" strokeWidth="0.4" />
                    {/* Data polyline */}
                    {points && (
                        <polyline points={points} fill="none" stroke="#2563eb" strokeWidth="0.7" vectorEffect="non-scaling-stroke" />
                    )}
                </svg>
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                    <span>{data[0]?.date}</span>
                    <span className="flex items-center gap-1">
                        <span className="inline-block w-2 h-2 bg-blue-600 rounded-full" /> Auditados
                        <span className="ml-3 inline-block w-2 h-px bg-emerald-500" /> Target
                    </span>
                    <span>{data[data.length - 1]?.date}</span>
                </div>
            </CardContent>
        </Card>
    );
};

const LastRunCard = ({ stats }) => {
    const lr = stats.last_run;
    if (!lr) {
        return (
            <Card>
                <CardContent className="pt-6 text-sm text-gray-500 flex items-center gap-2">
                    <Clock className="w-4 h-4" /> Aún no hay corridas registradas para este cliente.
                </CardContent>
            </Card>
        );
    }
    return (
        <Card data-testid="captacion-lastrun-card">
            <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-amber-500" /> Última corrida — {lr.ran_at?.slice(0, 16).replace('T', ' ')}
                </CardTitle>
            </CardHeader>
            <CardContent className="text-sm grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Elegibles" value={lr.eligible_count} />
                <Stat label="Seleccionadas" value={lr.selected_count} />
                <Stat label="Descartadas" value={lr.discarded_count} />
                <Stat
                    label="Paquetes seleccionados"
                    value={lr.knapsack?.selected_packages?.toLocaleString()}
                    sub={`target ajustado ${lr.knapsack?.adjusted_target?.toLocaleString()}`}
                />
                {lr.knapsack?.discard_reasons && Object.keys(lr.knapsack.discard_reasons).length > 0 && (
                    <div className="col-span-2 md:col-span-4 pt-2 text-xs text-gray-500">
                        <strong>Motivos de descarte:</strong> {Object.entries(lr.knapsack.discard_reasons).map(([k, v]) => `${k}=${v}`).join(' · ')}
                    </div>
                )}
            </CardContent>
        </Card>
    );
};

const Stat = ({ label, value, sub }) => (
    <div>
        <div className="text-2xl font-semibold tabular-nums">{value ?? '—'}</div>
        <div className="text-xs text-gray-500">{label}{sub ? ` · ${sub}` : ''}</div>
    </div>
);

const ConfigDialog = ({ open, onOpenChange, cfg, saving, onSave }) => {
    const [form, setForm] = useState(cfg);
    useEffect(() => { setForm(cfg); }, [cfg, open]);

    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

    // Live calculator
    const projectedWeekly = useMemo(() => (form.audit_target_packages_daily || 0) * 7, [form.audit_target_packages_daily]);
    const bandValid = useMemo(() => {
        return (form.audit_min_packages_daily ?? 0) <= (form.audit_target_packages_daily ?? 0)
            && (form.audit_target_packages_daily ?? 0) <= (form.audit_max_packages_daily ?? 0);
    }, [form]);

    const eligibilityArr = form.ingest_eligibility_states || ['in_progress'];

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>Configurar cohorte de captación</DialogTitle>
                </DialogHeader>

                <div className="space-y-5 py-2">
                    <Section title="Banda de paquetes diarios" subtitle="El sistema selecciona rutas hasta acumular el target ajustado. La banda evita desbordes (máx) y mantiene piso operativo (mín).">
                        <div className="grid grid-cols-3 gap-3">
                            <NumField label="Mínimo" value={form.audit_min_packages_daily}
                                onChange={(v) => set('audit_min_packages_daily', v)} testid="cfg-min" />
                            <NumField label="Target base" value={form.audit_target_packages_daily}
                                onChange={(v) => set('audit_target_packages_daily', v)} testid="cfg-target" highlight />
                            <NumField label="Máximo" value={form.audit_max_packages_daily}
                                onChange={(v) => set('audit_max_packages_daily', v)} testid="cfg-max" />
                        </div>
                        {!bandValid && (
                            <div className="mt-2 text-xs text-amber-600 flex items-center gap-1">
                                <AlertCircle className="w-3 h-3" /> Requiere: mín ≤ target ≤ máx
                            </div>
                        )}
                        <div className="mt-2 text-xs text-gray-500">
                            Con este target base, alcanzarás <strong className="text-gray-700">~{projectedWeekly.toLocaleString()}</strong> paquetes/semana en condiciones planas (sin ajuste).
                        </div>
                    </Section>

                    <Section title="Target semanal (calendar L–D)" subtitle="Si la semana va atrasada, el target ajustado del día sube hasta el máx. Si va sobrada, baja hasta el mín.">
                        <NumField label="Target semanal" value={form.audit_target_packages_weekly}
                            onChange={(v) => set('audit_target_packages_weekly', v)} testid="cfg-weekly" />
                        <div className="mt-2">
                            <Label className="text-xs">Estrategia de distribución</Label>
                            <Select value={form.audit_distribution_strategy} onValueChange={(v) => set('audit_distribution_strategy', v)}>
                                <SelectTrigger className="mt-1" data-testid="cfg-strategy">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="adaptive_calendar_week">Adaptive (recomendado)</SelectItem>
                                    <SelectItem value="flat">Flat (target fijo diario)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </Section>

                    <Section title="Hora de corte de ingesta" subtitle="A esta hora se ejecuta la selección y solo se consideran rutas con el estado operativo elegible.">
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label className="text-xs">Hora (CDMX)</Label>
                                <Input type="time" value={form.ingest_cutoff_time || '16:00'}
                                    onChange={(e) => set('ingest_cutoff_time', e.target.value)}
                                    data-testid="cfg-cutoff-time" />
                            </div>
                            <div>
                                <Label className="text-xs">Zona horaria</Label>
                                <Input value={form.ingest_cutoff_timezone || 'America/Mexico_City'}
                                    onChange={(e) => set('ingest_cutoff_timezone', e.target.value)}
                                    data-testid="cfg-tz" />
                            </div>
                        </div>
                    </Section>

                    <Section title="Estados elegibles del plan Routal" subtitle="Solo las rutas con estos estados a la hora de corte entran al pool de auditoría.">
                        <div className="space-y-2">
                            {PLAN_STATE_OPTIONS.map((opt) => {
                                const checked = eligibilityArr.includes(opt.value);
                                return (
                                    <div key={opt.value} className="flex items-center justify-between border rounded px-3 py-2">
                                        <div>
                                            <div className="text-sm font-medium flex items-center gap-2">
                                                {opt.label}
                                                {opt.recommended && (
                                                    <Badge className="bg-emerald-100 text-emerald-700 text-[10px] py-0">recomendado</Badge>
                                                )}
                                            </div>
                                        </div>
                                        <Switch
                                            checked={checked}
                                            data-testid={`cfg-elig-${opt.value}`}
                                            onCheckedChange={(c) => {
                                                if (c) set('ingest_eligibility_states', Array.from(new Set([...eligibilityArr, opt.value])));
                                                else set('ingest_eligibility_states', eligibilityArr.filter((x) => x !== opt.value));
                                            }}
                                        />
                                    </div>
                                );
                            })}
                        </div>
                    </Section>

                    <Section title="Salvaguardas">
                        <div>
                            <Label className="text-xs">Tolerancia de overshoot (banda flexible al alcanzar target)</Label>
                            <div className="flex items-center gap-3 mt-1">
                                <Slider
                                    value={[Math.round((form.audit_overshoot_tolerance ?? 0.1) * 100)]}
                                    max={50}
                                    min={0}
                                    step={1}
                                    onValueChange={(v) => set('audit_overshoot_tolerance', (v[0] || 0) / 100)}
                                    className="flex-1"
                                    data-testid="cfg-tolerance"
                                />
                                <span className="text-sm tabular-nums w-12 text-right">
                                    {Math.round((form.audit_overshoot_tolerance ?? 0.1) * 100)}%
                                </span>
                            </div>
                        </div>
                        <div className="mt-3">
                            <NumField label="Circuit breaker IA (paquetes 'Evaluando' simultáneos)"
                                value={form.audit_safety_circuit_breaker}
                                onChange={(v) => set('audit_safety_circuit_breaker', v)}
                                testid="cfg-circuit"
                            />
                        </div>
                    </Section>

                    <Section title="Activación">
                        <div className="flex items-center justify-between border rounded px-3 py-2">
                            <div>
                                <div className="text-sm font-medium">Selección automática</div>
                                <div className="text-xs text-gray-500">El scheduler corre solo a la hora configurada.</div>
                            </div>
                            <Switch
                                checked={!!form.selection_enabled}
                                onCheckedChange={(c) => set('selection_enabled', c)}
                                data-testid="cfg-selection-enabled"
                            />
                        </div>
                    </Section>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="cfg-cancel">Cancelar</Button>
                    <Button
                        onClick={() => onSave({
                            audit_target_packages_daily: form.audit_target_packages_daily,
                            audit_min_packages_daily: form.audit_min_packages_daily,
                            audit_max_packages_daily: form.audit_max_packages_daily,
                            audit_target_packages_weekly: form.audit_target_packages_weekly,
                            audit_overshoot_tolerance: form.audit_overshoot_tolerance,
                            audit_distribution_strategy: form.audit_distribution_strategy,
                            audit_safety_circuit_breaker: form.audit_safety_circuit_breaker,
                            ingest_cutoff_time: form.ingest_cutoff_time,
                            ingest_cutoff_timezone: form.ingest_cutoff_timezone,
                            ingest_eligibility_states: form.ingest_eligibility_states,
                            selection_enabled: form.selection_enabled,
                        })}
                        disabled={saving || !bandValid}
                        data-testid="cfg-save"
                    >
                        {saving ? 'Guardando...' : 'Guardar'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};

const Section = ({ title, subtitle, children }) => (
    <div className="space-y-1">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
        <div className="mt-2">{children}</div>
    </div>
);

const NumField = ({ label, value, onChange, testid, highlight = false }) => (
    <div>
        <Label className="text-xs">{label}</Label>
        <Input
            type="number"
            value={value ?? ''}
            onChange={(e) => onChange(parseInt(e.target.value || '0', 10))}
            className={`mt-1 ${highlight ? 'border-amber-400 ring-1 ring-amber-200' : ''}`}
            data-testid={testid}
        />
    </div>
);

export default Captacion;
