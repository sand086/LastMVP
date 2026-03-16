import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { 
    uploadLayout, 
    downloadTemplate, 
    getClients, 
    getProviders,
    getRetryPackages,
    createJourney,
    createUploadHistory,
    getUploadHistory
} from '../lib/api';
import { formatDate, downloadFile } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Checkbox } from '../components/ui/checkbox';
import { 
    Upload, 
    FileSpreadsheet, 
    Download,
    Calendar as CalendarIcon,
    AlertCircle,
    CheckCircle2,
    X,
    Loader2,
    Package,
    RefreshCw,
    History,
    Eye
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '../components/ui/dialog';
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

const Layout = () => {
    const navigate = useNavigate();
    const { canEdit } = useAuth();
    const fileInputRef = useRef(null);

    // State
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [uploadHistory, setUploadHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [creating, setCreating] = useState(false);

    // Upload state
    const [dragOver, setDragOver] = useState(false);
    const [uploadedFile, setUploadedFile] = useState(null);
    const [parsedData, setParsedData] = useState(null);
    const [uploadError, setUploadError] = useState(null);

    // Form state
    const [selectedDate, setSelectedDate] = useState(new Date());
    const [selectedClient, setSelectedClient] = useState('');
    const [selectedProvider, setSelectedProvider] = useState('');

    // Retry packages
    const [retryPackages, setRetryPackages] = useState([]);
    const [selectedRetryPackages, setSelectedRetryPackages] = useState([]);
    const [showRetryDialog, setShowRetryDialog] = useState(false);
    const [showConfirmDialog, setShowConfirmDialog] = useState(false);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [clientsRes, providersRes, historyRes] = await Promise.all([
                    getClients(),
                    getProviders(),
                    getUploadHistory(),
                ]);
                setClients(clientsRes.data);
                setProviders(providersRes.data);
                setUploadHistory(historyRes.data);
            } catch (error) {
                toast.error('Error al cargar datos');
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    // Fetch retry packages when provider changes
    useEffect(() => {
        const fetchRetryPackages = async () => {
            if (selectedProvider) {
                try {
                    const res = await getRetryPackages(selectedProvider);
                    setRetryPackages(res.data);
                } catch (error) {
                    console.error('Error fetching retry packages:', error);
                }
            } else {
                setRetryPackages([]);
            }
        };
        fetchRetryPackages();
    }, [selectedProvider]);

    const handleDragOver = (e) => {
        e.preventDefault();
        setDragOver(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setDragOver(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    };

    const handleFileInput = (e) => {
        const file = e.target.files?.[0];
        if (file) handleFileSelect(file);
    };

    const handleFileSelect = async (file) => {
        // Validate file type
        const validTypes = ['.csv', '.xlsx'];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        
        if (!validTypes.includes(ext)) {
            setUploadError('Solo se permiten archivos CSV o XLSX');
            return;
        }

        // Validate file size (5MB)
        if (file.size > 5 * 1024 * 1024) {
            setUploadError('El archivo excede 5MB');
            return;
        }

        setUploadedFile(file);
        setUploadError(null);
        setUploading(true);

        try {
            const res = await uploadLayout(file);
            setParsedData(res.data);
            toast.success(`${res.data.total_rows} paquetes encontrados`);
        } catch (error) {
            setUploadError(error.response?.data?.detail || 'Error al procesar archivo');
            setUploadedFile(null);
        } finally {
            setUploading(false);
        }
    };

    const handleDownloadTemplate = async () => {
        try {
            const res = await downloadTemplate();
            downloadFile(res.data, 'plantilla_layout.csv');
            toast.success('Plantilla descargada');
        } catch (error) {
            toast.error('Error al descargar plantilla');
        }
    };

    const handleClearFile = () => {
        setUploadedFile(null);
        setParsedData(null);
        setUploadError(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const handleProceed = () => {
        if (!selectedClient || !selectedProvider) {
            toast.error('Selecciona cliente y proveedor');
            return;
        }

        if (retryPackages.length > 0) {
            setSelectedRetryPackages(retryPackages.map(p => p.id));
            setShowRetryDialog(true);
        } else {
            setShowConfirmDialog(true);
        }
    };

    const handleConfirmRetry = () => {
        setShowRetryDialog(false);
        setShowConfirmDialog(true);
    };

    const handleCreateJourney = async () => {
        setShowConfirmDialog(false);
        setCreating(true);

        try {
            const journeyData = {
                date: format(selectedDate, 'yyyy-MM-dd'),
                client_id: selectedClient,
                provider_id: selectedProvider,
                packages: parsedData.packages,
                retry_packages: selectedRetryPackages,
            };

            const res = await createJourney(journeyData);

            // Create upload history entry
            await createUploadHistory({
                date: format(selectedDate, 'yyyy-MM-dd'),
                client_id: selectedClient,
                provider_id: selectedProvider,
                package_count: parsedData.total_rows + selectedRetryPackages.length,
                journey_id: res.data.id,
                journey_status: 'scheduled',
            });

            toast.success('Jornada creada exitosamente');
            navigate(`/journeys/${res.data.id}`);
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al crear jornada');
        } finally {
            setCreating(false);
        }
    };

    const toggleRetryPackage = (packageId) => {
        setSelectedRetryPackages(prev => 
            prev.includes(packageId)
                ? prev.filter(id => id !== packageId)
                : [...prev, packageId]
        );
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
                        Cargar Layout
                    </h1>
                    <p className="text-slate-500 text-sm">
                        Sube un archivo CSV o XLSX con los paquetes a entregar
                    </p>
                </div>
                <Button
                    variant="outline"
                    onClick={handleDownloadTemplate}
                    data-testid="download-template-btn"
                >
                    <Download className="w-4 h-4 mr-2" />
                    Descargar plantilla
                </Button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main upload area */}
                <div className="lg:col-span-2 space-y-6">
                    {/* File upload zone */}
                    <Card>
                        <CardContent className="p-6">
                            {!uploadedFile ? (
                                <div
                                    className={`drop-zone cursor-pointer ${dragOver ? 'drag-over' : ''}`}
                                    onDragOver={handleDragOver}
                                    onDragLeave={handleDragLeave}
                                    onDrop={handleDrop}
                                    onClick={() => fileInputRef.current?.click()}
                                    data-testid="file-drop-zone"
                                >
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".csv,.xlsx"
                                        onChange={handleFileInput}
                                        className="hidden"
                                        data-testid="file-input"
                                    />
                                    <Upload className="w-12 h-12 text-slate-400 mx-auto mb-4" />
                                    <p className="text-slate-700 font-medium mb-1">
                                        Arrastra tu archivo aquí
                                    </p>
                                    <p className="text-slate-500 text-sm mb-4">
                                        o haz clic para seleccionar
                                    </p>
                                    <p className="text-slate-400 text-xs">
                                        Formatos: CSV, XLSX • Máximo: 5MB
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {/* File info */}
                                    <div className="flex items-center justify-between p-4 bg-slate-50 rounded-sm">
                                        <div className="flex items-center gap-3">
                                            <FileSpreadsheet className="w-10 h-10 text-emerald-600" />
                                            <div>
                                                <p className="font-medium text-slate-900">
                                                    {uploadedFile.name}
                                                </p>
                                                <p className="text-sm text-slate-500">
                                                    {(uploadedFile.size / 1024).toFixed(1)} KB
                                                </p>
                                            </div>
                                        </div>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={handleClearFile}
                                            data-testid="clear-file-btn"
                                        >
                                            <X className="w-4 h-4" />
                                        </Button>
                                    </div>

                                    {uploading && (
                                        <div className="flex items-center justify-center py-8">
                                            <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                                            <span className="ml-3 text-slate-500">Procesando archivo...</span>
                                        </div>
                                    )}

                                    {parsedData && (
                                        <>
                                            <div className="flex items-center gap-2 text-emerald-600">
                                                <CheckCircle2 className="w-5 h-5" />
                                                <span className="font-medium">
                                                    {parsedData.total_rows} paquetes encontrados
                                                </span>
                                            </div>

                                            {/* Preview table */}
                                            <div className="border border-slate-200 rounded-sm overflow-hidden">
                                                <div className="bg-slate-50 px-4 py-2 border-b border-slate-200">
                                                    <p className="text-sm font-medium text-slate-700">
                                                        Vista previa (primeros 10 registros)
                                                    </p>
                                                </div>
                                                <div className="overflow-x-auto max-h-64">
                                                    <table className="data-table w-full text-xs">
                                                        <thead>
                                                            <tr>
                                                                <th>No. Guía</th>
                                                                <th>Destinatario</th>
                                                                <th>Dirección</th>
                                                                <th>Zona</th>
                                                                <th>Ventana</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {parsedData.preview.map((pkg, idx) => (
                                                                <tr key={idx}>
                                                                    <td className="font-mono">{pkg.tracking_number}</td>
                                                                    <td>{pkg.recipient_name}</td>
                                                                    <td className="max-w-xs truncate">{pkg.address}</td>
                                                                    <td>{pkg.zone}</td>
                                                                    <td>{pkg.delivery_window}</td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}

                            {uploadError && (
                                <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-sm flex items-start gap-3">
                                    <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                                    <div>
                                        <p className="font-medium text-red-800">Error al procesar</p>
                                        <p className="text-sm text-red-600">{uploadError}</p>
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Configuration */}
                    {parsedData && (
                        <Card className="animate-fade-in">
                            <CardHeader>
                                <CardTitle className="font-heading text-lg">
                                    Configurar jornada
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div className="space-y-2">
                                        <Label>Fecha de entrega</Label>
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

                                    <div className="space-y-2">
                                        <Label>Proveedor</Label>
                                        <Select value={selectedProvider} onValueChange={setSelectedProvider}>
                                            <SelectTrigger data-testid="select-provider">
                                                <SelectValue placeholder="Seleccionar proveedor" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {providers.map((provider) => (
                                                    <SelectItem key={provider.id} value={provider.id}>
                                                        {provider.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                {/* Retry packages indicator */}
                                {selectedProvider && retryPackages.length > 0 && (
                                    <div className="p-4 bg-amber-50 border border-amber-200 rounded-sm flex items-center gap-3">
                                        <RefreshCw className="w-5 h-5 text-amber-600" />
                                        <div className="flex-1">
                                            <p className="font-medium text-amber-800">
                                                {retryPackages.length} paquetes de reintento
                                            </p>
                                            <p className="text-sm text-amber-600">
                                                Se incluirán automáticamente de jornadas anteriores
                                            </p>
                                        </div>
                                    </div>
                                )}

                                <div className="flex justify-end pt-4">
                                    <Button
                                        onClick={handleProceed}
                                        disabled={!selectedClient || !selectedProvider}
                                        data-testid="proceed-btn"
                                    >
                                        <Package className="w-4 h-4 mr-2" />
                                        Crear jornada ({parsedData.total_rows + (selectedProvider ? retryPackages.length : 0)} paquetes)
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>

                {/* Upload history */}
                <div className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <History className="w-5 h-5" />
                                Historial de cargas
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="p-4 space-y-3">
                                    {[1, 2, 3].map((i) => (
                                        <div key={i} className="h-16 bg-slate-100 animate-pulse rounded" />
                                    ))}
                                </div>
                            ) : uploadHistory.length === 0 ? (
                                <div className="text-center py-8 text-slate-500">
                                    <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                    <p className="text-sm">Sin cargas recientes</p>
                                </div>
                            ) : (
                                <div className="divide-y divide-slate-100">
                                    {uploadHistory.slice(0, 10).map((entry) => (
                                        <div 
                                            key={entry.id} 
                                            className="p-4 hover:bg-slate-50 transition-colors"
                                        >
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="font-mono text-sm text-slate-900">
                                                    {formatDate(entry.date)}
                                                </span>
                                                <span className="text-xs text-slate-500">
                                                    {entry.package_count} paquetes
                                                </span>
                                            </div>
                                            <div className="flex items-center justify-between">
                                                <span className="text-sm text-slate-600">
                                                    {entry.provider_name}
                                                </span>
                                                <span className={`status-badge ${
                                                    entry.journey_status === 'closed' 
                                                        ? 'status-closed' 
                                                        : entry.journey_status === 'in_progress'
                                                            ? 'status-in_progress'
                                                            : 'status-scheduled'
                                                }`}>
                                                    {entry.journey_status === 'closed' ? 'Cerrada' : 
                                                     entry.journey_status === 'in_progress' ? 'En progreso' : 'Programada'}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>

            {/* Retry packages dialog */}
            <Dialog open={showRetryDialog} onOpenChange={setShowRetryDialog}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="font-heading">
                            Paquetes de reintento
                        </DialogTitle>
                        <DialogDescription>
                            Los siguientes paquetes no fueron entregados en jornadas anteriores.
                            Selecciona los que deseas incluir en esta jornada.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="max-h-96 overflow-y-auto">
                        <table className="data-table w-full text-sm">
                            <thead>
                                <tr>
                                    <th className="w-10"></th>
                                    <th>No. Guía</th>
                                    <th>Destinatario</th>
                                    <th>Fecha original</th>
                                </tr>
                            </thead>
                            <tbody>
                                {retryPackages.map((pkg) => (
                                    <tr key={pkg.id}>
                                        <td>
                                            <Checkbox
                                                checked={selectedRetryPackages.includes(pkg.id)}
                                                onCheckedChange={() => toggleRetryPackage(pkg.id)}
                                            />
                                        </td>
                                        <td className="font-mono">{pkg.tracking_number}</td>
                                        <td>{pkg.recipient_name}</td>
                                        <td className="font-mono text-xs">
                                            {formatDate(pkg.original_journey_date)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div className="flex justify-between items-center pt-4">
                        <p className="text-sm text-slate-500">
                            {selectedRetryPackages.length} de {retryPackages.length} seleccionados
                        </p>
                        <div className="flex gap-3">
                            <Button variant="outline" onClick={() => setShowRetryDialog(false)}>
                                Cancelar
                            </Button>
                            <Button onClick={handleConfirmRetry} data-testid="confirm-retry-btn">
                                Continuar
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            {/* Confirm dialog */}
            <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="font-heading">
                            Confirmar creación de jornada
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Se creará una jornada con los siguientes datos:
                            <ul className="mt-3 space-y-1 text-slate-700">
                                <li>• Fecha: <strong>{format(selectedDate, 'dd/MM/yyyy')}</strong></li>
                                <li>• Cliente: <strong>{clients.find(c => c.id === selectedClient)?.name}</strong></li>
                                <li>• Proveedor: <strong>{providers.find(p => p.id === selectedProvider)?.name}</strong></li>
                                <li>• Paquetes nuevos: <strong>{parsedData?.total_rows}</strong></li>
                                <li>• Paquetes de reintento: <strong>{selectedRetryPackages.length}</strong></li>
                                <li>• Total: <strong>{(parsedData?.total_rows || 0) + selectedRetryPackages.length}</strong></li>
                            </ul>
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction 
                            onClick={handleCreateJourney}
                            disabled={creating}
                            data-testid="confirm-create-btn"
                        >
                            {creating ? (
                                <>
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    Creando...
                                </>
                            ) : (
                                'Crear jornada'
                            )}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
};

export default Layout;
