import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
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
} from '../lib/api';
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
    Users
} from 'lucide-react';
import { toast } from 'sonner';
import ImageUploader from '../components/ImageUploader';
import EvidenceCarousel from '../components/EvidenceCarousel';

// Quality Tab Component
const QualityTab = ({ journey, packages, onEvaluate, onRefreshJourney }) => {
    const [filterIncomplete, setFilterIncomplete] = useState(false);
    const [evaluatingPkg, setEvaluatingPkg] = useState(null);
    const [evaluatingAll, setEvaluatingAll] = useState(false);
    const [expandedPkg, setExpandedPkg] = useState(null);
    const [carouselOpen, setCarouselOpen] = useState(false);
    const [carouselImages, setCarouselImages] = useState([]);
    const [carouselIndex, setCarouselIndex] = useState(0);
    const [carouselPkgInfo, setCarouselPkgInfo] = useState(null);

    const scoredPackages = packages.filter(p => p.evidence_score != null);
    const allScores = scoredPackages.map(p => p.evidence_score);
    const avgScore = allScores.length > 0 ? Math.round(allScores.reduce((a, b) => a + b, 0) / allScores.length) : 0;
    const complete = allScores.filter(s => s === 100).length;
    const partial = allScores.filter(s => s >= 60 && s < 100).length;
    const incomplete = allScores.filter(s => s < 60).length;
    const total = scoredPackages.length;
    const aiEvaluated = scoredPackages.filter(p => p.evidence_method === 'ai').length;

    const displayPackages = (filterIncomplete
        ? scoredPackages.filter(p => p.evidence_score < 100)
        : scoredPackages
    ).sort((a, b) => (a.evidence_score || 0) - (b.evidence_score || 0));

    const completePct = total > 0 ? Math.round(complete / total * 100) : 0;
    const partialPct = total > 0 ? Math.round(partial / total * 100) : 0;
    const incompletePct = total > 0 ? Math.round(incomplete / total * 100) : 0;

    const handleEvaluatePackage = async (pkg) => {
        const guide = pkg.order_reference_id || pkg.tracking_number;
        setEvaluatingPkg(guide);
        try {
            await evaluatePackageEvidence(journey.id, guide);
            toast.success(`Evaluación IA completada para ${guide}`);
            if (onRefreshJourney) onRefreshJourney();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al evaluar con IA');
        } finally {
            setEvaluatingPkg(null);
        }
    };

    const handleEvaluateAll = async () => {
        setEvaluatingAll(true);
        try {
            const res = await evaluateAllEvidence(journey.id);
            toast.success(`Evaluación IA completada: ${res.data.ai_evaluated || 0} con IA, ${res.data.rules_evaluated || 0} con reglas`);
            if (onRefreshJourney) onRefreshJourney();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al evaluar con IA');
        } finally {
            setEvaluatingAll(false);
        }
    };

    const openCarousel = (pkg, startIndex = 0) => {
        const urls = pkg.kosmo_proof_urls || [];
        const photoAnalyses = pkg.evidence_detail?.photos_analysis || [];
        const imgs = urls.map((url, i) => ({
            url,
            analysis: photoAnalyses[i] || null,
        }));
        if (imgs.length === 0) return;
        setCarouselImages(imgs);
        setCarouselIndex(startIndex);
        setCarouselPkgInfo({
            guide: pkg.tracking_number || pkg.order_reference_id,
            deliveryType: pkg.evidence_type,
            score: pkg.evidence_score,
        });
        setCarouselOpen(true);
    };

    if (scoredPackages.length === 0) {
        return (
            <Card>
                <CardContent className="py-12 text-center">
                    <CheckCircle2 className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                    <p className="text-slate-500 mb-4">No hay evaluaciones de calidad disponibles para esta ruta.</p>
                    <div className="flex items-center justify-center gap-3">
                        {journey.status === 'closed' && (
                            <>
                                <Button variant="outline" onClick={onEvaluate} data-testid="evaluate-quality-btn">
                                    <RefreshCw className="w-4 h-4 mr-2" /> Evaluar (reglas)
                                </Button>
                                <Button onClick={handleEvaluateAll} disabled={evaluatingAll} data-testid="evaluate-ai-btn">
                                    {evaluatingAll ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Search className="w-4 h-4 mr-2" />}
                                    Evaluar con IA
                                </Button>
                            </>
                        )}
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-4">
            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase">Score promedio</p>
                        <p className={`text-3xl font-mono font-bold ${
                            avgScore >= 90 ? 'text-emerald-600' : avgScore >= 70 ? 'text-amber-600' : 'text-red-600'
                        }`} data-testid="quality-avg-score">{avgScore}%</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase">Completos</p>
                        <p className="text-3xl font-mono font-bold text-emerald-600" data-testid="quality-complete-count">
                            {complete}<span className="text-lg text-slate-400">/{total}</span>
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase">Incompletos</p>
                        <p className="text-3xl font-mono font-bold text-red-600" data-testid="quality-incomplete-count">
                            {incomplete}
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase">Evaluados IA</p>
                        <p className="text-3xl font-mono font-bold text-blue-600" data-testid="quality-ai-count">
                            {aiEvaluated}<span className="text-lg text-slate-400">/{total}</span>
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Reviewed count */}
            <div className="text-sm text-slate-500 text-right">
                {packages.filter(p => p.reviewed_by).length}/{packages.length} revisados
            </div>

            {/* Distribution Bar */}
            <Card>
                <CardContent className="p-4">
                    <p className="text-xs text-slate-500 uppercase mb-2">Distribución de calidad</p>
                    <div className="flex h-6 rounded-sm overflow-hidden" data-testid="quality-distribution-bar">
                        {completePct > 0 && (
                            <div className="bg-emerald-500 flex items-center justify-center text-white text-xs font-mono" style={{ width: `${completePct}%` }}>
                                {completePct}%
                            </div>
                        )}
                        {partialPct > 0 && (
                            <div className="bg-amber-500 flex items-center justify-center text-white text-xs font-mono" style={{ width: `${partialPct}%` }}>
                                {partialPct}%
                            </div>
                        )}
                        {incompletePct > 0 && (
                            <div className="bg-red-500 flex items-center justify-center text-white text-xs font-mono" style={{ width: `${incompletePct}%` }}>
                                {incompletePct}%
                            </div>
                        )}
                    </div>
                    <div className="flex gap-4 mt-2 text-xs text-slate-500">
                        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Completos ({complete})</span>
                        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-amber-500" /> Parciales ({partial})</span>
                        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm bg-red-500" /> Incompletos ({incomplete})</span>
                    </div>
                </CardContent>
            </Card>

            {/* Packages Table */}
            <Card>
                <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-base">Detalle por paquete</CardTitle>
                        <div className="flex items-center gap-3">
                            <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
                                <Checkbox
                                    checked={filterIncomplete}
                                    onCheckedChange={setFilterIncomplete}
                                    data-testid="filter-incomplete-checkbox"
                                />
                                Solo incompletos
                            </label>
                            <Button variant="outline" size="sm" onClick={onEvaluate} className="h-7 text-xs" data-testid="re-evaluate-btn">
                                <RefreshCw className="w-3 h-3 mr-1" /> Reglas
                            </Button>
                            <Button size="sm" onClick={handleEvaluateAll} disabled={evaluatingAll} className="h-7 text-xs" data-testid="re-evaluate-ai-btn">
                                {evaluatingAll ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Search className="w-3 h-3 mr-1" />}
                                Evaluar IA
                            </Button>
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    <div className="max-h-[500px] overflow-y-auto">
                        <table className="data-table w-full text-sm">
                            <thead>
                                <tr>
                                    <th>Guía</th>
                                    <th>Tipo</th>
                                    <th>Score</th>
                                    <th>Método</th>
                                    <th>Faltante / Alertas</th>
                                    <th>Fotos</th>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {displayPackages.map((pkg) => {
                                    const guide = pkg.tracking_number || pkg.order_reference_id;
                                    const isExpanded = expandedPkg === pkg.id;
                                    const isEvaluating = evaluatingPkg === (pkg.order_reference_id || pkg.tracking_number);
                                    const photoCount = (pkg.kosmo_proof_urls || []).length;
                                    const alerts = pkg.evidence_detail?.alerts || [];
                                    const missing = pkg.evidence_detail?.missing_items || [];
                                    const aiObs = pkg.evidence_detail?.ai_observations || '';
                                    const criteria = pkg.evidence_detail?.criteria_met || {};

                                    return (
                                        <React.Fragment key={pkg.id}>
                                            <tr data-testid={`quality-row-${pkg.id}`}
                                                className={`cursor-pointer hover:bg-slate-50 ${isExpanded ? 'bg-slate-50' : ''}`}
                                                onClick={() => setExpandedPkg(isExpanded ? null : pkg.id)}>
                                                <td className="font-mono text-xs">{guide}</td>
                                                <td>
                                                    <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                                                        pkg.evidence_type === 'exitosa' ? 'bg-emerald-100 text-emerald-700' :
                                                        pkg.evidence_type === 'terceros' ? 'bg-blue-100 text-blue-700' :
                                                        pkg.evidence_type === 'fallida' ? 'bg-red-100 text-red-700' :
                                                        'bg-slate-100 text-slate-600'
                                                    }`}>
                                                        {pkg.evidence_type === 'exitosa' ? 'Exitosa' :
                                                         pkg.evidence_type === 'terceros' ? 'Terceros' :
                                                         pkg.evidence_type === 'fallida' ? 'Fallida' : '-'}
                                                    </span>
                                                </td>
                                                <td>
                                                    <span className={`font-mono font-bold ${
                                                        pkg.evidence_score === 100 ? 'text-emerald-600' :
                                                        pkg.evidence_score >= 60 ? 'text-amber-600' : 'text-red-600'
                                                    }`}>
                                                        {pkg.evidence_score}
                                                    </span>
                                                </td>
                                                <td>
                                                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                                                        pkg.evidence_method === 'ai' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'
                                                    }`}>
                                                        {pkg.evidence_method === 'ai' ? 'IA' : 'Reglas'}
                                                    </span>
                                                </td>
                                                <td className="text-xs text-slate-500 max-w-[220px]">
                                                    {missing.length > 0 ? (
                                                        <span className="text-red-600">{missing.join(', ')}</span>
                                                    ) : alerts.length > 0 ? (
                                                        <span className="text-amber-600">{alerts[0]}</span>
                                                    ) : (
                                                        <span className="text-emerald-500">Completo</span>
                                                    )}
                                                </td>
                                                <td>
                                                    {photoCount > 0 ? (
                                                        <button
                                                            className="text-blue-500 hover:text-blue-700 text-xs flex items-center gap-1"
                                                            onClick={(e) => { e.stopPropagation(); openCarousel(pkg); }}
                                                            data-testid={`quality-photos-${pkg.id}`}
                                                        >
                                                            <Camera className="w-3.5 h-3.5" /> {photoCount}
                                                        </button>
                                                    ) : (
                                                        <span className="text-slate-400 text-xs">0</span>
                                                    )}
                                                </td>
                                                <td>
                                                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                                                        <Button
                                                            variant="ghost" size="sm" className="h-6 px-1.5 text-xs"
                                                            disabled={isEvaluating}
                                                            onClick={() => handleEvaluatePackage(pkg)}
                                                            data-testid={`evaluate-pkg-${pkg.id}`}
                                                        >
                                                            {isEvaluating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                                                        </Button>
                                                        {pkg.tracking_url && (
                                                            <a href={pkg.tracking_url} target="_blank" rel="noopener noreferrer"
                                                                className="text-blue-500 hover:text-blue-700"
                                                                data-testid={`quality-kosmo-link-${pkg.id}`}>
                                                                <ExternalLink className="w-3.5 h-3.5" />
                                                            </a>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                            {/* Expanded detail row */}
                                            {isExpanded && (
                                                <tr>
                                                    <td colSpan={7} className="bg-slate-50 p-4">
                                                        <div className="space-y-3">
                                                            {/* Criteria checklist */}
                                                            {Object.keys(criteria).length > 0 && (
                                                                <div>
                                                                    <p className="text-xs font-medium text-slate-700 mb-1">Criterios evaluados:</p>
                                                                    <div className="flex flex-wrap gap-2">
                                                                        {Object.entries(criteria).map(([key, met]) => (
                                                                            <span key={key} className={`text-xs px-2 py-1 rounded flex items-center gap-1 ${
                                                                                met ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
                                                                            }`}>
                                                                                {met ? <Check className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                                                                                {key.replace(/_/g, ' ')}
                                                                            </span>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                            {/* Alerts */}
                                                            {alerts.length > 0 && (
                                                                <div>
                                                                    <p className="text-xs font-medium text-amber-700 mb-1">Alertas:</p>
                                                                    <ul className="text-xs text-amber-600 list-disc list-inside">
                                                                        {alerts.map((a, i) => <li key={i}>{a}</li>)}
                                                                    </ul>
                                                                </div>
                                                            )}
                                                            {/* AI Observations */}
                                                            {aiObs && (
                                                                <div>
                                                                    <p className="text-xs font-medium text-slate-700 mb-1">Observaciones IA:</p>
                                                                    <p className="text-xs text-slate-600 bg-white p-2 rounded border border-slate-200">{aiObs}</p>
                                                                </div>
                                                            )}
                                                            {/* Photo analysis */}
                                                            {(pkg.evidence_detail?.photos_analysis || []).length > 0 && (
                                                                <div>
                                                                    <p className="text-xs font-medium text-slate-700 mb-1">Análisis de fotos:</p>
                                                                    <div className="flex gap-2 overflow-x-auto">
                                                                        {(pkg.evidence_detail.photos_analysis).map((pa, i) => (
                                                                            <button key={i}
                                                                                className="shrink-0 bg-white border border-slate-200 rounded p-2 text-left hover:border-blue-300 transition w-36"
                                                                                onClick={() => openCarousel(pkg, i)}
                                                                            >
                                                                                <p className="text-xs font-medium text-slate-700 capitalize">{(pa.photo_type || 'foto').replace('_', ' ')}</p>
                                                                                <p className={`text-xs ${
                                                                                    pa.quality === 'buena' ? 'text-emerald-600' :
                                                                                    pa.quality === 'aceptable' ? 'text-amber-600' : 'text-red-600'
                                                                                }`}>{pa.quality || '-'}</p>
                                                                                {pa.description && <p className="text-xs text-slate-400 truncate mt-0.5">{pa.description}</p>}
                                                                            </button>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                            {/* Missing items */}
                                                            {missing.length > 0 && (
                                                                <div>
                                                                    <p className="text-xs font-medium text-red-700 mb-1">Faltantes:</p>
                                                                    <ul className="text-xs text-red-600 list-disc list-inside">
                                                                        {missing.map((m, i) => <li key={i}>{m}</li>)}
                                                                    </ul>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            {/* Evidence Carousel */}
            <EvidenceCarousel
                open={carouselOpen}
                onClose={() => setCarouselOpen(false)}
                images={carouselImages}
                initialIndex={carouselIndex}
                packageInfo={carouselPkgInfo}
            />
        </div>
    );
};

const JourneyDetail = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const { canEdit, isCoordinator } = useAuth();

    const [journey, setJourney] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('inicio');

    // Evidence Carousel state
    const [mainCarouselOpen, setMainCarouselOpen] = useState(false);
    const [mainCarouselImages, setMainCarouselImages] = useState([]);
    const [mainCarouselIndex, setMainCarouselIndex] = useState(0);
    const [mainCarouselPkgInfo, setMainCarouselPkgInfo] = useState(null);

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
    });
    const [startChecklist, setStartChecklist] = useState({
        whatsapp: false,
        odometer_photo: false,
        zone_confirmed: false,
        packages_scanned: false,
        retry_registered: false,
        cedis_arrival: false,
        cedis_pass: false,
        cosmo_route: false,
        cedis_screenshot: false,
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
    });
    const [incidentSubmitting, setIncidentSubmitting] = useState(false);
    const [showPackagesList, setShowPackagesList] = useState(false);

    useEffect(() => {
        fetchJourney();
        fetchImages();
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

            // Set active tab based on status
            if (res.data.status === 'scheduled') {
                setActiveTab('inicio');
            } else if (res.data.status === 'in_progress') {
                setActiveTab('incidencias');
            } else {
                setActiveTab('fin');
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
        const optionalKeys = ['odometer_photo', 'cedis_screenshot'];
        const requiredChecks = Object.entries(startChecklist)
            .filter(([key]) => !optionalKeys.includes(key))
            .every(([, v]) => v);
        if (!requiredChecks) {
            toast.error('Completa todos los items obligatorios del checklist');
            return;
        }

        setStartSubmitting(true);
        try {
            await startJourney(id, {
                ...startForm,
                checklist_completed: true,
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
            });
        }
        setShowIncidentModal(true);
    };

    const handleSaveIncident = async () => {
        if (!incidentForm.incident_type || !incidentForm.description || !incidentForm.severity) {
            toast.error('Completa los campos requeridos');
            return;
        }

        setIncidentSubmitting(true);
        try {
            if (editingIncident) {
                await updateIncident(editingIncident.id, incidentForm);
                toast.success('Incidencia actualizada');
            } else {
                await createIncident({
                    ...incidentForm,
                    journey_id: id,
                });
                toast.success('Incidencia registrada');
            }
            setShowIncidentModal(false);
            fetchJourney();
        } catch (error) {
            toast.error('Error al guardar incidencia');
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
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link to="/journeys">
                        <Button variant="ghost" size="icon" data-testid="back-btn">
                            <ArrowLeft className="w-5 h-5" />
                        </Button>
                    </Link>
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                                Ruta {formatDate(journey.date)}
                            </h1>
                            <span className={`status-badge ${getStatusColor(journey.status)}`}>
                                {getStatusLabel(journey.status)}
                            </span>
                            {journey.cosmo_route_id && (
                                <span className="text-xs text-slate-400 font-mono ml-2" data-testid="cosmo-route-id">
                                    {journey.cosmo_route_id}
                                </span>
                            )}
                        </div>
                        <p className="text-slate-500 text-sm">
                            {journey.driver_name && (
                                <span className="font-medium text-slate-700">{journey.driver_name} • </span>
                            )}
                            {journey.provider_name} • {journey.client_name}
                            {journey.route_type === 'Foránea' && journey.city && (
                                <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-violet-100 text-violet-700 rounded border border-violet-200">
                                    Foránea — {journey.city}
                                </span>
                            )}
                            {journey.route_type === 'CDMX / Zona Metro' && (
                                <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700 rounded border border-blue-200">
                                    CDMX
                                </span>
                            )}
                        </p>
                    </div>
                </div>
            </div>

            {/* Stats cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card className="p-4">
                    <div className="flex items-center gap-3">
                        <Package className="w-8 h-8 text-slate-400" strokeWidth={1.5} />
                        <div>
                            <p className="text-xs text-slate-500 uppercase tracking-wider">Paquetes</p>
                            <p className="text-xl font-heading font-bold">
                                {journey.packages_delivered}/{journey.packages_total}
                            </p>
                        </div>
                    </div>
                </Card>
                <Card className="p-4">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 flex items-center justify-center">
                            <Progress 
                                value={deliveryRate} 
                                className="h-8 w-8 rounded-full"
                                indicatorClassName={progressColor}
                            />
                        </div>
                        <div>
                            <p className="text-xs text-slate-500 uppercase tracking-wider">Progreso</p>
                            <p className="text-xl font-heading font-bold">{deliveryRate}%</p>
                        </div>
                    </div>
                </Card>
                <Card className="p-4">
                    <div className="flex items-center gap-3">
                        <AlertTriangle className={`w-8 h-8 ${openIncidents.length > 0 ? 'text-amber-500' : 'text-slate-400'}`} strokeWidth={1.5} />
                        <div>
                            <p className="text-xs text-slate-500 uppercase tracking-wider">Incidencias</p>
                            <p className="text-xl font-heading font-bold">{openIncidents.length} abiertas</p>
                        </div>
                    </div>
                </Card>
                <Card className="p-4">
                    <div className="flex items-center gap-3">
                        <Users className="w-8 h-8 text-slate-400" strokeWidth={1.5} />
                        <div>
                            <p className="text-xs text-slate-500 uppercase tracking-wider">Visitas</p>
                            <p className="text-xl font-heading font-bold">
                                {(journey.packages?.filter(p => p.status === 'delivered' || p.status === 'failed' || p.status === 'returned').length) || 0}
                            </p>
                            <p className="text-xs text-slate-400">intentos registrados</p>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Packages Overview with Kosmo Sync Indicators */}
            {journey.packages && journey.packages.length > 0 && (
                <Card>
                    <CardHeader className="pb-2">
                        <div className="flex items-center justify-between">
                            <CardTitle className="font-heading text-base flex items-center gap-2">
                                <Package className="w-4 h-4" />
                                Paquetes ({journey.packages.length})
                            </CardTitle>
                            <button
                                onClick={() => setShowPackagesList(!showPackagesList)}
                                className="text-xs text-slate-500 hover:text-slate-700 underline"
                                data-testid="toggle-packages-list"
                            >
                                {showPackagesList ? 'Ocultar' : 'Ver todos'}
                            </button>
                        </div>
                    </CardHeader>
                    {showPackagesList && (
                        <CardContent className="p-0">
                            <div className="max-h-96 overflow-y-auto">
                                <table className="data-table w-full text-sm">
                                    <thead>
                                        <tr>
                                            <th>No. Guía</th>
                                            <th>Destinatario</th>
                                            <th>Estado</th>
                                            <th>Soporte</th>
                                            <th>Evidencias</th>
                                            <th>Intentos</th>
                                            <th>Revisado</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {[...(journey.packages || [])].sort((a, b) => {
                                            // "returned" packages go to the end
                                            if (a.status === 'returned' && b.status !== 'returned') return 1;
                                            if (a.status !== 'returned' && b.status === 'returned') return -1;
                                            return 0;
                                        }).map((pkg) => (
                                            <tr key={pkg.id} data-testid={`pkg-row-${pkg.id}`}>
                                                <td className="font-mono text-xs">
                                                    {pkg.tracking_url ? (
                                                        <a href={pkg.tracking_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                                                            {pkg.tracking_number || pkg.order_reference_id}
                                                        </a>
                                                    ) : (
                                                        pkg.tracking_number || pkg.order_reference_id
                                                    )}
                                                </td>
                                                <td className="truncate max-w-[120px]">{pkg.recipient_name}</td>
                                                <td>
                                                    <div className="flex items-center gap-1.5">
                                                        <span className={`status-badge ${
                                                            pkg.status === 'returned' ? 'bg-slate-600 text-white' : getStatusColor(pkg.status)
                                                        }`}>
                                                            {getStatusLabel(pkg.status)}
                                                        </span>
                                                        {pkg.status === 'delivered' && pkg.kosmo_finished_at && (
                                                            <span className="text-xs text-slate-400 font-mono">
                                                                {formatMsTimestamp(pkg.kosmo_finished_at)}
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td>
                                                    {pkg.evidence_score != null ? (
                                                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                                                            pkg.evidence_score === 100 ? 'bg-emerald-100 text-emerald-700' :
                                                            pkg.evidence_score >= 60 ? 'bg-amber-100 text-amber-700' :
                                                            'bg-red-100 text-red-700'
                                                        }`} data-testid={`evidence-badge-${pkg.id}`}>
                                                            {pkg.evidence_score === 100 ? 'Completo' :
                                                             pkg.evidence_score >= 60 ? 'Parcial' : 'Incompleto'}
                                                        </span>
                                                    ) : (
                                                        <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded">Pendiente</span>
                                                    )}
                                                </td>
                                                <td>
                                                    <div className="flex items-center gap-1.5">
                                                        {pkg.kosmo_proof_count > 0 && (
                                                            pkg.kosmo_proof_urls?.length > 0 ? (
                                                                <button
                                                                    className="inline-flex items-center gap-0.5 text-blue-500 hover:text-blue-700 cursor-pointer"
                                                                    onClick={() => openMainCarousel(pkg)}
                                                                    data-testid={`kosmo-proof-carousel-${pkg.id}`}
                                                                    title="Ver evidencias"
                                                                >
                                                                    <Camera className="w-3.5 h-3.5" />
                                                                    <span className="text-xs font-mono">{pkg.kosmo_proof_urls.length}</span>
                                                                </button>
                                                            ) : pkg.tracking_url ? (
                                                                <a
                                                                    href={pkg.tracking_url}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="inline-flex items-center gap-0.5 text-blue-500 hover:text-blue-700 cursor-pointer"
                                                                    title="Ver evidencias en Kosmo"
                                                                    data-testid={`kosmo-proof-${pkg.id}`}
                                                                >
                                                                    <Camera className="w-3.5 h-3.5" />
                                                                    <span className="text-xs font-mono">{pkg.kosmo_proof_count}</span>
                                                                </a>
                                                            ) : (
                                                                <span className="inline-flex items-center gap-0.5 text-emerald-500">
                                                                    <Camera className="w-3.5 h-3.5" />
                                                                    <span className="text-xs font-mono">{pkg.kosmo_proof_count}</span>
                                                                </span>
                                                            )
                                                        )}
                                                        {pkg.kosmo_driver_note && (
                                                            <span
                                                                className="text-amber-500 cursor-help"
                                                                title={pkg.kosmo_driver_note}
                                                                data-testid={`kosmo-note-${pkg.id}`}
                                                            >
                                                                <MessageSquare className="w-3.5 h-3.5" />
                                                            </span>
                                                        )}
                                                        {pkg.evidence_detail?.missing_items?.length > 0 && (
                                                            <span
                                                                className="text-red-400 cursor-help"
                                                                title={`Falta: ${pkg.evidence_detail.missing_items.join(', ')}`}
                                                                data-testid={`missing-evidence-${pkg.id}`}
                                                            >
                                                                <AlertTriangle className="w-3.5 h-3.5" />
                                                            </span>
                                                        )}
                                                        {pkg.kosmo_scraped_at && (
                                                            <span
                                                                className="text-slate-400 cursor-help"
                                                                title={`Sincronizado ${getKosmoTimeSince(pkg.kosmo_scraped_at)}`}
                                                                data-testid={`kosmo-sync-icon-${pkg.id}`}
                                                            >
                                                                <Clock className="w-3 h-3" />
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="text-center">
                                                    {(pkg.delivery_attempt || 1) > 1 ? (
                                                        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-100 text-amber-700 text-xs font-bold" title={`Intento ${pkg.delivery_attempt}`}>
                                                            {pkg.delivery_attempt}
                                                        </span>
                                                    ) : (
                                                        <span className="text-slate-300 text-xs">1</span>
                                                    )}
                                                </td>
                                                <td>
                                                    {pkg.reviewed_by ? (
                                                        <span
                                                            className="text-emerald-500 cursor-help"
                                                            title={`Revisado por ${pkg.reviewed_by} a las ${formatTime(pkg.reviewed_at)}`}
                                                            data-testid={`reviewed-${pkg.id}`}
                                                        >
                                                            <CheckCircle2 className="w-4 h-4" />
                                                        </span>
                                                    ) : (
                                                        <button
                                                            onClick={() => handleReviewPackage(pkg.id)}
                                                            className="text-slate-300 hover:text-emerald-500 transition-colors"
                                                            title="Marcar como revisado"
                                                            data-testid={`review-btn-${pkg.id}`}
                                                        >
                                                            <Circle className="w-4 h-4" />
                                                        </button>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>

                            {/* Kosmo Evidence Panel for delivered packages */}
                            {journey.packages.some(p => p.status === 'delivered' && p.tracking_url && (p.kosmo_proof_count > 0 || p.kosmo_driver_note)) && (
                                <div className="border-t border-slate-200 p-3 bg-slate-50">
                                    <p className="text-xs font-medium text-slate-600 uppercase mb-2">Evidencias de Kosmo</p>
                                    <div className="space-y-1.5">
                                        {journey.packages
                                            .filter(p => p.status === 'delivered' && p.tracking_url && (p.kosmo_proof_count > 0 || p.kosmo_driver_note))
                                            .slice(0, 10)
                                            .map((pkg) => (
                                                <div key={pkg.id} className="flex items-center justify-between text-xs" data-testid={`kosmo-evidence-${pkg.id}`}>
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        <span className="font-mono text-slate-700 shrink-0">{pkg.tracking_number || pkg.order_reference_id}</span>
                                                        {pkg.kosmo_driver_note && (
                                                            <span className="text-slate-400 italic truncate max-w-[200px]">"{pkg.kosmo_driver_note}"</span>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2 shrink-0">
                                                        {pkg.kosmo_finished_at && (
                                                            <span className="text-slate-400 font-mono">{formatMsTimestamp(pkg.kosmo_finished_at)}</span>
                                                        )}
                                                        {pkg.kosmo_proof_count > 0 && (
                                                            <span className="text-slate-500">{pkg.kosmo_proof_count} fotos</span>
                                                        )}
                                                        <a
                                                            href={pkg.tracking_url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-blue-500 hover:text-blue-700"
                                                            title="Abrir en Kosmo"
                                                        >
                                                            <ExternalLink className="w-3.5 h-3.5" />
                                                        </a>
                                                    </div>
                                                </div>
                                            ))
                                        }
                                    </div>
                                </div>
                            )}
                        </CardContent>
                    )}
                </Card>
            )}

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="inicio" data-testid="tab-inicio">
                        <Play className="w-4 h-4 mr-2" />
                        Inicio
                    </TabsTrigger>
                    <TabsTrigger value="incidencias" data-testid="tab-incidencias">
                        <AlertTriangle className="w-4 h-4 mr-2" />
                        Incidencias ({journey.incidents?.length || 0})
                    </TabsTrigger>
                    <TabsTrigger value="fin" data-testid="tab-fin">
                        <Square className="w-4 h-4 mr-2" />
                        Fin
                    </TabsTrigger>
                    <TabsTrigger value="calidad" data-testid="tab-calidad">
                        <CheckCircle2 className="w-4 h-4 mr-2" />
                        Calidad
                    </TabsTrigger>
                </TabsList>

                {/* Tab: Inicio de Ruta */}
                <TabsContent value="inicio" className="space-y-6">
                    {journey.status === 'scheduled' && canEdit() ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="font-heading">Iniciar ruta</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    <div className="space-y-2">
                                        <Label>Hora de salida</Label>
                                        <Input
                                            type="datetime-local"
                                            value={startForm.departure_time}
                                            onChange={(e) => setStartForm({ ...startForm, departure_time: e.target.value })}
                                            data-testid="departure-time-input"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Odómetro inicial (km)</Label>
                                        <Input
                                            type="number"
                                            value={startForm.odometer_start}
                                            onChange={(e) => setStartForm({ ...startForm, odometer_start: e.target.value })}
                                            placeholder="45230"
                                            data-testid="odometer-start-input"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Nivel de combustible</Label>
                                        <Select
                                            value={startForm.fuel_level}
                                            onValueChange={(v) => setStartForm({ ...startForm, fuel_level: v })}
                                        >
                                            <SelectTrigger data-testid="fuel-level-select">
                                                <SelectValue placeholder="Seleccionar" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {FUEL_LEVELS.map((level) => (
                                                    <SelectItem key={level} value={level}>{level}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Condición del vehículo</Label>
                                        <Select
                                            value={startForm.vehicle_condition}
                                            onValueChange={(v) => setStartForm({ ...startForm, vehicle_condition: v })}
                                        >
                                            <SelectTrigger data-testid="vehicle-condition-select">
                                                <SelectValue placeholder="Seleccionar" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {VEHICLE_CONDITIONS.map((cond) => (
                                                    <SelectItem key={cond} value={cond}>{cond}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    {startForm.vehicle_condition === 'Con observación' && (
                                        <div className="space-y-2 md:col-span-2">
                                            <Label>Observaciones del vehículo</Label>
                                            <Input
                                                value={startForm.vehicle_notes}
                                                onChange={(e) => setStartForm({ ...startForm, vehicle_notes: e.target.value })}
                                                placeholder="Describe las observaciones"
                                                data-testid="vehicle-notes-input"
                                            />
                                        </div>
                                    )}
                                    <div className="space-y-2">
                                        <Label>Paquetes cargados</Label>
                                        <Input
                                            type="number"
                                            value={startForm.packages_loaded}
                                            onChange={(e) => setStartForm({ ...startForm, packages_loaded: parseInt(e.target.value) })}
                                            data-testid="packages-loaded-input"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Hora de llegada a CEDIS</Label>
                                        <Input
                                            type="time"
                                            value={startForm.arrival_time_cedis}
                                            onChange={(e) => setStartForm({ ...startForm, arrival_time_cedis: e.target.value })}
                                            data-testid="arrival-time-cedis-input"
                                        />
                                    </div>
                                </div>

                                {/* Backup driver fields */}
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div className="space-y-2">
                                        <Label>Mensajero de respaldo (opcional)</Label>
                                        <Input
                                            value={startForm.backup_driver_name}
                                            onChange={(e) => setStartForm({ ...startForm, backup_driver_name: e.target.value })}
                                            placeholder="Nombre del mensajero de respaldo"
                                            data-testid="backup-driver-name-input"
                                        />
                                    </div>
                                    {startForm.backup_driver_name && (
                                        <>
                                            <div className="space-y-2">
                                                <Label>Hora de solicitud del backup</Label>
                                                <Input
                                                    type="time"
                                                    value={startForm.backup_request_time}
                                                    onChange={(e) => setStartForm({ ...startForm, backup_request_time: e.target.value })}
                                                    data-testid="backup-request-time-input"
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <Label>Hora de incorporación del backup</Label>
                                                <Input
                                                    type="time"
                                                    value={startForm.backup_arrival_time}
                                                    onChange={(e) => setStartForm({ ...startForm, backup_arrival_time: e.target.value })}
                                                    data-testid="backup-arrival-time-input"
                                                />
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Route Type Selection */}
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    <div className="space-y-2">
                                        <Label>Tipo de ruta</Label>
                                        <Select value={startForm.route_type} onValueChange={(v) => setStartForm({ ...startForm, route_type: v })}>
                                            <SelectTrigger data-testid="select-route-type">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="CDMX / Zona Metro">CDMX / Zona Metro</SelectItem>
                                                <SelectItem value="Foránea">Foránea</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    {startForm.route_type === 'Foránea' && (
                                        <>
                                            <div className="space-y-2">
                                                <Label>Ciudad</Label>
                                                <Input
                                                    value={startForm.city}
                                                    onChange={(e) => setStartForm({ ...startForm, city: e.target.value })}
                                                    placeholder="Ej: Pachuca, Guadalajara"
                                                    data-testid="route-city-input"
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <Label>Máx. paquetes</Label>
                                                <Input
                                                    type="number"
                                                    value={startForm.max_packages}
                                                    onChange={(e) => setStartForm({ ...startForm, max_packages: parseInt(e.target.value) || 50 })}
                                                    data-testid="route-max-packages-input"
                                                />
                                            </div>
                                        </>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <Label>Notas adicionales</Label>
                                    <Textarea
                                        value={startForm.notes}
                                        onChange={(e) => setStartForm({ ...startForm, notes: e.target.value })}
                                        placeholder="Observaciones generales..."
                                        rows={3}
                                        data-testid="start-notes-textarea"
                                    />
                                </div>

                                {/* Image upload for start */}
                                <div className="space-y-1">
                                    <Label>Evidencia fotográfica <span className="text-slate-400 font-normal">(opcional)</span></Label>
                                    <ImageUploader
                                        images={startImages}
                                        onUpload={(files) => handleUploadImages(files, 'start')}
                                        onDelete={handleDeleteImage}
                                        uploading={uploadingImages}
                                        label="Agregar fotos de inicio"
                                    />
                                    <p className="text-xs text-slate-400">Solo si genera valor adicional — las evidencias en WhatsApp y Cosmo son el respaldo principal.</p>
                                </div>

                                {/* Checklist */}
                                <div className="border border-slate-200 rounded-sm p-4 space-y-3">
                                    <p className="font-medium text-slate-900 mb-3">Checklist de salida</p>
                                    {[
                                        { key: 'cedis_arrival', label: 'Llegada a CEDIS registrada con hora' },
                                        { key: 'cedis_pass', label: 'Confirmación de pase a CEDIS' },
                                        { key: 'cosmo_route', label: 'Confirmación de ruta en Cosmo / plataforma' },
                                        { key: 'packages_scanned', label: 'Paquetes escaneados y asignados en la plataforma del cliente' },
                                        { key: 'retry_registered', label: 'Paquetes de reintento del día anterior registrados' },
                                        { key: 'whatsapp', label: 'Driver / mensajero notificó salida del almacén' },
                                        { key: 'odometer_photo', label: 'Evidencia fotográfica del odómetro tomada', optional: true },
                                        { key: 'cedis_screenshot', label: 'Pantallazo CEDIS → 1ª entrega tomado', optional: true },
                                        { key: 'zone_confirmed', label: 'Zona de entrega confirmada' },
                                    ].map((item) => (
                                        <div key={item.key} className="flex items-center space-x-3">
                                            <Checkbox
                                                id={item.key}
                                                checked={startChecklist[item.key]}
                                                onCheckedChange={(checked) => 
                                                    setStartChecklist({ ...startChecklist, [item.key]: checked })
                                                }
                                                data-testid={`checklist-${item.key}`}
                                            />
                                            <label htmlFor={item.key} className="text-sm text-slate-700 cursor-pointer">
                                                {item.label}
                                                {item.optional && <span className="text-slate-400 ml-1">(opcional)</span>}
                                            </label>
                                        </div>
                                    ))}
                                </div>

                                <div className="flex justify-end">
                                    <Button
                                        onClick={handleStartJourney}
                                        disabled={startSubmitting}
                                        className="bg-status-success hover:bg-status-success/90"
                                        data-testid="start-journey-btn"
                                    >
                                        {startSubmitting ? (
                                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        ) : (
                                            <Play className="w-4 h-4 mr-2" />
                                        )}
                                        Iniciar ruta
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ) : journey.start_data ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="font-heading flex items-center gap-2">
                                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                                    Ruta iniciada
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Hora de salida</p>
                                        <p className="font-mono font-medium">{formatDateTime(journey.start_data.departure_time)}</p>
                                    </div>
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Odómetro inicial</p>
                                        <p className="font-mono font-medium">{journey.start_data.odometer_start?.toLocaleString()} km</p>
                                    </div>
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Combustible</p>
                                        <p className="font-medium">{journey.start_data.fuel_level}</p>
                                    </div>
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Paquetes cargados</p>
                                        <p className="font-mono font-medium">{journey.start_data.packages_loaded}</p>
                                    </div>
                                </div>
                                {journey.start_data.notes && (
                                    <div className="mt-4 p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase mb-1">Notas</p>
                                        <p className="text-sm">{journey.start_data.notes}</p>
                                    </div>
                                )}
                                {/* Show start images */}
                                {startImages.length > 0 && (
                                    <div className="mt-4">
                                        <p className="text-xs text-slate-500 uppercase mb-2">Evidencia fotográfica</p>
                                        <ImageUploader
                                            images={startImages}
                                            onDelete={canEdit() ? handleDeleteImage : null}
                                            disabled={!canEdit()}
                                        />
                                    </div>
                                )}
                                {/* Allow adding more images if in progress */}
                                {journey.status === 'in_progress' && canEdit() && (
                                    <div className="mt-4">
                                        <ImageUploader
                                            images={[]}
                                            onUpload={(files) => handleUploadImages(files, 'start')}
                                            uploading={uploadingImages}
                                            label="Agregar más fotos"
                                        />
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardContent className="py-12 text-center">
                                <Clock className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                <p className="text-slate-500">Ruta pendiente de inicio</p>
                            </CardContent>
                        </Card>
                    )}
                </TabsContent>

                {/* Tab: Incidencias */}
                <TabsContent value="incidencias" className="space-y-6">
                    <div className="flex items-center justify-between">
                        <h3 className="font-heading text-lg font-semibold">Incidencias registradas</h3>
                        <div className="flex gap-2">
                            {journey.incidents?.length > 0 && (
                                <Button variant="outline" onClick={handleExportIncidents} data-testid="export-incidents-btn">
                                    <Download className="w-4 h-4 mr-2" />
                                    Exportar CSV
                                </Button>
                            )}
                            {canEdit() && openIncidents.length > 0 && (
                                <Button 
                                    variant="outline" 
                                    onClick={() => setShowResolveAllConfirm(true)}
                                    disabled={resolvingAll}
                                    data-testid="resolve-all-incidents-btn"
                                >
                                    {resolvingAll ? (
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    ) : (
                                        <CheckCheck className="w-4 h-4 mr-2" />
                                    )}
                                    Resolver todas
                                </Button>
                            )}
                            {canEdit() && journey.status !== 'closed' && (
                                <Button onClick={() => handleOpenIncidentModal()} data-testid="add-incident-btn">
                                    <Plus className="w-4 h-4 mr-2" />
                                    Nueva incidencia
                                </Button>
                            )}
                        </div>
                    </div>

                    {journey.incidents?.length === 0 ? (
                        <Card>
                            <CardContent className="py-12 text-center">
                                <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
                                <p className="text-slate-600 font-medium">Sin incidencias</p>
                                <p className="text-slate-500 text-sm">No se han registrado incidencias en esta ruta</p>
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardContent className="p-0">
                                <table className="data-table w-full">
                                    <thead>
                                        <tr>
                                            <th>Hora</th>
                                            <th>Tipo</th>
                                            <th>Severidad</th>
                                            <th>Imputabilidad</th>
                                            <th>Descripción</th>
                                            <th>Fotos</th>
                                            <th>Estado</th>
                                            <th>Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {journey.incidents.map((incident) => (
                                            <tr key={incident.id} data-testid={`incident-row-${incident.id}`}>
                                                <td className="font-mono text-sm">
                                                    {formatTime(incident.occurred_at)}
                                                </td>
                                                <td>{incident.incident_type}</td>
                                                <td>
                                                    <span className={`status-badge ${getSeverityColor(incident.severity)}`}>
                                                        {incident.severity}
                                                    </span>
                                                </td>
                                                <td>
                                                    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${getImputabilityColor(incident.imputability)}`} data-testid={`imputability-badge-${incident.id}`}>
                                                        {incident.imputability || 'Por definir'}
                                                    </span>
                                                </td>
                                                <td className="max-w-xs truncate">{incident.description}</td>
                                                <td>
                                                    {incidentImages[incident.id]?.length > 0 ? (
                                                        <span className="flex items-center gap-1 text-slate-600">
                                                            <Camera className="w-4 h-4" />
                                                            {incidentImages[incident.id].length}
                                                        </span>
                                                    ) : (
                                                        <span className="text-slate-400">-</span>
                                                    )}
                                                </td>
                                                <td>
                                                    <span className={`status-badge ${getStatusColor(incident.status)}`}>
                                                        {getStatusLabel(incident.status)}
                                                    </span>
                                                </td>
                                                <td>
                                                    <div className="flex items-center gap-1">
                                                        {canEdit() && incident.status === 'open' && (
                                                            <>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="icon"
                                                                    onClick={() => handleOpenIncidentModal(incident)}
                                                                    data-testid={`edit-incident-${incident.id}`}
                                                                >
                                                                    <Pencil className="w-4 h-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="icon"
                                                                    onClick={() => handleResolveIncident(incident)}
                                                                    className="text-emerald-600"
                                                                    data-testid={`resolve-incident-${incident.id}`}
                                                                >
                                                                    <CheckCircle2 className="w-4 h-4" />
                                                                </Button>
                                                            </>
                                                        )}
                                                        {(isCoordinator() || canEdit()) && (
                                                            <Button
                                                                variant="ghost"
                                                                size="icon"
                                                                onClick={() => handleDeleteIncident(incident.id)}
                                                                className="text-red-600"
                                                                data-testid={`delete-incident-${incident.id}`}
                                                            >
                                                                <Trash2 className="w-4 h-4" />
                                                            </Button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </CardContent>
                        </Card>
                    )}
                </TabsContent>

                {/* Tab: Fin de Ruta */}
                <TabsContent value="fin" className="space-y-6">
                    {journey.status === 'in_progress' && canEdit() ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="font-heading">Cerrar ruta</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Hora de cierre</Label>
                                        <Input
                                            type="datetime-local"
                                            value={closeForm.closed_at}
                                            onChange={(e) => setCloseForm({ ...closeForm, closed_at: e.target.value })}
                                            data-testid="closed-at-input"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Odómetro final (km)</Label>
                                        <Input
                                            type="number"
                                            value={closeForm.odometer_end}
                                            onChange={(e) => setCloseForm({ ...closeForm, odometer_end: e.target.value })}
                                            placeholder="45380"
                                            data-testid="odometer-end-input"
                                        />
                                    </div>
                                </div>

                                {/* Auto-calculated metrics (read-only) */}
                                <div className="grid grid-cols-3 gap-4">
                                    <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-sm text-center">
                                        <p className="text-xs text-emerald-600 uppercase font-medium">Entregados</p>
                                        <p className="font-mono font-bold text-2xl text-emerald-700" data-testid="auto-delivered-count">
                                            {metrics.delivered}
                                        </p>
                                        <p className="text-xs text-emerald-500 mt-1">calculado automáticamente</p>
                                    </div>
                                    <div className="p-4 bg-red-50 border border-red-200 rounded-sm text-center">
                                        <p className="text-xs text-red-600 uppercase font-medium">Fallidos</p>
                                        <p className="font-mono font-bold text-2xl text-red-700" data-testid="auto-failed-count">
                                            {metrics.failed}
                                        </p>
                                        <p className="text-xs text-red-500 mt-1">calculado automáticamente</p>
                                    </div>
                                    <div className="p-4 bg-slate-100 border border-slate-300 rounded-sm text-center">
                                        <p className="text-xs text-slate-600 uppercase font-medium">Devoluciones</p>
                                        <p className="font-mono font-bold text-2xl text-slate-700" data-testid="auto-return-count">
                                            {metrics.toReturn}
                                        </p>
                                        <p className="text-xs text-slate-500 mt-1">seleccionados abajo</p>
                                    </div>
                                </div>

                                {/* Calculated operational metrics */}
                                <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 rounded-sm">
                                    <div>
                                        <p className="text-xs text-slate-500 uppercase">Km recorridos</p>
                                        <p className="font-mono font-bold text-lg">{metrics.kmTraveled.toLocaleString()}</p>
                                    </div>
                                    <div>
                                        <p className="text-xs text-slate-500 uppercase">Tasa de entrega</p>
                                        <p className={`font-mono font-bold text-lg ${
                                            parseFloat(metrics.deliveryRate) >= 70 ? 'text-emerald-600' :
                                            parseFloat(metrics.deliveryRate) >= 40 ? 'text-amber-600' : 'text-red-600'
                                        }`}>
                                            {metrics.deliveryRate}%
                                        </p>
                                    </div>
                                </div>

                                {/* Imputability summary in close form */}
                                {journey.incidents?.length > 0 && (
                                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase mb-2">Resumen de imputabilidad de incidencias</p>
                                        <div className="flex gap-4 text-sm">
                                            <span className="text-red-700 font-medium">
                                                Imputables a ME: {journey.incidents.filter(i => i.imputability === 'ME / Mensajero').length}
                                            </span>
                                            <span className="text-amber-700 font-medium">
                                                Imputables al cliente: {journey.incidents.filter(i => i.imputability === 'Cliente (destinatario)').length}
                                            </span>
                                        </div>
                                    </div>
                                )}

                                {/* Packages for return (pre-populated from Kosmo) */}
                                {returnCandidates.length > 0 && (
                                    <div className="border border-slate-200 rounded-sm">
                                        <div className="p-3 bg-slate-50 border-b border-slate-200">
                                            <div className="flex items-center justify-between mb-2">
                                                <div>
                                                    <p className="font-medium text-slate-900">Paquetes para devolución</p>
                                                    <p className="text-sm text-slate-500">Pre-seleccionados de Kosmo. Desmarca los que no aplican.</p>
                                                </div>
                                                <span className="text-sm text-slate-500">
                                                    {returnCandidates.length} candidatos
                                                </span>
                                            </div>
                                            {/* Search input */}
                                            <div className="relative">
                                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                                <Input
                                                    type="text"
                                                    placeholder="Buscar por No. Guía o destinatario..."
                                                    value={packageSearchTerm}
                                                    onChange={(e) => setPackageSearchTerm(e.target.value)}
                                                    className="pl-10 h-9"
                                                    data-testid="package-search-input"
                                                />
                                                {packageSearchTerm && (
                                                    <button
                                                        type="button"
                                                        onClick={() => setPackageSearchTerm('')}
                                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                                    >
                                                        <XCircle className="w-4 h-4" />
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                        <div className="max-h-64 overflow-y-auto">
                                            <table className="data-table w-full text-sm">
                                                <thead>
                                                    <tr>
                                                        <th className="w-10"></th>
                                                        <th>No. Guía</th>
                                                        <th>Destinatario</th>
                                                        <th>Motivo</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {returnCandidates
                                                        .filter(pkg => {
                                                            if (!packageSearchTerm) return true;
                                                            const search = packageSearchTerm.toLowerCase();
                                                            return (
                                                                (pkg.tracking_number || '').toLowerCase().includes(search) ||
                                                                (pkg.order_reference_id || '').toLowerCase().includes(search) ||
                                                                (pkg.recipient_name || '').toLowerCase().includes(search)
                                                            );
                                                        })
                                                        .map((pkg) => {
                                                            const isFailed = failedPackages.find(f => f.id === pkg.id);
                                                            return (
                                                                <tr key={pkg.id} className={isFailed ? 'bg-red-50' : ''}>
                                                                    <td>
                                                                        <Checkbox
                                                                            checked={!!isFailed}
                                                                            onCheckedChange={() => toggleFailedPackage(pkg)}
                                                                        />
                                                                    </td>
                                                                    <td className="font-mono">{pkg.tracking_number || pkg.order_reference_id}</td>
                                                                    <td>{pkg.recipient_name}</td>
                                                                    <td>
                                                                        {isFailed && (
                                                                            <Select
                                                                                value={isFailed.failure_reason}
                                                                                onValueChange={(v) => toggleFailedPackage(pkg, v)}
                                                                            >
                                                                                <SelectTrigger className="h-8">
                                                                                    <SelectValue />
                                                                                </SelectTrigger>
                                                                                <SelectContent>
                                                                                    {FAILURE_REASONS.map((r) => (
                                                                                        <SelectItem key={r} value={r}>{r}</SelectItem>
                                                                                    ))}
                                                                                </SelectContent>
                                                                            </Select>
                                                                        )}
                                                                    </td>
                                                                </tr>
                                                            );
                                                        })}
                                                </tbody>
                                            </table>
                                            {/* No results message */}
                                            {packageSearchTerm && returnCandidates.filter(pkg => {
                                                const search = packageSearchTerm.toLowerCase();
                                                return (
                                                    (pkg.tracking_number || '').toLowerCase().includes(search) ||
                                                    (pkg.order_reference_id || '').toLowerCase().includes(search) ||
                                                    (pkg.recipient_name || '').toLowerCase().includes(search)
                                                );
                                            }).length === 0 && (
                                                <div className="text-center py-6 text-slate-500">
                                                    <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                                    <p className="text-sm">No se encontraron paquetes con "{packageSearchTerm}"</p>
                                                </div>
                                            )}
                                        </div>
                                        {/* Selected count */}
                                        {failedPackages.length > 0 && (
                                            <div className="p-3 bg-slate-100 border-t border-slate-300 flex items-center justify-between">
                                                <span className="text-sm text-slate-700">
                                                    <strong>{failedPackages.length}</strong> paquete(s) Fallido(s) marcado(s) para devolución
                                                </span>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => setFailedPackages([])}
                                                    className="text-slate-600 hover:text-slate-700"
                                                >
                                                    Limpiar selección
                                                </Button>
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <Label>Notas de cierre</Label>
                                    <Textarea
                                        value={closeForm.notes}
                                        onChange={(e) => setCloseForm({ ...closeForm, notes: e.target.value })}
                                        placeholder="Observaciones finales..."
                                        rows={3}
                                        data-testid="close-notes-textarea"
                                    />
                                </div>

                                {/* Image upload for close */}
                                <div className="space-y-1">
                                    <Label>Evidencia fotográfica de cierre <span className="text-slate-400 font-normal">(opcional)</span></Label>
                                    <ImageUploader
                                        images={closeImages}
                                        onUpload={(files) => handleUploadImages(files, 'close')}
                                        onDelete={handleDeleteImage}
                                        uploading={uploadingImages}
                                        label="Agregar fotos de cierre"
                                    />
                                    <p className="text-xs text-slate-400">Solo si genera valor adicional — las evidencias en WhatsApp y Cosmo son el respaldo principal.</p>
                                </div>

                                {/* Checklist */}
                                <div className="border border-slate-200 rounded-sm p-4 space-y-3">
                                    <p className="font-medium text-slate-900 mb-3">Checklist de cierre</p>
                                    {[
                                        { key: 'cosmo_screenshot', label: 'Pantallazo de cierre de Cosmo adjuntado' },
                                        { key: 'odometer_final', label: 'Kilometraje final registrado' },
                                        { key: 'failed_list', label: 'Lista de paquetes no entregados completa' },
                                        { key: 'incidents_reviewed', label: 'Incidencias del día revisadas y cerradas' },
                                    ].map((item) => (
                                        <div key={item.key} className="flex items-center space-x-3">
                                            <Checkbox
                                                id={`close-${item.key}`}
                                                checked={closeChecklist[item.key]}
                                                onCheckedChange={(checked) => 
                                                    setCloseChecklist({ ...closeChecklist, [item.key]: checked })
                                                }
                                                data-testid={`close-checklist-${item.key}`}
                                            />
                                            <label htmlFor={`close-${item.key}`} className="text-sm text-slate-700 cursor-pointer">
                                                {item.label}
                                            </label>
                                        </div>
                                    ))}

                                    {/* Conditional return evidence item */}
                                    {failedPackages.length > 0 && (
                                        <div className="mt-4 pt-4 border-t border-slate-200 space-y-3">
                                            <div className="flex items-center space-x-3">
                                                <Checkbox
                                                    id="close-return_evidence"
                                                    checked={closeChecklist.return_evidence}
                                                    onCheckedChange={(checked) => 
                                                        setCloseChecklist({ ...closeChecklist, return_evidence: checked })
                                                    }
                                                    data-testid="close-checklist-return_evidence"
                                                />
                                                <label htmlFor="close-return_evidence" className="text-sm text-slate-700 cursor-pointer font-medium">
                                                    Evidencia fotográfica de devolución de paquetes
                                                </label>
                                            </div>
                                            <div className="ml-7">
                                                <ImageUploader
                                                    images={returnEvidenceImages}
                                                    onUpload={(files) => handleUploadImages(files, 'return_evidence')}
                                                    onDelete={handleDeleteImage}
                                                    uploading={uploadingImages}
                                                    label="Agregar fotos de devolución"
                                                />
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="flex justify-end">
                                    <Button
                                        onClick={handlePreCloseJourney}
                                        disabled={closeSubmitting}
                                        variant="destructive"
                                        data-testid="close-journey-btn"
                                    >
                                        {closeSubmitting ? (
                                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        ) : (
                                            <Square className="w-4 h-4 mr-2" />
                                        )}
                                        Cerrar ruta
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ) : journey.close_data ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="font-heading flex items-center gap-2">
                                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                                    Ruta cerrada
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Hora de cierre</p>
                                        <p className="font-mono font-medium">{formatDateTime(journey.close_data.closed_at)}</p>
                                    </div>
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Odómetro final</p>
                                        <p className="font-mono font-medium">{journey.close_data.odometer_end?.toLocaleString()} km</p>
                                    </div>
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Km recorridos</p>
                                        <p className="font-mono font-medium">{journey.close_data.km_traveled?.toLocaleString()}</p>
                                    </div>
                                    <div className="p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase">Tasa de entrega</p>
                                        <p className={`font-mono font-bold ${
                                            journey.close_data.delivery_rate >= 70 ? 'text-emerald-600' :
                                            journey.close_data.delivery_rate >= 40 ? 'text-amber-600' : 'text-red-600'
                                        }`}>
                                            {journey.close_data.delivery_rate}%
                                        </p>
                                    </div>
                                </div>
                                <div className="grid grid-cols-3 gap-4">
                                    <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-sm text-center">
                                        <p className="text-xs text-emerald-600 uppercase">Entregados</p>
                                        <p className="font-mono font-bold text-2xl text-emerald-700">{journey.close_data.packages_delivered}</p>
                                    </div>
                                    <div className="p-3 bg-red-50 border border-red-200 rounded-sm text-center">
                                        <p className="text-xs text-red-600 uppercase">Fallidos</p>
                                        <p className="font-mono font-bold text-2xl text-red-700">{journey.close_data.packages_failed}</p>
                                    </div>
                                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-sm text-center">
                                        <p className="text-xs text-amber-600 uppercase">Devoluciones</p>
                                        <p className="font-mono font-bold text-2xl text-amber-700">{journey.close_data.packages_to_retry}</p>
                                    </div>
                                </div>
                                {/* Show close images */}
                                {closeImages.length > 0 && (
                                    <div className="mt-4">
                                        <p className="text-xs text-slate-500 uppercase mb-2">Evidencia fotográfica de cierre</p>
                                        <ImageUploader
                                            images={closeImages}
                                            disabled={true}
                                        />
                                    </div>
                                )}
                                {/* Imputability summary */}
                                {journey.incidents?.length > 0 && (
                                    <div className="mt-4 p-3 bg-slate-50 rounded-sm">
                                        <p className="text-xs text-slate-500 uppercase mb-2">Resumen de imputabilidad</p>
                                        <div className="flex gap-4 text-sm">
                                            <span className="text-red-700 font-medium">
                                                Imputables a ME: {journey.incidents.filter(i => i.imputability === 'ME / Mensajero').length}
                                            </span>
                                            <span className="text-amber-700 font-medium">
                                                Imputables al cliente: {journey.incidents.filter(i => i.imputability === 'Cliente (destinatario)').length}
                                            </span>
                                            <span className="text-slate-600">
                                                Por definir: {journey.incidents.filter(i => !i.imputability || i.imputability === 'Por definir').length}
                                            </span>
                                        </div>
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardContent className="py-12 text-center">
                                <Clock className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                <p className="text-slate-500">
                                    {journey.status === 'scheduled' 
                                        ? 'Primero debes iniciar la ruta' 
                                        : 'La ruta aún no ha sido cerrada'}
                                </p>
                            </CardContent>
                        </Card>
                    )}
                </TabsContent>

                {/* Tab: Calidad */}
                <TabsContent value="calidad" className="space-y-6" data-testid="tab-calidad-content">
                    <QualityTab journey={journey} packages={journey.packages || []} onEvaluate={async () => {
                        try {
                            await evaluateJourneyQuality(journey.id);
                            toast.success('Evaluación de calidad actualizada');
                            fetchJourney();
                        } catch (e) {
                            toast.error('Error al evaluar calidad');
                        }
                    }} onRefreshJourney={fetchJourney} />
                </TabsContent>
            </Tabs>

            {/* Incident Modal */}
            <Dialog open={showIncidentModal} onOpenChange={setShowIncidentModal}>
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
                                onValueChange={(v) => setIncidentForm({ ...incidentForm, incident_type: v })}
                            >
                                <SelectTrigger data-testid="incident-type-select">
                                    <SelectValue placeholder="Seleccionar tipo" />
                                </SelectTrigger>
                                <SelectContent>
                                    {INCIDENT_TYPES.map((t) => (
                                        <SelectItem key={t} value={t}>{t}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
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
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowIncidentModal(false)}>
                            Cancelar
                        </Button>
                        <Button onClick={handleSaveIncident} disabled={incidentSubmitting} data-testid="save-incident-btn">
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
        </div>
    );
};

export default JourneyDetail;
