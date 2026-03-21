import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
    uploadHistoryOrders,
    uploadRouteSummary,
    createJourneysFromCosmo,
    getClients, 
    getProviders,
    getMessengerMappings,
    getUploadHistory
} from '../lib/api';
import { formatDate } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
    Upload, 
    FileSpreadsheet, 
    Calendar as CalendarIcon,
    AlertCircle,
    CheckCircle2,
    X,
    Loader2,
    Package,
    History,
    Truck,
    Users,
    ChevronRight,
    Link as LinkIcon,
    ExternalLink
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '../components/ui/alert-dialog';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '../components/ui/table';

const Layout = () => {
    const navigate = useNavigate();
    const { canEdit } = useAuth();
    const historyFileRef = useRef(null);
    const routeFileRef = useRef(null);

    // State
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [messengerMappings, setMessengerMappings] = useState({});
    const [uploadHistory, setUploadHistory] = useState([]);
    const [loading, setLoading] = useState(true);

    // Step tracking
    const [currentStep, setCurrentStep] = useState(1);

    // Step 1: History Orders
    const [historyFile, setHistoryFile] = useState(null);
    const [historyData, setHistoryData] = useState(null);
    const [historyUploading, setHistoryUploading] = useState(false);
    const [historyError, setHistoryError] = useState(null);

    // Step 2: Route Summary
    const [routeFile, setRouteFile] = useState(null);
    const [routeData, setRouteData] = useState(null);
    const [routeUploading, setRouteUploading] = useState(false);
    const [routeError, setRouteError] = useState(null);

    // Step 3: Configuration
    const [selectedDate, setSelectedDate] = useState(new Date());
    const [selectedClient, setSelectedClient] = useState('');
    const [driverProviderMap, setDriverProviderMap] = useState({});

    // Creation
    const [creating, setCreating] = useState(false);
    const [showConfirmDialog, setShowConfirmDialog] = useState(false);
    const [creationResult, setCreationResult] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [clientsRes, providersRes, mappingsRes, historyRes] = await Promise.all([
                    getClients(),
                    getProviders(),
                    getMessengerMappings(),
                    getUploadHistory(),
                ]);
                setClients(clientsRes.data);
                setProviders(providersRes.data);
                // Convert mappings array to object
                const mappingsObj = {};
                mappingsRes.data.forEach(m => {
                    mappingsObj[m.messenger_name] = m.provider_id;
                });
                setMessengerMappings(mappingsObj);
                setUploadHistory(historyRes.data);
            } catch (error) {
                toast.error('Error al cargar datos');
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    // Initialize driver-provider mappings when route data changes
    useEffect(() => {
        if (routeData?.drivers) {
            const newMap = {};
            routeData.drivers.forEach(driver => {
                // Use existing mapping if available
                newMap[driver] = messengerMappings[driver] || '';
            });
            setDriverProviderMap(newMap);
        }
    }, [routeData, messengerMappings]);

    // Step 1: Upload History Orders
    const handleHistoryFileSelect = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const validTypes = ['.csv', '.xlsx'];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        
        if (!validTypes.includes(ext)) {
            setHistoryError('Solo se permiten archivos CSV o XLSX');
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            setHistoryError('El archivo excede 10MB');
            return;
        }

        setHistoryFile(file);
        setHistoryError(null);
        setHistoryUploading(true);

        try {
            const res = await uploadHistoryOrders(file);
            setHistoryData(res.data);
            toast.success(`${res.data.total_orders} órdenes encontradas en ${res.data.total_routes} rutas`);
            setCurrentStep(2);
        } catch (error) {
            setHistoryError(error.response?.data?.detail || 'Error al procesar archivo');
            setHistoryFile(null);
        } finally {
            setHistoryUploading(false);
        }
    };

    // Step 2: Upload Route Summary
    const handleRouteFileSelect = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const validTypes = ['.csv', '.xlsx'];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        
        if (!validTypes.includes(ext)) {
            setRouteError('Solo se permiten archivos CSV o XLSX');
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            setRouteError('El archivo excede 10MB');
            return;
        }

        setRouteFile(file);
        setRouteError(null);
        setRouteUploading(true);

        try {
            const res = await uploadRouteSummary(file);
            setRouteData(res.data);
            toast.success(`${res.data.total_routes} rutas encontradas con ${res.data.drivers.length} mensajeros`);
            setCurrentStep(3);
        } catch (error) {
            setRouteError(error.response?.data?.detail || 'Error al procesar archivo');
            setRouteFile(null);
        } finally {
            setRouteUploading(false);
        }
    };

    // Update driver-provider mapping
    const handleDriverProviderChange = (driver, providerId) => {
        setDriverProviderMap(prev => ({
            ...prev,
            [driver]: providerId
        }));
    };

    // Check if all drivers have providers assigned
    const allDriversAssigned = () => {
        if (!routeData?.drivers) return false;
        return routeData.drivers.every(driver => driverProviderMap[driver]);
    };

    // Create journeys
    const handleCreateJourneys = async () => {
        setShowConfirmDialog(false);
        setCreating(true);

        try {
            // Build messenger-provider mappings
            const mappings = Object.entries(driverProviderMap).map(([messenger_name, provider_id]) => ({
                messenger_name,
                provider_id
            }));

            // Build history orders from the parsed data
            const allOrders = [];
            if (historyData?.routes) {
                historyData.routes.forEach(route => {
                    route.orders.forEach(order => {
                        allOrders.push({
                            ...order,
                            route_id: route.route_id,
                            order_id: route.route_id
                        });
                    });
                });
            }

            const payload = {
                date: format(selectedDate, 'yyyy-MM-dd'),
                client_id: selectedClient,
                history_orders: allOrders,
                route_summary: routeData?.routes || [],
                messenger_provider_mappings: mappings
            };

            const res = await createJourneysFromCosmo(payload);
            setCreationResult(res.data);
            toast.success(res.data.message);

            if (res.data.created_journeys?.length > 0) {
                // Navigate to journeys list after 2 seconds
                setTimeout(() => {
                    navigate('/journeys');
                }, 2000);
            }
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al crear rutas');
        } finally {
            setCreating(false);
        }
    };

    // Clear all and restart
    const handleClearAll = () => {
        setCurrentStep(1);
        setHistoryFile(null);
        setHistoryData(null);
        setHistoryError(null);
        setRouteFile(null);
        setRouteData(null);
        setRouteError(null);
        setDriverProviderMap({});
        setCreationResult(null);
        if (historyFileRef.current) historyFileRef.current.value = '';
        if (routeFileRef.current) routeFileRef.current.value = '';
    };

    if (!canEdit()) {
        return (
            <div className="text-center py-16">
                <AlertCircle className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-700 mb-2">
                    Acceso restringido
                </h3>
                <p className="text-slate-500">
                    No tienes permisos para cargar layouts
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                        Cargar Datos de Cosmo
                    </h1>
                    <p className="text-slate-500 text-sm">
                        Importa archivos history-orders y route-summary desde Cosmo
                    </p>
                </div>
                {(historyFile || routeFile) && (
                    <Button variant="outline" onClick={handleClearAll} data-testid="clear-all-btn">
                        <X className="w-4 h-4 mr-2" />
                        Limpiar todo
                    </Button>
                )}
            </div>

            {/* Steps indicator */}
            <div className="flex items-center gap-4 p-4 bg-white border border-slate-200 rounded-sm">
                <div className={`flex items-center gap-2 ${currentStep >= 1 ? 'text-slate-900' : 'text-slate-400'}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        currentStep > 1 ? 'bg-emerald-100 text-emerald-700' : 
                        currentStep === 1 ? 'bg-slate-900 text-white' : 'bg-slate-200'
                    }`}>
                        {currentStep > 1 ? <CheckCircle2 className="w-5 h-5" /> : '1'}
                    </div>
                    <span className="font-medium">History Orders</span>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300" />
                <div className={`flex items-center gap-2 ${currentStep >= 2 ? 'text-slate-900' : 'text-slate-400'}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        currentStep > 2 ? 'bg-emerald-100 text-emerald-700' : 
                        currentStep === 2 ? 'bg-slate-900 text-white' : 'bg-slate-200'
                    }`}>
                        {currentStep > 2 ? <CheckCircle2 className="w-5 h-5" /> : '2'}
                    </div>
                    <span className="font-medium">Route Summary</span>
                </div>
                <ChevronRight className="w-5 h-5 text-slate-300" />
                <div className={`flex items-center gap-2 ${currentStep >= 3 ? 'text-slate-900' : 'text-slate-400'}`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        currentStep === 3 ? 'bg-slate-900 text-white' : 'bg-slate-200'
                    }`}>
                        3
                    </div>
                    <span className="font-medium">Configurar y Crear</span>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main upload area */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Step 1: History Orders */}
                    <Card className={currentStep === 1 ? 'ring-2 ring-slate-900' : ''}>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <FileSpreadsheet className="w-5 h-5" />
                                Paso 1: Archivo History Orders
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {!historyFile ? (
                                <div
                                    className="drop-zone cursor-pointer"
                                    onClick={() => historyFileRef.current?.click()}
                                    data-testid="history-file-zone"
                                >
                                    <input
                                        ref={historyFileRef}
                                        type="file"
                                        accept=".csv,.xlsx"
                                        onChange={handleHistoryFileSelect}
                                        className="hidden"
                                        data-testid="history-file-input"
                                    />
                                    <Upload className="w-10 h-10 text-slate-400 mx-auto mb-3" />
                                    <p className="text-slate-700 font-medium">
                                        Selecciona archivo history-orders
                                    </p>
                                    <p className="text-slate-500 text-sm mt-1">
                                        Formato: history-orders-aaaa-mm-dd-aaaa-mm-dd.csv
                                    </p>
                                    <p className="text-slate-400 text-xs mt-2">
                                        CSV o XLSX • Máximo 10MB
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-sm">
                                        <div className="flex items-center gap-3">
                                            <FileSpreadsheet className="w-8 h-8 text-emerald-600" />
                                            <div>
                                                <p className="font-medium text-slate-900">{historyFile.name}</p>
                                                <p className="text-sm text-slate-500">
                                                    {(historyFile.size / 1024).toFixed(1)} KB
                                                </p>
                                            </div>
                                        </div>
                                        {historyUploading ? (
                                            <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                                        ) : (
                                            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                                        )}
                                    </div>

                                    {historyData && (
                                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-sm">
                                            <div className="flex items-center gap-2 text-emerald-700 mb-2">
                                                <Package className="w-5 h-5" />
                                                <span className="font-medium">
                                                    {historyData.total_orders} órdenes en {historyData.total_routes} rutas
                                                </span>
                                            </div>
                                            <p className="text-sm text-emerald-600">
                                                Columnas detectadas: order_reference_id, tracking_url, order_status
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}

                            {historyError && (
                                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-sm flex items-center gap-2 text-red-700">
                                    <AlertCircle className="w-5 h-5" />
                                    <span>{historyError}</span>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Step 2: Route Summary */}
                    <Card className={currentStep === 2 ? 'ring-2 ring-slate-900' : ''}>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <Truck className="w-5 h-5" />
                                Paso 2: Archivo Route Summary
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {currentStep < 2 ? (
                                <div className="text-center py-8 text-slate-400">
                                    <Truck className="w-10 h-10 mx-auto mb-2 opacity-50" />
                                    <p>Primero carga el archivo history-orders</p>
                                </div>
                            ) : !routeFile ? (
                                <div
                                    className="drop-zone cursor-pointer"
                                    onClick={() => routeFileRef.current?.click()}
                                    data-testid="route-file-zone"
                                >
                                    <input
                                        ref={routeFileRef}
                                        type="file"
                                        accept=".csv,.xlsx"
                                        onChange={handleRouteFileSelect}
                                        className="hidden"
                                        data-testid="route-file-input"
                                    />
                                    <Upload className="w-10 h-10 text-slate-400 mx-auto mb-3" />
                                    <p className="text-slate-700 font-medium">
                                        Selecciona archivo route-summary
                                    </p>
                                    <p className="text-slate-500 text-sm mt-1">
                                        Formato: route-summary-aaaa-mm-dd-aaaa-mm-dd.xlsx
                                    </p>
                                    <p className="text-slate-400 text-xs mt-2">
                                        CSV o XLSX • Máximo 10MB
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-sm">
                                        <div className="flex items-center gap-3">
                                            <FileSpreadsheet className="w-8 h-8 text-emerald-600" />
                                            <div>
                                                <p className="font-medium text-slate-900">{routeFile.name}</p>
                                                <p className="text-sm text-slate-500">
                                                    {(routeFile.size / 1024).toFixed(1)} KB
                                                </p>
                                            </div>
                                        </div>
                                        {routeUploading ? (
                                            <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                                        ) : (
                                            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                                        )}
                                    </div>

                                    {routeData && (
                                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-sm">
                                            <div className="flex items-center gap-2 text-emerald-700 mb-2">
                                                <Users className="w-5 h-5" />
                                                <span className="font-medium">
                                                    {routeData.total_routes} rutas con {routeData.drivers.length} mensajeros
                                                </span>
                                            </div>
                                            <p className="text-sm text-emerald-600">
                                                Columnas detectadas: Order ID, Driver, Team, Total Stops
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}

                            {routeError && (
                                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-sm flex items-center gap-2 text-red-700">
                                    <AlertCircle className="w-5 h-5" />
                                    <span>{routeError}</span>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Step 3: Configuration */}
                    {currentStep >= 3 && (
                        <Card className="ring-2 ring-slate-900">
                            <CardHeader>
                                <CardTitle className="font-heading text-lg flex items-center gap-2">
                                    <LinkIcon className="w-5 h-5" />
                                    Paso 3: Configuración y Asignación de Proveedores
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                {/* Date and Client */}
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Fecha de las rutas</Label>
                                        <Popover>
                                            <PopoverTrigger asChild>
                                                <Button 
                                                    variant="outline" 
                                                    className="w-full justify-start text-left font-normal"
                                                    data-testid="journey-date-picker"
                                                >
                                                    <CalendarIcon className="mr-2 h-4 w-4" />
                                                    {format(selectedDate, 'dd MMM yyyy', { locale: es })}
                                                </Button>
                                            </PopoverTrigger>
                                            <PopoverContent className="w-auto p-0" align="start">
                                                <Calendar
                                                    mode="single"
                                                    selected={selectedDate}
                                                    onSelect={(date) => date && setSelectedDate(date)}
                                                    initialFocus
                                                />
                                            </PopoverContent>
                                        </Popover>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Cliente</Label>
                                        <Select value={selectedClient} onValueChange={setSelectedClient}>
                                            <SelectTrigger data-testid="select-client">
                                                <SelectValue placeholder="Seleccionar cliente" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {clients.map((client) => (
                                                    <SelectItem key={client.id} value={client.id}>
                                                        {client.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                {/* Driver-Provider Mapping */}
                                <div className="border border-slate-200 rounded-sm">
                                    <div className="p-3 bg-slate-50 border-b border-slate-200">
                                        <p className="font-medium text-slate-900">Asignar Proveedor a cada Mensajero</p>
                                        <p className="text-sm text-slate-500">
                                            Los mensajeros detectados necesitan un proveedor asignado
                                        </p>
                                    </div>
                                    <div className="max-h-80 overflow-y-auto">
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead>Mensajero (Driver)</TableHead>
                                                    <TableHead>Proveedor Asignado</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {routeData?.drivers.map((driver) => (
                                                    <TableRow key={driver}>
                                                        <TableCell className="font-medium">{driver}</TableCell>
                                                        <TableCell>
                                                            <Select
                                                                value={driverProviderMap[driver] || ''}
                                                                onValueChange={(v) => handleDriverProviderChange(driver, v)}
                                                            >
                                                                <SelectTrigger 
                                                                    className={`w-full ${!driverProviderMap[driver] ? 'border-amber-400' : ''}`}
                                                                    data-testid={`provider-select-${driver}`}
                                                                >
                                                                    <SelectValue placeholder="Sin asignar" />
                                                                </SelectTrigger>
                                                                <SelectContent>
                                                                    {providers.map((provider) => (
                                                                        <SelectItem key={provider.id} value={provider.id}>
                                                                            {provider.name}
                                                                        </SelectItem>
                                                                    ))}
                                                                </SelectContent>
                                                            </Select>
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    </div>
                                </div>

                                {/* Warning if not all drivers assigned */}
                                {!allDriversAssigned() && (
                                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-sm flex items-center gap-2 text-amber-700">
                                        <AlertCircle className="w-5 h-5" />
                                        <span>Asigna un proveedor a todos los mensajeros para continuar</span>
                                    </div>
                                )}

                                {/* Create button */}
                                <div className="flex justify-end">
                                    <Button
                                        onClick={() => setShowConfirmDialog(true)}
                                        disabled={!selectedClient || !allDriversAssigned() || creating}
                                        data-testid="create-journeys-btn"
                                    >
                                        {creating ? (
                                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        ) : (
                                            <Package className="w-4 h-4 mr-2" />
                                        )}
                                        Crear Rutas
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Creation Result */}
                    {creationResult && (
                        <Card className="border-emerald-200 bg-emerald-50">
                            <CardHeader>
                                <CardTitle className="font-heading text-lg flex items-center gap-2 text-emerald-700">
                                    <CheckCircle2 className="w-5 h-5" />
                                    {creationResult.message}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {creationResult.created_journeys?.length > 0 && (
                                    <div>
                                        <p className="text-sm font-medium text-emerald-800 mb-2">Rutas creadas:</p>
                                        <ul className="space-y-1 text-sm text-emerald-700">
                                            {creationResult.created_journeys.map((j, idx) => (
                                                <li key={idx}>
                                                    • {j.driver} - {j.packages} paquetes (Ruta: {j.route_id})
                                                    {j.duplicates_skipped > 0 && (
                                                        <span className="text-amber-600 ml-2">
                                                            ({j.duplicates_skipped} duplicados omitidos)
                                                        </span>
                                                    )}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {creationResult.skipped_duplicates?.length > 0 && (
                                    <div>
                                        <p className="text-sm font-medium text-amber-700 mb-2">Rutas duplicadas omitidas:</p>
                                        <ul className="space-y-1 text-sm text-amber-600">
                                            {creationResult.skipped_duplicates.map((id, idx) => (
                                                <li key={idx}>• {id}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {creationResult.errors?.length > 0 && (
                                    <div>
                                        <p className="text-sm font-medium text-red-700 mb-2">Errores:</p>
                                        <ul className="space-y-1 text-sm text-red-600">
                                            {creationResult.errors.map((err, idx) => (
                                                <li key={idx}>• {err}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}
                </div>

                {/* Sidebar: Upload history & Preview */}
                <div className="space-y-6">
                    {/* Routes Preview */}
                    {historyData?.routes?.length > 0 && (
                        <Card>
                            <CardHeader>
                                <CardTitle className="font-heading text-lg flex items-center gap-2">
                                    <Truck className="w-5 h-5" />
                                    Rutas Detectadas
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-0">
                                <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
                                    {historyData.routes.slice(0, 10).map((route) => (
                                        <div key={route.route_id} className="p-3 hover:bg-slate-50">
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="font-mono text-sm font-medium">{route.route_id}</span>
                                                <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">
                                                    {route.orders.length} órdenes
                                                </span>
                                            </div>
                                            {route.driver_name && (
                                                <p className="text-xs text-slate-500">{route.driver_name}</p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Upload History */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <History className="w-5 h-5" />
                                Historial de Cargas
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="p-4 flex justify-center">
                                    <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                                </div>
                            ) : uploadHistory.length === 0 ? (
                                <div className="text-center py-8 text-slate-500">
                                    <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                    <p className="text-sm">Sin cargas recientes</p>
                                </div>
                            ) : (
                                <div className="divide-y divide-slate-100">
                                    {uploadHistory.slice(0, 8).map((entry) => (
                                        <div key={entry.id} className="p-3 hover:bg-slate-50">
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="font-mono text-sm">
                                                    {formatDate(entry.date)}
                                                </span>
                                                <span className="text-xs text-slate-500">
                                                    {entry.package_count} paquetes
                                                </span>
                                            </div>
                                            <p className="text-sm text-slate-600">{entry.provider_name}</p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>

            {/* Confirm Dialog */}
            <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="font-heading">
                            Confirmar creación de rutas
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Se crearán rutas con los siguientes datos:
                            <ul className="mt-3 space-y-1 text-slate-700">
                                <li>• Fecha: <strong>{format(selectedDate, 'dd/MM/yyyy')}</strong></li>
                                <li>• Cliente: <strong>{clients.find(c => c.id === selectedClient)?.name}</strong></li>
                                <li>• Rutas: <strong>{routeData?.total_routes}</strong></li>
                                <li>• Mensajeros: <strong>{routeData?.drivers.length}</strong></li>
                                <li>• Órdenes totales: <strong>{historyData?.total_orders}</strong></li>
                            </ul>
                            <p className="mt-3 text-sm text-amber-600">
                                Se omitirán automáticamente órdenes y rutas duplicadas.
                            </p>
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction 
                            onClick={handleCreateJourneys}
                            disabled={creating}
                            data-testid="confirm-create-btn"
                        >
                            {creating ? (
                                <>
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    Creando...
                                </>
                            ) : (
                                'Crear rutas'
                            )}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
};

export default Layout;
