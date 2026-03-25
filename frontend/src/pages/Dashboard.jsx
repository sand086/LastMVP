import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useSortableTable } from '../lib/useSortableTable';
import { useWebSocket } from '../lib/useWebSocket';
import { 
    getDashboardStats, 
    getJourneys, 
    getIncidentsBreakdown,
    getProviderComparison,
    exportJourneys,
    getClients,
    getProviders,
    syncKosmoTracking,
    getKosmoSyncStatus,
    searchPackages
} from '../lib/api';
import api from '../lib/api';
import { 
    formatDate, 
    getTodayDate, 
    getStatusColor, 
    getStatusLabel,
    getProgressColor,
    calculateDeliveryRate,
    downloadFile
} from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
    Truck, 
    Package, 
    AlertTriangle, 
    CheckCircle2, 
    Calendar as CalendarIcon,
    Download,
    Eye,
    RefreshCw,
    Upload,
    TrendingUp,
    Radio,
    ShieldCheck,
    Search
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

const KPICard = ({ title, value, subValue, icon: Icon, color, loading }) => (
    <Card className="kpi-card" data-testid={`kpi-${title.toLowerCase().replace(/\s+/g, '-')}`}>
        <CardContent className="p-0">
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-xs font-medium text-slate-500 uppercase tracking-wider mb-1">
                        {title}
                    </p>
                    {loading ? (
                        <div className="h-8 w-20 bg-slate-200 animate-pulse rounded" />
                    ) : (
                        <p className="text-3xl font-heading font-bold text-slate-900">
                            {value}
                        </p>
                    )}
                    {subValue && (
                        <p className="text-sm text-slate-500 mt-1">{subValue}</p>
                    )}
                </div>
                <div 
                    className="w-12 h-12 rounded-sm flex items-center justify-center"
                    style={{ backgroundColor: `${color}15` }}
                >
                    <Icon className="w-6 h-6" style={{ color }} strokeWidth={1.5} />
                </div>
            </div>
        </CardContent>
    </Card>
);

// Sortable Routes Table component
const RoutesTable = ({ journeys }) => {
    const { sortedData, SortHeader } = useSortableTable(journeys);
    return (
        <div className="overflow-x-auto">
            <table className="data-table w-full">
                <thead>
                    <tr>
                        <SortHeader field="date">Fecha</SortHeader>
                        <SortHeader field="client_name">Cliente</SortHeader>
                        <SortHeader field="provider_name">Proveedor</SortHeader>
                        <SortHeader field="driver_name">Driver</SortHeader>
                        <SortHeader field="packages_total">Paquetes</SortHeader>
                        <SortHeader field="packages_delivered">Progreso</SortHeader>
                        <SortHeader field="open_incidents_count">Incidencias</SortHeader>
                        <SortHeader field="status">Estado</SortHeader>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    {sortedData.map((journey) => {
                        const deliveryRate = calculateDeliveryRate(journey.packages_delivered, journey.packages_total);
                        const progressColor = getProgressColor(deliveryRate);
                        return (
                            <tr key={journey.id} data-testid={`journey-row-${journey.id}`}>
                                <td className="font-mono text-sm">{formatDate(journey.date)}</td>
                                <td>{journey.client_name}</td>
                                <td>{journey.provider_name}</td>
                                <td className="text-sm">
                                    {journey.driver_name ? (
                                        <span className="text-slate-700">
                                            {journey.driver_name.length > 20
                                                ? journey.driver_name.split(' ').slice(0, 1).join(' ') + ' ' + (journey.driver_name.split(' ')[1]?.[0] || '') + '.'
                                                : journey.driver_name}
                                        </span>
                                    ) : <span className="text-slate-400 italic">Sin asignar</span>}
                                </td>
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
                                <td>
                                    <span className={`status-badge ${getStatusColor(journey.status)}`}>{getStatusLabel(journey.status)}</span>
                                </td>
                                <td>
                                    <Link to={`/journeys/${journey.id}`}>
                                        <Button variant="ghost" size="sm" data-testid={`view-journey-${journey.id}`}>
                                            <Eye className="w-4 h-4 mr-1" />Ver detalle
                                        </Button>
                                    </Link>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

const Dashboard = () => {
    const { canEdit } = useAuth();
    const [stats, setStats] = useState(null);
    const [journeys, setJourneys] = useState([]);
    const [pagination, setPagination] = useState({ page: 1, page_size: 25, total_count: 0, total_pages: 1 });
    const [incidentsBreakdown, setIncidentsBreakdown] = useState({});
    const [providerComparison, setProviderComparison] = useState([]);
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);
    const [kosmoSync, setKosmoSync] = useState({ last_sync: null, total_checked: 0, updated: 0, errors: 0 });
    const [syncing, setSyncing] = useState(false);
    const [packageSearch, setPackageSearch] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [searching, setSearching] = useState(false);

    // Filters
    const [dateFrom, setDateFrom] = useState(new Date());
    const [dateTo, setDateTo] = useState(new Date());
    const [selectedClient, setSelectedClient] = useState('all');
    const [selectedProvider, setSelectedProvider] = useState('all');
    const [selectedStatus, setSelectedStatus] = useState('all');

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(25);

    const fetchData = useCallback(async () => {
        try {
            const dateFromStr = format(dateFrom, 'yyyy-MM-dd');
            const dateToStr = format(dateTo, 'yyyy-MM-dd');

            const [statsRes, journeysRes, breakdownRes, comparisonRes, clientsRes, providersRes, kosmoRes] = await Promise.all([
                getDashboardStats(dateFromStr, dateToStr),
                getJourneys({
                    date_from: dateFromStr,
                    date_to: dateToStr,
                    client_id: selectedClient !== 'all' ? selectedClient : undefined,
                    provider_id: selectedProvider !== 'all' ? selectedProvider : undefined,
                    status: selectedStatus !== 'all' ? selectedStatus : undefined,
                    page: currentPage,
                    page_size: pageSize,
                }),
                getIncidentsBreakdown(dateFromStr, dateToStr),
                getProviderComparison(dateFromStr, dateToStr),
                getClients(),
                getProviders(),
                getKosmoSyncStatus().catch(() => ({ data: { last_sync: null } })),
            ]);

            setStats(statsRes.data);
            const jData = journeysRes.data;
            setJourneys(jData.data || []);
            setPagination(jData.pagination || { page: 1, page_size: 25, total_count: 0, total_pages: 1 });
            setIncidentsBreakdown(breakdownRes.data);
            setProviderComparison(comparisonRes.data);
            setClients(clientsRes.data);
            setProviders(providersRes.data);
            if (kosmoRes.data) setKosmoSync(kosmoRes.data);
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
            toast.error('Error al cargar datos');
        } finally {
            setLoading(false);
        }
    }, [dateFrom, dateTo, selectedClient, selectedProvider, selectedStatus, currentPage, pageSize]);

    useEffect(() => {
        fetchData();
        
        // Polling every 60 seconds
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, [fetchData]);

    // WebSocket for real-time updates
    const handleWsEvent = useCallback((event) => {
        if (['stats_update', 'journey_update', 'incident_update', 'sync_update'].includes(event.type)) {
            fetchData();
        }
    }, [fetchData]);
    const { isConnected: wsConnected } = useWebSocket(handleWsEvent);

    // Reset page to 1 when filters change
    useEffect(() => {
        setCurrentPage(1);
    }, [dateFrom, dateTo, selectedClient, selectedProvider, selectedStatus]);

    const handleExport = async () => {
        setExporting(true);
        try {
            const dateFromStr = format(dateFrom, 'yyyy-MM-dd');
            const dateToStr = format(dateTo, 'yyyy-MM-dd');
            
            const response = await exportJourneys({
                date_from: dateFromStr,
                date_to: dateToStr,
                client_id: selectedClient !== 'all' ? selectedClient : undefined,
                provider_id: selectedProvider !== 'all' ? selectedProvider : undefined,
            });
            
            downloadFile(response.data, `rutas_${dateFromStr}_${dateToStr}.xlsx`);
            toast.success('Archivo exportado exitosamente');
        } catch (error) {
            toast.error('Error al exportar');
        }
        setExporting(false);
    };

    const handleRefresh = () => {
        setLoading(true);
        fetchData();
    };

    const handleKosmoSync = async () => {
        setSyncing(true);
        try {
            await syncKosmoTracking();
            toast.success('Sincronización iniciada en segundo plano');
            // Poll sync status after a short delay
            setTimeout(async () => {
                try {
                    const statusRes = await api.get('/sync/status');
                    const s = statusRes.data;
                    if (s.total_checked !== undefined) {
                        setKosmoSync({ last_sync: s.last_sync || new Date().toISOString(), total_checked: s.total_checked, updated: s.updated, errors: s.errors || 0 });
                    }
                } catch (_) {}
                fetchData();
                setSyncing(false);
            }, 5000);
        } catch (error) {
            toast.error('Error al sincronizar con Kosmo');
            setSyncing(false);
        }
    };

    const getTimeSince = (isoDate) => {
        if (!isoDate) return null;
        const diff = Math.floor((Date.now() - new Date(isoDate).getTime()) / 60000);
        if (diff < 1) return 'ahora';
        if (diff < 60) return `hace ${diff} min`;
        if (diff < 1440) return `hace ${Math.floor(diff / 60)}h`;
        return `hace ${Math.floor(diff / 1440)}d`;
    };

    const handlePackageSearch = async (query) => {
        setPackageSearch(query);
        if (query.length < 2) { setSearchResults([]); return; }
        setSearching(true);
        try {
            const res = await searchPackages(query);
            setSearchResults(res.data || []);
        } catch { setSearchResults([]); }
        finally { setSearching(false); }
    };

    return (
        <div className="space-y-6">
            {/* WebSocket connection indicator */}
            <div className="flex items-center justify-end">
                <span className="flex items-center gap-1.5 text-xs text-slate-400" data-testid="ws-status">
                    <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                    {wsConnected ? 'En vivo' : 'Reconectando...'}
                </span>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                <KPICard
                    title="Rutas activas"
                    value={stats?.active_journeys || 0}
                    subValue="en progreso hoy"
                    icon={Truck}
                    color="#1A7A4A"
                    loading={loading}
                />
                <KPICard
                    title="Paquetes entregados"
                    value={`${stats?.delivered_packages || 0}/${stats?.total_packages || 0}`}
                    subValue={`${stats?.delivery_rate || 0}% completado`}
                    icon={Package}
                    color="#2E6096"
                    loading={loading}
                />
                <KPICard
                    title="Incidencias abiertas"
                    value={stats?.open_incidents || 0}
                    subValue="requieren atención"
                    icon={AlertTriangle}
                    color="#C07000"
                    loading={loading}
                />
                <KPICard
                    title="Rutas cerradas"
                    value={stats?.closed_journeys || 0}
                    subValue="completadas hoy"
                    icon={CheckCircle2}
                    color="#2E6096"
                    loading={loading}
                />
                <KPICard
                    title="Calidad de soporte"
                    value={`${stats?.avg_evidence_score || 0}%`}
                    subValue={stats?.packages_incomplete_support > 0 ? `${stats.packages_incomplete_support} sin soporte completo` : 'Todos completos'}
                    icon={ShieldCheck}
                    color={
                        (stats?.avg_evidence_score || 0) >= 90 ? '#1A7A4A' :
                        (stats?.avg_evidence_score || 0) >= 70 ? '#C07000' : '#B91C1C'
                    }
                    loading={loading}
                />
            </div>

            {/* Package Search Bar */}
            <div className="relative" data-testid="package-search-container">
                <div className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-sm">
                    <Search className="w-4 h-4 text-slate-400 shrink-0" />
                    <input
                        type="text"
                        value={packageSearch}
                        onChange={(e) => handlePackageSearch(e.target.value)}
                        placeholder="Buscar paquete por guía o referencia..."
                        className="flex-1 text-sm bg-transparent outline-none placeholder:text-slate-400"
                        data-testid="package-search-input"
                    />
                    {searching && <RefreshCw className="w-3.5 h-3.5 text-slate-400 animate-spin" />}
                </div>
                {searchResults.length > 0 && packageSearch.length >= 2 && (
                    <div className="absolute z-20 w-full mt-1 bg-white border border-slate-200 rounded-sm shadow-lg max-h-64 overflow-y-auto">
                        {searchResults.map((pkg) => (
                            <a
                                key={pkg.id}
                                href={`/journeys/${pkg.journey_id}`}
                                className="flex items-center justify-between px-4 py-2.5 hover:bg-slate-50 border-b border-slate-100 last:border-0"
                                data-testid={`search-result-${pkg.id}`}
                            >
                                <div className="min-w-0">
                                    <p className="text-sm font-mono font-medium text-slate-900 truncate">
                                        {pkg.order_reference_id || pkg.tracking_number}
                                    </p>
                                    <p className="text-xs text-slate-500 truncate">{pkg.recipient_name} — {pkg.address}</p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0 ml-3">
                                    <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                                        pkg.status === 'delivered' ? 'bg-emerald-100 text-emerald-700' :
                                        pkg.status === 'failed' ? 'bg-red-100 text-red-700' :
                                        'bg-amber-100 text-amber-700'
                                    }`}>{pkg.status}</span>
                                    <span className="text-xs text-slate-400">{pkg.journey_date}</span>
                                </div>
                            </a>
                        ))}
                    </div>
                )}
            </div>

            {/* Kosmo Sync Indicator */}
            <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-sm" data-testid="kosmo-sync-bar">
                <div className="flex items-center gap-2 text-sm text-slate-600">
                    <Radio className="w-4 h-4 text-slate-400" />
                    <span>Sincronización Kosmo (cada 10 min):</span>
                    {kosmoSync.last_sync ? (
                        <span className="font-mono text-xs text-slate-500">
                            {getTimeSince(kosmoSync.last_sync)} — {kosmoSync.total_checked} verificados, {kosmoSync.updated} actualizados
                            {kosmoSync.errors > 0 && (
                                <span className="text-amber-600 font-medium ml-1">· {kosmoSync.errors} errores</span>
                            )}
                        </span>
                    ) : (
                        <span className="text-xs text-slate-400">Sin sincronización previa</span>
                    )}
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleKosmoSync}
                    disabled={syncing}
                    data-testid="kosmo-sync-btn"
                    className="h-7 text-xs"
                >
                    <RefreshCw className={`h-3 w-3 mr-1.5 ${syncing ? 'animate-spin' : ''}`} />
                    {syncing ? 'Sincronizando...' : 'Sincronizar ahora'}
                </Button>
            </div>

            {/* Filters */}
            <Card>
                <CardContent className="p-4">
                    <div className="flex flex-wrap items-center gap-4">
                        {/* Date Range */}
                        <div className="flex items-center gap-2">
                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button 
                                        variant="outline" 
                                        className="justify-start text-left font-normal"
                                        data-testid="date-from-picker"
                                    >
                                        <CalendarIcon className="mr-2 h-4 w-4" />
                                        {format(dateFrom, 'dd MMM yyyy', { locale: es })}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-auto p-0" align="start">
                                    <Calendar
                                        mode="single"
                                        selected={dateFrom}
                                        onSelect={(date) => date && setDateFrom(date)}
                                        initialFocus
                                    />
                                </PopoverContent>
                            </Popover>
                            <span className="text-slate-400">—</span>
                            <Popover>
                                <PopoverTrigger asChild>
                                    <Button 
                                        variant="outline" 
                                        className="justify-start text-left font-normal"
                                        data-testid="date-to-picker"
                                    >
                                        <CalendarIcon className="mr-2 h-4 w-4" />
                                        {format(dateTo, 'dd MMM yyyy', { locale: es })}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-auto p-0" align="start">
                                    <Calendar
                                        mode="single"
                                        selected={dateTo}
                                        onSelect={(date) => date && setDateTo(date)}
                                        initialFocus
                                    />
                                </PopoverContent>
                            </Popover>
                        </div>

                        {/* Client Filter */}
                        <Select value={selectedClient} onValueChange={setSelectedClient}>
                            <SelectTrigger className="w-[180px]" data-testid="client-filter">
                                <SelectValue placeholder="Cliente" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Todos los clientes</SelectItem>
                                {clients.map((client) => (
                                    <SelectItem key={client.id} value={client.id}>
                                        {client.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        {/* Provider Filter */}
                        <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                            <SelectTrigger className="w-[180px]" data-testid="provider-filter">
                                <SelectValue placeholder="Proveedor" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Todos los proveedores</SelectItem>
                                {providers.map((provider) => (
                                    <SelectItem key={provider.id} value={provider.id}>
                                        {provider.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>

                        {/* Status Filter */}
                        <Select value={selectedStatus} onValueChange={setSelectedStatus}>
                            <SelectTrigger className="w-[160px]" data-testid="status-filter">
                                <SelectValue placeholder="Estado" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">Todos</SelectItem>
                                <SelectItem value="scheduled">Programada</SelectItem>
                                <SelectItem value="in_progress">En progreso</SelectItem>
                                <SelectItem value="closed">Cerrada</SelectItem>
                            </SelectContent>
                        </Select>

                        <div className="flex-1" />

                        <Button 
                            variant="outline" 
                            size="icon"
                            onClick={handleRefresh}
                            data-testid="refresh-btn"
                        >
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>

                        <Button
                            variant="outline"
                            onClick={handleExport}
                            disabled={exporting}
                            data-testid="export-btn"
                        >
                            <Download className="h-4 w-4 mr-2" />
                            Exportar
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Journey Table */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <CardTitle className="font-heading text-lg">Rutas</CardTitle>
                        {canEdit() && (
                            <Link to="/layout">
                                <Button size="sm" data-testid="new-journey-btn">
                                    <Upload className="h-4 w-4 mr-2" />
                                    Cargar layout
                                </Button>
                            </Link>
                        )}
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    {journeys.length === 0 ? (
                        <div className="text-center py-12">
                            <Truck className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                            <p className="text-slate-500 mb-4">No hay rutas para mostrar</p>
                            {canEdit() && (
                                <Link to="/layout">
                                    <Button variant="outline" data-testid="empty-upload-btn">
                                        <Upload className="h-4 w-4 mr-2" />
                                        ¿Cargar un layout?
                                    </Button>
                                </Link>
                            )}
                        </div>
                    ) : (
                        <RoutesTable journeys={journeys} />
                    )}
                </CardContent>
                {/* Pagination Controls */}
                {pagination.total_pages > 0 && (
                    <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200" data-testid="pagination-controls">
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                            <span>Filas:</span>
                            <Select value={String(pageSize)} onValueChange={(val) => { setPageSize(Number(val)); setCurrentPage(1); }}>
                                <SelectTrigger className="w-[70px] h-8" data-testid="page-size-selector">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="25">25</SelectItem>
                                    <SelectItem value="50">50</SelectItem>
                                    <SelectItem value="75">75</SelectItem>
                                    <SelectItem value="100">100</SelectItem>
                                </SelectContent>
                            </Select>
                            <span className="text-slate-400 ml-2" data-testid="pagination-info">
                                Página {pagination.page} de {pagination.total_pages} ({pagination.total_count} rutas)
                            </span>
                        </div>
                        <div className="flex items-center gap-1">
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 px-2"
                                disabled={currentPage <= 1}
                                onClick={() => setCurrentPage(1)}
                                data-testid="pagination-first"
                            >
                                {'<<'}
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 px-3"
                                disabled={currentPage <= 1}
                                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                data-testid="pagination-prev"
                            >
                                Anterior
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 px-3"
                                disabled={currentPage >= pagination.total_pages}
                                onClick={() => setCurrentPage(p => Math.min(pagination.total_pages, p + 1))}
                                data-testid="pagination-next"
                            >
                                Siguiente
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 px-2"
                                disabled={currentPage >= pagination.total_pages}
                                onClick={() => setCurrentPage(pagination.total_pages)}
                                data-testid="pagination-last"
                            >
                                {'>>'}
                            </Button>
                        </div>
                    </div>
                )}
            </Card>

            {/* Bottom section: Metrics + Provider Comparison */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Daily Metrics */}
                <Card>
                    <CardHeader>
                        <CardTitle className="font-heading text-lg flex items-center gap-2">
                            <TrendingUp className="w-5 h-5" />
                            Métricas del día
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-sm">
                                <span className="text-sm text-slate-600">Tasa de entrega promedio</span>
                                <span className="font-mono font-semibold text-lg">
                                    {stats?.delivery_rate || 0}%
                                </span>
                            </div>
                            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-sm">
                                <span className="text-sm text-slate-600">Km totales recorridos</span>
                                <span className="font-mono font-semibold text-lg">
                                    {(stats?.total_km || 0).toLocaleString()} km
                                </span>
                            </div>
                            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-sm">
                                <span className="text-sm text-slate-600">Total rutas</span>
                                <span className="font-mono font-semibold text-lg">
                                    {stats?.total_journeys || 0}
                                </span>
                            </div>
                        </div>

                        {/* Incidents Breakdown */}
                        {Object.keys(incidentsBreakdown).length > 0 && (
                            <div className="mt-6">
                                <h4 className="text-sm font-medium text-slate-700 mb-3">
                                    Incidencias por tipo
                                </h4>
                                <div className="space-y-2">
                                    {Object.entries(incidentsBreakdown).map(([type, count]) => (
                                        <div 
                                            key={type} 
                                            className="flex items-center justify-between text-sm"
                                        >
                                            <span className="text-slate-600 truncate pr-2">{type}</span>
                                            <span className="font-mono bg-slate-100 px-2 py-0.5 rounded">
                                                {count}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Provider Comparison */}
                <Card>
                    <CardHeader>
                        <CardTitle className="font-heading text-lg flex items-center gap-2">
                            <Truck className="w-5 h-5" />
                            Comparativo de proveedores
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {providerComparison.length === 0 ? (
                            <p className="text-center text-slate-500 py-8">
                                No hay datos de proveedores para el período seleccionado
                            </p>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="data-table w-full text-sm">
                                    <thead>
                                        <tr>
                                            <th>Proveedor</th>
                                            <th className="text-center">Rutas</th>
                                            <th className="text-center">Entrega %</th>
                                            <th className="text-center">Incidencias</th>
                                            <th className="text-right">Km</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {providerComparison.map((provider) => (
                                            <tr key={provider.provider_id}>
                                                <td className="font-medium">{provider.provider_name}</td>
                                                <td className="text-center font-mono">
                                                    {provider.journeys_count}
                                                </td>
                                                <td className="text-center">
                                                    <span className={`font-mono ${
                                                        provider.avg_delivery_rate >= 70 
                                                            ? 'text-emerald-600' 
                                                            : provider.avg_delivery_rate >= 40 
                                                                ? 'text-amber-600' 
                                                                : 'text-red-600'
                                                    }`}>
                                                        {provider.avg_delivery_rate}%
                                                    </span>
                                                </td>
                                                <td className="text-center font-mono">
                                                    {provider.total_incidents}
                                                </td>
                                                <td className="text-right font-mono">
                                                    {provider.total_km.toLocaleString()}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
};

export default Dashboard;
