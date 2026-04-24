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
    getUploadHistory,
    createProviderInline,
    updateDeliveryNotes,
} from '../lib/api';
import { Button } from '../components/ui/button';
import { AlertCircle, X } from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { WizardSteps } from '../components/layout/WizardSteps';
import { UpdateNotesSection } from '../components/layout/UpdateNotesSection';
import { RoutesPreviewCard, UploadHistoryCard } from '../components/layout/LayoutSidebar';
import { LayoutStep1History } from '../components/layout/LayoutStep1History';
import { LayoutStep2Route } from '../components/layout/LayoutStep2Route';
import { LayoutStep3Config } from '../components/layout/LayoutStep3Config';
import { LayoutCreationResult } from '../components/layout/LayoutCreationResult';
import { LayoutConfirmDialog, LayoutPendingProviderDialog } from '../components/layout/LayoutDialogs';

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

    // Pending providers modal (blocking)
    const [pendingProviders, setPendingProviders] = useState([]);
    const [currentPendingIdx, setCurrentPendingIdx] = useState(-1);
    const [pendingProviderForm, setPendingProviderForm] = useState({ name: '', contact_name: '', rfc: '' });
    const [creatingPendingProvider, setCreatingPendingProvider] = useState(false);

    // Update notes section
    const [notesUploading, setNotesUploading] = useState(false);
    const [notesResult, setNotesResult] = useState(null);
    const notesFileRef = useRef(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const results = await Promise.allSettled([
                    getClients(),
                    getProviders(),
                    getMessengerMappings(),
                    getUploadHistory(),
                ]);
                const [clientsRes, providersRes, mappingsRes, historyRes] = results;

                if (clientsRes.status === 'fulfilled') setClients(clientsRes.value.data);
                if (providersRes.status === 'fulfilled') setProviders(providersRes.value.data);
                if (mappingsRes.status === 'fulfilled') {
                    const mappingsObj = {};
                    (mappingsRes.value.data || []).forEach(m => {
                        mappingsObj[m.messenger_name] = m.provider_id;
                    });
                    setMessengerMappings(mappingsObj);
                }
                if (historyRes.status === 'fulfilled') setUploadHistory(historyRes.value.data);

                const failed = results.filter(r => r.status === 'rejected');
                if (failed.length > 0) {
                    console.warn('Partial load failures:', failed.map(f => f.reason?.message));
                }
            } catch (error) {
                toast.error('Error al cargar datos');
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    useEffect(() => {
        if (routeData?.drivers) {
            const newMap = {};
            routeData.drivers.forEach(driver => {
                newMap[driver] = messengerMappings[driver] || '';
            });
            setDriverProviderMap(newMap);
        }
    }, [routeData, messengerMappings]);

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
            toast.success(`${res.data.total_orders} órdenes encontradas en ${res.data.total_routes} rutas${res.data.ignored_rows ? ` (${res.data.ignored_rows} filas ignoradas)` : ''}`);
            setCurrentStep(2);
        } catch (error) {
            setHistoryError(error.response?.data?.detail || 'Error al procesar archivo');
            setHistoryFile(null);
        } finally {
            setHistoryUploading(false);
        }
    };

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

            if (res.data.routes?.length > 0) {
                const firstCreationDate = res.data.routes[0].creation_date;
                if (firstCreationDate) {
                    const dateStr = firstCreationDate.includes('T') ? firstCreationDate.split('T')[0] : firstCreationDate;
                    const parsed = new Date(dateStr + 'T12:00:00');
                    if (!isNaN(parsed.getTime())) setSelectedDate(parsed);
                }
            }

            if (res.data.pending_providers?.length > 0) {
                setPendingProviders(res.data.pending_providers);
                setCurrentPendingIdx(0);
                const first = res.data.pending_providers[0];
                setPendingProviderForm({ name: first.team_name, contact_name: '', rfc: '' });
            } else {
                setCurrentStep(3);
            }
        } catch (error) {
            setRouteError(error.response?.data?.detail || 'Error al procesar archivo');
            setRouteFile(null);
        } finally {
            setRouteUploading(false);
        }
    };

    const handleDriverProviderChange = (driver, providerId) => {
        setDriverProviderMap(prev => ({ ...prev, [driver]: providerId }));
    };

    const allDriversAssigned = routeData?.drivers
        ? routeData.drivers.every(driver => driverProviderMap[driver])
        : false;

    const handleCreateJourneys = async () => {
        setShowConfirmDialog(false);
        setCreating(true);

        try {
            const mappings = Object.entries(driverProviderMap).map(([messenger_name, provider_id]) => ({
                messenger_name, provider_id,
            }));

            const allOrders = [];
            if (historyData?.routes) {
                historyData.routes.forEach(route => {
                    route.orders.forEach(order => {
                        allOrders.push({ ...order, route_id: route.route_id, order_id: route.route_id });
                    });
                });
            }

            const payload = {
                date: format(selectedDate, 'yyyy-MM-dd'),
                client_id: selectedClient,
                history_orders: allOrders,
                route_summary: routeData?.routes || [],
                messenger_provider_mappings: mappings,
            };

            const res = await createJourneysFromCosmo(payload);
            setCreationResult(res.data);
            toast.success(res.data.message);

            if (res.data.created_journeys?.length > 0) {
                setTimeout(() => navigate('/journeys'), 2000);
            }
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al crear rutas');
        } finally {
            setCreating(false);
        }
    };

    const handleClearAll = () => {
        setCurrentStep(1);
        setHistoryFile(null); setHistoryData(null); setHistoryError(null);
        setRouteFile(null); setRouteData(null); setRouteError(null);
        setDriverProviderMap({});
        setCreationResult(null);
        setPendingProviders([]); setCurrentPendingIdx(-1);
        if (historyFileRef.current) historyFileRef.current.value = '';
        if (routeFileRef.current) routeFileRef.current.value = '';
    };

    const handleCreatePendingProvider = async () => {
        if (!pendingProviderForm.name.trim()) { toast.error('Nombre del proveedor requerido'); return; }
        setCreatingPendingProvider(true);
        try {
            const res = await createProviderInline({
                name: pendingProviderForm.name.trim(),
                contact_name: pendingProviderForm.contact_name || '',
                rfc: pendingProviderForm.rfc || '',
                created_via: 'layout_upload',
            });
            const newProv = res.data;
            toast.success(`Proveedor "${newProv.name}" ${newProv.already_existed ? 'ya existia' : 'creado'}`);

            const currentPending = pendingProviders[currentPendingIdx];
            if (currentPending?.drivers) {
                const newMap = { ...driverProviderMap };
                currentPending.drivers.forEach(dn => { newMap[dn] = newProv.id; });
                setDriverProviderMap(newMap);
            }

            try {
                const provRes = await getProviders();
                setProviders(provRes.data);
            } catch (err) { console.error('Failed to refresh providers:', err); }

            const nextIdx = currentPendingIdx + 1;
            if (nextIdx < pendingProviders.length) {
                setCurrentPendingIdx(nextIdx);
                const next = pendingProviders[nextIdx];
                setPendingProviderForm({ name: next.team_name, contact_name: '', rfc: '' });
            } else {
                setPendingProviders([]);
                setCurrentPendingIdx(-1);
                setCurrentStep(3);
            }
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al crear proveedor');
        } finally {
            setCreatingPendingProvider(false);
        }
    };

    const handleCancelPendingUpload = () => {
        setPendingProviders([]); setCurrentPendingIdx(-1);
        setRouteFile(null); setRouteData(null);
        if (routeFileRef.current) routeFileRef.current.value = '';
        toast.info('Carga cancelada');
    };

    const handleUploadNotes = async (file) => {
        if (!file) return;
        setNotesUploading(true);
        setNotesResult(null);
        try {
            const res = await updateDeliveryNotes(file);
            setNotesResult(res.data);
            if (res.data.updated > 0) toast.success(`${res.data.updated} registros actualizados`);
            else toast.info('No se encontraron registros para actualizar');
        } catch (err) {
            let msg = err.response?.data?.detail;
            if (!msg) {
                if (err.response?.status === 413) msg = 'Archivo demasiado grande (límite del servidor). Reduce a menos de 10MB.';
                else if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) msg = 'Tiempo de espera agotado. Intenta con un archivo más pequeño.';
                else if (err.message === 'Network Error') msg = 'Error de red. Verifica tu conexión e intenta de nuevo.';
                else msg = err.message || 'Error al actualizar notas';
            }
            toast.error(msg);
            setNotesResult({ error: msg });
        } finally {
            setNotesUploading(false);
        }
    };

    if (!canEdit()) {
        return (
            <div className="text-center py-16">
                <AlertCircle className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-700 mb-2">Acceso restringido</h3>
                <p className="text-slate-500">No tienes permisos para cargar layouts</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
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

            <WizardSteps currentStep={currentStep} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <LayoutStep1History
                        currentStep={currentStep}
                        historyFile={historyFile}
                        historyData={historyData}
                        historyUploading={historyUploading}
                        historyError={historyError}
                        historyFileRef={historyFileRef}
                        onFileSelect={handleHistoryFileSelect}
                    />

                    <LayoutStep2Route
                        currentStep={currentStep}
                        routeFile={routeFile}
                        routeData={routeData}
                        routeUploading={routeUploading}
                        routeError={routeError}
                        routeFileRef={routeFileRef}
                        onFileSelect={handleRouteFileSelect}
                    />

                    {currentStep >= 3 && (
                        <LayoutStep3Config
                            selectedDate={selectedDate}
                            setSelectedDate={setSelectedDate}
                            selectedClient={selectedClient}
                            setSelectedClient={setSelectedClient}
                            clients={clients}
                            providers={providers}
                            routeData={routeData}
                            driverProviderMap={driverProviderMap}
                            onDriverProviderChange={handleDriverProviderChange}
                            allDriversAssigned={allDriversAssigned}
                            creating={creating}
                            onOpenConfirm={() => setShowConfirmDialog(true)}
                        />
                    )}

                    <LayoutCreationResult result={creationResult} />
                </div>

                <div className="space-y-6">
                    <RoutesPreviewCard routes={historyData?.routes} />
                    <UpdateNotesSection
                        notesFileRef={notesFileRef}
                        notesUploading={notesUploading}
                        notesResult={notesResult}
                        onUpload={handleUploadNotes}
                    />
                    <UploadHistoryCard loading={loading} uploadHistory={uploadHistory} />
                </div>
            </div>

            <LayoutConfirmDialog
                open={showConfirmDialog}
                onOpenChange={setShowConfirmDialog}
                selectedDate={selectedDate}
                selectedClient={selectedClient}
                clients={clients}
                routeData={routeData}
                historyData={historyData}
                onConfirm={handleCreateJourneys}
                creating={creating}
            />

            <LayoutPendingProviderDialog
                currentPendingIdx={currentPendingIdx}
                pendingProviders={pendingProviders}
                pendingProviderForm={pendingProviderForm}
                setPendingProviderForm={setPendingProviderForm}
                onCreate={handleCreatePendingProvider}
                onCancel={handleCancelPendingUpload}
                creating={creatingPendingProvider}
            />
        </div>
    );
};

export default Layout;
