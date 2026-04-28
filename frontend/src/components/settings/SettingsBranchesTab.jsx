import React, { useState, useEffect, useCallback } from 'react';
import {
    Loader2, Building2, Plus, Save, Trash2, ToggleLeft, ToggleRight,
    Eye, EyeOff, KeyRound, MapPin,
} from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { toast } from 'sonner';
import {
    listBranches, createBranch, updateBranch, deleteBranch,
    migrateCubboCities, setBranchRoutalCreds, toggleBranchRoutal,
    getClients,
} from '../../lib/api';

const COMMON_CITY_CODES = ['CDMX', 'GDL', 'MOR', 'MTY', 'PUE', 'QRO', 'PACHUCA'];

const BranchRow = ({ branch, onChanged }) => {
    const [showCredsForm, setShowCredsForm] = useState(false);
    const [savingCreds, setSavingCreds] = useState(false);
    const [toggling, setToggling] = useState(false);
    const [showApiKey, setShowApiKey] = useState(false);
    const [apiKey, setApiKey] = useState('');
    const [projectId, setProjectId] = useState('');
    const [webhookSecret, setWebhookSecret] = useState('');

    const handleSaveCreds = async () => {
        if (!apiKey && !projectId && !webhookSecret) {
            toast.error('Ingresa al menos un campo para guardar');
            return;
        }
        setSavingCreds(true);
        try {
            await setBranchRoutalCreds(branch.id, {
                routal_api_key: apiKey || undefined,
                routal_project_id: projectId || undefined,
                routal_webhook_secret: webhookSecret || undefined,
            });
            toast.success(`✔ Credenciales Routal guardadas para ${branch.code}`);
            setApiKey(''); setProjectId(''); setWebhookSecret('');
            setShowCredsForm(false);
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error guardando credenciales');
        } finally {
            setSavingCreds(false);
        }
    };

    const handleToggleRoutal = async () => {
        if (!branch.has_routal_credentials) {
            toast.error('Configura primero las credenciales Routal de esta sucursal');
            return;
        }
        setToggling(true);
        try {
            // Toggle is implicit: if has_routal_credentials → assume active=true; user toggles to false to disable
            // We don't track active in branch row directly; we always toggle to opposite by hitting endpoint
            const next = !branch.routal_active;  // assume active when creds exist
            await toggleBranchRoutal(branch.id, next);
            toast.success(next ? '✔ Routal habilitado' : '⏸ Routal deshabilitado · drivers usarán Kosmo');
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error en toggle');
        } finally { setToggling(false); }
    };

    const handleDelete = async () => {
        if (branch.journeys_count > 0) {
            const ok = window.confirm(
                `Esta sucursal tiene ${branch.journeys_count} journey(s) asociados.\n\n` +
                `Se desactivará (soft-delete) preservando el historial.\n\n¿Continuar?`
            );
            if (!ok) return;
        }
        try {
            await deleteBranch(branch.id);
            toast.success('Sucursal desactivada');
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al eliminar');
        }
    };

    const handleToggleActive = async () => {
        try {
            await updateBranch(branch.id, { active: !branch.active });
            toast.success(branch.active ? 'Sucursal desactivada' : 'Sucursal activada');
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error');
        }
    };

    return (
        <div
            className={`p-3 rounded-lg border ${branch.active ? 'border-slate-200 bg-white' : 'border-slate-200 bg-slate-50 opacity-60'}`}
            data-testid={`branch-row-${branch.code}`}
        >
            <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 flex-1 min-w-0">
                    <div className="flex flex-col items-center justify-center w-14 h-14 bg-slate-100 rounded-lg">
                        <MapPin className="w-4 h-4 text-slate-500" />
                        <span className="font-mono text-xs font-bold text-slate-700 mt-0.5">{branch.code}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-slate-800 truncate">{branch.name}</span>
                            {branch.has_routal_credentials ? (
                                <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded border border-emerald-200 text-[10px] font-semibold uppercase">
                                    Routal OK
                                </span>
                            ) : (
                                <span className="px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded border border-amber-200 text-[10px] font-semibold uppercase">
                                    Sin Routal
                                </span>
                            )}
                            {!branch.active && (
                                <span className="px-1.5 py-0.5 bg-red-50 text-red-700 rounded border border-red-200 text-[10px] font-semibold uppercase">
                                    Inactiva
                                </span>
                            )}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                            {branch.journeys_count} journey(s) · ID <span className="font-mono">{branch.id.slice(0, 8)}…</span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setShowCredsForm(v => !v)}
                        data-testid={`branch-creds-toggle-${branch.code}`}
                        title="Configurar credenciales Routal"
                    >
                        <KeyRound className="w-3.5 h-3.5 mr-1" />
                        Routal
                    </Button>
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleToggleActive}
                        data-testid={`branch-toggle-active-${branch.code}`}
                        title={branch.active ? 'Desactivar sucursal' : 'Reactivar'}
                    >
                        {branch.active ? <ToggleRight className="w-4 h-4 text-emerald-600" /> : <ToggleLeft className="w-4 h-4 text-slate-400" />}
                    </Button>
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={handleDelete}
                        className="text-red-600 hover:bg-red-50"
                        data-testid={`branch-delete-${branch.code}`}
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                </div>
            </div>

            {showCredsForm && (
                <div className="mt-3 p-3 bg-slate-50 border border-slate-200 rounded-md" data-testid={`branch-creds-form-${branch.code}`}>
                    <div className="text-xs text-slate-600 mb-2">
                        Credenciales <span className="font-semibold">cifradas con Fernet AES-128</span> al guardar.
                        Solo se reemplazan los campos que llenes — déjalos vacíos para no cambiar.
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                        <div className="space-y-1">
                            <Label className="text-xs">API Key Routal</Label>
                            <div className="relative">
                                <Input
                                    type={showApiKey ? 'text' : 'password'}
                                    value={apiKey}
                                    onChange={e => setApiKey(e.target.value)}
                                    placeholder="api_key_..."
                                    className="font-mono text-xs pr-8"
                                    data-testid={`branch-api-key-${branch.code}`}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowApiKey(v => !v)}
                                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                >
                                    {showApiKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                                </button>
                            </div>
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs">Project ID</Label>
                            <Input
                                value={projectId}
                                onChange={e => setProjectId(e.target.value)}
                                placeholder="636aaed5..."
                                className="font-mono text-xs"
                                data-testid={`branch-project-id-${branch.code}`}
                            />
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs">Webhook Secret</Label>
                            <Input
                                type="password"
                                value={webhookSecret}
                                onChange={e => setWebhookSecret(e.target.value)}
                                placeholder="webhook_secret_..."
                                className="font-mono text-xs"
                                data-testid={`branch-webhook-secret-${branch.code}`}
                            />
                        </div>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-[11px] text-slate-500">
                            Webhook URL: <code className="bg-white px-1 rounded border">/api/webhooks/routal/{branch.client_id?.slice(0, 8)}…</code>
                        </span>
                        <div className="flex gap-2">
                            <Button size="sm" variant="ghost" onClick={() => setShowCredsForm(false)}>
                                Cancelar
                            </Button>
                            <Button
                                size="sm"
                                onClick={handleSaveCreds}
                                disabled={savingCreds}
                                className="bg-emerald-600 hover:bg-emerald-700 text-white"
                                data-testid={`branch-save-creds-${branch.code}`}
                            >
                                {savingCreds ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1" />}
                                Guardar
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const ClientBranchSection = ({ client, onChanged }) => {
    const [branches, setBranches] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showAddForm, setShowAddForm] = useState(false);
    const [newCode, setNewCode] = useState('');
    const [newName, setNewName] = useState('');
    const [adding, setAdding] = useState(false);

    const fetchBranches = useCallback(async () => {
        setLoading(true);
        try {
            const r = await listBranches(client.id);
            setBranches(r.data);
        } catch (err) {
            console.error(err);
        } finally { setLoading(false); }
    }, [client.id]);

    useEffect(() => { fetchBranches(); }, [fetchBranches]);

    const handleAdd = async () => {
        if (!newCode || !newName) {
            toast.error('Código y nombre son obligatorios');
            return;
        }
        setAdding(true);
        try {
            await createBranch({
                client_id: client.id,
                code: newCode.toUpperCase(),
                name: newName,
                active: true,
            });
            toast.success(`✔ Sucursal ${newCode.toUpperCase()} creada`);
            setNewCode(''); setNewName(''); setShowAddForm(false);
            await fetchBranches();
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al crear');
        } finally { setAdding(false); }
    };

    const handleMigrate = async () => {
        const ok = window.confirm(
            `Crear automáticamente las 6 sucursales estándar de Cubbo (CDMX, GDL, MOR, MTY, PUE, QRO).\n\n` +
            `Idempotente: las que ya existan se omitirán.\n\n¿Continuar?`
        );
        if (!ok) return;
        try {
            const r = await migrateCubboCities(false);
            const created = r.data.created || [];
            const skipped = r.data.skipped_existing || [];
            toast.success(`✔ Migración: ${created.length} creadas, ${skipped.length} omitidas`);
            await fetchBranches();
            onChanged?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error en migración');
        }
    };

    const isCubbo = client.name?.toLowerCase() === 'cubbo';

    return (
        <Card className="mb-4">
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="w-4 h-4" />
                        {client.name}
                        <span className="text-xs font-normal text-slate-500">
                            · {branches.length} sucursal(es)
                        </span>
                    </CardTitle>
                    <div className="flex gap-2">
                        {isCubbo && branches.length === 0 && (
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={handleMigrate}
                                className="border-emerald-300 text-emerald-700"
                                data-testid={`migrate-cubbo-${client.id}`}
                            >
                                Crear 6 sucursales estándar
                            </Button>
                        )}
                        <Button
                            size="sm"
                            onClick={() => setShowAddForm(v => !v)}
                            data-testid={`add-branch-${client.id}`}
                        >
                            <Plus className="w-3.5 h-3.5 mr-1" /> Nueva sucursal
                        </Button>
                    </div>
                </div>
            </CardHeader>
            <CardContent className="pt-0">
                {showAddForm && (
                    <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-2">
                            <div className="space-y-1">
                                <Label className="text-xs">Código</Label>
                                <select
                                    list="city-codes"
                                    value={newCode}
                                    onChange={e => setNewCode(e.target.value)}
                                    className="w-full h-9 px-3 rounded-md border bg-white font-mono text-sm"
                                    data-testid="new-branch-code"
                                >
                                    <option value="">— elegir —</option>
                                    {COMMON_CITY_CODES.map(c => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </div>
                            <div className="space-y-1 sm:col-span-2">
                                <Label className="text-xs">Nombre</Label>
                                <Input
                                    value={newName}
                                    onChange={e => setNewName(e.target.value)}
                                    placeholder={`${client.name} ${newCode || 'CIUDAD'}`}
                                    data-testid="new-branch-name"
                                />
                            </div>
                        </div>
                        <div className="flex justify-end gap-2">
                            <Button size="sm" variant="ghost" onClick={() => setShowAddForm(false)}>Cancelar</Button>
                            <Button size="sm" onClick={handleAdd} disabled={adding} data-testid="save-new-branch">
                                {adding ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Save className="w-3.5 h-3.5 mr-1" />}
                                Crear
                            </Button>
                        </div>
                    </div>
                )}

                {loading ? (
                    <div className="text-center py-6 text-slate-500">
                        <Loader2 className="w-5 h-5 inline animate-spin" />
                    </div>
                ) : branches.length === 0 ? (
                    <div className="text-center py-6 text-sm text-slate-500">
                        Sin sucursales configuradas para este cliente
                    </div>
                ) : (
                    <div className="space-y-2">
                        {branches.map(b => (
                            <BranchRow key={b.id} branch={b} onChanged={fetchBranches} />
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
};

const SettingsBranchesTab = () => {
    const [clients, setClients] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchClients = useCallback(async () => {
        try {
            const r = await getClients();
            setClients(r.data);
        } catch (err) {
            toast.error('Error cargando clientes');
        } finally { setLoading(false); }
    }, []);

    useEffect(() => { fetchClients(); }, [fetchClients]);

    if (loading) {
        return (
            <div className="text-center py-12 text-slate-500">
                <Loader2 className="w-6 h-6 inline animate-spin" />
            </div>
        );
    }

    return (
        <div className="space-y-1" data-testid="settings-branches-tab">
            <div className="mb-4 p-3 bg-slate-50 border border-slate-200 rounded-md text-sm text-slate-700">
                <strong className="text-slate-900">Sucursales (RT-13)</strong> — agrupa unidades regionales bajo un cliente
                (ej. Cubbo CDMX, GDL, MOR…). Cada sucursal puede tener sus propias credenciales Routal (RT-01),
                permitiendo manejar múltiples ciudades con API keys distintas. Toggle on/off por sucursal hace rollback
                automático a flujo Kosmo (RT-02).
            </div>
            {clients.map(c => (
                <ClientBranchSection key={c.id} client={c} />
            ))}
        </div>
    );
};

export default SettingsBranchesTab;
