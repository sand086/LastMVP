import React, { useState, useEffect, useCallback } from 'react';
import {
    Eye, EyeOff, Save, Loader2, CheckCircle2, AlertTriangle, Trash2, Copy, Plug, RefreshCw,
    GitBranch, ChevronDown, ChevronUp,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Switch } from '../ui/switch';
import { toast } from 'sonner';
import {
    upsertIntegration, updateIntegrationStatus, testIntegration,
    deleteIntegration, getRoutalWebhookStatus, migrateRoutalLegacyJourneys,
    restoreOrphanIncidents,
} from '../../lib/api';

const PLACEHOLDER_MASK = '••••••••••••';

const ClientIntegrationCard = ({ client, integration, onChanged }) => {
    const existing = integration || {};
    const summary = existing.credentials_summary || {};

    const [type, setType] = useState(existing.integration_type || 'manual');
    const [status, setStatus] = useState(existing.status || 'inactive');
    const [apiKey, setApiKey] = useState('');
    const [apiKeyVisible, setApiKeyVisible] = useState(false);
    const [projectId, setProjectId] = useState(summary.routal_project_id || '');
    const [webhookSecret, setWebhookSecret] = useState('');
    const [webhookSecretVisible, setWebhookSecretVisible] = useState(false);

    const [config, setConfig] = useState({
        auto_create_journeys: existing.config?.auto_create_journeys ?? true,
        auto_close_journeys: existing.config?.auto_close_journeys ?? true,
        sync_drivers: existing.config?.sync_drivers ?? true,
    });

    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);
    const [whStatus, setWhStatus] = useState(null);

    // iter80 — Migración legacy plan→route
    const [showMigrate, setShowMigrate] = useState(false);
    const [migrateDays, setMigrateDays] = useState(30);
    const [migrateRunning, setMigrateRunning] = useState(false);
    const [migrateDryResult, setMigrateDryResult] = useState(null);
    const [migrateAppliedResult, setMigrateAppliedResult] = useState(null);
    // iter82 — Restaurar incidencias huérfanas (bug iter79)
    const [restoreRunning, setRestoreRunning] = useState(false);
    const [restoreResult, setRestoreResult] = useState(null);

    const handleRestoreIncidents = async (dry = true) => {
        if (!existing.client_id) return;
        setRestoreRunning(true);
        if (dry) setRestoreResult(null);
        try {
            const r = await restoreOrphanIncidents(existing.client_id, dry, null);
            setRestoreResult(r.data);
            const found = r.data.orphan_incidents_found || 0;
            if (dry) {
                if (found === 0) toast.success('Sin incidencias huérfanas');
                else toast.warning(`${found} incidencia(s) huérfana(s) detectada(s)`);
            } else {
                const restored = (r.data.restored_by_tracking || 0) + (r.data.restored_by_fallback || 0);
                toast.success(`✔ ${restored} incidencia(s) restaurada(s) (${r.data.restored_by_tracking} tracking + ${r.data.restored_by_fallback} fallback)`);
                onChanged?.();
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error restaurando incidencias');
        } finally {
            setRestoreRunning(false);
        }
    };

    const handleMigrateDryRun = async () => {
        if (!existing.client_id) return;
        setMigrateRunning(true);
        setMigrateDryResult(null);
        setMigrateAppliedResult(null);
        try {
            const r = await migrateRoutalLegacyJourneys(existing.client_id, migrateDays, true, null);
            setMigrateDryResult(r.data);
            const found = r.data.scanned || 0;
            if (found === 0) {
                toast.success(`Sin journeys legacy en últimos ${migrateDays} días`);
            } else {
                toast.warning(`${found} journey(s) legacy detectada(s) — revisa antes de aplicar`);
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error en dry-run');
        } finally {
            setMigrateRunning(false);
        }
    };

    const handleMigrateApply = async () => {
        if (!migrateDryResult || !migrateDryResult.scanned) {
            toast.error('Primero corre el dry-run');
            return;
        }
        const ok = window.confirm(
            `Se migrarán ${migrateDryResult.scanned} journey(s) legacy del modelo plan→journey ` +
            `al modelo route→journey (1 journey por driver real). ` +
            `\n\nLas legacy se preservan con audit trail (migrated_to_journeys[]) y se ocultan de listas. ` +
            `\n\nPackages e incidents se reasignan a las journeys nuevas.\n\n¿Continuar?`
        );
        if (!ok) return;
        setMigrateRunning(true);
        try {
            const r = await migrateRoutalLegacyJourneys(existing.client_id, migrateDays, false, null);
            setMigrateAppliedResult(r.data);
            toast.success(
                `✔ ${r.data.migrated} legacy journeys migradas · ${r.data.packages_moved} pkgs movidos` +
                (r.data.errors ? ` · ${r.data.errors} error(es)` : '')
            );
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error aplicando migración');
        } finally {
            setMigrateRunning(false);
        }
    };

    const refreshWebhookStatus = useCallback(async () => {
        if (!existing.client_id || existing.integration_type !== 'routal') return;
        try {
            const r = await getRoutalWebhookStatus(existing.client_id);
            setWhStatus(r.data);
        } catch { /* ignore */ }
    }, [existing.client_id, existing.integration_type]);

    useEffect(() => { refreshWebhookStatus(); }, [refreshWebhookStatus]);

    const isDirty = (
        type !== (existing.integration_type || 'manual') ||
        status !== (existing.status || 'inactive') ||
        apiKey || webhookSecret ||
        projectId !== (summary.routal_project_id || '') ||
        config.auto_create_journeys !== (existing.config?.auto_create_journeys ?? true) ||
        config.auto_close_journeys !== (existing.config?.auto_close_journeys ?? true) ||
        config.sync_drivers !== (existing.config?.sync_drivers ?? true)
    );

    const handleSave = async () => {
        setSaving(true);
        try {
            const credentials = {};
            if (type === 'routal') {
                if (apiKey) credentials.routal_api_key = apiKey;
                if (projectId) credentials.routal_project_id = projectId;
                if (webhookSecret) credentials.routal_webhook_secret = webhookSecret;
            }
            const payload = {
                integration_type: type,
                credentials: Object.keys(credentials).length ? credentials : null,
                config,
                status,
            };
            await upsertIntegration(client.id, payload);
            toast.success(`Integración guardada para ${client.name}`);
            setApiKey('');
            setWebhookSecret('');
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error guardando integración');
        } finally {
            setSaving(false);
        }
    };

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const r = await testIntegration(client.id);
            setTestResult(r.data);
            const t = r.data.type || 'routal';
            if (r.data.ok) {
                if (t === 'kosmo') {
                    toast.success(`Kosmo OK · scraper ${r.data.scraper_status} · ${r.data.journeys_active_today} rutas hoy`);
                } else if (t === 'manual') {
                    toast.success(`Manual OK · ${r.data.recent_journeys_30d} rutas últimos 30d`);
                } else {
                    toast.success(`Conexión OK (${r.data.latency_ms}ms)`);
                }
            } else {
                toast.error(`Error: ${r.data.error}`);
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error probando conexión');
        } finally {
            setTesting(false);
        }
    };

    const handleToggleStatus = async () => {
        const next = status === 'active' ? 'inactive' : 'active';
        try {
            await updateIntegrationStatus(client.id, next);
            setStatus(next);
            toast.success(`Integración ${next === 'active' ? 'activada' : 'desactivada'}`);
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error cambiando estado');
        }
    };

    const handleDelete = async () => {
        if (!confirm(`¿Eliminar integración para ${client.name}? Las credenciales se borrarán.`)) return;
        try {
            await deleteIntegration(client.id);
            toast.success('Integración eliminada');
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error eliminando');
        }
    };

    const webhookUrl = whStatus?.webhook_url;
    const isRoutal = type === 'routal';

    return (
        <div
            data-testid={`integration-card-${client.id}`}
            className="bg-white border border-slate-200 rounded-md p-5 hover:shadow-sm transition-shadow"
        >
            {/* Header */}
            <div className="flex items-start justify-between mb-4 pb-4 border-b border-slate-100">
                <div>
                    <h3 className="font-semibold text-slate-900 text-base">{client.name}</h3>
                    <p className="text-xs text-slate-500 mt-0.5 font-mono">{client.id.slice(0, 18)}…</p>
                </div>
                <div className="flex items-center gap-2">
                    {existing.client_id && (
                        <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${
                                status === 'active' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
                            }`}
                            data-testid={`integration-status-${client.id}`}
                        >
                            {status === 'active' ? 'Activa' : status === 'testing' ? 'Pruebas' : 'Inactiva'}
                        </span>
                    )}
                </div>
            </div>

            {/* Type selector */}
            <div className="mb-4">
                <Label className="text-xs text-slate-600 mb-1.5 block">Tipo de integración</Label>
                <Select value={type} onValueChange={setType}>
                    <SelectTrigger data-testid={`integration-type-${client.id}`}>
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="manual">Manual (sin API)</SelectItem>
                        <SelectItem value="kosmo">Kosmo</SelectItem>
                        <SelectItem value="routal">Routal</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Routal credentials (only when type=routal) */}
            {isRoutal && (
                <div className="space-y-3 mb-4 p-3 bg-violet-50/50 border border-violet-100 rounded-md">
                    <div className="flex items-center gap-2 text-violet-800 text-xs font-semibold mb-1">
                        <Plug className="w-3.5 h-3.5" />
                        Credenciales Routal
                    </div>
                    <div>
                        <Label className="text-xs text-slate-600 mb-1 block">Project ID</Label>
                        <Input
                            value={projectId}
                            onChange={(e) => setProjectId(e.target.value)}
                            placeholder="proj_..."
                            className="font-mono text-xs"
                            data-testid={`routal-project-id-${client.id}`}
                        />
                    </div>
                    <div>
                        <Label className="text-xs text-slate-600 mb-1 block flex items-center justify-between">
                            <span>API Key {summary.has_api_key && <span className="text-emerald-600 ml-1">✓ Guardada</span>}</span>
                        </Label>
                        <div className="relative">
                            <Input
                                type={apiKeyVisible ? 'text' : 'password'}
                                value={apiKey}
                                onChange={(e) => setApiKey(e.target.value)}
                                placeholder={summary.has_api_key ? PLACEHOLDER_MASK : 'sk_live_...'}
                                className="font-mono text-xs pr-9"
                                data-testid={`routal-api-key-${client.id}`}
                            />
                            <button
                                type="button"
                                onClick={() => setApiKeyVisible(v => !v)}
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                data-testid={`routal-api-key-toggle-${client.id}`}
                            >
                                {apiKeyVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>
                    <div>
                        <Label className="text-xs text-slate-600 mb-1 block">
                            Webhook Secret {summary.has_webhook_secret && <span className="text-emerald-600 ml-1">✓ Guardado</span>}
                        </Label>
                        <div className="relative">
                            <Input
                                type={webhookSecretVisible ? 'text' : 'password'}
                                value={webhookSecret}
                                onChange={(e) => setWebhookSecret(e.target.value)}
                                placeholder={summary.has_webhook_secret ? PLACEHOLDER_MASK : 'whsec_...'}
                                className="font-mono text-xs pr-9"
                                data-testid={`routal-webhook-secret-${client.id}`}
                            />
                            <button
                                type="button"
                                onClick={() => setWebhookSecretVisible(v => !v)}
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                            >
                                {webhookSecretVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>

                    {webhookUrl && (
                        <div className="bg-white p-2 rounded border border-violet-100">
                            <Label className="text-xs text-slate-600 mb-1 block">Webhook URL para Routal</Label>
                            <div className="flex items-center gap-1">
                                <code className="text-[10.5px] text-slate-700 break-all flex-1 font-mono">{webhookUrl}</code>
                                <button
                                    type="button"
                                    onClick={() => { navigator.clipboard.writeText(webhookUrl); toast.success('Copiado'); }}
                                    className="text-violet-600 hover:text-violet-800 p-1"
                                    data-testid={`copy-webhook-url-${client.id}`}
                                >
                                    <Copy className="w-3 h-3" />
                                </button>
                            </div>
                        </div>
                    )}

                    {whStatus && (
                        <div className="text-[11px] text-slate-600 flex items-center gap-3 pt-2 border-t border-violet-100">
                            <span data-testid={`webhook-pending-${client.id}`}>
                                <strong>{whStatus.pending}</strong> pendientes
                            </span>
                            <span><strong className={whStatus.failed > 0 ? 'text-red-600' : ''}>{whStatus.failed}</strong> fallidos</span>
                            {whStatus.last_event_at && (
                                <span className="text-slate-400">Último: {new Date(whStatus.last_event_at).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}</span>
                            )}
                            <button onClick={refreshWebhookStatus} className="text-violet-600 hover:text-violet-800 ml-auto"><RefreshCw className="w-3 h-3" /></button>
                        </div>
                    )}
                </div>
            )}

            {/* Config switches */}
            {isRoutal && (
                <div className="space-y-2 mb-4">
                    {[
                        ['auto_create_journeys', 'Crear rutas automáticamente'],
                        ['auto_close_journeys', 'Cerrar rutas al completar plan'],
                        ['sync_drivers', 'Sincronizar drivers'],
                    ].map(([key, label]) => (
                        <div key={key} className="flex items-center justify-between">
                            <Label htmlFor={`${key}-${client.id}`} className="text-xs text-slate-700 cursor-pointer">{label}</Label>
                            <Switch
                                id={`${key}-${client.id}`}
                                checked={config[key]}
                                onCheckedChange={(v) => setConfig({ ...config, [key]: v })}
                                data-testid={`config-${key}-${client.id}`}
                            />
                        </div>
                    ))}
                </div>
            )}

            {/* Test result alert */}
            {testResult && (
                <div
                    className={`p-2 rounded-md text-xs flex items-start gap-2 mb-3 ${
                        testResult.ok ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-red-50 text-red-800 border border-red-200'
                    }`}
                    data-testid={`test-result-${client.id}`}
                >
                    {testResult.ok ? <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" /> : <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />}
                    <div className="flex-1">
                        {testResult.type === 'kosmo' && (
                            <>
                                <p className="font-semibold">Kosmo · scraper {testResult.scraper_status}</p>
                                <p className="mt-0.5">
                                    {testResult.last_sync_age_hours != null
                                        ? `Último sync hace ${testResult.last_sync_age_hours}h · `
                                        : 'Sin syncs · '}
                                    {testResult.journeys_active_today} rutas activas hoy · {testResult.journeys_pending_sync} pendientes
                                </p>
                            </>
                        )}
                        {testResult.type === 'manual' && (
                            <>
                                <p className="font-semibold">Manual · estado {testResult.manual_status}</p>
                                <p className="mt-0.5">
                                    {testResult.total_journeys} rutas total · {testResult.recent_journeys_30d} últimos 30d
                                    {testResult.latest_journey_date && ` · última: ${testResult.latest_journey_date}`}
                                </p>
                            </>
                        )}
                        {testResult.type !== 'kosmo' && testResult.type !== 'manual' && (
                            <span>
                                {testResult.ok ? `Conexión exitosa (${testResult.latency_ms}ms)` : testResult.error}
                            </span>
                        )}
                    </div>
                </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 pt-3 border-t border-slate-100">
                <Button
                    onClick={handleSave}
                    disabled={saving || !isDirty}
                    size="sm"
                    className="bg-slate-900 hover:bg-slate-800 text-white"
                    data-testid={`save-integration-${client.id}`}
                >
                    {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Save className="w-3.5 h-3.5 mr-1.5" />}
                    Guardar
                </Button>
                {existing.client_id && (
                    <Button
                        onClick={handleTest}
                        disabled={testing || (isRoutal && !summary.has_api_key)}
                        size="sm"
                        variant="outline"
                        data-testid={`test-integration-${client.id}`}
                    >
                        {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Plug className="w-3.5 h-3.5 mr-1.5" />}
                        Probar conexión
                    </Button>
                )}
                {existing.client_id && (
                    <>
                        <Button
                            onClick={handleToggleStatus}
                            size="sm"
                            variant="outline"
                            data-testid={`toggle-status-${client.id}`}
                        >
                            {status === 'active' ? 'Desactivar' : 'Activar'}
                        </Button>
                        {isRoutal && (
                            <Button
                                onClick={() => setShowMigrate(v => !v)}
                                size="sm"
                                variant="outline"
                                className={showMigrate ? 'bg-amber-50 border-amber-300 text-amber-800' : 'text-amber-700 border-amber-200'}
                                title="Migrar journeys legacy del modelo plan→journey al modelo route→journey"
                                data-testid={`migrate-legacy-toggle-${client.id}`}
                            >
                                <GitBranch className="w-3.5 h-3.5 mr-1.5" />
                                Migrar legacy
                                {showMigrate ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
                            </Button>
                        )}
                        <Button
                            onClick={handleDelete}
                            size="sm"
                            variant="outline"
                            className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200 ml-auto"
                            data-testid={`delete-integration-${client.id}`}
                        >
                            <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                    </>
                )}
            </div>

            {/* iter80 — Migración legacy panel */}
            {isRoutal && showMigrate && (
                <div
                    className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-md"
                    data-testid={`migrate-panel-${client.id}`}
                >
                    <div className="flex items-start gap-2 mb-3 text-xs text-amber-900">
                        <GitBranch className="w-4 h-4 mt-0.5 flex-shrink-0" />
                        <div>
                            <p className="font-semibold">Migración legacy: Plan → Route</p>
                            <p className="text-[11px] mt-0.5 leading-relaxed">
                                Antes (modelo viejo): 1 journey por <strong>plan Routal</strong> con todos los stops fusionados.<br/>
                                Ahora (modelo correcto): 1 journey por <strong>route real</strong> (driver), stops filtrados.<br/>
                                Esta herramienta hidrata cada plan vía API Routal y parte las legacy en N journeys correctas.
                                <strong> Dry-run</strong> primero (sin cambios), luego <strong>Aplicar</strong>.
                                Idempotente, preserva audit trail.
                            </p>
                        </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                        <div className="space-y-1">
                            <Label className="text-xs text-slate-700">Días hacia atrás</Label>
                            <Input
                                type="number"
                                min="1"
                                max="180"
                                value={migrateDays}
                                onChange={(e) => setMigrateDays(Number(e.target.value) || 30)}
                                className="font-mono"
                                data-testid={`migrate-days-${client.id}`}
                            />
                        </div>
                        <div className="flex items-end">
                            <Button
                                onClick={handleMigrateDryRun}
                                disabled={migrateRunning}
                                size="sm"
                                variant="outline"
                                className="w-full"
                                data-testid={`migrate-dryrun-${client.id}`}
                            >
                                {migrateRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
                                Detectar legacy (dry-run)
                            </Button>
                        </div>
                        <div className="flex items-end">
                            <Button
                                onClick={handleMigrateApply}
                                disabled={migrateRunning || !migrateDryResult || !migrateDryResult.scanned}
                                size="sm"
                                className="w-full bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50"
                                data-testid={`migrate-apply-${client.id}`}
                            >
                                {migrateRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                                Aplicar migración
                            </Button>
                        </div>
                    </div>

                    {migrateDryResult && (
                        <div
                            className="bg-white rounded p-2 text-xs space-y-2"
                            data-testid={`migrate-dry-result-${client.id}`}
                        >
                            <div className="flex items-center justify-between font-semibold text-slate-800">
                                <span>
                                    {migrateDryResult.scanned} journey(s) legacy ·{' '}
                                    {migrateDryResult.plans_inspected} plans Routal inspeccionados
                                </span>
                                <span className="text-slate-500 text-[10px] uppercase">
                                    {migrateAppliedResult ? `aplicado · ${migrateAppliedResult.migrated} migradas` : 'dry-run'}
                                </span>
                            </div>
                            {migrateDryResult.scanned === 0 && (
                                <p className="text-emerald-700 text-[11px]">
                                    ✓ Sin journeys legacy en últimos {migrateDryResult.days_back} días.
                                </p>
                            )}
                            {migrateDryResult.scanned > 0 && Array.isArray(migrateDryResult.details) && (
                                <div className="max-h-64 overflow-y-auto border-t border-slate-200 pt-1">
                                    <table className="w-full text-[10px] font-mono">
                                        <thead className="text-slate-500 sticky top-0 bg-white">
                                            <tr>
                                                <th className="text-left py-1">Plan Routal</th>
                                                <th className="text-left">Legacy ID</th>
                                                <th className="text-center">Routes nuevas</th>
                                                <th className="text-left">Drivers (pkgs)</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {migrateDryResult.details.map((d, i) => (
                                                <tr key={d.legacy_journey_id || i} className="border-b border-slate-100">
                                                    <td className="py-1">{d.plan_id?.slice(0, 12)}…</td>
                                                    <td className="text-slate-500">{d.legacy_journey_id?.slice(0, 8) || '—'}</td>
                                                    <td className="text-center">
                                                        {d.new_journeys?.length || 0}
                                                    </td>
                                                    <td className="text-slate-700 truncate max-w-[280px]">
                                                        {(d.new_journeys || []).map(nj =>
                                                            `${nj.driver?.slice(0, 18) || '?'}(${nj.packages || 0})`
                                                        ).join(' · ')}
                                                        {d.status === 'skipped' && <span className="text-slate-400 italic"> · skip ({d.reason})</span>}
                                                        {d.status === 'error' && <span className="text-red-600"> · error</span>}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                            {migrateAppliedResult && (
                                <div className="bg-emerald-50 border border-emerald-200 rounded px-2 py-1.5 text-[11px] text-emerald-900 mt-1">
                                    ✓ {migrateAppliedResult.migrated} journey(s) migrada(s) ·{' '}
                                    {migrateAppliedResult.packages_moved} package(s) movido(s)
                                    {migrateAppliedResult.errors > 0 && <> · <strong>{migrateAppliedResult.errors} error(es)</strong></>}
                                </div>
                            )}
                        </div>
                    )}

                    {/* iter82 — Restaurar incidencias huérfanas */}
                    <div className="mt-3 pt-3 border-t border-amber-200">
                        <div className="flex items-start gap-2 mb-2 text-xs text-amber-900">
                            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                            <div>
                                <p className="font-semibold">Restaurar incidencias huérfanas</p>
                                <p className="text-[11px] mt-0.5 leading-relaxed">
                                    Si tras "Aplicar migración" notaste incidencias faltantes en
                                    rutas migradas, este fix las re-asigna a las journeys nuevas
                                    matcheando por <code className="bg-white px-1 rounded">tracking_number</code>.
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <Button
                                onClick={() => handleRestoreIncidents(true)}
                                disabled={restoreRunning}
                                size="sm"
                                variant="outline"
                                className="flex-1"
                                data-testid={`restore-incidents-dryrun-${client.id}`}
                            >
                                {restoreRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <RefreshCw className="w-3.5 h-3.5 mr-1.5" />}
                                Detectar huérfanas
                            </Button>
                            <Button
                                onClick={() => handleRestoreIncidents(false)}
                                disabled={restoreRunning || !restoreResult || !restoreResult.orphan_incidents_found}
                                size="sm"
                                className="flex-1 bg-amber-600 hover:bg-amber-700 text-white disabled:opacity-50"
                                data-testid={`restore-incidents-apply-${client.id}`}
                            >
                                {restoreRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                                Restaurar incidencias
                            </Button>
                        </div>
                        {restoreResult && (
                            <div
                                className="bg-white rounded p-2 text-xs mt-2"
                                data-testid={`restore-incidents-result-${client.id}`}
                            >
                                <div className="flex items-center justify-between font-semibold text-slate-800 mb-1">
                                    <span>
                                        {restoreResult.orphan_incidents_found} huérfana(s) detectada(s) ·{' '}
                                        {restoreResult.legacy_journeys_inspected} journeys legacy
                                    </span>
                                    <span className="text-slate-500 text-[10px] uppercase">
                                        {restoreResult.dry_run ? 'dry-run' : 'aplicado'}
                                    </span>
                                </div>
                                {restoreResult.orphan_incidents_found > 0 && (
                                    <div className="grid grid-cols-3 gap-2 text-[10px] mb-2">
                                        <div className="bg-emerald-50 rounded px-2 py-1">
                                            <div className="text-slate-500">Por tracking</div>
                                            <div className="font-bold text-emerald-700">{restoreResult.restored_by_tracking}</div>
                                        </div>
                                        <div className="bg-blue-50 rounded px-2 py-1">
                                            <div className="text-slate-500">Por fallback</div>
                                            <div className="font-bold text-blue-700">{restoreResult.restored_by_fallback}</div>
                                        </div>
                                        <div className="bg-red-50 rounded px-2 py-1">
                                            <div className="text-slate-500">Sin restaurar</div>
                                            <div className="font-bold text-red-700">{restoreResult.could_not_restore}</div>
                                        </div>
                                    </div>
                                )}
                                {restoreResult.orphan_incidents_found === 0 && (
                                    <p className="text-emerald-700 text-[11px]">
                                        ✓ No hay incidencias huérfanas. Todas apuntan a journeys correctas.
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default ClientIntegrationCard;
