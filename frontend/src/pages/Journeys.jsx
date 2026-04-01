import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getJourneys, getClients, getProviders } from '../lib/api';
import { 
    formatDate, 
    getStatusColor, 
    getStatusLabel,
    getProgressColor,
    calculateDeliveryRate 
} from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Progress } from '../components/ui/progress';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
    Truck, 
    Calendar as CalendarIcon,
    Eye,
    Upload,
    AlertTriangle,
    Filter,
    X
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

const Journeys = () => {
    const { canEdit } = useAuth();
    const [journeys, setJourneys] = useState([]);
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [loading, setLoading] = useState(true);

    // Filters
    const [dateFrom, setDateFrom] = useState(null);
    const [dateTo, setDateTo] = useState(null);
    const [selectedClient, setSelectedClient] = useState('all');
    const [selectedProvider, setSelectedProvider] = useState('all');
    const [selectedStatus, setSelectedStatus] = useState('all');
    const [showFilters, setShowFilters] = useState(false);

    const fetchData = useCallback(async () => {
        try {
            const params = {};
            if (dateFrom) params.date_from = format(dateFrom, 'yyyy-MM-dd');
            if (dateTo) params.date_to = format(dateTo, 'yyyy-MM-dd');
            if (selectedClient !== 'all') params.client_id = selectedClient;
            if (selectedProvider !== 'all') params.provider_id = selectedProvider;
            if (selectedStatus !== 'all') params.status = selectedStatus;

            const results = await Promise.allSettled([
                getJourneys(params),
                getClients(),
                getProviders(),
            ]);

            const [journeysRes, clientsRes, providersRes] = results;

            if (journeysRes.status === 'fulfilled') {
                setJourneys(journeysRes.value.data?.data || journeysRes.value.data || []);
            }
            if (clientsRes.status === 'fulfilled') setClients(clientsRes.value.data);
            if (providersRes.status === 'fulfilled') setProviders(providersRes.value.data);

            const failed = results.filter(r => r.status === 'rejected');
            if (failed.length === results.length) {
                toast.error('Error al cargar rutas');
            } else if (failed.length > 0) {
                console.warn('Partial fetch failures:', failed.map(f => f.reason?.message));
            }
        } catch (error) {
            console.error('Error fetching journeys:', error);
            toast.error('Error al cargar rutas');
        } finally {
            setLoading(false);
        }
    }, [dateFrom, dateTo, selectedClient, selectedProvider, selectedStatus]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const clearFilters = () => {
        setDateFrom(null);
        setDateTo(null);
        setSelectedClient('all');
        setSelectedProvider('all');
        setSelectedStatus('all');
    };

    const hasActiveFilters = dateFrom || dateTo || selectedClient !== 'all' || selectedProvider !== 'all' || selectedStatus !== 'all';

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                        Rutas
                    </h1>
                    <p className="text-slate-500 text-sm">
                        Gestiona todas las rutas de entrega
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <Button
                        variant="outline"
                        onClick={() => setShowFilters(!showFilters)}
                        data-testid="toggle-filters-btn"
                    >
                        <Filter className="w-4 h-4 mr-2" />
                        Filtros
                        {hasActiveFilters && (
                            <span className="ml-2 w-2 h-2 bg-blue-500 rounded-full" />
                        )}
                    </Button>
                    {canEdit() && (
                        <Link to="/layout">
                            <Button data-testid="new-layout-btn">
                                <Upload className="w-4 h-4 mr-2" />
                                Cargar layout
                            </Button>
                        </Link>
                    )}
                </div>
            </div>

            {/* Filters */}
            {showFilters && (
                <Card className="animate-fade-in">
                    <CardContent className="p-4">
                        <div className="flex flex-wrap items-center gap-4">
                            {/* Date Range */}
                            <div className="flex items-center gap-2">
                                <Popover>
                                    <PopoverTrigger asChild>
                                        <Button 
                                            variant="outline" 
                                            className="justify-start text-left font-normal"
                                            data-testid="journeys-date-from"
                                        >
                                            <CalendarIcon className="mr-2 h-4 w-4" />
                                            {dateFrom ? format(dateFrom, 'dd MMM', { locale: es }) : 'Desde'}
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-auto p-0" align="start">
                                        <Calendar
                                            mode="single"
                                            selected={dateFrom}
                                            onSelect={setDateFrom}
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
                                            data-testid="journeys-date-to"
                                        >
                                            <CalendarIcon className="mr-2 h-4 w-4" />
                                            {dateTo ? format(dateTo, 'dd MMM', { locale: es }) : 'Hasta'}
                                        </Button>
                                    </PopoverTrigger>
                                    <PopoverContent className="w-auto p-0" align="start">
                                        <Calendar
                                            mode="single"
                                            selected={dateTo}
                                            onSelect={setDateTo}
                                            initialFocus
                                        />
                                    </PopoverContent>
                                </Popover>
                            </div>

                            <Select value={selectedClient} onValueChange={setSelectedClient}>
                                <SelectTrigger className="w-[180px]" data-testid="journeys-client-filter">
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

                            <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                                <SelectTrigger className="w-[180px]" data-testid="journeys-provider-filter">
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

                            <Select value={selectedStatus} onValueChange={setSelectedStatus}>
                                <SelectTrigger className="w-[160px]" data-testid="journeys-status-filter">
                                    <SelectValue placeholder="Estado" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todos</SelectItem>
                                    <SelectItem value="scheduled">Programada</SelectItem>
                                    <SelectItem value="in_progress">En progreso</SelectItem>
                                    <SelectItem value="closed">Cerrada</SelectItem>
                                </SelectContent>
                            </Select>

                            {hasActiveFilters && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={clearFilters}
                                    data-testid="clear-filters-btn"
                                >
                                    <X className="w-4 h-4 mr-1" />
                                    Limpiar
                                </Button>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Journey List */}
            <Card>
                <CardContent className="p-0">
                    {loading ? (
                        <div className="p-8 space-y-4">
                            {[1, 2, 3].map((i) => (
                                <div key={`skel-${i}`} className="h-16 bg-slate-100 animate-pulse rounded" />
                            ))}
                        </div>
                    ) : journeys.length === 0 ? (
                        <div className="text-center py-16">
                            <Truck className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                            <h3 className="text-lg font-medium text-slate-700 mb-2">
                                No hay rutas
                            </h3>
                            <p className="text-slate-500 mb-6 max-w-md mx-auto">
                                {hasActiveFilters 
                                    ? 'No se encontraron rutas con los filtros seleccionados'
                                    : 'Comienza cargando un layout para crear tu primera ruta'}
                            </p>
                            {canEdit() && !hasActiveFilters && (
                                <Link to="/layout">
                                    <Button data-testid="empty-state-upload-btn">
                                        <Upload className="w-4 h-4 mr-2" />
                                        Cargar layout
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
                                        <th>Tipo</th>
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
                                            <tr key={journey.id} data-testid={`journey-item-${journey.id}`}>
                                                <td className="font-mono text-sm">
                                                    {formatDate(journey.date)}
                                                </td>
                                                <td>{journey.client_name}</td>
                                                <td>{journey.provider_name}</td>
                                                <td>
                                                    {journey.route_type === 'Foránea' ? (
                                                        <span className="px-1.5 py-0.5 text-xs font-medium bg-violet-100 text-violet-700 rounded">
                                                            Foránea{journey.city ? ` — ${journey.city}` : ''}
                                                        </span>
                                                    ) : (
                                                        <span className="px-1.5 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded">
                                                            CDMX
                                                        </span>
                                                    )}
                                                </td>
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
                                                            data-testid={`view-detail-${journey.id}`}
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
        </div>
    );
};

export default Journeys;
