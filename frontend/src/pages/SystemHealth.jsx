import React, { useState, useEffect, useCallback } from 'react';
import api, { getTokenConsumption, updateExchangeRate } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Progress } from '../components/ui/progress';
import { 
    Activity, 
    Database, 
    AlertTriangle, 
    HardDrive, 
    Clock, 
    RefreshCw, 
    Zap, 
    BarChart3,
    Users,
    TrendingUp,
    DollarSign,
    Loader2,
} from 'lucide-react';
import { toast } from 'sonner';

const SystemHealth = () => {
    const [health, setHealth] = useState(null);
    const [perf, setPerf] = useState(null);
    const [tokenData, setTokenData] = useState(null);
    const [editingRate, setEditingRate] = useState(false);
    const [newRate, setNewRate] = useState('');
    const [savingRate, setSavingRate] = useState(false);
    const [loading, setLoading] = useState(true);
    const [lastRefresh, setLastRefresh] = useState(null);

    const fetchData = useCallback(async () => {
        try {
            const [healthRes, perfRes, tokenRes] = await Promise.all([
                api.get('/system/health'),
                api.get('/system/performance'),
                getTokenConsumption().catch(() => ({ data: null })),
            ]);
            setHealth(healthRes.data);
            setPerf(perfRes.data);
            if (tokenRes.data) setTokenData(tokenRes.data);
            setLastRefresh(new Date());
        } catch (error) {
            console.error('Error fetching health data:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 30000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const StatusDot = ({ ok }) => (
        <span className={`inline-block w-3 h-3 rounded-full ${ok ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
    );

    if (loading) {
        return (
            <div className="flex items-center justify-center py-20">
                <RefreshCw className="w-6 h-6 animate-spin text-slate-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">Health Dashboard</h1>
                    <p className="text-slate-500 text-sm">
                        Estado del sistema en tiempo real (auto-refresh 30s)
                        {lastRefresh && <span className="ml-2 text-xs text-slate-400">Actualizado: {lastRefresh.toLocaleTimeString()}</span>}
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={fetchData} data-testid="refresh-health-btn">
                    <RefreshCw className="w-4 h-4 mr-2" /> Actualizar
                </Button>
            </div>

            {/* Status Cards */}
            {health && (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <Card className="p-4" data-testid="card-api-status">
                        <div className="flex items-center gap-3 mb-2">
                            <Activity className="w-5 h-5 text-slate-500" />
                            <span className="text-xs text-slate-500 uppercase">API</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <StatusDot ok={health.api_status === 'ok'} />
                            <span className="font-mono font-bold text-lg">
                                {health.api_status === 'ok' ? 'OK' : 'DOWN'}
                            </span>
                        </div>
                    </Card>

                    <Card className="p-4" data-testid="card-mongo-status">
                        <div className="flex items-center gap-3 mb-2">
                            <Database className="w-5 h-5 text-slate-500" />
                            <span className="text-xs text-slate-500 uppercase">MongoDB</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <StatusDot ok={health.mongo_status === 'connected'} />
                            <span className="font-mono text-sm">{health.mongo_latency_ms}ms</span>
                        </div>
                    </Card>

                    <Card className="p-4" data-testid="card-latency">
                        <div className="flex items-center gap-3 mb-2">
                            <Zap className="w-5 h-5 text-slate-500" />
                            <span className="text-xs text-slate-500 uppercase">Latencia</span>
                        </div>
                        <p className="font-mono font-bold text-lg">{health.avg_latency_ms}ms</p>
                        <p className="text-xs text-slate-400">prom. 100 req</p>
                    </Card>

                    <Card className="p-4" data-testid="card-errors-4xx">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangle className="w-5 h-5 text-amber-500" />
                            <span className="text-xs text-slate-500 uppercase">4xx (24h)</span>
                        </div>
                        <p className="font-mono font-bold text-lg text-amber-600">{health.errors_4xx_24h}</p>
                    </Card>

                    <Card className="p-4" data-testid="card-errors-5xx">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangle className="w-5 h-5 text-red-500" />
                            <span className="text-xs text-slate-500 uppercase">5xx (24h)</span>
                        </div>
                        <p className="font-mono font-bold text-lg text-red-600">{health.errors_5xx_24h}</p>
                    </Card>

                    <Card className="p-4" data-testid="card-uploads">
                        <div className="flex items-center gap-3 mb-2">
                            <HardDrive className="w-5 h-5 text-slate-500" />
                            <span className="text-xs text-slate-500 uppercase">Uploads</span>
                        </div>
                        <p className="font-mono font-bold text-lg">{health.upload_size_mb} MB</p>
                    </Card>
                </div>
            )}

            {/* Uptime */}
            {health && (
                <Card className="p-4">
                    <div className="flex items-center gap-3">
                        <Clock className="w-5 h-5 text-slate-500" />
                        <span className="text-sm text-slate-500">Uptime:</span>
                        <span className="font-mono font-medium">{health.uptime}</span>
                    </div>
                </Card>
            )}

            {/* Error Timeline */}
            {health?.recent_errors?.length > 0 && (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="font-heading text-base">Últimos errores</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="overflow-x-auto">
                            <table className="data-table w-full text-sm">
                                <thead>
                                    <tr>
                                        <th>Timestamp</th>
                                        <th>Método</th>
                                        <th>Endpoint</th>
                                        <th>Status</th>
                                        <th>IP</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {health.recent_errors.map((err, i) => (
                                        <tr key={i}>
                                            <td className="font-mono text-xs">{err.timestamp?.slice(0, 19)}</td>
                                            <td><span className="px-1.5 py-0.5 text-xs font-mono bg-slate-100 rounded">{err.method}</span></td>
                                            <td className="font-mono text-xs">{err.path}</td>
                                            <td>
                                                <span className={`px-1.5 py-0.5 text-xs font-mono rounded ${
                                                    err.status_code >= 500 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                                                }`}>{err.status_code}</span>
                                            </td>
                                            <td className="font-mono text-xs">{err.client_ip}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Performance Metrics */}
            {perf && (
                <>
                    <h2 className="font-heading text-lg font-bold text-slate-900 mt-8">Performance Metrics</h2>

                    {/* Requests per hour chart */}
                    {Object.keys(perf.requests_per_hour || {}).length > 0 && (
                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="font-heading text-base flex items-center gap-2">
                                    <BarChart3 className="w-4 h-4" /> Requests por hora (7 días)
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-end gap-1 h-32">
                                    {Array.from({ length: 24 }, (_, h) => {
                                        const count = perf.requests_per_hour[String(h)] || 0;
                                        const maxCount = Math.max(1, ...Object.values(perf.requests_per_hour));
                                        const heightPct = (count / maxCount) * 100;
                                        return (
                                            <div key={h} className="flex-1 flex flex-col items-center gap-1">
                                                <div
                                                    className="w-full bg-slate-900 rounded-t-sm transition-all"
                                                    style={{ height: `${heightPct}%`, minHeight: count > 0 ? 4 : 0 }}
                                                    title={`${h}:00 - ${count} requests`}
                                                />
                                                {h % 4 === 0 && <span className="text-[10px] text-slate-400">{h}h</span>}
                                            </div>
                                        );
                                    })}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Slowest endpoints */}
                        {perf.slowest_endpoints?.length > 0 && (
                            <Card>
                                <CardHeader className="pb-3">
                                    <CardTitle className="font-heading text-base flex items-center gap-2">
                                        <TrendingUp className="w-4 h-4" /> Endpoints más lentos
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-2">
                                        {perf.slowest_endpoints.map((ep, i) => (
                                            <div key={i} className="flex items-center justify-between p-2 bg-slate-50 rounded-sm text-sm">
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <span className="px-1.5 py-0.5 text-xs font-mono bg-slate-200 rounded shrink-0">{ep.method}</span>
                                                    <span className="font-mono text-xs truncate">{ep.path}</span>
                                                </div>
                                                <div className="flex items-center gap-3 shrink-0 ml-2">
                                                    <span className="font-mono text-xs text-slate-500">{ep.count}x</span>
                                                    <span className={`font-mono font-bold text-sm ${
                                                        ep.avg_ms > 1000 ? 'text-red-600' : ep.avg_ms > 500 ? 'text-amber-600' : 'text-emerald-600'
                                                    }`}>{ep.avg_ms}ms</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Most active users */}
                        {perf.active_users?.length > 0 && (
                            <Card>
                                <CardHeader className="pb-3">
                                    <CardTitle className="font-heading text-base flex items-center gap-2">
                                        <Users className="w-4 h-4" /> Usuarios más activos (7 días)
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-2">
                                        {perf.active_users.map((u, i) => {
                                            const maxActions = perf.active_users[0]?.actions || 1;
                                            return (
                                                <div key={i} className="flex items-center gap-3">
                                                    <span className="text-sm font-medium w-32 truncate">{u.name}</span>
                                                    <div className="flex-1">
                                                        <Progress value={(u.actions / maxActions) * 100} className="h-2" />
                                                    </div>
                                                    <span className="font-mono text-sm font-bold w-12 text-right">{u.actions}</span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </CardContent>
                            </Card>
                        )}
                    </div>

                    {/* Layout processing stats */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <Card className="p-4">
                            <p className="text-xs text-slate-500 uppercase mb-1">Layouts (7d)</p>
                            <p className="font-mono font-bold text-lg">{perf.total_layouts_7d}</p>
                        </Card>
                        <Card className="p-4">
                            <p className="text-xs text-slate-500 uppercase mb-1">Tamaño prom. archivo</p>
                            <p className="font-mono font-bold text-lg">{perf.avg_layout_file_size_kb} KB</p>
                        </Card>
                    </div>
                </>
            )}

            {/* Token Consumption & Cost Tracking */}
            {tokenData && (
                <>
                    <div className="flex items-center justify-between mt-6">
                        <h2 className="text-base font-semibold text-slate-800 flex items-center gap-2">
                            <DollarSign className="w-5 h-5" /> Consumo y Costos
                        </h2>
                        <div className="flex items-center gap-2 text-xs text-slate-500">
                            <span>TC USD/MXN:</span>
                            {editingRate ? (
                                <div className="flex items-center gap-1">
                                    <Input
                                        type="number"
                                        step="0.01"
                                        value={newRate}
                                        onChange={(e) => setNewRate(e.target.value)}
                                        className="w-20 h-6 text-xs"
                                        data-testid="exchange-rate-input"
                                    />
                                    <Button size="sm" className="h-6 text-xs px-2" disabled={savingRate}
                                        data-testid="save-exchange-rate"
                                        onClick={async () => {
                                            setSavingRate(true);
                                            try {
                                                await updateExchangeRate(parseFloat(newRate));
                                                toast.success('Tipo de cambio actualizado');
                                                setEditingRate(false);
                                                fetchData();
                                            } catch { toast.error('Error'); }
                                            finally { setSavingRate(false); }
                                        }}>
                                        {savingRate ? <Loader2 className="w-3 h-3 animate-spin" /> : 'OK'}
                                    </Button>
                                    <Button size="sm" variant="ghost" className="h-6 text-xs px-2"
                                        onClick={() => setEditingRate(false)}>X</Button>
                                </div>
                            ) : (
                                <button
                                    className="font-mono text-blue-600 hover:underline cursor-pointer"
                                    onClick={() => { setNewRate(String(tokenData.exchange_rate)); setEditingRate(true); }}
                                    data-testid="edit-exchange-rate"
                                >
                                    ${tokenData.exchange_rate}
                                </button>
                            )}
                        </div>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="token-consumption-section">
                        <Card className="p-4">
                            <p className="text-xs text-slate-500 uppercase mb-1">Evaluaciones IA</p>
                            <p className="font-mono font-bold text-lg text-blue-600" data-testid="ai-eval-count">{tokenData.ai_evaluations}</p>
                        </Card>
                        <Card className="p-4">
                            <p className="text-xs text-slate-500 uppercase mb-1">Costo variable (USD)</p>
                            <p className="font-mono font-bold text-lg text-amber-600">${tokenData.variable_cost_usd}</p>
                        </Card>
                        <Card className="p-4">
                            <p className="text-xs text-slate-500 uppercase mb-1">Costo fijo (USD)</p>
                            <p className="font-mono font-bold text-lg text-slate-600">${tokenData.fixed_cost_usd}</p>
                        </Card>
                        <Card className="p-4">
                            <p className="text-xs text-slate-500 uppercase mb-1">Costo total (MXN)</p>
                            <p className="font-mono font-bold text-lg text-emerald-600" data-testid="total-cost-mxn">${tokenData.total_cost_mxn}</p>
                        </Card>
                    </div>
                    <Card className="mt-2">
                        <CardContent className="p-4">
                            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                                <div>
                                    <p className="text-xs text-slate-500">Tokens estimados</p>
                                    <p className="font-mono">{tokenData.estimated_tokens?.toLocaleString()}</p>
                                </div>
                                <div>
                                    <p className="text-xs text-slate-500">Variable MXN</p>
                                    <p className="font-mono">${tokenData.variable_cost_mxn}</p>
                                </div>
                                <div>
                                    <p className="text-xs text-slate-500">Fijo MXN (deploy)</p>
                                    <p className="font-mono">${tokenData.fixed_cost_mxn}</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </>
            )}
        </div>
    );
};

export default SystemHealth;
