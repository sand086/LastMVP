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
} from '../lib/api';
import api from '../lib/api';
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
import QualityTabV2 from '../components/QualityTabV2';
import GuiasTab from '../components/GuiasTab';
import PulseBanner from '../components/PulseBanner';
import { JourneyStartTab } from '../components/JourneyStartTab';
import { JourneyIncidentsTab } from '../components/JourneyIncidentsTab';
import { JourneyCloseTab } from '../components/JourneyCloseTab';

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
            const msg = res.data?.message || 'Evaluación IA iniciada';
            toast.success(msg);
            // Refresh after a short delay to show updated results
            setTimeout(() => {
                if (onRefreshJourney) onRefreshJourney();
            }, 3000);
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
                                                                        {alerts.map((a, i) => <li key={`alert-${i}-${a.slice(0,10)}`}>{a}</li>)}
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
                                                                            <button key={`photo-${pa.photo_type || 'foto'}-${i}`}
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
                                                                        {missing.map((m, i) => <li key={`missing-${i}-${m.slice(0,10)}`}>{m}</li>)}
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
    });
    const [incidentSubmitting, setIncidentSubmitting] = useState(false);
    const [showPackagesList, setShowPackagesList] = useState(false);

    // Sortable table hooks
    const { sortedData: sortedPackages, SortHeader: PkgSortHeader } = useSortableTable(journey?.packages || []);
    const { sortedData: sortedIncidents, SortHeader: IncSortHeader } = useSortableTable(journey?.incidents || [], 'occurred_at', 'desc');

    // Batch rescrape state
    const [batchRescraping, setBatchRescraping] = useState(false);
    const [batchRescrapeProgress, setBatchRescrapeProgress] = useState({ done: 0, total: 0, recovered: 0 });

    useEffect(() => {
        fetchJourney();
        fetchImages();
        // Fetch pulse config
        api.get('/admin/config').then(res => {
            setPulseConfig(res.data?.pulse_config || null);
        }).catch(() => {});
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
        setIncidentForm({
            occurred_at: new Date().toISOString().slice(0, 16),
            incident_type: 'Evidencia Insuficiente',
            description: `Incidencia registrada desde Guias para paquete ${pkg.tracking_number || pkg.order_reference_id || ''}`,
            severity: 'Media',
            tracking_number: pkg.tracking_number || pkg.order_reference_id || '',
            action_taken: '',
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
                if (res.data.status === 'scheduled' && !res.data.start_data) {
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
                    source: incidentForm.source || 'incidencias',
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
                            {journey.order_id && (
                                <button
                                    className="inline-flex items-center gap-1.5 text-xs font-mono text-blue-700 bg-blue-50 border border-blue-200 rounded px-2 py-0.5 ml-2 hover:bg-blue-100 transition-colors"
                                    onClick={() => { navigator.clipboard.writeText(journey.order_id); toast.success('Order ID copiado'); }}
                                    title="Copiar Order ID"
                                    data-testid="copy-order-id"
                                >
                                    {journey.order_id}
                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                                </button>
                            )}
                            {journey.cosmo_route_id && !journey.order_id && (
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
                            {journey.route_type && journey.route_type !== 'CDMX / Zona Metro' && (
                                <span className="ml-2 px-2 py-0.5 text-xs font-medium bg-violet-100 text-violet-700 rounded border border-violet-200">
                                    {journey.route_type}{journey.city ? ` — ${journey.city}` : ''}
                                </span>
                            )}
                            {(!journey.route_type || journey.route_type === 'CDMX / Zona Metro') && (
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

            {/* Pulse Banner - between KPIs and Tabs */}
            {journey.status === 'in_progress' && pulseConfig && (
                <PulseBanner journey={journey} pulseConfig={pulseConfig} />
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
                    <TabsTrigger value="guias" data-testid="tab-guias">
                        <Package className="w-4 h-4 mr-2" />
                        Guías
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
