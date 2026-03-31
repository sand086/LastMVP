import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { toast } from 'sonner';
import {
    Plus, Trash2, Play, RefreshCw, Copy, ChevronDown, ChevronUp,
    CheckCircle2, XCircle, Clock, Loader2, Globe, Key, Zap, Eye, EyeOff,
} from 'lucide-react';
import {
    getWebhookEvents, getWebhooks, createWebhook, updateWebhook,
    deleteWebhook, testWebhook, getWebhookDeliveries, regenerateWebhookSecret,
} from '../lib/api';

const STATUS_COLORS = {
    success: 'text-emerald-600 bg-emerald-50 border-emerald-200',
    failed: 'text-red-600 bg-red-50 border-red-200',
    pending: 'text-amber-600 bg-amber-50 border-amber-200',
};

export const WebhooksTab = () => {
    const [webhooks, setWebhooks] = useState([]);
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [expandedId, setExpandedId] = useState(null);
    const [deliveries, setDeliveries] = useState({});
    const [testingId, setTestingId] = useState(null);

    const loadData = useCallback(async () => {
        try {
            const [whRes, evRes] = await Promise.all([getWebhooks(), getWebhookEvents()]);
            setWebhooks(whRes.data);
            setEvents(evRes.data.events);
        } catch {
            toast.error('Error al cargar webhooks');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    const handleToggle = async (wh) => {
        try {
            await updateWebhook(wh.id, { is_active: !wh.is_active });
            setWebhooks(prev => prev.map(w => w.id === wh.id ? { ...w, is_active: !w.is_active } : w));
            toast.success(wh.is_active ? 'Webhook desactivado' : 'Webhook activado');
        } catch { toast.error('Error al actualizar'); }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Eliminar este webhook?')) return;
        try {
            await deleteWebhook(id);
            setWebhooks(prev => prev.filter(w => w.id !== id));
            toast.success('Webhook eliminado');
        } catch { toast.error('Error al eliminar'); }
    };

    const handleTest = async (id) => {
        setTestingId(id);
        try {
            const res = await testWebhook(id);
            if (res.data.status === 'success') {
                toast.success(`Test exitoso (${res.data.final_status_code})`);
            } else {
                toast.error(`Test fallido: ${res.data.attempts?.slice(-1)[0]?.error || res.data.final_status_code}`);
            }
            loadData();
        } catch { toast.error('Error al enviar test'); }
        finally { setTestingId(null); }
    };

    const handleExpand = async (id) => {
        if (expandedId === id) { setExpandedId(null); return; }
        setExpandedId(id);
        try {
            const res = await getWebhookDeliveries(id);
            setDeliveries(prev => ({ ...prev, [id]: res.data }));
        } catch { /* ignore */ }
    };

    if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="font-heading text-lg font-semibold">Webhooks</h3>
                    <p className="text-sm text-slate-500">Integra LastMile OS con sistemas externos tipo Plug&Play</p>
                </div>
                <Button onClick={() => setShowCreate(true)} data-testid="create-webhook-btn">
                    <Plus className="w-4 h-4 mr-2" />
                    Nuevo webhook
                </Button>
            </div>

            {/* Events reference */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium text-slate-600 flex items-center gap-2">
                        <Zap className="w-4 h-4" />
                        Eventos disponibles
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {events.map(e => (
                            <div key={e.event} className="flex items-start gap-2 text-sm p-2 bg-slate-50 rounded">
                                <code className="font-mono text-xs bg-slate-200 px-1.5 py-0.5 rounded shrink-0">{e.event}</code>
                                <span className="text-slate-600">{e.description}</span>
                            </div>
                        ))}
                    </div>
                </CardContent>
            </Card>

            {/* Webhooks list */}
            {webhooks.length === 0 ? (
                <Card>
                    <CardContent className="py-12 text-center">
                        <Globe className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500">No hay webhooks configurados</p>
                        <p className="text-sm text-slate-400 mt-1">Crea uno para recibir eventos en tiempo real</p>
                    </CardContent>
                </Card>
            ) : (
                <div className="space-y-3">
                    {webhooks.map(wh => (
                        <WebhookCard
                            key={wh.id}
                            webhook={wh}
                            expanded={expandedId === wh.id}
                            deliveries={deliveries[wh.id] || []}
                            testing={testingId === wh.id}
                            onToggle={() => handleToggle(wh)}
                            onDelete={() => handleDelete(wh.id)}
                            onTest={() => handleTest(wh.id)}
                            onExpand={() => handleExpand(wh.id)}
                            onReload={loadData}
                        />
                    ))}
                </div>
            )}

            <CreateWebhookDialog
                open={showCreate}
                onClose={() => setShowCreate(false)}
                events={events}
                onCreated={(wh) => { setWebhooks(prev => [...prev, wh]); setShowCreate(false); }}
            />
        </div>
    );
};

function WebhookCard({ webhook: wh, expanded, deliveries, testing, onToggle, onDelete, onTest, onExpand, onReload }) {
    const [showSecret, setShowSecret] = useState(false);
    const [regenerating, setRegenerating] = useState(false);

    const handleRegenerate = async () => {
        if (!window.confirm('Regenerar el secret? Los sistemas externos necesitaran actualizarlo.')) return;
        setRegenerating(true);
        try {
            const res = await regenerateWebhookSecret(wh.id);
            toast.success('Secret regenerado');
            onReload();
        } catch { toast.error('Error'); }
        finally { setRegenerating(false); }
    };

    return (
        <Card className={!wh.is_active ? 'opacity-60' : ''} data-testid={`webhook-card-${wh.id}`}>
            <CardContent className="p-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                        <button
                            onClick={onToggle}
                            className={`w-10 h-5 rounded-full transition-colors relative ${wh.is_active ? 'bg-emerald-500' : 'bg-slate-300'}`}
                            data-testid={`webhook-toggle-${wh.id}`}
                        >
                            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${wh.is_active ? 'left-5' : 'left-0.5'}`} />
                        </button>
                        <div className="min-w-0">
                            <p className="font-medium text-slate-900 truncate">{wh.name}</p>
                            <p className="text-xs text-slate-500 font-mono truncate">{wh.url}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        <div className="text-right text-xs text-slate-500 hidden md:block">
                            <span className="text-emerald-600 font-medium">{wh.deliveries_success}</span>
                            <span className="mx-1">/</span>
                            <span className="text-red-600 font-medium">{wh.deliveries_failed}</span>
                            <span className="mx-1">/</span>
                            <span>{wh.deliveries_total}</span>
                        </div>
                        <Button variant="outline" size="sm" onClick={onTest} disabled={testing} data-testid={`webhook-test-${wh.id}`}>
                            {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={onExpand}>
                            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={onDelete} className="text-red-600" data-testid={`webhook-delete-${wh.id}`}>
                            <Trash2 className="w-4 h-4" />
                        </Button>
                    </div>
                </div>

                {/* Events tags */}
                <div className="flex flex-wrap gap-1.5 mt-3">
                    {wh.events.map(e => (
                        <span key={e} className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                            {e}
                        </span>
                    ))}
                </div>

                {/* Expanded: secret + deliveries */}
                {expanded && (
                    <div className="mt-4 pt-4 border-t border-slate-200 space-y-4">
                        {/* Secret */}
                        <div className="space-y-2">
                            <Label className="text-xs uppercase text-slate-500 flex items-center gap-1">
                                <Key className="w-3 h-3" /> HMAC Secret
                            </Label>
                            <div className="flex items-center gap-2">
                                <code className="flex-1 font-mono text-xs bg-slate-100 p-2 rounded">
                                    {showSecret ? wh.secret : '••••••••••••••••••••••••••••••••'}
                                </code>
                                <Button variant="ghost" size="sm" onClick={() => setShowSecret(!showSecret)}>
                                    {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => { navigator.clipboard.writeText(wh.secret); toast.success('Copiado'); }}>
                                    <Copy className="w-4 h-4" />
                                </Button>
                                <Button variant="outline" size="sm" onClick={handleRegenerate} disabled={regenerating}>
                                    <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} />
                                </Button>
                            </div>
                            <p className="text-xs text-slate-400">Usa este secret para verificar payloads con HMAC-SHA256 (header: X-Webhook-Signature)</p>
                        </div>

                        {/* Verification code snippet */}
                        <div className="space-y-1">
                            <Label className="text-xs uppercase text-slate-500">Verificacion (ejemplo)</Label>
                            <pre className="text-xs bg-slate-900 text-green-400 p-3 rounded overflow-x-auto">
{`import hmac, hashlib

def verify(payload_bytes, signature, secret):
    expected = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)`}
                            </pre>
                        </div>

                        {/* Delivery log */}
                        <div className="space-y-2">
                            <Label className="text-xs uppercase text-slate-500">Ultimas entregas</Label>
                            {deliveries.length === 0 ? (
                                <p className="text-sm text-slate-400">Sin entregas registradas</p>
                            ) : (
                                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                                    {deliveries.map(d => (
                                        <div key={d.id} className={`flex items-center justify-between text-xs p-2 rounded border ${STATUS_COLORS[d.status]}`}>
                                            <div className="flex items-center gap-2">
                                                {d.status === 'success' ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                                                 d.status === 'failed' ? <XCircle className="w-3.5 h-3.5" /> :
                                                 <Clock className="w-3.5 h-3.5" />}
                                                <code className="font-mono">{d.event}</code>
                                                {d.is_test && <span className="bg-slate-200 text-slate-600 px-1 rounded">TEST</span>}
                                            </div>
                                            <div className="flex items-center gap-3">
                                                <span>{d.final_status_code || 'ERR'}</span>
                                                <span className="text-slate-400">{d.attempts?.length || 0} intento(s)</span>
                                                <span className="text-slate-400">{new Date(d.timestamp).toLocaleTimeString()}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

function CreateWebhookDialog({ open, onClose, events, onCreated }) {
    const [form, setForm] = useState({ name: '', url: '', events: [] });
    const [submitting, setSubmitting] = useState(false);

    const toggleEvent = (event) => {
        setForm(prev => ({
            ...prev,
            events: prev.events.includes(event)
                ? prev.events.filter(e => e !== event)
                : [...prev.events, event],
        }));
    };

    const handleSubmit = async () => {
        if (!form.name || !form.url || form.events.length === 0) {
            toast.error('Completa nombre, URL y al menos un evento');
            return;
        }
        setSubmitting(true);
        try {
            const res = await createWebhook(form);
            toast.success('Webhook creado');
            onCreated(res.data);
            setForm({ name: '', url: '', events: [] });
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al crear webhook');
        } finally { setSubmitting(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle>Nuevo Webhook</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                    <div className="space-y-2">
                        <Label>Nombre</Label>
                        <Input
                            value={form.name}
                            onChange={e => setForm({ ...form, name: e.target.value })}
                            placeholder="Ej: ERP Cubbo, Slack Alertas"
                            data-testid="webhook-name-input"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>URL de destino</Label>
                        <Input
                            value={form.url}
                            onChange={e => setForm({ ...form, url: e.target.value })}
                            placeholder="https://api.tu-sistema.com/webhooks/lastmile"
                            data-testid="webhook-url-input"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Eventos</Label>
                        <div className="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto">
                            {events.map(e => (
                                <div key={e.event} className="flex items-start gap-3 p-2 bg-slate-50 rounded">
                                    <Checkbox
                                        checked={form.events.includes(e.event)}
                                        onCheckedChange={() => toggleEvent(e.event)}
                                        data-testid={`webhook-event-${e.event}`}
                                    />
                                    <div>
                                        <code className="text-xs font-mono font-medium">{e.event}</code>
                                        <p className="text-xs text-slate-500">{e.description}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button onClick={handleSubmit} disabled={submitting} data-testid="webhook-submit-btn">
                        {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                        Crear webhook
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
