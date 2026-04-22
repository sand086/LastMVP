import React from 'react';
import { TabsContent } from '../../components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Database, Copy, Check, Globe, Shield, Key } from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const WEBHOOK_ENDPOINTS = [
    { method: 'GET', path: '/api/webhooks/events', desc: 'Lista eventos disponibles' },
    { method: 'GET', path: '/api/webhooks', desc: 'Lista webhooks configurados' },
    { method: 'POST', path: '/api/webhooks', desc: 'Crear nuevo webhook' },
    { method: 'PUT', path: '/api/webhooks/{id}', desc: 'Actualizar webhook' },
    { method: 'DELETE', path: '/api/webhooks/{id}', desc: 'Eliminar webhook' },
    { method: 'POST', path: '/api/webhooks/{id}/test', desc: 'Enviar evento de prueba' },
    { method: 'GET', path: '/api/webhooks/{id}/deliveries', desc: 'Log de entregas' },
    { method: 'POST', path: '/api/webhooks/{id}/regenerate-secret', desc: 'Regenerar HMAC secret' },
];

const WEBHOOK_EVENTS = [
    'journey.started', 'journey.closed', 'incident.created', 'incident.resolved',
    'package.status_changed', 'layout.uploaded', 'quality.evaluated',
];

const methodBadgeColor = (method) => {
    if (method === 'GET') return 'bg-emerald-100 text-emerald-700';
    if (method === 'POST') return 'bg-blue-100 text-blue-700';
    if (method === 'PUT') return 'bg-amber-100 text-amber-700';
    return 'bg-red-100 text-red-700';
};

export const DocsTab = ({ schema, visibleToken, copied, onCopy }) => (
    <TabsContent value="docs" className="space-y-6">
        {/* Auth Info */}
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <Database className="w-5 h-5" />
                    Autenticación
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <p className="text-sm text-slate-600">
                    Todas las peticiones requieren un token JWT en el header Authorization.
                </p>
                <div className="bg-slate-900 rounded-sm p-4 overflow-x-auto">
                    <code className="text-sm text-emerald-400">
                        Authorization: Bearer {visibleToken ? visibleToken.substring(0, 40) + '...' : '(cargando token...)'}
                    </code>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onCopy(visibleToken, 'token')}
                        disabled={!visibleToken}
                        data-testid="copy-token-btn"
                    >
                        {copied === 'token' ? <Check className="w-4 h-4 mr-1" /> : <Copy className="w-4 h-4 mr-1" />}
                        Copiar Token
                    </Button>
                    <span className="text-xs text-slate-500">El token expira en 8 horas</span>
                </div>
            </CardContent>
        </Card>

        {/* Endpoints */}
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg">Endpoints Disponibles</CardTitle>
                <CardDescription>
                    URL Base: <code className="bg-slate-100 px-2 py-1 rounded">{API_URL}/api</code>
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {schema?.endpoints?.map((endpoint) => (
                    <div key={`ep-${endpoint.method}-${endpoint.name}`} className="border border-slate-200 rounded-sm overflow-hidden">
                        <div className="bg-slate-50 p-4 border-b border-slate-200">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h4 className="font-medium text-slate-900">{endpoint.name}</h4>
                                    <p className="text-sm text-slate-500">{endpoint.description}</p>
                                </div>
                                <span className="px-3 py-1 bg-emerald-100 text-emerald-700 text-xs font-mono rounded">
                                    {endpoint.method}
                                </span>
                            </div>
                            <code className="text-sm text-blue-600 mt-2 block">{endpoint.endpoint}</code>
                        </div>
                        <div className="p-4 space-y-4">
                            <div>
                                <h5 className="text-sm font-medium text-slate-700 mb-2">Parámetros</h5>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="border-b border-slate-100">
                                                <th className="text-left py-2 pr-4 font-medium text-slate-600">Nombre</th>
                                                <th className="text-left py-2 pr-4 font-medium text-slate-600">Tipo</th>
                                                <th className="text-left py-2 font-medium text-slate-600">Descripción</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {endpoint.parameters?.map((param) => (
                                                <tr key={`${endpoint.name}-${param.name}`} className="border-b border-slate-50">
                                                    <td className="py-2 pr-4">
                                                        <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">{param.name}</code>
                                                    </td>
                                                    <td className="py-2 pr-4 text-slate-600 text-xs">
                                                        {param.type}
                                                        {param.format && <span className="text-slate-400"> ({param.format})</span>}
                                                    </td>
                                                    <td className="py-2 text-slate-600 text-xs">
                                                        {param.enum && `Valores: ${param.enum.join(', ')}`}
                                                        {param.default && ` (default: ${param.default})`}
                                                        {!param.required && <span className="text-slate-400"> (opcional)</span>}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            <div>
                                <h5 className="text-sm font-medium text-slate-700 mb-2">Campos de Respuesta</h5>
                                <div className="flex flex-wrap gap-1">
                                    {endpoint.fields?.map((field) => (
                                        <span key={`${endpoint.name}-f-${field}`} className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">
                                            {field}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                ))}
            </CardContent>
        </Card>

        {/* Webhooks Reference */}
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <Globe className="w-5 h-5" />
                    Webhooks API (Plug & Play)
                </CardTitle>
                <CardDescription>
                    Suscribete a eventos en tiempo real para integrar sistemas externos
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-3">
                    {WEBHOOK_ENDPOINTS.map((ep) => (
                        <div key={`wh-${ep.method}-${ep.path}`} className="flex items-center gap-3 text-sm">
                            <span className={`px-2 py-0.5 rounded text-xs font-mono font-medium ${methodBadgeColor(ep.method)}`}>
                                {ep.method}
                            </span>
                            <code className="text-xs text-slate-700 font-mono">{ep.path}</code>
                            <span className="text-slate-500 text-xs">{ep.desc}</span>
                        </div>
                    ))}
                </div>
                <div className="mt-4 p-3 bg-slate-50 rounded text-sm text-slate-600 space-y-1">
                    <p className="font-medium text-slate-700">Eventos disponibles:</p>
                    <div className="grid grid-cols-2 gap-1 text-xs font-mono">
                        {WEBHOOK_EVENTS.map((ev) => <span key={ev}>{ev}</span>)}
                    </div>
                </div>
            </CardContent>
        </Card>

        {/* Security */}
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <Shield className="w-5 h-5" />
                    Seguridad
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-600">
                <div className="flex items-start gap-2">
                    <Key className="w-4 h-4 mt-0.5 text-slate-500 shrink-0" />
                    <p><strong>JWT Auth</strong>: Todas las peticiones requieren token Bearer. Expira en 8h.</p>
                </div>
                <div className="flex items-start gap-2">
                    <Shield className="w-4 h-4 mt-0.5 text-slate-500 shrink-0" />
                    <p><strong>CORS</strong>: Solo dominios autorizados. Rate limiting: 10 req/min en login.</p>
                </div>
                <div className="flex items-start gap-2">
                    <Globe className="w-4 h-4 mt-0.5 text-slate-500 shrink-0" />
                    <p><strong>Webhook HMAC</strong>: Cada webhook tiene un secret unico. Verifica payloads con <code className="bg-slate-100 px-1 rounded">X-Webhook-Signature: sha256=...</code></p>
                </div>
                <div className="flex items-start gap-2">
                    <Database className="w-4 h-4 mt-0.5 text-slate-500 shrink-0" />
                    <p><strong>Headers de seguridad</strong>: HSTS, X-Content-Type-Options, X-Frame-Options habilitados.</p>
                </div>
            </CardContent>
        </Card>
    </TabsContent>
);

export default DocsTab;
