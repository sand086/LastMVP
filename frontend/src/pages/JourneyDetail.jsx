import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useSortableTable } from '../lib/useSortableTable';
import { 
    getJourney, 
    startJourney, 
    closeJourney,
    createIncident,
    updateIncident,
    deleteIncident,
    resolveAllIncidents,
    exportIncidents,
    uploadJourneyImages,
    getJourneyImages,
    deleteJourneyImage,
    evaluateJourneyQuality,
    reviewPackage,
    evaluatePackageEvidence,
    evaluateAllEvidence,
    bulkUpdatePackageStatus,
    rescrapePackage,
    batchRescrapeJourney,
    getProviders,
    changeJourneyProvider,
} from '../lib/api';
import api from '../lib/api';
import { exportJourneyPdf } from '../lib/journeyPdfExport';
import { buildIncidentDescription } from '../lib/incidentTemplate';
import { 
    formatDate, 
    formatDateTime,
    formatTime,
    getStatusColor, 
    getStatusLabel,
    getSeverityColor,
    getProgressColor,
    calculateDeliveryRate,
    generateWhatsAppStartSummary,
    generateWhatsAppCloseSummary,
    copyToClipboard,
    downloadFile,
    INCIDENT_TYPES,
    FUEL_LEVELS,
    VEHICLE_CONDITIONS,
    FAILURE_REASONS,
    SEVERITY_OPTIONS,
    IMPUTABILITY_OPTIONS,
    getImputabilityColor,
} from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Progress } from '../components/ui/progress';
import { Checkbox } from '../components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
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
import { 
    ArrowLeft,
    Truck,
    Play,
    Square,
    AlertTriangle,
    Package,
    Clock,
    Gauge,
    Fuel,
    FileText,
    Camera,
    Copy,
    Check,
    Plus,
    Pencil,
    Trash2,
    Download,
    Loader2,
    CheckCircle2,
    XCircle,
    RefreshCw,
    Search,
    MessageSquare,
    ExternalLink,
    CheckCheck,
    Circle,
    Users,
    Save,
} from 'lucide-react';
import { toast } from 'sonner';
import ImageUploader from '../components/ImageUploader';
import EvidenceCarousel from '../components/EvidenceCarousel';
import GuiasTab from '../components/GuiasTab';
import PulseBanner from '../components/PulseBanner';
import { JourneyStartTab } from '../components/JourneyStartTab';
import { JourneyIncidentsTab } from '../components/JourneyIncidentsTab';
import { JourneyCloseTab } from '../components/JourneyCloseTab';
import { ProviderEditDialogs } from '../components/journey/ProviderEditDialogs';

const JourneyDetail = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { canEdit, isCoordinator } = useAuth();

    const [journey, setJourney] = useState(null);
    const [loading, setLoading] = useState(true);
    const [pulseConfig, setPulseConfig] = useState(null);
    const [activeTab, setActiveTab] = useState(() => {
        // Smart default: show Calidad for routes with packages, Inicio for new routes
        return 'inicio';
    });
    const initialTabSet = React.useRef(false);

    // Evidence Carousel state
    const [mainCarouselOpen, setMainCarouselOpen] = useState(false);
    const [mainCarouselImages, setMainCarouselImages] = useState([]);
    const [mainCarouselIndex, setMainCarouselIndex] = useState(0);
    const [mainCarouselPkgInfo, setMainCarouselPkgInfo] = useState(null);

    // Bulk status update state
    const [selectedPackages, setSelectedPackages] = useState({});
    const [bulkStatus, setBulkStatus] = useState('');
    const [bulkSaving, setBulkSaving] = useState(false);

    // Images state
    const [startImages, setStartImages] = useState([]);
    const [closeImages, setCloseImages] = useState([]);
    const [returnEvidenceImages, setReturnEvidenceImages] = useState([]);
    const [incidentImages, setIncidentImages] = useState({});
    const [uploadingImages, setUploadingImages] = useState(false);

    // Start form state
    const [startForm, setStartForm] = useState({
        departure_time: new Date().toISOString().slice(0, 16),
        odometer_start: '',
        fuel_level: '',
        vehicle_condition: '',
        vehicle_notes: '',
        packages_loaded: 0,
        notes: '',
        arrival_time_cedis: '',
        backup_driver_name: '',
        backup_request_time: '',
        backup_arrival_time: '',
        route_type: 'CDMX / Zona Metro',
        city: '',
        max_packages: 50,
        traslado_primer_punto: 40,
    });
    const [startSubmitting, setStartSubmitting] = useState(false);
    const [showStartSummary, setShowStartSummary] = useState(false);
    const [startSummary, setStartSummary] = useState('');
    const [copied, setCopied] = useState(false);

    // Close form state
    const [closeForm, setCloseForm] = useState({
        closed_at: new Date().toISOString().slice(0, 16),
        odometer_end: '',
        notes: '',
    });
    const [closeChecklist, setCloseChecklist] = useState({
        cosmo_screenshot: false,
        odometer_final: false,
        failed_list: false,
        incidents_reviewed: false,
        return_evidence: false,
    });
    const [failedPackages, setFailedPackages] = useState([]);
    const [closeSubmitting, setCloseSubmitting] = useState(false);
    const [showCloseSummary, setShowCloseSummary] = useState(false);
    const [closeSummary, setCloseSummary] = useState('');
    const [showCloseConfirm, setShowCloseConfirm] = useState(false);
    const [packageSearchTerm, setPackageSearchTerm] = useState('');

    // Incident state
    const [showIncidentModal, setShowIncidentModal] = useState(false);
    const [editingIncident, setEditingIncident] = useState(null);
    const [showResolveAllConfirm, setShowResolveAllConfirm] = useState(false);
    const [resolvingAll, setResolvingAll] = useState(false);
    const [incidentForm, setIncidentForm] = useState({
        occurred_at: new Date().toISOString().slice(0, 16),
        incident_type: '',
        description: '',
        severity: '',
        tracking_number: '',
        action_taken: '',
        comentario_asesor: '',
    });
    const [incidentSubmitting, setIncidentSubmitting] = useState(false);
    const [showPackagesList, setShowPackagesList] = useState(false);

    // Sortable table hooks
    const { sortedData: sortedPackages, SortHeader: PkgSortHeader } = useSortableTable(journey?.packages || []);
    const { sortedData: sortedIncidents, SortHeader: IncSortHeader } = useSortableTable(journey?.incidents || [], 'occurred_at', 'desc');

    // Batch rescrape state
    const [batchRescraping, setBatchRescraping] = useState(false);
    const [batchRescrapeProgress, setBatchRescrapeProgress] = useState({ done: 0, total: 0, recovered: 0 });

    // Provider edit state (P1)
    const [showProviderEdit, setShowProviderEdit] = useState(false);
    const [providersList, setProvidersList] = useState([]);
    const [selectedProvider, setSelectedProvider] = useState('');
    const [providerEditSaving, setProviderEditSaving] = useState(false);
    const [showProviderConfirm, setShowProviderConfirm] = useState(false);

    useEffect(() => {
        fetchJourney();
        fetchImages();
        // Fetch pulse config
        api.get('/admin/config').then(res => {
            setPulseConfig(res.data?.pulse_config || null);
        }).catch((err) => { console.error('Failed to load pulse config:', err); });
        // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchJourney/fetchImages are stable, only re-run on id change
    }, [id]);

    const fetchImages = async () => {
        try {
            const res = await getJourneyImages(id);
            const images = res.data;
            
            // Separate images by section
            setStartImages(images.filter(img => img.section === 'start'));
            setCloseImages(images.filter(img => img.section === 'close'));
            setReturnEvidenceImages(images.filter(img => img.section === 'return_evidence'));
            
            // Group incident images by incident_id
            const incidentImgs = {};
            images.filter(img => img.section === 'incident').forEach(img => {
                if (img.incident_id) {
                    if (!incidentImgs[img.incident_id]) {
                        incidentImgs[img.incident_id] = [];
                    }
                    incidentImgs[img.incident_id].push(img);
                }
            });
            setIncidentImages(incidentImgs);
        } catch (error) {
            console.error('Error fetching images:', error);
        }
    };

    const handleUploadImages = async (files, section, incidentId = null) => {
        setUploadingImages(true);
        try {
            await uploadJourneyImages(files, id, section, incidentId);
            toast.success('Imágenes subidas correctamente');
            fetchImages();
        } catch (error) {
            toast.error('Error al subir imágenes');
        } finally {
            setUploadingImages(false);
        }
    };

    const handleDeleteImage = async (imageId) => {
        try {
            await deleteJourneyImage(imageId);
            toast.success('Imagen eliminada');
            fetchImages();
        } catch (error) {
            toast.error('Error al eliminar imagen');
        }
    };

    // Open evidence carousel for any package
    const openMainCarousel = (pkg, startIndex = 0) => {
        const urls = pkg.kosmo_proof_urls || [];
        const photoAnalyses = pkg.evidence_detail?.photos_analysis || [];
        const imgs = urls.map((url, i) => ({
            url,
            analysis: photoAnalyses[i] || null,
        }));
        if (imgs.length === 0) return;
        setMainCarouselImages(imgs);
        setMainCarouselIndex(startIndex);
        setMainCarouselPkgInfo({
            guide: pkg.tracking_number || pkg.order_reference_id,
            deliveryType: pkg.evidence_type,
            score: pkg.evidence_score,
        });
        setMainCarouselOpen(true);
    };

    // Bulk status update
    const selectedPkgIds = Object.entries(selectedPackages).filter(([, v]) => v).map(([k]) => k);
    const handleBulkSave = async () => {
        if (!bulkStatus || selectedPkgIds.length === 0) return;
        setBulkSaving(true);
        try {
            const res = await bulkUpdatePackageStatus(id, selectedPkgIds, bulkStatus);
            toast.success(`${res.data.updated} paquetes actualizados a "${bulkStatus}"`);
            setSelectedPackages({});
            setBulkStatus('');
            fetchJourney();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al actualizar');
        } finally {
            setBulkSaving(false);
        }
    };

    const toggleSelectAll = () => {
        const pkgs = journey?.packages || [];
        const allSelected = pkgs.every(p => selectedPackages[p.id]);
        const newSelection = {};
        if (!allSelected) {
            pkgs.forEach(p => { newSelection[p.id] = true; });
        }
        setSelectedPackages(newSelection);
    };

    // Handler for inline incident registration from GuiasTab
    const handleRegisterIncidentFromGuias = (pkg) => {
        // Auto-fill structured template from AI evaluation (criterios fallidos +
        // alertas + score). Replaces the previous generic placeholder. Agent can
        // edit freely before saving.
        const tpl = buildIncidentDescription(pkg, journey);
        setIncidentForm({
            occurred_at: new Date().toISOString().slice(0, 16),
            incident_type: tpl.incident_type || '',
            description: tpl.description,
            severity: tpl.severity || 'Medio',
            tracking_number: pkg.tracking_number || pkg.order_reference_id || '',
            action_taken: '',
            comentario_asesor: '',
            source: 'guias',
        });
        setEditingIncident(null);
        setShowIncidentModal(true);
    };

    const fetchJourney = async () => {
        try {
            const res = await getJourney(id);
            setJourney(res.data);
            
            // Initialize forms with journey data
            if (res.data.start_data) {
                setStartForm(prev => ({
                    ...prev,
                    ...res.data.start_data,
                }));
            } else {
                setStartForm(prev => ({
                    ...prev,
                    packages_loaded: res.data.packages_total,
                }));
            }

            // Pre-populate failed packages for close form (P0-4)
            if (res.data.status === 'in_progress' && res.data.packages) {
                const autoFailed = res.data.packages
                    .filter(p => 
                        p.status === 'failed' || 
                        p.kosmo_status_raw === 'cancelled' || 
                        p.kosmo_status_raw === 'failed'
                    )
                    .map(p => ({ id: p.id, failure_reason: p.failure_reason || 'Otro' }));
                setFailedPackages(autoFailed);
            }

            // Set active tab based on status (only on initial load)
            if (!initialTabSet.current) {
                initialTabSet.current = true;
                if ((res.data.status === 'scheduled' || res.data.status === 'planificada') && !res.data.start_data) {
                    setActiveTab('inicio');
                } else if (res.data.status === 'in_progress') {
                    setActiveTab('incidencias');
                } else if (res.data.status === 'closed') {
                    setActiveTab('guias');
                } else {
                    setActiveTab('inicio');
                }
            }
        } catch (error) {
            toast.error('Error al cargar ruta');
            navigate('/journeys');
        } finally {
            setLoading(false);
        }
    };

    // Start journey handlers
    const handleStartJourney = async () => {
        setStartSubmitting(true);
        try {
            await startJourney(id, {
                ...startForm,
            });

            const summary = generateWhatsAppStartSummary(journey, startForm);
            setStartSummary(summary);
            setShowStartSummary(true);
            
            toast.success('Ruta iniciada');
            fetchJourney();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al iniciar ruta');
        } finally {
            setStartSubmitting(false);
        }
    };

    // Close journey handlers
    const handlePreCloseJourney = () => {
        const requiredChecks = { ...closeChecklist };
        
        // return_evidence is only required when there are packages to return
        if (failedPackages.length === 0) {
            delete requiredChecks.return_evidence;
        }
        
        const allChecked = Object.values(requiredChecks).every(v => v);
        if (!allChecked) {
            toast.error('Completa todos los items del checklist');
            return;
        }
        
        if (!closeForm.odometer_end || parseInt(closeForm.odometer_end) <= 0) {
            toast.error('Ingresa el odómetro final antes de cerrar la ruta');
            return;
        }

        setShowCloseConfirm(true);
    };

    const handleCloseJourney = async () => {
        setShowCloseConfirm(false);
        setCloseSubmitting(true);

        try {
            // Auto-calculate delivered and failed from package statuses
            const packages = journey.packages || [];
            const deliveredCount = packages.filter(p => p.status === 'delivered').length;
            const failedCount = packages.filter(p => p.status === 'failed').length;

            const closeData = {
                ...closeForm,
                packages_delivered: deliveredCount,
                packages_failed: failedCount,
                failed_packages: failedPackages,
                checklist_completed: true,
            };

            const res = await closeJourney(id, closeData);
            
            const updatedJourney = { ...journey, close_data: res.data.close_data };
            const summary = generateWhatsAppCloseSummary(updatedJourney, res.data.close_data);
            setCloseSummary(summary);
            setShowCloseSummary(true);
            
            toast.success('Ruta cerrada');
            fetchJourney();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al cerrar ruta');
        } finally {
            setCloseSubmitting(false);
        }
    };

    // Incident handlers
    const handleOpenIncidentModal = (incident = null) => {
        if (incident) {
            setEditingIncident(incident);
            setIncidentForm({
                occurred_at: incident.occurred_at?.slice(0, 16) || new Date().toISOString().slice(0, 16),
                incident_type: incident.incident_type || '',
                description: incident.description || '',
                severity: incident.severity || '',
                tracking_number: incident.tracking_number || '',
                action_taken: incident.action_taken || '',
                imputability: incident.imputability || 'Por definir',
                comentario_asesor: incident.comentario_asesor || '',
            });
        } else {
            setEditingIncident(null);
            setIncidentForm({
                occurred_at: new Date().toISOString().slice(0, 16),
                incident_type: '',
                description: '',
                severity: '',
                tracking_number: '',
                action_taken: '',
                imputability: 'Por definir',
                comentario_asesor: '',
            });
        }
        setShowIncidentModal(true);
    };

    // Cuando cambia el tipo de incidencia, limpiar comentario_asesor si ya no es 'otro'
    const handleIncidentTypeChange = (newType) => {
        setIncidentForm(prev => ({
            ...prev,
            incident_type: newType,
            comentario_asesor: newType === 'otro' ? prev.comentario_asesor : '',
        }));
    };

    const handleSaveIncident = async () => {
        if (!incidentForm.incident_type || !incidentForm.description || !incidentForm.severity) {
            toast.error('Completa los campos requeridos');
            return;
        }
        if (incidentForm.incident_type === 'otro' && !(incidentForm.comentario_asesor || '').trim()) {
            toast.error('Describe brevemente el tipo de incidencia.');
            return;
        }

        setIncidentSubmitting(true);
        try {
            // Solo enviar comentario_asesor cuando el tipo es 'otro'
            const payload = { ...incidentForm };
            if (payload.incident_type !== 'otro') {
                payload.comentario_asesor = null;
            } else {
                payload.comentario_asesor = (payload.comentario_asesor || '').trim();
            }

            if (editingIncident) {
                await updateIncident(editingIncident.id, payload);
                toast.success('Incidencia actualizada');
            } else {
                await createIncident({
                    ...payload,
                    journey_id: id,
                    source: payload.source || 'incidencias',
                });
                toast.success('Incidencia registrada');
            }
            setShowIncidentModal(false);
            fetchJourney();
        } catch (error) {
            toast.error(error?.response?.data?.detail || 'Error al guardar incidencia');
        } finally {
            setIncidentSubmitting(false);
        }
    };

    const handleResolveIncident = async (incident) => {
        try {
            await updateIncident(incident.id, {
                ...incident,
                status: 'resolved',
                action_taken: incident.action_taken || 'Resuelta por el coordinador',
            });
            toast.success('Incidencia resuelta');
            fetchJourney();
        } catch (error) {
            toast.error('Error al resolver incidencia');
        }
    };

    const handleDeleteIncident = async (incidentId) => {
        try {
            await deleteIncident(incidentId);
            toast.success('Incidencia eliminada');
            fetchJourney();
        } catch (error) {
            toast.error('Error al eliminar incidencia');
        }
    };

    const handleResolveAllIncidents = async () => {
        setShowResolveAllConfirm(false);
        setResolvingAll(true);
        try {
            const res = await resolveAllIncidents(id);
            toast.success(`${res.data.resolved_count} incidencias marcadas como resueltas`);
            fetchJourney();
        } catch (error) {
            toast.error('Error al resolver incidencias');
        } finally {
            setResolvingAll(false);
        }
    };

    const handleReviewPackage = async (packageId) => {
        try {
            await reviewPackage(packageId);
            toast.success('Paquete marcado como revisado');
            fetchJourney();
        } catch (error) {
            toast.error('Error al marcar como revisado');
        }
    };

    const handleExportIncidents = async () => {
        try {
            const res = await exportIncidents({ journey_id: id });
            downloadFile(res.data, `incidencias_${journey.date}.csv`);
            toast.success('Incidencias exportadas');
        } catch (error) {
            toast.error('Error al exportar');
        }
    };

    // Provider edit handlers (P1)
    const openProviderEdit = async () => {
        try {
            const res = await getProviders();
            setProvidersList(res.data);
        } catch (err) { console.error('Failed to load providers:', err); }
        setSelectedProvider(journey.provider_id || '');
        setShowProviderEdit(true);
    };

    const handleSaveProvider = async () => {
        if (!selectedProvider) { toast.error('Selecciona un proveedor'); return; }
        if (selectedProvider === journey.provider_id) { setShowProviderEdit(false); return; }
        // If route is closed/completed, require confirmation
        if (journey.status === 'closed') {
            setShowProviderConfirm(true);
            return;
        }
        await doSaveProvider();
    };

    const doSaveProvider = async () => {
        setProviderEditSaving(true);
        setShowProviderConfirm(false);
        try {
            const res = await changeJourneyProvider(id, { provider_id: selectedProvider });
            if (res.data.changed) {
                toast.success(res.data.message);
                fetchJourney();
            } else {
                toast.info(res.data.message);
            }
            setShowProviderEdit(false);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al cambiar proveedor');
        } finally {
            setProviderEditSaving(false);
        }
    };

    const handleCopy = (text) => {
        copyToClipboard(text);
        setCopied(true);
        toast.success('Copiado al portapapeles');
        setTimeout(() => setCopied(false), 2000);
    };

    const toggleFailedPackage = (pkg, reason) => {
        setFailedPackages(prev => {
            const existing = prev.find(p => p.id === pkg.id);
            if (existing) {
                if (reason) {
                    return prev.map(p => p.id === pkg.id ? { ...p, failure_reason: reason } : p);
                }
                return prev.filter(p => p.id !== pkg.id);
            }
            return [...prev, { id: pkg.id, failure_reason: reason || 'Otro' }];
        });
    };

    // Calculate close metrics from actual package data
    const calculateCloseMetrics = () => {
        const packages = journey?.packages || [];
        const delivered = packages.filter(p => p.status === 'delivered').length;
        const failed = packages.filter(p => p.status === 'failed').length;
        const toReturn = failedPackages.length;
        const packagesLoaded = journey?.start_data?.packages_loaded || journey?.packages_total || 0;
        const odometerStart = journey?.start_data?.odometer_start || 0;
        const odometerEnd = parseInt(closeForm.odometer_end) || 0;
        const kmTraveled = odometerEnd - odometerStart;
        const deliveryRate = packagesLoaded > 0 ? ((delivered / packagesLoaded) * 100).toFixed(1) : 0;

        return { delivered, failed, toReturn, kmTraveled, deliveryRate };
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        );
    }

    if (!journey) return null;

    const deliveryRate = calculateDeliveryRate(journey.packages_delivered, journey.packages_total);
    const progressColor = getProgressColor(deliveryRate);
    const openIncidents = journey.incidents?.filter(i => i.status === 'open') || [];
    const metrics = calculateCloseMetrics();
    const returnCandidates = journey.packages?.filter(p => 
        p.status === 'pending' || p.status === 'failed' || 
        p.kosmo_status_raw === 'cancelled' || p.kosmo_status_raw === 'failed'
    ) || [];

    const getKosmoTimeSince = (isoDate) => {
        if (!isoDate) return '';
        const diff = Math.floor((Date.now() - new Date(isoDate).getTime()) / 60000);
        if (diff < 1) return 'ahora';
        if (diff < 60) return `hace ${diff} min`;
        if (diff < 1440) return `hace ${Math.floor(diff / 60)}h`;
        return `hace ${Math.floor(diff / 1440)}d`;
    };

    const formatMsTimestamp = (ms) => {
        if (!ms) return null;
        const d = new Date(ms);
        return d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className="space-y-4 sm:space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex items-start sm:items-center gap-3 sm:gap-4">
                    <Link to="/journeys">
                        <Button variant="ghost" size="icon" className="flex-shrink-0 mt-0.5 sm:mt-0" data-testid="back-btn">
                            <ArrowLeft className="w-5 h-5" />
                        </Button>
                    </Link>
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <h1 className="font-heading text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
                                Ruta {formatDate(journey.date)}
                            </h1>
                            <span className={`status-badge ${getStatusColor(journey.status)}`}>
                                {getStatusLabel(journey.status)}
                            </span>
                        </div>
                        {journey.order_id && (
                            <button
                                className="inline-flex items-center gap-1.5 text-xs font-mono text-blue-700 bg-blue-50 border border-blue-200 rounded px-2 py-0.5 mt-1 hover:bg-blue-100 transition-colors"
                                onClick={() => { navigator.clipboard.writeText(journey.order_id); toast.success('Order ID copiado'); }}
                                title="Copiar Order ID"
                                data-testid="copy-order-id"
                            >
                                {journey.order_id}
                                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            </button>
                        )}
                        {journey.cosmo_route_id && !journey.order_id && (
                            <span className="text-xs text-slate-400 font-mono block mt-1" data-testid="cosmo-route-id">
                                {journey.cosmo_route_id}
                            </span>
                        )}
                        {journey.source === 'routal' && journey.routal_plan_id && (
                            <button
                                onClick={() => {
                                    navigator.clipboard?.writeText(journey.routal_plan_id);
                                    toast.success('Routal Plan ID copiado');
                                }}
                                className="text-xs text-slate-500 font-mono mt-1 inline-flex items-center gap-1 hover:text-slate-700 transition-colors"
                                title={journey.routal_plan_label ? `${journey.routal_plan_label} · click para copiar` : 'click para copiar'}
                                data-testid="routal-plan-id"
                            >
                                <span className="px-1.5 py-0.5 bg-emerald-50 text-emerald-700 rounded border border-emerald-200 text-[10px] font-semibold uppercase">Routal</span>
                                {journey.routal_plan_label || journey.routal_plan_id.slice(0, 12) + '…'}
                                <svg className="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                            </button>
                        )}
                        <p className="text-slate-500 text-xs sm:text-sm mt-1 flex flex-wrap items-center gap-x-1">
                            {journey.driver_name && (
                                <span className="font-medium text-slate-700">{journey.driver_name} •</span>
                            )}
                            <span className="inline-flex items-center gap-1">
                                {journey.provider_name}
                                {isCoordinator() && (
                                    <button
                                        onClick={openProviderEdit}
                                        className="inline-flex items-center justify-center w-5 h-5 rounded hover:bg-slate-200 transition-colors"
                                        title="Cambiar proveedor de esta ruta"
                                        data-testid="edit-route-provider-btn"
                                    >
                                        <Pencil className="w-3 h-3 text-slate-400" />
                                    </button>
                                )}
                            </span>
                            <span>• {journey.client_name}</span>
                            {journey.route_type && journey.route_type !== 'CDMX / Zona Metro' && (
                                <span className="px-2 py-0.5 text-xs font-medium bg-violet-100 text-violet-700 rounded border border-violet-200">
                                    {journey.route_type}{journey.city ? ` — ${journey.city}` : ''}
                                </span>
                            )}
                            {(!journey.route_type || journey.route_type === 'CDMX / Zona Metro') && (
                                <span className="px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded border border-blue-200">
                                    CDMX
                                </span>
                            )}
                        </p>
                    </div>
                </div>
                <div className="flex-shrink-0">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={async () => {
                            try {
                                await exportJourneyPdf(journey);
                                toast.success('PDF descargado');
                            } catch (err) {
                                console.error('PDF export error:', err);
                                toast.error('No se pudo generar el PDF');
                            }
                        }}
                        data-testid="export-journey-pdf-btn"
                    >
                        <Download className="w-4 h-4 mr-2" />
                        Exportar PDF
                    </Button>
                </div>
            </div>

            {/* Stats cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                <Card className="p-3 sm:p-4">
                    <div className="flex items-center gap-2 sm:gap-3">
                        <Package className="w-6 h-6 sm:w-8 sm:h-8 text-slate-400" strokeWidth={1.5} />
                        <div>
                            <p className="text-[10px] sm:text-xs text-slate-500 uppercase tracking-wider">Paquetes</p>
                            <p className="text-lg sm:text-xl font-heading font-bold">
                                {journey.packages_delivered}/{journey.packages_total}
                            </p>
                        </div>
                    </div>
                </Card>
                <Card className="p-3 sm:p-4">
                    <div className="flex items-center gap-2 sm:gap-3">
                        <div className="w-6 h-6 sm:w-8 sm:h-8 flex items-center justify-center">
                            <Progress 
                                value={deliveryRate} 
                                className="h-6 w-6 sm:h-8 sm:w-8 rounded-full"
                                indicatorClassName={progressColor}
                            />
                        </div>
                        <div>
                            <p className="text-[10px] sm:text-xs text-slate-500 uppercase tracking-wider">Progreso</p>
                            <p className="text-lg sm:text-xl font-heading font-bold">{deliveryRate}%</p>
                        </div>
                    </div>
                </Card>
                <Card className="p-3 sm:p-4">
                    <div className="flex items-center gap-2 sm:gap-3">
                        <AlertTriangle className={`w-6 h-6 sm:w-8 sm:h-8 ${openIncidents.length > 0 ? 'text-amber-500' : 'text-slate-400'}`} strokeWidth={1.5} />
                        <div>
                            <p className="text-[10px] sm:text-xs text-slate-500 uppercase tracking-wider">Incidencias</p>
                            <p className="text-lg sm:text-xl font-heading font-bold">{openIncidents.length} <span className="hidden sm:inline">abiertas</span></p>
                        </div>
                    </div>
                </Card>
                <Card className="p-3 sm:p-4">
                    <div className="flex items-center gap-2 sm:gap-3">
                        <Users className="w-6 h-6 sm:w-8 sm:h-8 text-slate-400" strokeWidth={1.5} />
                        <div>
                            <p className="text-[10px] sm:text-xs text-slate-500 uppercase tracking-wider">Visitas</p>
                            <p className="text-lg sm:text-xl font-heading font-bold">
                                {(journey.packages?.filter(p => p.status === 'delivered' || p.status === 'failed' || p.status === 'returned').length) || 0}
                            </p>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Pulse Banner - between KPIs and Tabs */}
            {journey.status === 'in_progress' && pulseConfig && (
                <PulseBanner journey={journey} pulseConfig={pulseConfig} />
            )}

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-4 h-10 sm:h-auto">
                    <TabsTrigger value="inicio" data-testid="tab-inicio" className="text-xs sm:text-sm px-1 sm:px-3">
                        <Play className="w-4 h-4 sm:mr-2" />
                        <span className="hidden sm:inline">Inicio</span>
                    </TabsTrigger>
                    <TabsTrigger value="incidencias" data-testid="tab-incidencias" className="text-xs sm:text-sm px-1 sm:px-3 relative">
                        <AlertTriangle className="w-4 h-4 sm:mr-2" />
                        <span className="hidden sm:inline">Incidencias ({journey.incidents?.length || 0})</span>
                        {(journey.incidents?.length || 0) > 0 && (
                            <span className="sm:hidden absolute -top-1 -right-1 w-4 h-4 text-[9px] font-bold bg-amber-500 text-white rounded-full flex items-center justify-center">{journey.incidents?.length || 0}</span>
                        )}
                    </TabsTrigger>
                    <TabsTrigger value="fin" data-testid="tab-fin" className="text-xs sm:text-sm px-1 sm:px-3">
                        <Square className="w-4 h-4 sm:mr-2" />
                        <span className="hidden sm:inline">Fin</span>
                    </TabsTrigger>
                    <TabsTrigger value="guias" data-testid="tab-guias" className="text-xs sm:text-sm px-1 sm:px-3">
                        <Package className="w-4 h-4 sm:mr-2" />
                        <span className="hidden sm:inline">Guias</span>
                    </TabsTrigger>
                </TabsList>

                {/* Tab: Inicio de Ruta */}
                <TabsContent value="inicio" className="space-y-6">
                    <JourneyStartTab
                        journey={journey}
                        canEdit={canEdit}
                        startForm={startForm}
                        setStartForm={setStartForm}
                        startSubmitting={startSubmitting}
                        startImages={startImages}
                        handleUploadImages={handleUploadImages}
                        handleDeleteImage={handleDeleteImage}
                        uploadingImages={uploadingImages}
                        handleStartJourney={handleStartJourney}
                    />
                </TabsContent>

                {/* Tab: Incidencias */}
                <TabsContent value="incidencias" className="space-y-6">
                    <JourneyIncidentsTab
                        journey={journey}
                        canEdit={canEdit}
                        isCoordinator={isCoordinator}
                        sortedIncidents={sortedIncidents}
                        IncSortHeader={IncSortHeader}
                        incidentImages={incidentImages}
                        openIncidents={openIncidents}
                        resolvingAll={resolvingAll}
                        handleOpenIncidentModal={handleOpenIncidentModal}
                        handleResolveIncident={handleResolveIncident}
                        handleDeleteIncident={handleDeleteIncident}
                        handleExportIncidents={handleExportIncidents}
                        setShowResolveAllConfirm={setShowResolveAllConfirm}
                    />
                </TabsContent>

                {/* Tab: Fin de Ruta */}
                <TabsContent value="fin" className="space-y-6">
                    <JourneyCloseTab
                        journey={journey}
                        canEdit={canEdit}
                        closeForm={closeForm}
                        setCloseForm={setCloseForm}
                        closeChecklist={closeChecklist}
                        setCloseChecklist={setCloseChecklist}
                        closeSubmitting={closeSubmitting}
                        closeImages={closeImages}
                        returnEvidenceImages={returnEvidenceImages}
                        failedPackages={failedPackages}
                        setFailedPackages={setFailedPackages}
                        returnCandidates={returnCandidates}
                        metrics={metrics}
                        packageSearchTerm={packageSearchTerm}
                        setPackageSearchTerm={setPackageSearchTerm}
                        handleUploadImages={handleUploadImages}
                        handleDeleteImage={handleDeleteImage}
                        uploadingImages={uploadingImages}
                        handlePreCloseJourney={handlePreCloseJourney}
                        toggleFailedPackage={toggleFailedPackage}
                    />
                </TabsContent>

                {/* Tab: Guías */}
                <TabsContent value="guias" className="space-y-6" data-testid="tab-guias-content">
                    <GuiasTab journey={journey} packages={journey.packages || []} onRefreshJourney={fetchJourney} onRegisterIncident={handleRegisterIncidentFromGuias} />
                </TabsContent>
            </Tabs>

            {/* Incident Modal */}
            <Dialog open={showIncidentModal} onOpenChange={(open) => {
                // Bug fix 2026-05-25: si el modal se cierra (X / click fuera / ESC)
                // con datos en el form sin guardar, confirmar para evitar la
                // "incidencia fantasma" — el usuario crea el form, lo cierra sin
                // submit, y asume que se guardo. Sin esta proteccion la incidencia
                // nunca llega al backend y desaparece silenciosamente.
                if (!open && !editingIncident) {
                    const hasContent = !!(
                        (incidentForm.incident_type || '').trim() ||
                        (incidentForm.description || '').trim() ||
                        (incidentForm.tracking_number || '').trim() ||
                        (incidentForm.comentario_asesor || '').trim() ||
                        (incidentForm.action_taken || '').trim()
                    );
                    if (hasContent && !window.confirm('Tienes datos sin guardar en este formulario de incidencia. ¿Cerrar de todas formas? Los datos se perderán.')) {
                        return;
                    }
                }
                setShowIncidentModal(open);
            }}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="font-heading">
                            {editingIncident ? 'Editar incidencia' : 'Nueva incidencia'}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label>Fecha/Hora</Label>
                                <Input
                                    type="datetime-local"
                                    value={incidentForm.occurred_at}
                                    onChange={(e) => setIncidentForm({ ...incidentForm, occurred_at: e.target.value })}
                                    data-testid="incident-time-input"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Severidad *</Label>
                                <Select
                                    value={incidentForm.severity}
                                    onValueChange={(v) => setIncidentForm({ ...incidentForm, severity: v })}
                                >
                                    <SelectTrigger data-testid="incident-severity-select">
                                        <SelectValue placeholder="Seleccionar" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {SEVERITY_OPTIONS.map((s) => (
                                            <SelectItem key={s} value={s}>{s}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Tipo de incidencia *</Label>
                            <Select
                                value={incidentForm.incident_type}
                                onValueChange={handleIncidentTypeChange}
                            >
                                <SelectTrigger data-testid="incident-type-select">
                                    <SelectValue placeholder="Seleccionar tipo" />
                                </SelectTrigger>
                                <SelectContent className="max-w-[min(92vw,560px)]">
                                    {INCIDENT_TYPES.map((t) => (
                                        <SelectItem
                                            key={t.value}
                                            value={t.value}
                                            data-testid={`incident-type-option-${t.value}`}
                                            className="whitespace-normal"
                                        >
                                            {t.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        {incidentForm.incident_type === 'otro' && (
                            <div
                                className="space-y-2 animate-in fade-in slide-in-from-top-2 duration-200"
                                data-testid="incident-comentario-asesor-wrapper"
                            >
                                <Label htmlFor="comentario-asesor">Comentario del asesor *</Label>
                                <Textarea
                                    id="comentario-asesor"
                                    value={incidentForm.comentario_asesor}
                                    onChange={(e) =>
                                        setIncidentForm({
                                            ...incidentForm,
                                            comentario_asesor: e.target.value.slice(0, 500),
                                        })
                                    }
                                    placeholder="Describe brevemente el tipo de incidencia (hasta 500 caracteres)"
                                    rows={2}
                                    maxLength={500}
                                    data-testid="incident-comentario-asesor-textarea"
                                />
                                <div className="flex items-center justify-between text-xs">
                                    {!(incidentForm.comentario_asesor || '').trim() ? (
                                        <p className="text-red-600" data-testid="comentario-asesor-error">
                                            Describe brevemente el tipo de incidencia.
                                        </p>
                                    ) : <span />}
                                    <span className="text-slate-400">
                                        {(incidentForm.comentario_asesor || '').length}/500
                                    </span>
                                </div>
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label>Descripción *</Label>
                            <Textarea
                                value={incidentForm.description}
                                onChange={(e) => setIncidentForm({ ...incidentForm, description: e.target.value })}
                                placeholder="Describe la incidencia..."
                                rows={3}
                                data-testid="incident-description-textarea"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>No. de guía (opcional)</Label>
                            <Input
                                value={incidentForm.tracking_number}
                                onChange={(e) => setIncidentForm({ ...incidentForm, tracking_number: e.target.value })}
                                placeholder="TRK001"
                                data-testid="incident-tracking-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Imputabilidad</Label>
                            <Select
                                value={incidentForm.imputability}
                                onValueChange={(v) => setIncidentForm({ ...incidentForm, imputability: v })}
                            >
                                <SelectTrigger data-testid="incident-imputability-select">
                                    <SelectValue placeholder="Seleccionar" />
                                </SelectTrigger>
                                <SelectContent>
                                    {IMPUTABILITY_OPTIONS.map((opt) => (
                                        <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Acción tomada (opcional)</Label>
                            <Textarea
                                value={incidentForm.action_taken}
                                onChange={(e) => setIncidentForm({ ...incidentForm, action_taken: e.target.value })}
                                placeholder="Describe las acciones realizadas..."
                                rows={2}
                                data-testid="incident-action-textarea"
                            />
                        </div>
                        {/* Image upload for incident */}
                        {editingIncident && (
                            <div className="space-y-2">
                                <Label>Evidencia fotográfica</Label>
                                <ImageUploader
                                    images={incidentImages[editingIncident.id] || []}
                                    onUpload={(files) => handleUploadImages(files, 'incident', editingIncident.id)}
                                    onDelete={handleDeleteImage}
                                    uploading={uploadingImages}
                                    label="Agregar fotos"
                                />
                            </div>
                        )}
                    </div>
                    <DialogFooter className="flex flex-col sm:flex-row gap-2 sm:items-center">
                        {/* Hint visible cuando el boton Guardar esta disabled —
                            evita que el coordinador piense que ya guardo cuando
                            en realidad ningun submit ocurrio. */}
                        {(() => {
                            const missing = [];
                            if (!incidentForm.incident_type) missing.push('Tipo');
                            if (!incidentForm.severity) missing.push('Severidad');
                            if (!(incidentForm.description || '').trim()) missing.push('Descripción');
                            if (incidentForm.incident_type === 'otro' && !(incidentForm.comentario_asesor || '').trim()) missing.push('Comentario');
                            if (missing.length === 0 || incidentSubmitting) return null;
                            return (
                                <p className="text-xs text-amber-700 sm:mr-auto" data-testid="save-incident-disabled-hint">
                                    Faltan campos: <span className="font-semibold">{missing.join(', ')}</span>
                                </p>
                            );
                        })()}
                        <Button variant="outline" onClick={() => setShowIncidentModal(false)} data-testid="cancel-incident-btn">
                            Cancelar
                        </Button>
                        <Button
                            onClick={handleSaveIncident}
                            disabled={
                                incidentSubmitting ||
                                !incidentForm.incident_type ||
                                !incidentForm.severity ||
                                !(incidentForm.description || '').trim() ||
                                (incidentForm.incident_type === 'otro' && !(incidentForm.comentario_asesor || '').trim())
                            }
                            data-testid="save-incident-btn"
                        >
                            {incidentSubmitting ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : null}
                            {editingIncident ? 'Actualizar' : 'Registrar'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Close Confirm Dialog */}
            <AlertDialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="font-heading">¿Cerrar ruta?</AlertDialogTitle>
                        <AlertDialogDescription>
                            Esta acción es irreversible. Los paquetes seleccionados serán marcados como devueltos.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction onClick={handleCloseJourney} data-testid="confirm-close-btn">
                            Cerrar ruta
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Start Summary Dialog */}
            <Dialog open={showStartSummary} onOpenChange={setShowStartSummary}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="font-heading">Resumen de inicio</DialogTitle>
                        <DialogDescription>
                            Copia este resumen para compartir por WhatsApp
                        </DialogDescription>
                    </DialogHeader>
                    <div className="whatsapp-summary">{startSummary}</div>
                    <DialogFooter>
                        <Button onClick={() => handleCopy(startSummary)} data-testid="copy-start-summary-btn">
                            {copied ? <Check className="w-4 h-4 mr-2" /> : <Copy className="w-4 h-4 mr-2" />}
                            {copied ? 'Copiado' : 'Copiar al portapapeles'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Close Summary Dialog */}
            <Dialog open={showCloseSummary} onOpenChange={setShowCloseSummary}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="font-heading">Resumen de cierre</DialogTitle>
                        <DialogDescription>
                            Copia este resumen para compartir por WhatsApp
                        </DialogDescription>
                    </DialogHeader>
                    <div className="whatsapp-summary">{closeSummary}</div>
                    <DialogFooter>
                        <Button onClick={() => handleCopy(closeSummary)} data-testid="copy-close-summary-btn">
                            {copied ? <Check className="w-4 h-4 mr-2" /> : <Copy className="w-4 h-4 mr-2" />}
                            {copied ? 'Copiado' : 'Copiar al portapapeles'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Resolve All Incidents Confirm Dialog */}
            <AlertDialog open={showResolveAllConfirm} onOpenChange={setShowResolveAllConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="font-heading">¿Resolver todas las incidencias?</AlertDialogTitle>
                        <AlertDialogDescription>
                            ¿Confirmas que deseas marcar las {openIncidents.length} incidencias abiertas como resueltas?
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction onClick={handleResolveAllIncidents} data-testid="confirm-resolve-all-btn">
                            Resolver todas
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Main Evidence Carousel */}
            <EvidenceCarousel
                open={mainCarouselOpen}
                onClose={() => setMainCarouselOpen(false)}
                images={mainCarouselImages}
                initialIndex={mainCarouselIndex}
                packageInfo={mainCarouselPkgInfo}
            />

            {/* Provider Edit + Confirm Dialogs */}
            <ProviderEditDialogs
                showProviderEdit={showProviderEdit}
                setShowProviderEdit={setShowProviderEdit}
                selectedProvider={selectedProvider}
                setSelectedProvider={setSelectedProvider}
                providersList={providersList}
                handleSaveProvider={handleSaveProvider}
                providerEditSaving={providerEditSaving}
                showProviderConfirm={showProviderConfirm}
                setShowProviderConfirm={setShowProviderConfirm}
                doSaveProvider={doSaveProvider}
            />
        </div>
    );
};

export default JourneyDetail;
