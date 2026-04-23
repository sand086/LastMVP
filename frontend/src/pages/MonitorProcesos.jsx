import React, { useState, useEffect, useCallback } from 'react';
import { getAiEvalJobs, getAiEvalJob, createAiEvalJobManual, cancelAiEvalJob, retryAiEvalErrors } from '../lib/api';
import api from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Progress } from '../components/ui/progress';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../components/ui/dialog';
import {
    Activity, Search, RefreshCw, Loader2, ChevronLeft, ChevronRight,
    Clock, Zap, Cpu, XCircle, Eye, RotateCcw, AlertTriangle, Pause,
} from 'lucide-react';
import { toast } from 'sonner';

const STATUS_CONFIG = {
    'En_Cola': { label: 'En Cola', color: 'bg-amber-100 text-amber-700', progressColor: 'bg-amber-400' },
    'Evaluando': { label: 'Evaluando', color: 'bg-blue-100 text-blue-700', progressColor: 'bg-blue-500' },
    'Evaluada': { label: 'Evaluada', color: 'bg-emerald-100 text-emerald-700', progressColor: 'bg-emerald-500' },
    'Error': { label: 'Error', color: 'bg-red-100 text-red-700', progressColor: 'bg-red-500' },
    'Parcial': { label: 'Parcial', color: 'bg-orange-100 text-orange-700', progressColor: 'bg-orange-500' },
};

const TRIGGER_LABELS = {
    'scheduler_event': 'Auto (Evento)',
    'scheduler_cron': 'Auto (Cron)',
    'user_manual': 'Manual',
};

const formatDuration = (s) => {
    if (!s) return '-';
    if (s < 60) return `${s}s`;
    return `${Math.floor(s / 60)}m ${s % 60}s`;
};

const formatDateTime = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
};

const MonitorProcesos = () => {
    const [jobs, setJobs] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pages, setPages] = useState(1);
    const [loading, setLoading] = useState(true);
    const [filterStatus, setFilterStatus] = useState('all');
    const [filterTrigger, setFilterTrigger] = useState('all');
    const [filterRoute, setFilterRoute] = useState('');

    // Detail modal
    const [detailJob, setDetailJob] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);

    // Worker pause state (reuses /ai-evaluation/config)
    const [pauseState, setPauseState] = useState({ is_paused: false, reason: null, paused_until: null });
    const fetchPauseState = useCallback(async () => {
        try {
            const res = await api.get('/ai-evaluation/config');
            setPauseState(res.data.pause_state || { is_paused: false });
        } catch { /* ignore */ }
    }, []);
    useEffect(() => {
        fetchPauseState();
        const it = setInterval(fetchPauseState, 15000);
        return () => clearInterval(it);
    }, [fetchPauseState]);

    const fetchJobs = useCallback(async () => {
        setLoading(true);
        try {
            const params = { page, limit: 20 };
            if (filterStatus !== 'all') params.status = filterStatus;
            if (filterTrigger !== 'all') params.triggered_by = filterTrigger;
            if (filterRoute.trim()) params.route_id = filterRoute.trim();
            const res = await getAiEvalJobs(params);
            setJobs(res.data.data);
            setTotal(res.data.total);
            setPages(res.data.pages);
        } catch (err) {
            console.error('Failed to fetch jobs:', err);
        } finally {
            setLoading(false);
        }
    }, [page, filterStatus, filterTrigger, filterRoute]);

    useEffect(() => { fetchJobs(); }, [fetchJobs]);

    // Auto-refresh every 10s if there are active jobs
    useEffect(() => {
        const hasActive = jobs.some(j => j.status === 'En_Cola' || j.status === 'Evaluando');
        if (!hasActive) return;
        const interval = setInterval(fetchJobs, 10000);
        return () => clearInterval(interval);
    }, [jobs, fetchJobs]);

    const openDetail = async (jobId) => {
        setDetailLoading(true);
        try {
            const res = await getAiEvalJob(jobId);
            setDetailJob(res.data);
        } catch (err) {
            toast.error('Error al cargar detalle');
            console.error('Job detail error:', err);
        } finally {
            setDetailLoading(false);
        }
    };

    const handleCancel = async (jobId) => {
        try {
            await cancelAiEvalJob(jobId);
            toast.success('Job cancelado');
            fetchJobs();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'No se pudo cancelar');
        }
    };

    const handleReeval = async (routeId, routeName) => {
        try {
            const res = await createAiEvalJobManual({ route_id: routeId, force_reevaluate: true });
            toast.success(`Re-evaluacion encolada: ${res.data.total} guias de ${routeName}`);
            fetchJobs();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error');
        }
    };

    const [retryingAll, setRetryingAll] = useState(false);
    const handleRetryAllErrors = async () => {
        if (!window.confirm('Reencolar TODAS las rutas con jobs en Error? Se crearán nuevos jobs de evaluación (hasta 50 rutas).')) return;
        setRetryingAll(true);
        try {
            const res = await retryAiEvalErrors({ max_jobs: 50 });
            if (res.data.retried > 0) {
                toast.success(`${res.data.retried} rutas reencoladas (${res.data.skipped} ya estaban en curso)`);
            } else {
                toast.info(res.data.message || 'No hay jobs Error para reintentar');
            }
            fetchJobs();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al reintentar');
        } finally {
            setRetryingAll(false);
        }
    };

    return (
        <div className="space-y-4 sm:space-y-6" data-testid="monitor-procesos-page">
            {/* Header */}
            <div>
                <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">Monitor de Procesos - Evaluacion IA</h1>
                <p className="text-slate-500 text-xs sm:text-sm">Seguimiento en tiempo real del estado de las evaluaciones automaticas de guias</p>
            </div>

            {/* Worker paused banner */}
            {pauseState.is_paused && (
                <div
                    className="flex items-center gap-3 p-3 rounded-lg border border-amber-300 bg-amber-50"
                    data-testid="worker-paused-banner"
                >
                    <Pause className="w-5 h-5 text-amber-700 shrink-0" />
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-amber-900">Worker pausado — no se tomarán nuevos jobs</p>
                        <p className="text-xs text-amber-700 mt-0.5 truncate">{pauseState.reason || 'Pausa manual'}</p>
                    </div>
                    <a href="/admin?tab=model" className="text-xs font-semibold text-amber-800 underline whitespace-nowrap">Configurar →</a>
                </div>
            )}

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                <div className="relative flex-1 min-w-[150px] max-w-xs">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input value={filterRoute} onChange={(e) => { setFilterRoute(e.target.value); setPage(1); }} placeholder="Filtrar por route_id..." className="pl-9 text-sm" data-testid="filter-route" />
                </div>
                <Select value={filterStatus} onValueChange={(v) => { setFilterStatus(v); setPage(1); }}>
                    <SelectTrigger className="w-[140px]" data-testid="filter-status"><SelectValue placeholder="Estatus" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        <SelectItem value="En_Cola">En Cola</SelectItem>
                        <SelectItem value="Evaluando">Evaluando</SelectItem>
                        <SelectItem value="Evaluada">Evaluada</SelectItem>
                        <SelectItem value="Error">Error</SelectItem>
                        <SelectItem value="Parcial">Parcial</SelectItem>
                    </SelectContent>
                </Select>
                <Select value={filterTrigger} onValueChange={(v) => { setFilterTrigger(v); setPage(1); }}>
                    <SelectTrigger className="w-[150px]" data-testid="filter-trigger"><SelectValue placeholder="Origen" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        <SelectItem value="scheduler_event">Auto (Evento)</SelectItem>
                        <SelectItem value="scheduler_cron">Auto (Cron)</SelectItem>
                        <SelectItem value="user_manual">Manual</SelectItem>
                    </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={fetchJobs} data-testid="refresh-jobs-btn"><RefreshCw className="w-4 h-4 mr-1" />Actualizar</Button>
                <Button variant="outline" size="sm" onClick={handleRetryAllErrors} disabled={retryingAll} className="text-amber-700 border-amber-300 hover:bg-amber-50" data-testid="retry-all-errors-btn" title="Reencola todas las rutas en estado Error">
                    {retryingAll ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RotateCcw className="w-4 h-4 mr-1" />}
                    Reintentar Errores
                </Button>
                <span className="text-xs text-slate-400">{total} jobs</span>
            </div>

            {/* Table */}
            <Card>
                <CardContent className="p-0">
                    {loading ? (
                        <div className="p-8 flex justify-center"><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>
                    ) : jobs.length === 0 ? (
                        <div className="text-center py-12">
                            <Activity className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                            <p className="text-slate-500">No hay jobs de evaluacion</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="data-table w-full">
                                <thead>
                                    <tr>
                                        <th>Fecha</th>
                                        <th>Ruta</th>
                                        <th>Origen</th>
                                        <th>Guias</th>
                                        <th>Avance</th>
                                        <th>Estatus</th>
                                        <th>Tokens</th>
                                        <th>Duracion</th>
                                        <th>Acciones</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {jobs.map(job => {
                                        const sc = STATUS_CONFIG[job.status] || STATUS_CONFIG['Error'];
                                        return (
                                            <tr key={job.job_id} data-testid={`job-row-${job.job_id}`}>
                                                <td className="text-xs font-mono">{formatDateTime(job.fecha_creacion)}</td>
                                                <td className="font-medium text-sm max-w-[120px] truncate" title={job.route_name}>{job.route_name}</td>
                                                <td>
                                                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                                                        {job.triggered_by === 'user_manual' && <Zap className="w-3 h-3 inline mr-1" />}
                                                        {TRIGGER_LABELS[job.triggered_by] || job.triggered_by}
                                                    </span>
                                                </td>
                                                <td className="font-mono text-sm">{job.guias_evaluadas}/{job.total_guias}</td>
                                                <td className="w-[100px]">
                                                    <div className="flex items-center gap-2">
                                                        <Progress value={job.progress_percent} className="h-2 flex-1" indicatorClassName={sc.progressColor} />
                                                        <span className="text-xs font-mono w-8 text-right">{job.progress_percent}%</span>
                                                    </div>
                                                </td>
                                                <td><span className={`px-2 py-0.5 text-xs font-medium rounded ${sc.color}`}>{sc.label}</span></td>
                                                <td className="font-mono text-xs">{(job.tokens_consumidos || 0).toLocaleString()}</td>
                                                <td className="text-xs">{formatDuration(job.duracion_segundos)}</td>
                                                <td>
                                                    <div className="flex items-center gap-1">
                                                        <Button variant="ghost" size="icon" onClick={() => openDetail(job.job_id)} title="Ver detalle" data-testid={`view-job-${job.job_id}`}><Eye className="w-4 h-4" /></Button>
                                                        {job.status === 'En_Cola' && (
                                                            <Button variant="ghost" size="icon" className="text-red-500" onClick={() => handleCancel(job.job_id)} title="Cancelar" data-testid={`cancel-job-${job.job_id}`}><XCircle className="w-4 h-4" /></Button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Pagination */}
            {pages > 1 && (
                <div className="flex items-center justify-between text-sm text-slate-500">
                    <span>Pagina {page} de {pages}</span>
                    <div className="flex gap-1">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><ChevronLeft className="w-4 h-4" /></Button>
                        <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(p => p + 1)}><ChevronRight className="w-4 h-4" /></Button>
                    </div>
                </div>
            )}

            {/* Detail Modal */}
            <Dialog open={!!detailJob} onOpenChange={() => setDetailJob(null)}>
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                    {detailLoading ? (
                        <div className="p-8 flex justify-center"><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>
                    ) : detailJob && (
                        <>
                            <DialogHeader>
                                <DialogTitle className="font-heading">Detalle: {detailJob.route_name}</DialogTitle>
                                <DialogDescription>
                                    Job {detailJob.job_id?.slice(0, 8)}... | {TRIGGER_LABELS[detailJob.triggered_by]} | {formatDateTime(detailJob.fecha_creacion)}
                                    {detailJob.triggered_by_user && ` | ${detailJob.triggered_by_user}`}
                                </DialogDescription>
                            </DialogHeader>

                            {/* Friendly error banner */}
                            {detailJob.error_detail && (
                                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700" data-testid="job-error-detail">
                                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                                    <span>{detailJob.error_detail}</span>
                                </div>
                            )}

                            {/* Summary */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-3">
                                <div className="text-center p-2 bg-slate-50 rounded">
                                    <p className="text-lg font-mono font-bold">{detailJob.guias_evaluadas}/{detailJob.total_guias}</p>
                                    <p className="text-[10px] text-slate-500">Evaluadas</p>
                                </div>
                                <div className="text-center p-2 bg-slate-50 rounded">
                                    <p className="text-lg font-mono font-bold text-red-600">{detailJob.guias_con_error}</p>
                                    <p className="text-[10px] text-slate-500">Errores</p>
                                </div>
                                <div className="text-center p-2 bg-slate-50 rounded">
                                    <p className="text-lg font-mono font-bold">{(detailJob.tokens_consumidos || 0).toLocaleString()}</p>
                                    <p className="text-[10px] text-slate-500">Tokens</p>
                                </div>
                                <div className="text-center p-2 bg-slate-50 rounded">
                                    <p className="text-lg font-mono font-bold">{formatDuration(detailJob.duracion_segundos)}</p>
                                    <p className="text-[10px] text-slate-500">Duracion</p>
                                </div>
                            </div>

                            {/* Guias table */}
                            <div className="overflow-x-auto max-h-[300px]">
                                <table className="data-table w-full text-sm">
                                    <thead>
                                        <tr><th>Guia ID</th><th>Estatus</th><th>Tokens</th><th>Error</th></tr>
                                    </thead>
                                    <tbody>
                                        {(detailJob.guias_detail || []).map(g => {
                                            const gc = STATUS_CONFIG[g.status] || STATUS_CONFIG['Error'];
                                            return (
                                                <tr key={g.guia_id}>
                                                    <td className="font-mono text-xs">{g.guia_id?.slice(0, 12)}...</td>
                                                    <td><span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${gc.color}`}>{gc.label}</span></td>
                                                    <td className="font-mono text-xs">{g.tokens || 0}</td>
                                                    <td className="text-xs text-red-600 max-w-[200px] truncate" title={g.error || ''}>{g.error || '-'}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            <DialogFooter className="gap-2">
                                <Button variant="outline" onClick={() => setDetailJob(null)}>Cerrar</Button>
                                <Button onClick={() => { handleReeval(detailJob.route_id, detailJob.route_name); setDetailJob(null); }} data-testid="reeval-from-detail">
                                    <RotateCcw className="w-4 h-4 mr-2" />Re-evaluar ruta
                                </Button>
                            </DialogFooter>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
};

export default MonitorProcesos;
