import React, { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
    FileText, Download, Loader2, RefreshCw, ChevronLeft, ChevronRight, Filter
} from 'lucide-react';
import { toast } from 'sonner';
import { downloadFile } from '../lib/utils';

const ACTION_LABELS = {
    login_success: 'Login exitoso',
    login_failed: 'Login fallido',
    route_created: 'Ruta creada',
    route_started: 'Ruta iniciada',
    route_closed: 'Ruta cerrada',
    incident_created: 'Incidencia creada',
    incident_resolved: 'Incidencia resuelta',
    incident_updated: 'Incidencia actualizada',
    layout_uploaded: 'Layout cargado',
    user_created: 'Usuario creado',
    user_modified: 'Usuario modificado',
    user_deleted: 'Usuario eliminado',
    export_generated: 'Exportación generada',
};

const getActionColor = (action) => {
    if (action.includes('failed') || action.includes('deleted')) return 'bg-red-100 text-red-700';
    if (action.includes('created') || action.includes('success')) return 'bg-emerald-100 text-emerald-700';
    if (action.includes('started') || action.includes('uploaded')) return 'bg-blue-100 text-blue-700';
    if (action.includes('closed') || action.includes('resolved')) return 'bg-slate-100 text-slate-700';
    return 'bg-slate-100 text-slate-600';
};

const SystemLogs = () => {
    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);
    const [actionTypes, setActionTypes] = useState([]);

    // Filters
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [filterUser, setFilterUser] = useState('');
    const [filterAction, setFilterAction] = useState('all');
    const [errorsOnly, setErrorsOnly] = useState(false);

    const fetchLogs = useCallback(async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ page: String(page), page_size: '30' });
            if (dateFrom) params.append('date_from', dateFrom);
            if (dateTo) params.append('date_to', dateTo);
            if (filterUser) params.append('user_id', filterUser);
            if (filterAction && filterAction !== 'all') params.append('action', filterAction);
            if (errorsOnly) params.append('errors_only', 'true');
            
            const res = await api.get(`/system/logs?${params}`);
            setLogs(res.data.logs);
            setTotal(res.data.total);
            setTotalPages(res.data.total_pages);
        } catch (error) {
            console.error('Error fetching logs:', error);
        } finally {
            setLoading(false);
        }
    }, [page, dateFrom, dateTo, filterUser, filterAction, errorsOnly]);

    const fetchActionTypes = useCallback(async () => {
        try {
            const res = await api.get('/system/logs/actions');
            setActionTypes(res.data.actions || []);
        } catch (error) {
            console.error('Error fetching action types:', error);
        }
    }, []);

    useEffect(() => { fetchLogs(); }, [fetchLogs]);
    useEffect(() => { fetchActionTypes(); }, [fetchActionTypes]);

    const handleExport = async () => {
        setExporting(true);
        try {
            const params = new URLSearchParams();
            if (dateFrom) params.append('date_from', dateFrom);
            if (dateTo) params.append('date_to', dateTo);
            if (filterUser) params.append('user_id', filterUser);
            if (filterAction && filterAction !== 'all') params.append('action', filterAction);
            if (errorsOnly) params.append('errors_only', 'true');
            
            const res = await api.get(`/system/logs/export?${params}`, { responseType: 'blob' });
            downloadFile(res.data, `audit_logs_${new Date().toISOString().slice(0,10)}.csv`);
            toast.success('Logs exportados');
        } catch (error) {
            toast.error('Error al exportar logs');
        } finally {
            setExporting(false);
        }
    };

    const handleFilter = () => {
        setPage(1);
        fetchLogs();
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">Log Viewer</h1>
                    <p className="text-slate-500 text-sm">Auditoría de acciones del sistema ({total} registros)</p>
                </div>
                <Button variant="outline" onClick={handleExport} disabled={exporting} data-testid="export-logs-btn">
                    {exporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Download className="w-4 h-4 mr-2" />}
                    Exportar CSV
                </Button>
            </div>

            {/* Filters */}
            <Card>
                <CardContent className="pt-4">
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
                        <div className="space-y-1">
                            <Label className="text-xs">Desde</Label>
                            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="log-filter-from" />
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs">Hasta</Label>
                            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="log-filter-to" />
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs">Acción</Label>
                            <Select value={filterAction} onValueChange={setFilterAction}>
                                <SelectTrigger data-testid="log-filter-action">
                                    <SelectValue placeholder="Todas" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todas</SelectItem>
                                    {actionTypes.map(a => (
                                        <SelectItem key={a} value={a}>{ACTION_LABELS[a] || a}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="flex items-end gap-2">
                            <label className="flex items-center gap-2 text-sm cursor-pointer">
                                <input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} className="rounded" />
                                Solo errores
                            </label>
                        </div>
                        <Button onClick={handleFilter} data-testid="apply-log-filters-btn">
                            <Filter className="w-4 h-4 mr-2" /> Filtrar
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Logs Table */}
            <Card>
                <CardContent className="p-0">
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
                        </div>
                    ) : logs.length === 0 ? (
                        <div className="text-center py-12 text-slate-500">
                            <FileText className="w-10 h-10 mx-auto mb-2 text-slate-300" />
                            <p>No hay logs para los filtros seleccionados</p>
                        </div>
                    ) : (
                        <div className="overflow-x-auto">
                            <table className="data-table w-full text-sm">
                                <thead>
                                    <tr>
                                        <th>Timestamp</th>
                                        <th>Usuario</th>
                                        <th>Rol</th>
                                        <th>Acción</th>
                                        <th>Entidad</th>
                                        <th>ID</th>
                                        <th>IP</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {logs.map((log) => (
                                        <tr key={log.id} data-testid={`log-row-${log.id}`}>
                                            <td className="font-mono text-xs whitespace-nowrap">{log.timestamp?.slice(0, 19)}</td>
                                            <td className="text-xs">{log.user_name || log.user_id}</td>
                                            <td><span className="px-1.5 py-0.5 text-xs bg-slate-100 rounded">{log.user_role}</span></td>
                                            <td>
                                                <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${getActionColor(log.action)}`}>
                                                    {ACTION_LABELS[log.action] || log.action}
                                                </span>
                                            </td>
                                            <td className="text-xs">{log.entity_type}</td>
                                            <td className="font-mono text-xs max-w-[100px] truncate">{log.entity_id}</td>
                                            <td className="font-mono text-xs">{log.ip}</td>
                                            <td>
                                                <span className={`px-1.5 py-0.5 text-xs rounded ${
                                                    log.status === 'success' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                                                }`}>{log.status}</span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between">
                    <p className="text-sm text-slate-500">Página {page} de {totalPages}</p>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                            <ChevronLeft className="w-4 h-4" />
                        </Button>
                        <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                            <ChevronRight className="w-4 h-4" />
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SystemLogs;
