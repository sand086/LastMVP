import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
    getDashboardStats, 
    getJourneys, 
    getIncidentsBreakdown,
    getProviderComparison,
    exportJourneys,
    getClients,
    getProviders
} from '../lib/api';
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
    TrendingUp
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

const Dashboard = () => {
    const { canEdit } = useAuth();
    const [stats, setStats] = useState(null);
    const [journeys, setJourneys] = useState([]);
    const [incidentsBreakdown, setIncidentsBreakdown] = useState({});
    const [providerComparison, setProviderComparison] = useState([]);
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);

    // Filters
    const [dateFrom, setDateFrom] = useState(new Date());
    const [dateTo, setDateTo] = useState(new Date());
    const [selectedClient, setSelectedClient] = useState('all');
    const [selectedProvider, setSelectedProvider] = useState('all');
    const [selectedStatus, setSelectedStatus] = useState('all');

    const fetchData = useCallback(async () => {
        try {
            const dateFromStr = format(dateFrom, 'yyyy-MM-dd');
            const dateToStr = format(dateTo, 'yyyy-MM-dd');

            const [statsRes, journeysRes, breakdownRes, comparisonRes, clientsRes, providersRes] = await Promise.all([
                getDashboardStats(dateFromStr),
                getJourneys({
                    date_from: dateFromStr,
                    date_to: dateToStr,
                    client_id: selectedClient !== 'all' ? selectedClient : undefined,
                    provider_id: selectedProvider !== 'all' ? selectedProvider : undefined,
                    status: selectedStatus !== 'all' ? selectedStatus : undefined,
                }),
                getIncidentsBreakdown(dateFromStr, dateToStr),
                getProviderComparison(dateFromStr, dateToStr),
                getClients(),
                getProviders(),
            ]);

            setStats(statsRes.data);
            setJourneys(journeysRes.data);
            setIncidentsBreakdown(breakdownRes.data);
            setProviderComparison(comparisonRes.data);
            setClients(clientsRes.data);
            setProviders(providersRes.data);
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
            toast.error('Error al cargar datos');
        } finally {
            setLoading(false);
        }
    }, [dateFrom, dateTo, selectedClient, selectedProvider, selectedStatus]);

    useEffect(() => {
        fetchData();
        
        // Polling every 60 seconds
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, [fetchData]);

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
            
            downloadFile(response.data, `jornadas_${dateFromStr}_${dateToStr}.xlsx`);
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

    return (
        <div className="space-y-6">
            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <KPICard
                    title="Jornadas activas"
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
                    title="Jornadas cerradas"
                    value={stats?.closed_journeys || 0}
                    subValue="completadas hoy"
                    icon={CheckCircle2}
                    color="#2E6096"
                    loading={loading}
                />
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
                        <CardTitle className="font-heading text-lg">Jornadas</CardTitle>
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
                            <p className="text-slate-500 mb-4">No hay jornadas para mostrar</p>
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
                        <div className="overflow-x-auto">
                            <table className="data-table w-full">
                                <thead>
                                    <tr>
                                        <th>Fecha</th>
                                        <th>Cliente</th>
                                        <th>Proveedor</th>
                                        <th>Paquetes</th>
                                        <th>Progreso</th>
                                        <th>Incidencias</th>
                                        <th>Estado</th>
                                        <th>Acciones</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {journeys.map((journey) => {
                                        const deliveryRate = calculateDeliveryRate(
                                            journey.packages_delivered,
                                            journey.packages_total
                                        );
                                        const progressColor = getProgressColor(deliveryRate);
                                        
                                        return (
                                            <tr key={journey.id} data-testid={`journey-row-${journey.id}`}>
                                                <td className="font-mono text-sm">
                                                    {formatDate(journey.date)}
                                                </td>
                                                <td>{journey.client_name}</td>
                                                <td>{journey.provider_name}</td>
                                                <td className="font-mono">
                                                    {journey.packages_delivered}/{journey.packages_total}
                                                </td>
                                                <td className="w-32">
                                                    <div className="flex items-center gap-2">
                                                        <Progress 
                                                            value={deliveryRate} 
                                                            className="h-2 flex-1"
                                                            indicatorClassName={progressColor}
                                                        />
                                                        <span className="text-xs font-mono w-10 text-right">
                                                            {deliveryRate}%
                                                        </span>
                                                    </div>
                                                </td>
                                                <td>
                                                    {journey.open_incidents_count > 0 ? (
                                                        <span className="inline-flex items-center gap-1 text-amber-600">
                                                            <AlertTriangle className="w-4 h-4" />
                                                            {journey.open_incidents_count}
                                                        </span>
                                                    ) : (
                                                        <span className="text-slate-400">0</span>
                                                    )}
                                                </td>
                                                <td>
                                                    <span className={`status-badge ${getStatusColor(journey.status)}`}>
                                                        {getStatusLabel(journey.status)}
                                                    </span>
                                                </td>
                                                <td>
                                                    <Link to={`/journeys/${journey.id}`}>
                                                        <Button 
                                                            variant="ghost" 
                                                            size="sm"
                                                            data-testid={`view-journey-${journey.id}`}
                                                        >
                                                            <Eye className="w-4 h-4 mr-1" />
                                                            Ver detalle
                                                        </Button>
                                                    </Link>
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
                                <span className="text-sm text-slate-600">Total jornadas</span>
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
                                            <th className="text-center">Jornadas</th>
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
