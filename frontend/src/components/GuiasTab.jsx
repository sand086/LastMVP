import React, { useState, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
    evaluatePackageEvidence,
    evaluateAllEvidence,
    batchRescrapeJourney,
    reviewPackageWithNote,
} from '../lib/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import {
    RefreshCw,
    Search,
    Loader2,
    ChevronDown,
    ChevronRight,
    Camera,
    ExternalLink,
    Check,
    X,
    AlertTriangle,
    Circle,
    CheckCircle2,
    Eye,
} from 'lucide-react';
import { toast } from 'sonner';
import EvidenceCarousel from './EvidenceCarousel';

const SEGMENT_FILTERS = [
    { key: 'all', label: 'Todas' },
    { key: 'alert', label: 'Con alerta' },
    { key: 'no_evidence', label: 'Sin evidencia' },
    { key: 'pending_review', label: 'Pendiente revisión' },
];

const ScoreCircle = ({ score }) => {
    if (score == null) return <span className="text-xs text-slate-400">—</span>;
    const color = score >= 90 ? 'text-emerald-600 border-emerald-400' :
                  score >= 60 ? 'text-amber-600 border-amber-400' :
                  'text-red-600 border-red-400';
    return (
        <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full border-2 text-xs font-bold font-mono ${color}`}
              data-testid="score-circle">
            {score}
        </span>
    );
};

const StatusPill = ({ status }) => {
    const map = {
        delivered: { label: 'Exitosa', cls: 'bg-emerald-100 text-emerald-700' },
        failed: { label: 'Fallida', cls: 'bg-red-100 text-red-700' },
        returned: { label: 'Devuelta', cls: 'bg-slate-200 text-slate-700' },
        pending: { label: 'Pendiente', cls: 'bg-slate-100 text-slate-500' },
    };
    const { label, cls } = map[status] || map.pending;
    return <span className={`text-xs font-medium px-2 py-0.5 rounded ${cls}`}>{label}</span>;
};

const GuiasTab = ({ journey, packages, onRefreshJourney }) => {
    const { hasRole } = useAuth();
    const canReview = hasRole(['coordinator', 'developer']);
    const isReadOnly = hasRole(['agent', 'proveedor']);

    const [segment, setSegment] = useState('all');
    const [expandedId, setExpandedId] = useState(null);
    const [evaluatingPkg, setEvaluatingPkg] = useState(null);
    const [evaluatingAll, setEvaluatingAll] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [rejectingPkg, setRejectingPkg] = useState(null);
    const [rejectNote, setRejectNote] = useState('');
    const [savingReview, setSavingReview] = useState(null);

    // Carousel state
    const [carouselOpen, setCarouselOpen] = useState(false);
    const [carouselImages, setCarouselImages] = useState([]);
    const [carouselIndex, setCarouselIndex] = useState(0);
    const [carouselPkgInfo, setCarouselPkgInfo] = useState(null);

    // KPI calculations
    const kpis = useMemo(() => {
        const totalPkgs = packages.length;
        const withScore = packages.filter(p => p.ai_score != null);
        const avgScore = withScore.length > 0
            ? Math.round(withScore.reduce((sum, p) => sum + p.ai_score, 0) / withScore.length)
            : 0;
        const complete = withScore.filter(p => p.ai_score === 100).length;
        const aiEvaluated = withScore.length;
        const manualReviewed = packages.filter(p => p.manually_reviewed).length;
        return { avgScore, complete, totalScored: withScore.length, aiEvaluated, manualReviewed, totalPkgs };
    }, [packages]);

    // AI errors aggregation for alert
    const aiErrorSummary = useMemo(() => {
        const errorMap = {};
        packages.forEach(p => {
            (p.ai_errors || []).forEach(e => {
                errorMap[e] = (errorMap[e] || 0) + 1;
            });
        });
        return Object.entries(errorMap).sort((a, b) => b[1] - a[1]);
    }, [packages]);

    // Filtered and sorted packages
    const filteredPackages = useMemo(() => {
        let list = [...packages];
        if (segment === 'alert') list = list.filter(p => (p.ai_errors || []).length > 0);
        if (segment === 'no_evidence') list = list.filter(p => p.photos_count === 0);
        if (segment === 'pending_review') list = list.filter(p => !p.manually_reviewed);
        // Sort: errors first, then alphabetically by guide
        list.sort((a, b) => {
            const aErr = (a.ai_errors || []).length;
            const bErr = (b.ai_errors || []).length;
            if (bErr !== aErr) return bErr - aErr;
            const aGuide = a.order_reference_id || a.tracking_number || '';
            const bGuide = b.order_reference_id || b.tracking_number || '';
            return aGuide.localeCompare(bGuide);
        });
        return list;
    }, [packages, segment]);

    const handleEvaluatePackage = async (pkg) => {
        const guide = pkg.order_reference_id || pkg.tracking_number;
        setEvaluatingPkg(guide);
        try {
            await evaluatePackageEvidence(journey.id, guide);
            toast.success(`Evaluación IA completada para ${guide}`);
            onRefreshJourney?.();
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
            toast.success(res.data?.message || 'Evaluación IA iniciada');
            setTimeout(() => onRefreshJourney?.(), 3000);
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al evaluar con IA');
        } finally {
            setEvaluatingAll(false);
        }
    };

    const handleResync = async () => {
        setSyncing(true);
        try {
            const res = await batchRescrapeJourney(journey.id);
            toast.success(res.data?.message || 'Re-sincronización completa');
            onRefreshJourney?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al sincronizar');
        } finally {
            setSyncing(false);
        }
    };

    const handleApprove = async (pkg) => {
        setSavingReview(pkg.id);
        try {
            await reviewPackageWithNote(pkg.id, { manually_reviewed: true });
            toast.success('Guía aprobada');
            setExpandedId(null);
            onRefreshJourney?.();
        } catch (err) {
            toast.error('Error al aprobar');
        } finally {
            setSavingReview(null);
        }
    };

    const handleReject = async (pkg) => {
        if (!rejectNote.trim()) {
            toast.error('Ingresa el motivo de rechazo');
            return;
        }
        setSavingReview(pkg.id);
        try {
            await reviewPackageWithNote(pkg.id, { manually_reviewed: false, manually_reviewed_note: rejectNote });
            toast.success('Guía rechazada');
            setRejectingPkg(null);
            setRejectNote('');
            setExpandedId(null);
            onRefreshJourney?.();
        } catch (err) {
            toast.error('Error al rechazar');
        } finally {
            setSavingReview(null);
        }
    };

    const openCarousel = (pkg, startIndex = 0) => {
        const urls = pkg.kosmo_proof_urls || [];
        const photoAnalyses = pkg.evidence_detail?.photos_analysis || [];
        const imgs = urls.map((url, i) => ({ url, analysis: photoAnalyses[i] || null }));
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

    const getGuide = (pkg) => pkg.order_reference_id || pkg.tracking_number || '';

    return (
        <div className="space-y-4" data-testid="guias-tab">
            {/* Global Actions */}
            <div className="flex items-center justify-between">
                <h3 className="font-heading text-base font-semibold text-slate-800">Guías de la ruta</h3>
                {!isReadOnly && (
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={handleResync} disabled={syncing} data-testid="resync-kosmo-btn">
                            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${syncing ? 'animate-spin' : ''}`} />
                            Re-sincronizar Kosmo
                        </Button>
                        <Button size="sm" onClick={handleEvaluateAll} disabled={evaluatingAll} data-testid="evaluate-all-btn">
                            {evaluatingAll ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Search className="w-3.5 h-3.5 mr-1.5" />}
                            Evaluar IA todas
                        </Button>
                    </div>
                )}
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase tracking-wider">Score promedio</p>
                        <p className={`text-3xl font-mono font-bold ${
                            kpis.avgScore >= 90 ? 'text-emerald-600' : kpis.avgScore >= 60 ? 'text-amber-600' : 'text-red-600'
                        }`} data-testid="kpi-avg-score">{kpis.avgScore}%</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase tracking-wider">Completos</p>
                        <p className="text-3xl font-mono font-bold text-emerald-600" data-testid="kpi-complete">
                            {kpis.complete}<span className="text-lg text-slate-400">/{kpis.totalScored}</span>
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase tracking-wider">Evaluados IA</p>
                        <p className="text-3xl font-mono font-bold text-blue-600" data-testid="kpi-ai-evaluated">
                            {kpis.aiEvaluated}<span className="text-lg text-slate-400">/{kpis.totalPkgs}</span>
                        </p>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4 text-center">
                        <p className="text-xs text-slate-500 uppercase tracking-wider">Revisión manual</p>
                        <p className="text-3xl font-mono font-bold text-violet-600" data-testid="kpi-manual-reviewed">
                            {kpis.manualReviewed}<span className="text-lg text-slate-400">/{kpis.totalPkgs}</span>
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* AI Alert Banner */}
            {aiErrorSummary.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-3" data-testid="ai-alert-banner">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <div className="text-sm">
                        <p className="font-medium text-amber-800">
                            Alertas IA detectadas — Driver: {journey.driver_name || 'N/A'}
                        </p>
                        <div className="flex flex-wrap gap-2 mt-1">
                            {aiErrorSummary.slice(0, 5).map(([error, count]) => (
                                <span key={error} className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">
                                    {error} ({count})
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Segment Filter Pills */}
            <div className="flex gap-2" data-testid="segment-filters">
                {SEGMENT_FILTERS.map(f => (
                    <button
                        key={f.key}
                        className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                            segment === f.key
                                ? 'bg-slate-900 text-white border-slate-900'
                                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                        }`}
                        onClick={() => setSegment(f.key)}
                        data-testid={`segment-${f.key}`}
                    >
                        {f.label}
                        {f.key !== 'all' && (
                            <span className="ml-1 opacity-70">
                                ({f.key === 'alert' ? packages.filter(p => (p.ai_errors || []).length > 0).length :
                                  f.key === 'no_evidence' ? packages.filter(p => p.photos_count === 0).length :
                                  packages.filter(p => !p.manually_reviewed).length})
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {/* Main Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="max-h-[600px] overflow-y-auto">
                        <table className="data-table w-full text-sm">
                            <thead>
                                <tr>
                                    <th className="w-8"></th>
                                    <th>No. guía</th>
                                    <th>Destinatario</th>
                                    <th>Estado</th>
                                    <th>Score IA</th>
                                    <th>Errores</th>
                                    <th>Fotos</th>
                                    <th>Intento</th>
                                    <th>Revisión</th>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filteredPackages.map(pkg => {
                                    const guide = getGuide(pkg);
                                    const isExpanded = expandedId === pkg.id;
                                    const isEvaluating = evaluatingPkg === guide;
                                    const hasErrors = (pkg.ai_errors || []).length > 0;
                                    const proofUrls = pkg.kosmo_proof_urls || [];

                                    return (
                                        <React.Fragment key={pkg.id}>
                                            <tr
                                                className={`cursor-pointer hover:bg-slate-50 transition-colors ${isExpanded ? 'bg-slate-50' : ''}`}
                                                onClick={() => setExpandedId(isExpanded ? null : pkg.id)}
                                                data-testid={`guia-row-${pkg.id}`}
                                            >
                                                <td className="text-center">
                                                    {isExpanded
                                                        ? <ChevronDown className="w-4 h-4 text-slate-400" />
                                                        : <ChevronRight className="w-4 h-4 text-slate-400" />}
                                                </td>
                                                <td className="font-mono text-xs">
                                                    {pkg.kosmo_url ? (
                                                        <a href={pkg.kosmo_url} target="_blank" rel="noopener noreferrer"
                                                           className="text-blue-600 hover:underline"
                                                           onClick={e => e.stopPropagation()}>
                                                            {guide}
                                                        </a>
                                                    ) : guide}
                                                </td>
                                                <td className="truncate max-w-[120px] text-xs">{pkg.recipient_name}</td>
                                                <td><StatusPill status={pkg.status} /></td>
                                                <td><ScoreCircle score={pkg.ai_score} /></td>
                                                <td>
                                                    {hasErrors ? (
                                                        <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                                                            {pkg.ai_errors[0]}{pkg.ai_errors.length > 1 ? ` +${pkg.ai_errors.length - 1}` : ''}
                                                        </span>
                                                    ) : pkg.ai_score != null ? (
                                                        <span className="text-xs bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded">Todas correctas</span>
                                                    ) : (
                                                        <span className="text-xs text-slate-400">—</span>
                                                    )}
                                                </td>
                                                <td>
                                                    {pkg.photos_count > 0 ? (
                                                        <button className="text-blue-500 hover:text-blue-700 text-xs flex items-center gap-1"
                                                                onClick={e => { e.stopPropagation(); openCarousel(pkg); }}>
                                                            <Camera className="w-3.5 h-3.5" /> {pkg.photos_count}
                                                        </button>
                                                    ) : (
                                                        <span className="text-slate-400 text-xs">0</span>
                                                    )}
                                                </td>
                                                <td className="text-center text-xs font-mono">{pkg.delivery_attempt || 1}°</td>
                                                <td className="text-center">
                                                    {pkg.manually_reviewed ? (
                                                        <CheckCircle2 className="w-4 h-4 text-emerald-500 mx-auto" />
                                                    ) : (
                                                        <Circle className="w-4 h-4 text-slate-300 mx-auto" />
                                                    )}
                                                </td>
                                                <td onClick={e => e.stopPropagation()}>
                                                    <div className="flex items-center gap-1">
                                                        {!isReadOnly && (
                                                            <Button variant="ghost" size="sm" className="h-6 px-1.5"
                                                                    disabled={isEvaluating}
                                                                    onClick={() => handleEvaluatePackage(pkg)}
                                                                    data-testid={`eval-pkg-${pkg.id}`}>
                                                                {isEvaluating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3.5 h-3.5" />}
                                                            </Button>
                                                        )}
                                                        {pkg.kosmo_url && (
                                                            <a href={pkg.kosmo_url} target="_blank" rel="noopener noreferrer"
                                                               className="text-blue-500 hover:text-blue-700 p-1"
                                                               data-testid={`kosmo-link-${pkg.id}`}>
                                                                <ExternalLink className="w-3.5 h-3.5" />
                                                            </a>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>

                                            {/* Expanded Detail Row */}
                                            {isExpanded && (
                                                <tr data-testid={`guia-detail-${pkg.id}`}>
                                                    <td colSpan={10} className="bg-slate-50 p-0">
                                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
                                                            {/* Column 1: Evidencias Kosmo */}
                                                            <div className="space-y-2">
                                                                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Evidencias Kosmo</p>
                                                                {proofUrls.length > 0 ? (
                                                                    <div className="flex gap-2 flex-wrap">
                                                                        {proofUrls.slice(0, 4).map((url, i) => (
                                                                            <button key={`thumb-${i}`}
                                                                                    className="w-16 h-16 rounded border border-slate-200 overflow-hidden hover:border-blue-400 transition-colors"
                                                                                    onClick={() => openCarousel(pkg, i)}>
                                                                                <img src={url} alt={`Foto ${i + 1}`}
                                                                                     className="w-full h-full object-cover"
                                                                                     onError={e => { e.target.src = ''; e.target.className = 'w-full h-full bg-slate-200'; }} />
                                                                            </button>
                                                                        ))}
                                                                        {proofUrls.length > 4 && (
                                                                            <button className="w-16 h-16 rounded border border-slate-200 bg-slate-100 flex items-center justify-center text-xs text-slate-500 hover:bg-slate-200"
                                                                                    onClick={() => openCarousel(pkg, 4)}>
                                                                                +{proofUrls.length - 4} más
                                                                            </button>
                                                                        )}
                                                                    </div>
                                                                ) : (
                                                                    <p className="text-xs text-slate-400">Sin fotos disponibles</p>
                                                                )}
                                                                {pkg.delivery_note && (
                                                                    <p className="text-xs text-slate-600 bg-white border border-slate-200 rounded p-2 mt-1">
                                                                        {pkg.delivery_note}
                                                                    </p>
                                                                )}
                                                                <div className="text-xs text-slate-400 flex items-center gap-2">
                                                                    {pkg.kosmo_finished_at && (
                                                                        <span>Entrega: {new Date(pkg.kosmo_finished_at).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}</span>
                                                                    )}
                                                                    <span>{pkg.photos_count} fotos en Kosmo</span>
                                                                </div>
                                                            </div>

                                                            {/* Column 2: Evaluación IA */}
                                                            <div className="space-y-2">
                                                                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Evaluación IA</p>
                                                                {hasErrors ? (
                                                                    <div className="bg-red-50 border border-red-200 rounded p-3 space-y-1">
                                                                        {pkg.ai_errors.map((err, i) => (
                                                                            <p key={`err-${i}`} className="text-xs text-red-700 flex items-center gap-1">
                                                                                <X className="w-3 h-3 shrink-0" /> {err}
                                                                            </p>
                                                                        ))}
                                                                    </div>
                                                                ) : pkg.ai_score != null ? (
                                                                    <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
                                                                        <p className="text-xs text-emerald-700 flex items-center gap-1">
                                                                            <Check className="w-3 h-3" /> Sin errores detectados
                                                                        </p>
                                                                    </div>
                                                                ) : (
                                                                    <p className="text-xs text-slate-400">No evaluado por IA</p>
                                                                )}
                                                                <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                                                                    {pkg.ai_score != null && <span>Score: <strong className="font-mono">{pkg.ai_score}</strong></span>}
                                                                    {pkg.ai_confidence != null && <span>Confianza: <strong className="font-mono">{Math.round(pkg.ai_confidence * 100)}%</strong></span>}
                                                                </div>
                                                                {pkg.evidence_detail?.ai_observations && (
                                                                    <p className="text-xs text-slate-500 bg-white border rounded p-2">{pkg.evidence_detail.ai_observations}</p>
                                                                )}
                                                            </div>

                                                            {/* Column 3: Revisión Manual */}
                                                            <div className="space-y-2">
                                                                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Revisión manual</p>
                                                                {pkg.manually_reviewed && (
                                                                    <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
                                                                        <p className="text-xs text-emerald-700">Revisado por: {pkg.reviewed_by}</p>
                                                                        {pkg.review_note && <p className="text-xs text-slate-600 mt-1">{pkg.review_note}</p>}
                                                                    </div>
                                                                )}
                                                                {pkg.rejection_reason && !pkg.manually_reviewed && (
                                                                    <div className="bg-red-50 border border-red-200 rounded p-3">
                                                                        <p className="text-xs text-red-700">Rechazado: {pkg.rejection_reason}</p>
                                                                    </div>
                                                                )}
                                                                {canReview && !pkg.manually_reviewed && (
                                                                    <div className="space-y-2 mt-2">
                                                                        {rejectingPkg === pkg.id ? (
                                                                            <div className="space-y-2">
                                                                                <Input
                                                                                    placeholder="Motivo de rechazo..."
                                                                                    value={rejectNote}
                                                                                    onChange={e => setRejectNote(e.target.value)}
                                                                                    className="text-xs h-8"
                                                                                    data-testid={`reject-note-${pkg.id}`}
                                                                                />
                                                                                <div className="flex gap-2">
                                                                                    <Button size="sm" variant="destructive" className="h-7 text-xs"
                                                                                            onClick={() => handleReject(pkg)}
                                                                                            disabled={savingReview === pkg.id}
                                                                                            data-testid={`confirm-reject-${pkg.id}`}>
                                                                                        {savingReview === pkg.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
                                                                                        Confirmar
                                                                                    </Button>
                                                                                    <Button size="sm" variant="ghost" className="h-7 text-xs"
                                                                                            onClick={() => { setRejectingPkg(null); setRejectNote(''); }}>
                                                                                        Cancelar
                                                                                    </Button>
                                                                                </div>
                                                                            </div>
                                                                        ) : (
                                                                            <div className="flex gap-2">
                                                                                <Button size="sm" variant="outline"
                                                                                        className="h-7 text-xs border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                                                                                        onClick={() => handleApprove(pkg)}
                                                                                        disabled={savingReview === pkg.id}
                                                                                        data-testid={`approve-btn-${pkg.id}`}>
                                                                                    {savingReview === pkg.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}
                                                                                    Aprobar
                                                                                </Button>
                                                                                <Button size="sm" variant="outline"
                                                                                        className="h-7 text-xs border-red-300 text-red-700 hover:bg-red-50"
                                                                                        onClick={() => setRejectingPkg(pkg.id)}
                                                                                        data-testid={`reject-btn-${pkg.id}`}>
                                                                                    <X className="w-3 h-3 mr-1" /> Rechazar
                                                                                </Button>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                    );
                                })}
                                {filteredPackages.length === 0 && (
                                    <tr>
                                        <td colSpan={10} className="text-center py-8 text-slate-400 text-sm">
                                            No hay guías que coincidan con el filtro seleccionado.
                                        </td>
                                    </tr>
                                )}
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

export default GuiasTab;
