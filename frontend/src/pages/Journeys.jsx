import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getClients, getProviders, deleteJourney, listClientConfigs, runSelection } from '../lib/api';
import { useJourneys } from '../hooks/useJourneys';
import { 
    formatDate, 
    getStatusColor, 
    getStatusLabel,
    getProgressColor,
    calculateDeliveryRate 
} from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Progress } from '../components/ui/progress';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { 
    Truck, Calendar as CalendarIcon, Eye, Upload, AlertTriangle,
    Filter, X, Search, Trash2, Loader2, ChevronLeft, ChevronRight,
    ExternalLink, PlayCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import PulseStrip from '../components/PulseStrip';
import PulseCell from '../components/PulseCell';
import api from '../lib/api';

const PAGE_SIZE_OPTIONS = [25, 50, 100];

const Journeys = () => {
    const { canEdit, hasRole, isCoordinator } = useAuth();
    const canDelete = hasRole(['coordinator', 'developer']);
    const canRunSelection = isCoordinator();
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [pulseConfig, setPulseConfig] = useState(null);
    const [selectionClients, setSelectionClients] = useState([]);
    const [runningSel, setRunningSel] = useState(false);

    // Filters
    const [dateFrom, setDateFrom] = useState(null);
    const [dateTo, setDateTo] = useState(null);
    const [selectedClient, setSelectedClient] = useState('all');
    const [selectedProvider, setSelectedProvider] = useState('all');
    const [selectedStatus, setSelectedStatus] = useState('all');
    const [showFilters, setShowFilters] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');

    // Pagination
    const [pageSize, setPageSize] = useState(25);
    const [currentPage, setCurrentPage] = useState(1);

    // Delete modal
    const [deleteModal, setDeleteModal] = useState({ open: false, journey: null });
    const [deleting, setDeleting] = useState(false);

    // P08 — Journeys via useJourneys hook (cancela auto, retry x2 en network errors)
    const journeysFilters = useMemo(() => ({
        date_from: dateFrom ? format(dateFrom, 'yyyy-MM-dd') : undefined,
        date_to: dateTo ? format(dateTo, 'yyyy-MM-dd') : undefined,
        client_id: selectedClient !== 'all' ? selectedClient : undefined,
        provider_id: selectedProvider !== 'all' ? selectedProvider : undefined,
        status: selectedStatus !== 'all' ? selectedStatus : undefined,
    }), [dateFrom, dateTo, selectedClient, selectedProvider, selectedStatus]);

    const { data: journeysData, loading: journeysLoading, error: journeysError, refetch: refetchJourneys } = useJourneys(journeysFilters);
    const journeys = useMemo(() => journeysData?.data || journeysData || [], [journeysData]);

    // Clients + Providers + Config: one-shot al montar (no requieren retry/cancel)
    const fetchAux = useCallback(async () => {
        try {
            const results = await Promise.allSettled([
                getClients(),
                getProviders(),
                api.get('/admin/config'),
                listClientConfigs().catch(() => ({ data: { data: [] } })),
            ]);
            const [clientsRes, providersRes, configRes, selRes] = results;
            if (clientsRes.status === 'fulfilled') setClients(clientsRes.value.data);
            if (providersRes.status === 'fulfilled') setProviders(providersRes.value.data);
            if (configRes.status === 'fulfilled') setPulseConfig(configRes.value.data?.pulse_config || null);
            if (selRes.status === 'fulfilled') {
                const items = selRes.value.data?.data || [];
                setSelectionClients(items.filter(c => c.selection_enabled && c.active !== false));
            }
        } catch { /* silent — clients/providers no son críticos */ }
    }, []);

    useEffect(() => { fetchAux(); }, [fetchAux]);

    // Loading combinado: muestra spinner mientras journeys carga (clients/providers son secundarios)
    const loading = journeysLoading;

    // Mostrar toast solo si journeys falla con error no recuperable (red persistente o 5xx)
    useEffect(() => {
        if (journeysError) {
            toast.error('Error al cargar rutas');
        }
    }, [journeysError]);

    // Refetch externo (compatibilidad con código que llamaba fetchData())
    const fetchData = refetchJourneys;

    const hasActiveFilters = dateFrom || dateTo || selectedClient !== 'all' || selectedProvider !== 'all' || selectedStatus !== 'all';

    const clearFilters = () => {
        setDateFrom(null); setDateTo(null);
        setSelectedClient('all'); setSelectedProvider('all'); setSelectedStatus('all');
        setSearchQuery('');
    };

    // Client-side search + pagination
    const filteredJourneys = useMemo(() => {
        if (!searchQuery.trim()) return journeys;
        const q = searchQuery.toLowerCase().trim();
        return journeys.filter(j =>
            (j.order_id || '').toLowerCase().includes(q) ||
            (j.driver_name || '').toLowerCase().includes(q) ||
            (j.client_name || '').toLowerCase().includes(q) ||
            (j.provider_name || '').toLowerCase().includes(q) ||
            (j.routal_plan_id || '').toLowerCase().includes(q) ||
            (j.routal_plan_label || '').toLowerCase().includes(q)
        );
    }, [journeys, searchQuery]);

    const totalPages = Math.max(1, Math.ceil(filteredJourneys.length / pageSize));
    const paginatedJourneys = useMemo(() => {
        const start = (currentPage - 1) * pageSize;
        return filteredJourneys.slice(start, start + pageSize);
    }, [filteredJourneys, currentPage, pageSize]);

    // Reset page when filters change
    useEffect(() => { setCurrentPage(1); }, [searchQuery, pageSize, journeys]);

    const handleDelete = async () => {
        const j = deleteModal.journey;
        if (!j) return;
        setDeleting(true);
        try {
            const res = await deleteJourney(j.id);
            toast.success(res.data?.message || 'Ruta eliminada');
            setDeleteModal({ open: false, journey: null });
            fetchData();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al eliminar ruta');
        }
        setDeleting(false);
    };

    const handleRunSelectionToday = async () => {
        if (selectionClients.length === 0) {
            toast.error('No hay clientes con selección habilitada');
            return;
        }
        const ok = window.confirm(
            `Re-ejecutará la selección SEL01 de hoy para ${selectionClients.length} cliente(s) con Routal habilitado.\n\n` +
            `Idempotente: drivers ya seleccionados se preservan, journeys NO se duplican.\n\n¿Continuar?`
        );
        if (!ok) return;
        setRunningSel(true);
        let totalSelected = 0;
        let totalErrors = 0;
        try {
            for (const cfg of selectionClients) {
                try {
                    const r = await runSelection(cfg.client_id);
                    totalSelected += r.data?.selected || 0;
                } catch (err) {
                    totalErrors++;
                    console.error(`SEL01 ${cfg.client_name}:`, err.response?.data?.detail);
                }
            }
            if (totalErrors === 0) {
                toast.success(`✔ SEL01 ejecutado · ${totalSelected} drivers seleccionados`);
            } else {
                toast.warning(`SEL01 con errores: ${totalSelected} drivers seleccionados, ${totalErrors} cliente(s) fallaron`);
            }
            fetchData();
        } finally {
            setRunningSel(false);
        }
    };

    const getRouteTypeLabel = (journey) => {
        const rt = journey.route_type || '';
        if (rt === 'CDMX / Zona Metro' || rt === 'CDMX') {
            return <span className="px-1.5 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded">CDMX</span>;
        }
        return (
            <span className="px-1.5 py-0.5 text-xs font-medium bg-violet-100 text-violet-700 rounded">
                {rt || 'CDMX'}{journey.city ? ` — ${journey.city}` : ''}
            </span>
        );
    };

    return (
        <div className="space-y-4" data-testid="journeys-page">
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold text-slate-900">Rutas</h2>
                <div className="flex items-center gap-2">
                    {/* Search bar */}
                    <div className="relative w-64">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <Input
                            placeholder="Buscar Order ID, plan Routal, driver..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            className="pl-9 h-9 text-sm"
                            data-testid="search-journeys-input"
                        />
                        {searchQuery && (
                            <button className="absolute right-2 top-1/2 -translate-y-1/2" onClick={() => setSearchQuery('')}>
                                <X className="w-3.5 h-3.5 text-slate-400" />
                            </button>
                        )}
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setShowFilters(!showFilters)} data-testid="toggle-filters-btn">
                        <Filter className="w-4 h-4 mr-1" />
                        Filtros {hasActiveFilters && <span className="ml-1 w-2 h-2 rounded-full bg-blue-500" />}
                    </Button>
                    {canRunSelection && selectionClients.length > 0 && (
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={handleRunSelectionToday}
                            disabled={runningSel}
                            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                            title={`Re-ejecuta SEL01 para ${selectionClients.length} cliente(s)`}
                            data-testid="run-selection-today-btn"
                        >
                            {runningSel ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <PlayCircle className="w-4 h-4 mr-1" />}
                            Re-ejecutar SEL01
                        </Button>
                    )}
                    {canEdit() && (
                        <Link to="/layout">
                            <Button size="sm" data-testid="upload-layout-btn">
                                <Upload className="w-4 h-4 mr-1" /> Cargar layout
                            </Button>
                        </Link>
                    )}
                </div>
            </div>

            {/* Filters panel */}
            {showFilters && (
                <Card>
                    <CardContent className="py-3 px-4">
                        <div className="flex flex-wrap gap-3 items-end">
                            <div className="space-y-1">
                                <span className="text-xs text-slate-500">Desde</span>
                                <Popover>
                                    <PopoverTrigger asChild>
                                        <Button variant="outline" size="sm" className="h-9 w-40 justify-start" data-testid="filter-date-from">
                                            <CalendarIcon className="w-4 h-4 mr-2" />
                                            {dateFrom ? format(dateFrom, 'dd MMM yyyy', { locale: es }) : 'Seleccionar'}
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-auto p-0"><Calendar mode="single" selected={dateFrom} onSelect={setDateFrom} locale={es} /></PopoverContent>
                                </Popover>
                            </div>
                            <div className="space-y-1">
                                <span className="text-xs text-slate-500">Hasta</span>
                                <Popover>
                                    <PopoverTrigger asChild>
                                        <Button variant="outline" size="sm" className="h-9 w-40 justify-start" data-testid="filter-date-to">
                                            <CalendarIcon className="w-4 h-4 mr-2" />
                                            {dateTo ? format(dateTo, 'dd MMM yyyy', { locale: es }) : 'Seleccionar'}
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-auto p-0"><Calendar mode="single" selected={dateTo} onSelect={setDateTo} locale={es} /></PopoverContent>
                                </Popover>
                            </div>
                            <Select value={selectedClient} onValueChange={setSelectedClient}>
                                <SelectTrigger className="w-40 h-9" data-testid="filter-client"><SelectValue placeholder="Cliente" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todos</SelectItem>
                                    {clients.map(c => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                                <SelectTrigger className="w-40 h-9" data-testid="filter-provider"><SelectValue placeholder="Proveedor" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todos</SelectItem>
                                    {providers.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                                </SelectContent>
                            </Select>
                            <Select value={selectedStatus} onValueChange={setSelectedStatus}>
                                <SelectTrigger className="w-36 h-9" data-testid="filter-status"><SelectValue placeholder="Estado" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todos</SelectItem>
                                    <SelectItem value="scheduled">Programada</SelectItem>
                                    <SelectItem value="in_progress">En progreso</SelectItem>
                                    <SelectItem value="closed">Cerrada</SelectItem>
                                </SelectContent>
                            </Select>
                            {hasActiveFilters && (
                                <Button variant="ghost" size="sm" onClick={clearFilters} data-testid="clear-filters-btn">
                                    <X className="w-4 h-4 mr-1" /> Limpiar
                                </Button>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            {pulseConfig && <PulseStrip journeys={journeys} pulseConfig={pulseConfig} />}

            {/* Journey List */}
            <Card>
                <CardContent className="p-0">
                    {loading ? (
                        <div className="p-8 space-y-4">
                            {[1, 2, 3].map((i) => <div key={`skel-${i}`} className="h-16 bg-slate-100 animate-pulse rounded" />)}
                        </div>
                    ) : filteredJourneys.length === 0 ? (
                        <div className="text-center py-16">
                            <Truck className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                            <h3 className="text-lg font-medium text-slate-700 mb-2">No hay rutas</h3>
                            <p className="text-slate-500 mb-6 max-w-md mx-auto">
                                {searchQuery ? `Sin resultados para "${searchQuery}"` :
                                 hasActiveFilters ? 'No se encontraron rutas con los filtros seleccionados' :
                                 'Comienza cargando un layout para crear tu primera ruta'}
                            </p>
                            {canEdit() && !hasActiveFilters && !searchQuery && (
                                <Link to="/layout"><Button data-testid="empty-state-upload-btn"><Upload className="w-4 h-4 mr-2" /> Cargar layout</Button></Link>
                            )}
                        </div>
                    ) : (
                        <>
                            <div className="overflow-x-auto">
                                <table className="data-table w-full">
                                    <thead>
                                        <tr>
                                            <th>Origen / ID</th>
                                            <th>Fecha</th>
                                            <th>Driver</th>
                                            <th>Cliente</th>
                                            <th>Proveedor</th>
                                            <th>Tipo</th>
                                            <th>Paquetes</th>
                                            <th>Progreso</th>
                                            <th>Incidencias</th>
                                            <th>Pulse</th>
                                            <th>Estado</th>
                                            <th>Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {paginatedJourneys.map((journey) => {
                                            const deliveryRate = calculateDeliveryRate(journey.packages_delivered, journey.packages_total);
                                            const progressColor = getProgressColor(deliveryRate);
                                            return (
                                                <tr key={journey.id} data-testid={`journey-item-${journey.id}`}>
                                                    <td className="max-w-[180px]" data-testid={`journey-source-${journey.id}`}>
                                                        {journey.source === 'routal' && journey.routal_plan_id ? (
                                                            <div className="flex items-center gap-1.5">
                                                                <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded border border-emerald-200 text-[10px] font-semibold uppercase shrink-0">Routal</span>
                                                                <span
                                                                    className="font-mono text-xs text-slate-700 truncate"
                                                                    title={journey.routal_plan_id}
                                                                >
                                                                    {journey.routal_plan_label || journey.routal_plan_id.slice(0, 10) + '…'}
                                                                </span>
                                                                {journey.routal_project_id && (
                                                                    <a
                                                                        href={`https://planner.routal.com/h/${journey.routal_project_id}/planner/plan/${journey.routal_plan_id}/stops`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        onClick={(e) => e.stopPropagation()}
                                                                        title="Abrir en Routal Planner"
                                                                        className="text-emerald-600 hover:text-emerald-800 shrink-0"
                                                                        data-testid={`open-routal-${journey.id}`}
                                                                    >
                                                                        <ExternalLink className="w-3.5 h-3.5" />
                                                                    </a>
                                                                )}
                                                            </div>
                                                        ) : journey.order_id ? (
                                                            <span className="font-mono text-xs text-blue-700 truncate inline-block max-w-full" title={journey.order_id}>
                                                                {journey.order_id}
                                                            </span>
                                                        ) : (
                                                            <span className="text-slate-400">—</span>
                                                        )}
                                                    </td>
                                                    <td className="font-mono text-sm">{formatDate(journey.date)}</td>
                                                    <td className="text-sm max-w-[120px] truncate" title={journey.driver_name}>
                                                        {journey.driver_name || <span className="text-slate-400">—</span>}
                                                    </td>
                                                    <td>{journey.client_name}</td>
                                                    <td>{journey.provider_name}</td>
                                                    <td>{getRouteTypeLabel(journey)}</td>
                                                    <td className="font-mono">{journey.packages_delivered}/{journey.packages_total}</td>
                                                    <td className="w-32">
                                                        <div className="flex items-center gap-2">
                                                            <Progress value={deliveryRate} className="h-2 flex-1" indicatorClassName={progressColor} />
                                                            <span className="text-xs font-mono w-10 text-right">{deliveryRate}%</span>
                                                        </div>
                                                    </td>
                                                    <td>
                                                        {journey.open_incidents_count > 0 ? (
                                                            <span className="inline-flex items-center gap-1 text-amber-600">
                                                                <AlertTriangle className="w-4 h-4" />{journey.open_incidents_count}
                                                            </span>
                                                        ) : <span className="text-slate-400">0</span>}
                                                    </td>
                                                    <td><PulseCell journey={journey} pulseConfig={pulseConfig} /></td>
                                                    <td>
                                                        <span className={`status-badge ${getStatusColor(journey.status)}`}>
                                                            {getStatusLabel(journey.status)}
                                                        </span>
                                                    </td>
                                                    <td>
                                                        <div className="flex items-center gap-1">
                                                            <Link to={`/journeys/${journey.id}`}>
                                                                <Button variant="ghost" size="sm" data-testid={`view-detail-${journey.id}`}>
                                                                    <Eye className="w-4 h-4" />
                                                                </Button>
                                                            </Link>
                                                            {canDelete && (
                                                                <Button variant="ghost" size="sm"
                                                                    className="text-red-500 hover:text-red-700 hover:bg-red-50"
                                                                    onClick={() => setDeleteModal({ open: true, journey })}
                                                                    data-testid={`delete-journey-${journey.id}`}>
                                                                    <Trash2 className="w-4 h-4" />
                                                                </Button>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            {/* Pagination */}
                            <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200" data-testid="pagination-bar">
                                <div className="flex items-center gap-2 text-sm text-slate-500">
                                    <span>{filteredJourneys.length} ruta{filteredJourneys.length !== 1 ? 's' : ''}</span>
                                    <span className="text-slate-300">|</span>
                                    <Select value={String(pageSize)} onValueChange={v => setPageSize(Number(v))}>
                                        <SelectTrigger className="w-20 h-7 text-xs" data-testid="page-size-select"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {PAGE_SIZE_OPTIONS.map(s => <SelectItem key={s} value={String(s)}>{s} / pag</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="flex items-center gap-1">
                                    <Button variant="ghost" size="sm" disabled={currentPage <= 1}
                                        onClick={() => setCurrentPage(p => p - 1)} data-testid="prev-page-btn">
                                        <ChevronLeft className="w-4 h-4" />
                                    </Button>
                                    <span className="text-sm text-slate-600 px-2">{currentPage} / {totalPages}</span>
                                    <Button variant="ghost" size="sm" disabled={currentPage >= totalPages}
                                        onClick={() => setCurrentPage(p => p + 1)} data-testid="next-page-btn">
                                        <ChevronRight className="w-4 h-4" />
                                    </Button>
                                </div>
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Delete Confirmation Modal */}
            <Dialog open={deleteModal.open} onOpenChange={(open) => !open && setDeleteModal({ open: false, journey: null })}>
                <DialogContent data-testid="delete-journey-modal">
                    <DialogHeader>
                        <DialogTitle className="text-red-700">Eliminar ruta</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 py-2">
                        <p className="text-sm text-slate-600">
                            Esta accion eliminara permanentemente la ruta y todos sus datos asociados:
                        </p>
                        <ul className="text-sm text-slate-600 space-y-1 pl-4 list-disc">
                            <li>Todos los paquetes de la ruta</li>
                            <li>Todas las incidencias registradas</li>
                            <li>Todas las imagenes y evidencias</li>
                            <li>Evaluaciones de IA y training samples</li>
                        </ul>
                        {deleteModal.journey && (
                            <div className="bg-slate-50 rounded-lg p-3 space-y-1">
                                <p className="text-xs text-slate-500">Ruta a eliminar:</p>
                                <p className="text-sm font-medium">{deleteModal.journey.order_id || deleteModal.journey.id?.slice(0, 12)}</p>
                                <p className="text-xs text-slate-500">
                                    {formatDate(deleteModal.journey.date)} — {deleteModal.journey.driver_name || 'Sin driver'} — {deleteModal.journey.packages_total} paquetes
                                </p>
                            </div>
                        )}
                        <p className="text-xs font-semibold text-red-600">
                            Esta accion no se puede deshacer.
                        </p>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteModal({ open: false, journey: null })} disabled={deleting}>
                            Cancelar
                        </Button>
                        <Button variant="destructive" onClick={handleDelete} disabled={deleting} data-testid="confirm-delete-btn">
                            {deleting ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Trash2 className="w-4 h-4 mr-1" />}
                            Eliminar definitivamente
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};

export default Journeys;
