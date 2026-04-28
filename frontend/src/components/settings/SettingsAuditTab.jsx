import React, { useState, useEffect, useCallback } from 'react';
import {
    Loader2, ShieldAlert, ClipboardCheck, Clock, Users, Save,
    PlayCircle, RefreshCw, AlertTriangle, CheckCircle2, CalendarRange,
    Download, CalendarSync,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { toast } from 'sonner';
import {
    listClientConfigs, getClients, patchClientConfig,
    runSelection, runSelectionRange, backfillSelectionFromRoutal,
    reconcileJourneyDates, getSelectionSummary,
} from '../../lib/api';

const formatDate = (d) => {
    if (!d) return '—';
    try {
        return new Date(d).toLocaleString('es-MX', {
            day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
        });
    } catch { return String(d); }
};

const SettingsAuditTab = ({ isDeveloper }) => {
    const [clients, setClients] = useState([]);
    const [configs, setConfigs] = useState({}); // by client_id
    const [summaries, setSummaries] = useState({}); // by client_id (today)
    const [loading, setLoading] = useState(true);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [clientsRes, configsRes] = await Promise.allSettled([
                getClients(),
                listClientConfigs(),
            ]);
            const clientList = clientsRes.status === 'fulfilled' ? (clientsRes.value.data || []) : [];
            setClients(clientList);

            const cfgMap = {};
            if (configsRes.status === 'fulfilled') {
                (configsRes.value.data?.data || []).forEach(c => { cfgMap[c.client_id] = c; });
            }
            setConfigs(cfgMap);

            // Fetch summaries for clients with selection_enabled
            const enabled = Object.values(cfgMap).filter(c => c.selection_enabled);
            const summaryResults = await Promise.allSettled(
                enabled.map(c => getSelectionSummary(c.client_id))
            );
            const sumMap = {};
            enabled.forEach((c, i) => {
                if (summaryResults[i].status === 'fulfilled') {
                    sumMap[c.client_id] = summaryResults[i].value.data;
                }
            });
            setSummaries(sumMap);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { if (isDeveloper) fetchAll(); }, [isDeveloper, fetchAll]);

    if (!isDeveloper) {
        return (
            <div
                data-testid="audit-restricted"
                className="bg-amber-50 border border-amber-200 rounded-md p-6 text-center"
            >
                <ShieldAlert className="w-10 h-10 text-amber-600 mx-auto mb-3" />
                <h3 className="font-semibold text-amber-900 mb-1">Acceso restringido</h3>
                <p className="text-sm text-amber-800">Solo desarrolladores pueden gestionar la selección de auditorías.</p>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12 text-slate-500" data-testid="audit-loading">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                Cargando configuración...
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="audit-tab">
            <div className="bg-blue-50 border border-blue-200 rounded-md p-4 text-sm text-blue-900">
                <div className="flex items-start gap-2">
                    <ClipboardCheck className="w-4 h-4 flex-shrink-0 mt-0.5 text-blue-600" />
                    <div>
                        <p className="font-semibold mb-1">Selección de auditorías por cliente (SEL01)</p>
                        <p className="text-xs leading-relaxed">
                            Cuando <code className="bg-white px-1 rounded">selection_enabled = true</code>, los planes de Routal se almacenan en staging
                            y un scheduler diario (hora configurable, tz CDMX) elige rotativamente hasta <strong>max_daily_audits</strong> drivers
                            usando el algoritmo en 2 fases: (1) drivers no auditados ayer, (2) rotación por count 30d.
                            Si <code className="bg-white px-1 rounded">selection_enabled = false</code>, se crean Journeys directamente como antes.
                        </p>
                    </div>
                </div>
            </div>

            {clients.length === 0 ? (
                <div className="text-center py-12 text-slate-500" data-testid="audit-empty">
                    No hay clientes configurados.
                </div>
            ) : (
                <div className="space-y-4">
                    {clients.map(client => (
                        <ClientAuditCard
                            key={client.id}
                            client={client}
                            config={configs[client.id]}
                            summary={summaries[client.id]}
                            onChanged={fetchAll}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};


const ClientAuditCard = ({ client, config, summary, onChanged }) => {
    const cfg = config || {};
    const [enabled, setEnabled] = useState(cfg.selection_enabled ?? false);
    const [maxDaily, setMaxDaily] = useState(cfg.max_daily_audits ?? 30);
    const initialTimes = (cfg.scheduler_times && cfg.scheduler_times.length ? cfg.scheduler_times : [cfg.scheduler_time || '06:00']);
    const [schedTime, setSchedTime] = useState(initialTimes[0]);
    const [schedTimes, setSchedTimes] = useState(initialTimes);
    const [newSchedTime, setNewSchedTime] = useState('');
    const [active, setActive] = useState(cfg.active ?? true);
    const [saving, setSaving] = useState(false);
    const [running, setRunning] = useState(false);
    const [runningRange, setRunningRange] = useState(false);
    const [backfilling, setBackfilling] = useState(false);
    const [reconciling, setReconciling] = useState(false);
    const [reconcileResult, setReconcileResult] = useState(null);
    const [reconcileDays, setReconcileDays] = useState(30);
    const [showReconcile, setShowReconcile] = useState(false);
    const [showRange, setShowRange] = useState(false);
    const today = new Date().toISOString().slice(0, 10);
    const sevenDaysAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
    const [rangeFrom, setRangeFrom] = useState(sevenDaysAgo);
    const [rangeTo, setRangeTo] = useState(today);
    const [rangeResult, setRangeResult] = useState(null);

    const sortedSchedTimes = JSON.stringify([...schedTimes].sort());
    const sortedInitial = JSON.stringify([...initialTimes].sort());
    const dirty = (
        enabled !== (cfg.selection_enabled ?? false) ||
        Number(maxDaily) !== (cfg.max_daily_audits ?? 30) ||
        sortedSchedTimes !== sortedInitial ||
        active !== (cfg.active ?? true)
    );

    const handleAddTime = () => {
        if (!/^\d{2}:\d{2}$/.test(newSchedTime)) {
            toast.error('Formato HH:MM');
            return;
        }
        if (schedTimes.includes(newSchedTime)) {
            toast.error('Esa hora ya existe');
            return;
        }
        if (schedTimes.length >= 10) {
            toast.error('Máximo 10 cortes diarios');
            return;
        }
        setSchedTimes([...schedTimes, newSchedTime].sort());
        setNewSchedTime('');
    };

    const handleRemoveTime = (t) => {
        if (schedTimes.length <= 1) {
            toast.error('Debe haber al menos una hora');
            return;
        }
        setSchedTimes(schedTimes.filter(x => x !== t));
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const md = parseInt(maxDaily, 10);
            if (!md || md <= 0 || md > 500) {
                toast.error('max_daily_audits debe estar entre 1 y 500');
                return;
            }
            for (const t of schedTimes) {
                if (!/^\d{2}:\d{2}$/.test(t)) {
                    toast.error(`Hora inválida: ${t}`);
                    return;
                }
            }
            await patchClientConfig(client.id, {
                selection_enabled: enabled,
                max_daily_audits: md,
                scheduler_times: schedTimes,
                active,
            });
            toast.success(`Configuración guardada para ${client.name}`);
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error guardando configuración');
        } finally {
            setSaving(false);
        }
    };

    const handleRunNow = async () => {
        setRunning(true);
        try {
            const r = await runSelection(client.id);
            const d = r.data;
            toast.success(
                `Selección ejecutada: ${d.selected}/${d.total} drivers (P1: ${d.phase_1}, P2: ${d.phase_2})`
            );
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error ejecutando selección');
        } finally {
            setRunning(false);
        }
    };

    const handleRunRange = async () => {
        if (!rangeFrom || !rangeTo) {
            toast.error('Selecciona ambas fechas');
            return;
        }
        if (rangeFrom > rangeTo) {
            toast.error('La fecha inicial debe ser anterior o igual a la final');
            return;
        }
        setRunningRange(true);
        setRangeResult(null);
        try {
            const r = await runSelectionRange(client.id, rangeFrom, rangeTo);
            const d = r.data;
            setRangeResult(d);
            toast.success(
                `Rango procesado: ${d.days_in_range} días · ${d.selected}/${d.total} drivers seleccionados`
            );
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error ejecutando rango');
        } finally {
            setRunningRange(false);
        }
    };

    const handleBackfill = async () => {
        if (!rangeFrom || !rangeTo) {
            toast.error('Selecciona ambas fechas');
            return;
        }
        if (rangeFrom > rangeTo) {
            toast.error('La fecha inicial debe ser anterior o igual a la final');
            return;
        }
        const ok = window.confirm(
            `Backfill desde Routal: descargará planes históricos del rango ${rangeFrom} → ${rangeTo} ` +
            `vía API (sin esperar webhooks) y ejecutará el algoritmo SEL01 día por día.\n\n` +
            `Cap de seguridad: máximo 200 planes por llamada. Si tu flota es grande, usa rangos más cortos.\n\n` +
            `¿Continuar?`
        );
        if (!ok) return;
        setBackfilling(true);
        setRangeResult(null);
        try {
            const r = await backfillSelectionFromRoutal(client.id, rangeFrom, rangeTo, true);
            const d = r.data;
            setRangeResult({
                days_in_range: (d.selection_results || []).length,
                days_with_data: (d.selection_results || []).filter(x => x.total > 0).length,
                total: d.selection_totals?.total || 0,
                selected: d.selection_totals?.selected || 0,
                phase_1: d.selection_totals?.phase_1 || 0,
                phase_2: d.selection_totals?.phase_2 || 0,
                unselected: (d.selection_totals?.total || 0) - (d.selection_totals?.selected || 0),
                results: (d.selection_results || []).map(x => ({ ...x, ok: x.ok, error: x.error })),
                _backfill: {
                    pages_scanned: d.pages_scanned,
                    plans_scanned: d.plans_scanned,
                    plans_in_range: d.plans_in_range,
                    staged: d.staged,
                    skipped_no_driver: d.skipped_no_driver,
                    skipped_error: d.skipped_error,
                    truncated: d.truncated,
                },
            });
            toast.success(
                `Backfill OK: ${d.staged} planes hidratados · ${d.selection_totals?.selected || 0}/${d.selection_totals?.total || 0} drivers seleccionados` +
                (d.truncated ? ' · ⚠ truncado al cap (200)' : '')
            );
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error en backfill');
        } finally {
            setBackfilling(false);
        }
    };

    const handleReconcileDryRun = async () => {
        setReconciling(true);
        setReconcileResult(null);
        try {
            const r = await reconcileJourneyDates(client.id, reconcileDays, true);
            setReconcileResult(r.data);
            const found = r.data.discrepancies_found || 0;
            if (found === 0) {
                toast.success(`Sin discrepancias en ${r.data.journeys_checked} journeys revisados`);
            } else {
                toast.warning(`${found} discrepancia(s) detectada(s) de ${r.data.journeys_checked} journeys`);
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error consultando reconciliación');
        } finally {
            setReconciling(false);
        }
    };

    const handleReconcileApply = async () => {
        if (!reconcileResult || !reconcileResult.discrepancies_found) {
            toast.error('Primero corre un dry-run y revisa las discrepancias');
            return;
        }
        const ok = window.confirm(
            `Se actualizarán ${reconcileResult.discrepancies_found} journey(s) para que su fecha coincida con Routal.\n\n` +
            `Esto afecta solo el campo journey.date (no toca paquetes ni incidencias).\n\n¿Continuar?`
        );
        if (!ok) return;
        setReconciling(true);
        try {
            const r = await reconcileJourneyDates(client.id, reconcileDays, false);
            setReconcileResult(r.data);
            toast.success(`✔ ${r.data.fixed} journey(s) corregido(s) · ${r.data.errors} error(es)`);
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error aplicando reconciliación');
        } finally {
            setReconciling(false);
        }
    };

    const phaseColor = (phase) => ({
        phase_1: 'bg-emerald-100 text-emerald-700',
        phase_2: 'bg-violet-100 text-violet-700',
        mixed: 'bg-blue-100 text-blue-700',
        none: 'bg-slate-100 text-slate-500',
    }[phase] || 'bg-slate-100 text-slate-500');

    return (
        <div
            data-testid={`audit-card-${client.id}`}
            className="bg-white border border-slate-200 rounded-md p-5 hover:shadow-sm transition-shadow"
        >
            <div className="flex items-start justify-between mb-4 pb-4 border-b border-slate-100">
                <div>
                    <h3 className="font-semibold text-slate-900 text-base">{client.name}</h3>
                    <p className="text-xs text-slate-500 mt-0.5 font-mono">{client.id.slice(0, 18)}…</p>
                </div>
                <div className="flex items-center gap-2">
                    {enabled ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-emerald-100 text-emerald-700"
                              data-testid={`audit-enabled-badge-${client.id}`}>
                            Selección ON
                        </span>
                    ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-slate-100 text-slate-500">
                            Auto-crear (legacy)
                        </span>
                    )}
                </div>
            </div>

            {/* Configuration */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div className="space-y-1">
                    <Label className="text-xs text-slate-600 flex items-center gap-1.5">
                        <Users className="w-3 h-3" />
                        Drivers/día (máx)
                    </Label>
                    <Input
                        type="number"
                        min="1"
                        max="500"
                        value={maxDaily}
                        onChange={(e) => setMaxDaily(e.target.value)}
                        disabled={!enabled}
                        className="font-mono"
                        data-testid={`max-daily-${client.id}`}
                    />
                </div>
                <div className="space-y-1">
                    <Label className="text-xs text-slate-600 flex items-center gap-1.5">
                        <Clock className="w-3 h-3" />
                        Cortes horarios (CDMX)
                    </Label>
                    <div className="flex flex-wrap gap-1.5 items-center bg-white px-2 py-1.5 rounded-md border border-slate-200 min-h-[36px]">
                        {schedTimes.map(t => (
                            <span
                                key={t}
                                className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded font-mono text-xs"
                                data-testid={`sched-time-chip-${client.id}-${t}`}
                            >
                                {t}
                                {schedTimes.length > 1 && (
                                    <button
                                        type="button"
                                        onClick={() => handleRemoveTime(t)}
                                        disabled={!enabled}
                                        className="text-emerald-500 hover:text-red-600 disabled:opacity-30"
                                        title={`Quitar ${t}`}
                                    >×</button>
                                )}
                            </span>
                        ))}
                        <input
                            type="time"
                            value={newSchedTime}
                            onChange={(e) => setNewSchedTime(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    e.preventDefault();
                                    handleAddTime();
                                }
                            }}
                            disabled={!enabled || schedTimes.length >= 10}
                            className="text-xs font-mono border-0 outline-none bg-transparent w-[80px]"
                            data-testid={`new-sched-time-${client.id}`}
                        />
                        <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={handleAddTime}
                            disabled={!enabled || !newSchedTime || schedTimes.length >= 10}
                            className="h-6 px-1.5 text-xs"
                            data-testid={`add-sched-time-${client.id}`}
                        >+</Button>
                    </div>
                </div>
                <div className="space-y-1">
                    <Label className="text-xs text-slate-600">Selección habilitada</Label>
                    <div className="flex items-center justify-between bg-slate-50 px-3 py-2 rounded-md border border-slate-200">
                        <span className="text-xs text-slate-700">
                            {enabled ? 'Algoritmo activo' : 'Auto-crear directo'}
                        </span>
                        <Switch
                            checked={enabled}
                            onCheckedChange={setEnabled}
                            data-testid={`selection-enabled-${client.id}`}
                        />
                    </div>
                </div>
            </div>

            {/* Today summary */}
            {enabled && summary && (
                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 mb-4" data-testid={`audit-summary-${client.id}`}>
                    <div className="flex items-center justify-between mb-2">
                        <p className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
                            Resumen de hoy ({summary.date})
                        </p>
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${phaseColor(summary.phase_applied)}`}>
                            {summary.phase_applied}
                        </span>
                    </div>
                    <div className="grid grid-cols-4 gap-2 text-sm">
                        <div className="text-center">
                            <p className="font-mono font-bold text-lg text-slate-900">{summary.total_plans}</p>
                            <p className="text-[10px] text-slate-500 uppercase">Planes</p>
                        </div>
                        <div className="text-center">
                            <p className="font-mono font-bold text-lg text-emerald-700">{summary.selected}</p>
                            <p className="text-[10px] text-slate-500 uppercase">Seleccionados</p>
                        </div>
                        <div className="text-center">
                            <p className="font-mono font-bold text-lg text-slate-500">{summary.unselected}</p>
                            <p className="text-[10px] text-slate-500 uppercase">No selec.</p>
                        </div>
                        <div className="text-center">
                            <p className="font-mono text-xs text-slate-700">P1: <strong>{summary.phase_1}</strong></p>
                            <p className="font-mono text-xs text-slate-700">P2: <strong>{summary.phase_2}</strong></p>
                        </div>
                    </div>
                    {summary.last_scheduled_run_date && (
                        <p className="text-[10px] text-slate-400 mt-2 text-right">
                            Última ejecución scheduler: {summary.last_scheduled_run_date} · {formatDate(cfg.last_scheduled_run_at)}
                        </p>
                    )}
                </div>
            )}

            {enabled && summary?.total_plans > summary?.max_daily_audits * 3 && (
                <div className="flex items-start gap-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800 mb-3">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>
                        Flota ({summary.total_plans}) supera 3× max_daily ({summary.max_daily_audits}). La rotación cubrirá lentamente la flotilla.
                    </span>
                </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-3 border-t border-slate-100">
                <Button
                    onClick={handleSave}
                    disabled={saving || !dirty}
                    size="sm"
                    className="bg-slate-900 hover:bg-slate-800 text-white"
                    data-testid={`save-audit-${client.id}`}
                >
                    {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Save className="w-3.5 h-3.5 mr-1.5" />}
                    Guardar
                </Button>
                {enabled && (
                    <Button
                        onClick={handleRunNow}
                        disabled={running}
                        size="sm"
                        variant="outline"
                        data-testid={`run-selection-${client.id}`}
                    >
                        {running ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <PlayCircle className="w-3.5 h-3.5 mr-1.5" />}
                        Ejecutar ahora
                    </Button>
                )}
                {enabled && (
                    <Button
                        onClick={() => setShowRange(v => !v)}
                        size="sm"
                        variant="outline"
                        className={showRange ? 'bg-slate-100' : ''}
                        data-testid={`toggle-range-${client.id}`}
                    >
                        <CalendarRange className="w-3.5 h-3.5 mr-1.5" />
                        Recuperar rango
                    </Button>
                )}
                {enabled && (
                    <Button
                        onClick={() => setShowReconcile(v => !v)}
                        size="sm"
                        variant="outline"
                        className={showReconcile ? 'bg-slate-100' : ''}
                        title="Compara journey.date contra Routal execution_date y corrige discrepancias"
                        data-testid={`toggle-reconcile-${client.id}`}
                    >
                        <CalendarSync className="w-3.5 h-3.5 mr-1.5" />
                        Reconciliar fechas
                    </Button>
                )}
                <Button
                    onClick={() => onChanged?.()}
                    size="sm"
                    variant="ghost"
                    className="ml-auto text-slate-500"
                    data-testid={`refresh-audit-${client.id}`}
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                </Button>
            </div>

            {/* Range picker */}
            {enabled && showRange && (
                <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-md" data-testid={`range-panel-${client.id}`}>
                    <div className="flex items-start gap-2 mb-3 text-xs text-blue-900">
                        <CalendarRange className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        <div>
                            <p className="font-semibold">Recuperar rutas en rango histórico</p>
                            <p className="text-[11px] mt-0.5 leading-relaxed">
                                <strong>Procesar staged:</strong> re-ejecuta el algoritmo SEL01 sobre los planes ya guardados en <code className="bg-white px-1 rounded">routal_daily_plans</code> (recibidos vía webhook).<br />
                                <strong>Backfill Routal:</strong> descarga planes históricos consultando la API <code className="bg-white px-1 rounded">GET /v2/plans</code> directamente, los hidrata como si fueran webhooks, y luego corre SEL01 día por día. Útil cuando activaste <em>selection_enabled</em> recientemente y no tienes histórico. Idempotente · cap 200 planes por llamada · máx 90 días.
                            </p>
                        </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
                        <div className="space-y-1">
                            <Label className="text-xs text-slate-700">Desde</Label>
                            <Input
                                type="date"
                                value={rangeFrom}
                                max={today}
                                onChange={(e) => setRangeFrom(e.target.value)}
                                className="font-mono"
                                data-testid={`range-from-${client.id}`}
                            />
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs text-slate-700">Hasta</Label>
                            <Input
                                type="date"
                                value={rangeTo}
                                max={today}
                                onChange={(e) => setRangeTo(e.target.value)}
                                className="font-mono"
                                data-testid={`range-to-${client.id}`}
                            />
                        </div>
                        <div className="flex items-end">
                            <Button
                                onClick={handleRunRange}
                                disabled={runningRange || backfilling}
                                size="sm"
                                variant="outline"
                                className="w-full"
                                title="Re-ejecuta el algoritmo solo sobre planes ya staged en routal_daily_plans"
                                data-testid={`run-range-${client.id}`}
                            >
                                {runningRange ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <PlayCircle className="w-3.5 h-3.5 mr-1.5" />}
                                Procesar staged
                            </Button>
                        </div>
                        <div className="flex items-end">
                            <Button
                                onClick={handleBackfill}
                                disabled={runningRange || backfilling}
                                size="sm"
                                className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                                title="Descarga planes históricos de Routal vía API y los hidrata en routal_daily_plans, luego ejecuta SEL01"
                                data-testid={`backfill-${client.id}`}
                            >
                                {backfilling ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Download className="w-3.5 h-3.5 mr-1.5" />}
                                Backfill Routal
                            </Button>
                        </div>
                    </div>

                    {rangeResult && (
                        <div className="bg-white rounded p-2 text-xs space-y-1" data-testid={`range-result-${client.id}`}>
                            {rangeResult._backfill && (
                                <div className="bg-blue-50 border border-blue-200 rounded px-2 py-1.5 mb-1 text-[10px] text-blue-900">
                                    <strong>Backfill Routal:</strong> {rangeResult._backfill.staged} planes hidratados de {rangeResult._backfill.plans_in_range} en rango
                                    ({rangeResult._backfill.pages_scanned} pág. · {rangeResult._backfill.plans_scanned} scaneados)
                                    {rangeResult._backfill.skipped_no_driver > 0 && <> · {rangeResult._backfill.skipped_no_driver} sin driver</>}
                                    {rangeResult._backfill.skipped_error > 0 && <> · {rangeResult._backfill.skipped_error} con error</>}
                                    {rangeResult._backfill.truncated && <span className="ml-1 text-amber-700 font-semibold">⚠ truncado al cap 200</span>}
                                </div>
                            )}
                            <div className="flex justify-between font-semibold text-slate-800">
                                <span>{rangeResult.days_in_range} días procesados ({rangeResult.days_with_data} con datos)</span>
                                <span className="text-emerald-700">{rangeResult.selected}/{rangeResult.total} drivers</span>
                            </div>
                            <div className="text-[10px] text-slate-500">
                                P1: {rangeResult.phase_1} · P2: {rangeResult.phase_2} · No selec: {rangeResult.unselected}
                            </div>
                            <details className="mt-1">
                                <summary className="cursor-pointer text-slate-600 hover:text-slate-900 text-[11px]">Ver detalle por día</summary>
                                <div className="mt-1 max-h-40 overflow-y-auto space-y-0.5">
                                    {rangeResult.results.map(r => (
                                        <div key={r.date} className={`flex justify-between font-mono text-[10px] px-1 py-0.5 ${r.ok ? '' : 'bg-red-50 text-red-700'}`}>
                                            <span>{r.date}</span>
                                            <span className="text-slate-600">
                                                {r.ok ? `${r.selected}/${r.total} (P1:${r.phase_1} P2:${r.phase_2})` : (r.error || 'error')}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </details>
                        </div>
                    )}
                </div>
            )}

            {/* Reconcile dates panel */}
            {enabled && showReconcile && (
                <div className="mt-3 p-3 bg-violet-50 border border-violet-200 rounded-md" data-testid={`reconcile-panel-${client.id}`}>
                    <div className="flex items-start gap-2 mb-3 text-xs text-violet-900">
                        <CalendarSync className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        <div>
                            <p className="font-semibold">Reconciliar fechas con Routal</p>
                            <p className="text-[11px] mt-0.5 leading-relaxed">
                                Compara <code className="bg-white px-1 rounded">journey.date</code> contra <code className="bg-white px-1 rounded">execution_date</code> de Routal (autoritativo). Detecta journeys con offset de fecha (típicamente 1 día por timezone/payload inconsistente). <strong>Dry-run primero</strong> para revisar; luego <strong>Aplicar fix</strong>.
                            </p>
                        </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                        <div className="space-y-1">
                            <Label className="text-xs text-slate-700">Días hacia atrás</Label>
                            <Input
                                type="number"
                                min="1"
                                max="365"
                                value={reconcileDays}
                                onChange={(e) => setReconcileDays(Number(e.target.value) || 30)}
                                className="font-mono"
                                data-testid={`reconcile-days-${client.id}`}
                            />
                        </div>
                        <div className="flex items-end">
                            <Button
                                onClick={handleReconcileDryRun}
                                disabled={reconciling}
                                size="sm"
                                variant="outline"
                                className="w-full"
                                data-testid={`reconcile-dryrun-${client.id}`}
                            >
                                {reconciling ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CalendarSync className="w-3.5 h-3.5 mr-1.5" />}
                                Detectar discrepancias
                            </Button>
                        </div>
                        <div className="flex items-end">
                            <Button
                                onClick={handleReconcileApply}
                                disabled={reconciling || !reconcileResult || !reconcileResult.discrepancies_found}
                                size="sm"
                                className="w-full bg-violet-600 hover:bg-violet-700 text-white disabled:opacity-50"
                                data-testid={`reconcile-apply-${client.id}`}
                            >
                                {reconciling ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                                Aplicar fix
                            </Button>
                        </div>
                    </div>

                    {reconcileResult && (
                        <div className="bg-white rounded p-2 text-xs space-y-2" data-testid={`reconcile-result-${client.id}`}>
                            <div className="flex justify-between font-semibold text-slate-800">
                                <span>
                                    {reconcileResult.journeys_checked} journeys revisados ·{' '}
                                    {reconcileResult.discrepancies_found > 0 ? (
                                        <span className="text-amber-700">{reconcileResult.discrepancies_found} discrepancia(s)</span>
                                    ) : (
                                        <span className="text-emerald-700">sin discrepancias ✓</span>
                                    )}
                                </span>
                                <span className="text-slate-500">
                                    {reconcileResult.dry_run ? 'dry-run' : `${reconcileResult.fixed} corregidos`}
                                    {reconcileResult.errors > 0 && ` · ${reconcileResult.errors} errores`}
                                </span>
                            </div>
                            {reconcileResult.discrepancies && reconcileResult.discrepancies.length > 0 && (
                                <div className="max-h-64 overflow-y-auto border-t border-slate-200 pt-1">
                                    <table className="w-full text-[10px] font-mono">
                                        <thead className="text-slate-500 sticky top-0 bg-white">
                                            <tr>
                                                <th className="text-left py-1">Driver</th>
                                                <th className="text-left">Plan Routal</th>
                                                <th className="text-center">LastMile</th>
                                                <th className="text-center">→ Routal</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {reconcileResult.discrepancies.map(d => (
                                                <tr key={d.journey_id} className="border-b border-slate-100 hover:bg-violet-50">
                                                    <td className="py-1 truncate max-w-[160px]" title={d.driver_name}>{d.driver_name || '—'}</td>
                                                    <td className="text-slate-500" title={d.label}>{d.routal_plan_id?.slice(0, 8)}…</td>
                                                    <td className="text-center text-red-600">{d.current_date}</td>
                                                    <td className="text-center text-emerald-700 font-semibold">{d.authoritative_date}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {enabled && summary?.selected > 0 && (
                <details className="mt-3 text-xs">
                    <summary className="cursor-pointer text-slate-600 hover:text-slate-900 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        Ver {summary.selected} drivers seleccionados hoy
                    </summary>
                    <div className="mt-2 max-h-48 overflow-y-auto bg-slate-50 rounded p-2 space-y-1">
                        {summary.drivers_selected.map(d => (
                            <div key={d.driver_id} className="flex items-center justify-between text-[11px]">
                                <span className="font-mono text-slate-700">{d.driver_name || d.driver_id}</span>
                                <span className="flex items-center gap-2 text-slate-500">
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] ${phaseColor(d.phase)}`}>{d.phase}</span>
                                    <span>{d.audit_count_30d}/30d</span>
                                </span>
                            </div>
                        ))}
                    </div>
                </details>
            )}
        </div>
    );
};

export default SettingsAuditTab;
