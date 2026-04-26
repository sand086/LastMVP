import React, { useState, useEffect, useCallback } from 'react';
import {
    Loader2, ShieldAlert, ClipboardCheck, Clock, Users, Save,
    PlayCircle, RefreshCw, AlertTriangle, CheckCircle2,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { toast } from 'sonner';
import {
    listClientConfigs, getClients, patchClientConfig,
    runSelection, getSelectionSummary,
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
    const [schedTime, setSchedTime] = useState(cfg.scheduler_time ?? '06:00');
    const [active, setActive] = useState(cfg.active ?? true);
    const [saving, setSaving] = useState(false);
    const [running, setRunning] = useState(false);

    const dirty = (
        enabled !== (cfg.selection_enabled ?? false) ||
        Number(maxDaily) !== (cfg.max_daily_audits ?? 30) ||
        schedTime !== (cfg.scheduler_time ?? '06:00') ||
        active !== (cfg.active ?? true)
    );

    const handleSave = async () => {
        setSaving(true);
        try {
            const md = parseInt(maxDaily, 10);
            if (!md || md <= 0 || md > 500) {
                toast.error('max_daily_audits debe estar entre 1 y 500');
                return;
            }
            if (!/^\d{2}:\d{2}$/.test(schedTime)) {
                toast.error('Hora debe tener formato HH:MM (ej. 06:00)');
                return;
            }
            await patchClientConfig(client.id, {
                selection_enabled: enabled,
                max_daily_audits: md,
                scheduler_time: schedTime,
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
                        Hora del scheduler (CDMX)
                    </Label>
                    <Input
                        type="time"
                        value={schedTime}
                        onChange={(e) => setSchedTime(e.target.value)}
                        disabled={!enabled}
                        className="font-mono"
                        data-testid={`scheduler-time-${client.id}`}
                    />
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
