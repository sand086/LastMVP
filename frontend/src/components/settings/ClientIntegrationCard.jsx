import React, { useState, useEffect, useCallback } from 'react';
import { Eye, EyeOff, Save, Loader2, CheckCircle2, AlertTriangle, Trash2, Copy, Plug, RefreshCw } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Switch } from '../ui/switch';
import { toast } from 'sonner';
import {
    upsertIntegration, updateIntegrationStatus, testIntegration,
    deleteIntegration, getRoutalWebhookStatus,
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
            if (r.data.ok) toast.success(`Conexión OK (${r.data.latency_ms}ms)`);
            else toast.error(`Error: ${r.data.error}`);
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
                    <span>
                        {testResult.ok ? `Conexión exitosa (${testResult.latency_ms}ms)` : testResult.error}
                    </span>
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
                {isRoutal && existing.client_id && (
                    <Button
                        onClick={handleTest}
                        disabled={testing || !summary.has_api_key}
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
        </div>
    );
};

export default ClientIntegrationCard;
