import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
    evaluatePackageEvidence,
    evaluateAllEvidence,
    batchRescrapeJourney,
    reviewPackageWithNote,
    evaluateConfidence,
    reviewDiscrepancy,
    bulkUpdatePackageStatus,
} from '../lib/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Checkbox } from './ui/checkbox';
import {
    RefreshCw, Search, Loader2, ChevronDown, ChevronRight, Camera,
    ExternalLink, Check, X, AlertTriangle, Circle, CheckCircle2,
    XCircle, Eye, ShieldAlert, ShieldCheck, BarChart3,
} from 'lucide-react';
import { toast } from 'sonner';
import EvidenceCarousel from './EvidenceCarousel';

/* ─── Segment filters ─── */
const SEGMENT_FILTERS = [
    { key: 'all', label: 'Todas' },
    { key: 'alert', label: 'Con alerta' },
    { key: 'discrepancy', label: 'Discrepancia' },
    { key: 'no_evidence', label: 'Sin evidencia' },
    { key: 'pending_review', label: 'Pendiente revisión' },
];

/* ─── Score circle ─── */
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

/* ─── Confidence bar ─── */
const ConfidenceBar = ({ score }) => {
    if (score == null) return <span className="text-xs text-slate-400">—</span>;
    const color = score >= 70 ? '#10B981' : score >= 30 ? '#D97706' : '#EF4444';
    const textCls = score >= 70 ? 'text-emerald-600' : score >= 30 ? 'text-amber-600' : 'text-red-600';
    return (
        <div className="flex items-center gap-2 min-w-[80px]" data-testid="confidence-bar">
            <div className="flex-1 h-1 bg-slate-200 rounded-full overflow-hidden">
                <div style={{ width: `${score}%`, background: color }} className="h-full rounded-full transition-all" />
            </div>
            <span className={`text-xs font-mono font-bold ${textCls}`}>{score}%</span>
        </div>
    );
};

/* ─── Status pill (with discrepancy support) ─── */
const StatusPill = ({ status, discrepancy }) => {
    if (discrepancy?.detected) {
        return (
            <span className="text-xs font-medium px-2.5 py-0.5 rounded-full border border-amber-400 bg-amber-50 text-amber-700 inline-flex items-center gap-1"
                  data-testid="status-discrepancy">
                <AlertTriangle className="w-3 h-3" /> Discrepancia
            </span>
        );
    }
    const map = {
        delivered: { label: 'Exitosa', cls: 'bg-emerald-100 text-emerald-700' },
        failed: { label: 'Fallida', cls: 'bg-red-100 text-red-700' },
        returned: { label: 'Devuelta', cls: 'bg-slate-200 text-slate-700' },
        pending: { label: 'Pendiente', cls: 'bg-slate-100 text-slate-500' },
    };
    const { label, cls } = map[status] || map.pending;
    return <span className={`text-xs font-medium px-2.5 py-0.5 rounded-full ${cls}`}>{label}</span>;
};

/* ─── Review indicator ─── */
const ReviewIndicator = ({ pkg }) => {
    if (pkg.manually_reviewed) {
        return <CheckCircle2 className="w-4 h-4 text-emerald-500 mx-auto" data-testid={`review-approved-${pkg.id}`} />;
    }
    if (pkg.rejection_reason) {
        return <XCircle className="w-4 h-4 text-red-500 mx-auto" data-testid={`review-rejected-${pkg.id}`} />;
    }
    if (pkg.manual_review?.decision === 'confirm_return') {
        return <XCircle className="w-4 h-4 text-red-500 mx-auto" data-testid={`review-return-${pkg.id}`} />;
    }
    if (pkg.manual_review?.decision === 'mark_valid') {
        return <CheckCircle2 className="w-4 h-4 text-emerald-500 mx-auto" data-testid={`review-valid-${pkg.id}`} />;
    }
    return <Circle className="w-4 h-4 text-slate-300 mx-auto" data-testid={`review-pending-${pkg.id}`} />;
};

/* ─── Main component ─── */
const GuiasTab = ({ journey, packages, onRefreshJourney }) => {
    const { hasRole } = useAuth();
    const canReview = hasRole(['coordinator', 'developer']);
    const isReadOnly = hasRole(['agent', 'proveedor']);

    const [segment, setSegment] = useState('all');
    const [expandedId, setExpandedId] = useState(null);
    const [evaluatingPkg, setEvaluatingPkg] = useState(null);
    const [evaluatingAll, setEvaluatingAll] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [evaluatingConfidence, setEvaluatingConfidence] = useState(false);
    const [rejectingPkg, setRejectingPkg] = useState(null);
    const [rejectNote, setRejectNote] = useState('');
    const [savingReview, setSavingReview] = useState(null);
    const [reviewOverrides, setReviewOverrides] = useState({});
    const [carouselOpen, setCarouselOpen] = useState(false);
    const [carouselImages, setCarouselImages] = useState([]);
    const [carouselIndex, setCarouselIndex] = useState(0);
    const [carouselPkgInfo, setCarouselPkgInfo] = useState(null);
    const [selectedPkgs, setSelectedPkgs] = useState({});
    const [bulkStatus, setBulkStatus] = useState('');
    const [bulkSaving, setBulkSaving] = useState(false);
    const rowRefs = useRef({});
    const tableContainerRef = useRef(null);

    useEffect(() => { setReviewOverrides({}); setSelectedPkgs({}); }, [packages]);

    const mergedPackages = useMemo(() => {
        return packages.map(p => {
            const override = reviewOverrides[p.id];
            return override ? { ...p, ...override } : p;
        });
    }, [packages, reviewOverrides]);

    /* ─── KPIs including discrepancy metrics ─── */
    const kpis = useMemo(() => {
        const total = mergedPackages.length;
        const withScore = mergedPackages.filter(p => p.ai_score != null);
        const avgScore = withScore.length > 0 ? Math.round(withScore.reduce((s, p) => s + p.ai_score, 0) / withScore.length) : 0;
        const complete = withScore.filter(p => p.ai_score === 100).length;
        const aiEvaluated = withScore.length;
        const manualReviewed = mergedPackages.filter(p => p.manually_reviewed || p.manual_review?.decision).length;
        const discrepancies = mergedPackages.filter(p => p.discrepancy?.detected).length;
        const withConfidence = mergedPackages.filter(p => p.confidence?.score != null);
        const avgConfidence = withConfidence.length > 0
            ? Math.round(withConfidence.reduce((s, p) => s + p.confidence.score, 0) / withConfidence.length)
            : null;
        return { avgScore, complete, totalScored: withScore.length, aiEvaluated, manualReviewed, totalPkgs: total, discrepancies, avgConfidence };
    }, [mergedPackages]);

    const aiErrorSummary = useMemo(() => {
        const errorMap = {};
        mergedPackages.forEach(p => (p.ai_errors || []).forEach(e => { errorMap[e] = (errorMap[e] || 0) + 1; }));
        return Object.entries(errorMap).sort((a, b) => b[1] - a[1]);
    }, [mergedPackages]);

    /* ─── Segment counts (memoized) ─── */
    const segmentCounts = useMemo(() => ({
        all: mergedPackages.length,
        alert: mergedPackages.filter(p => (p.ai_errors || []).length > 0).length,
        discrepancy: mergedPackages.filter(p => p.discrepancy?.detected).length,
        no_evidence: mergedPackages.filter(p => (p.photos_count || 0) === 0 && !(p.kosmo_proof_urls?.length)).length,
        pending_review: mergedPackages.filter(p => !p.manually_reviewed && !p.rejection_reason && !p.manual_review?.decision).length,
    }), [mergedPackages]);

    const filteredPackages = useMemo(() => {
        let list = [...mergedPackages];
        if (segment === 'alert') list = list.filter(p => (p.ai_errors || []).length > 0);
        if (segment === 'discrepancy') list = list.filter(p => p.discrepancy?.detected);
        if (segment === 'no_evidence') list = list.filter(p => (p.photos_count || 0) === 0 && !(p.kosmo_proof_urls?.length));
        if (segment === 'pending_review') list = list.filter(p => !p.manually_reviewed && !p.rejection_reason && !p.manual_review?.decision);
        list.sort((a, b) => {
            // Discrepancies first
            const aDisc = a.discrepancy?.detected ? 1 : 0;
            const bDisc = b.discrepancy?.detected ? 1 : 0;
            if (bDisc !== aDisc) return bDisc - aDisc;
            const aErr = (a.ai_errors || []).length;
            const bErr = (b.ai_errors || []).length;
            if (bErr !== aErr) return bErr - aErr;
            const aGuide = a.order_reference_id || a.tracking_number || '';
            const bGuide = b.order_reference_id || b.tracking_number || '';
            return aGuide.localeCompare(bGuide);
        });
        return list;
    }, [mergedPackages, segment]);

    const findNextPending = useCallback((currentId) => {
        const idx = filteredPackages.findIndex(p => p.id === currentId);
        for (let i = idx + 1; i < filteredPackages.length; i++) {
            const p = filteredPackages[i];
            if (!p.manually_reviewed && !p.rejection_reason && !p.manual_review?.decision) return p;
        }
        for (let i = 0; i < idx; i++) {
            const p = filteredPackages[i];
            if (!p.manually_reviewed && !p.rejection_reason && !p.manual_review?.decision) return p;
        }
        return null;
    }, [filteredPackages]);

    const scrollToRow = useCallback((pkgId) => {
        setTimeout(() => { rowRefs.current[pkgId]?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 100);
    }, []);

    const advanceToNext = useCallback((reviewedPkgId) => {
        const next = findNextPending(reviewedPkgId);
        if (next) { setExpandedId(next.id); scrollToRow(next.id); }
        else { setExpandedId(null); toast.success('Todas las guías han sido revisadas'); }
    }, [findNextPending, scrollToRow]);

    /* ─── Action handlers ─── */
    const handleApprove = async (pkg) => {
        setSavingReview(pkg.id);
        try {
            await reviewPackageWithNote(pkg.id, { manually_reviewed: true });
            setReviewOverrides(prev => ({ ...prev, [pkg.id]: { manually_reviewed: true, rejection_reason: null, reviewed_by: 'Tú' } }));
            toast.success('Guía aprobada');
            setRejectingPkg(null); setRejectNote('');
            advanceToNext(pkg.id);
            onRefreshJourney?.();
        } catch { toast.error('Error al aprobar'); }
        finally { setSavingReview(null); }
    };

    const handleReject = async (pkg) => {
        if (!rejectNote.trim()) { toast.error('Ingresa el motivo de rechazo'); return; }
        setSavingReview(pkg.id);
        try {
            await reviewPackageWithNote(pkg.id, { manually_reviewed: false, manually_reviewed_note: rejectNote });
            setReviewOverrides(prev => ({ ...prev, [pkg.id]: { manually_reviewed: false, rejection_reason: rejectNote, reviewed_by: 'Tú' } }));
            toast.success('Guía rechazada');
            setRejectingPkg(null); setRejectNote('');
            advanceToNext(pkg.id);
            onRefreshJourney?.();
        } catch { toast.error('Error al rechazar'); }
        finally { setSavingReview(null); }
    };

    const handleDiscrepancyReview = async (pkg, decision) => {
        const guideId = pkg.order_reference_id || pkg.tracking_number || pkg.id;
        setSavingReview(pkg.id);
        try {
            await reviewDiscrepancy(journey.id, guideId, { decision });
            const isReturn = decision === 'confirm_return';
            setReviewOverrides(prev => ({
                ...prev,
                [pkg.id]: {
                    ...(isReturn ? { status: 'returned' } : {}),
                    discrepancy: isReturn ? pkg.discrepancy : { ...pkg.discrepancy, detected: false },
                    manual_review: { decision, reviewed_by: 'Tú', reviewed_at: new Date().toISOString(), status: 'reviewed' },
                },
            }));
            toast.success(isReturn ? 'Devolución confirmada' : 'Guía marcada como válida');
            advanceToNext(pkg.id);
            onRefreshJourney?.();
        } catch { toast.error('Error al revisar discrepancia'); }
        finally { setSavingReview(null); }
    };

    const handleEvaluatePackage = async (pkg) => {
        const guide = pkg.order_reference_id || pkg.tracking_number;
        setEvaluatingPkg(guide);
        try {
            await evaluatePackageEvidence(journey.id, guide);
            toast.success(`Evaluación IA completada para ${guide}`);
            onRefreshJourney?.();
        } catch (err) { toast.error(err.response?.data?.detail || 'Error al evaluar con IA'); }
        finally { setEvaluatingPkg(null); }
    };

    const handleEvaluateAll = async () => {
        setEvaluatingAll(true);
        try {
            const res = await evaluateAllEvidence(journey.id);
            toast.success(res.data?.message || 'Evaluación IA iniciada');
            setTimeout(() => onRefreshJourney?.(), 3000);
        } catch (err) { toast.error(err.response?.data?.detail || 'Error al evaluar con IA'); }
        finally { setEvaluatingAll(false); }
    };

    const handleEvaluateConfidence = async () => {
        setEvaluatingConfidence(true);
        try {
            const res = await evaluateConfidence(journey.id);
            toast.success(res.data?.message || 'Evaluación de confianza completa');
            onRefreshJourney?.();
        } catch (err) { toast.error(err.response?.data?.detail || 'Error al evaluar confianza'); }
        finally { setEvaluatingConfidence(false); }
    };

    const handleResync = async () => {
        setSyncing(true);
        try {
            const res = await batchRescrapeJourney(journey.id);
            toast.success(res.data?.message || 'Re-sincronización completa');
            onRefreshJourney?.();
        } catch (err) { toast.error(err.response?.data?.detail || 'Error al sincronizar'); }
        finally { setSyncing(false); }
    };

    const openCarousel = (pkg, startIndex = 0) => {
        const urls = pkg.kosmo_proof_urls || [];
        const photoAnalyses = pkg.evidence_detail?.photos_analysis || [];
        const imgs = urls.map((url, i) => ({ url, analysis: photoAnalyses[i] || null }));
        if (imgs.length === 0) return;
        setCarouselImages(imgs); setCarouselIndex(startIndex);
        setCarouselPkgInfo({ guide: pkg.tracking_number || pkg.order_reference_id, deliveryType: pkg.evidence_type, score: pkg.evidence_score });
        setCarouselOpen(true);
    };

    const getGuide = (pkg) => pkg.order_reference_id || pkg.tracking_number || '';

    /* ─── Bulk selection ─── */
    const selectedIds = useMemo(() => Object.entries(selectedPkgs).filter(([, v]) => v).map(([k]) => k), [selectedPkgs]);
    const allFilteredSelected = filteredPackages.length > 0 && filteredPackages.every(p => selectedPkgs[p.id]);

    const toggleSelectAll = () => {
        if (allFilteredSelected) {
            setSelectedPkgs({});
        } else {
            const next = {};
            filteredPackages.forEach(p => { next[p.id] = true; });
            setSelectedPkgs(next);
        }
    };

    const togglePkg = (pkgId) => {
        setSelectedPkgs(prev => ({ ...prev, [pkgId]: !prev[pkgId] }));
    };

    const handleBulkSave = async () => {
        if (!bulkStatus || selectedIds.length === 0) return;
        setBulkSaving(true);
        try {
            const res = await bulkUpdatePackageStatus(journey.id, selectedIds, bulkStatus);
            toast.success(`${res.data.updated} paquetes actualizados a "${bulkStatus}"`);
            setSelectedPkgs({});
            setBulkStatus('');
            onRefreshJourney?.();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al actualizar estatus');
        } finally {
            setBulkSaving(false);
        }
    };

    return (
        <div className="space-y-4" data-testid="guias-tab">
            {/* Global Actions */}
            <div className="flex items-center justify-between">
                <h3 className="font-heading text-base font-semibold text-slate-800">Guías de la ruta</h3>
                {!isReadOnly && (
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={handleResync} disabled={syncing} data-testid="resync-kosmo-btn">
                            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${syncing ? 'animate-spin' : ''}`} /> Re-sincronizar Kosmo
                        </Button>
                        <Button variant="outline" size="sm" onClick={handleEvaluateConfidence} disabled={evaluatingConfidence} data-testid="evaluate-confidence-btn">
                            {evaluatingConfidence ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <ShieldAlert className="w-3.5 h-3.5 mr-1.5" />}
                            Evaluar confianza
                        </Button>
                        <Button size="sm" onClick={handleEvaluateAll} disabled={evaluatingAll} data-testid="evaluate-all-btn">
                            {evaluatingAll ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <Search className="w-3.5 h-3.5 mr-1.5" />}
                            Evaluar IA todas
                        </Button>
                    </div>
                )}
            </div>

            {/* KPI Cards — 6 cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <KpiCard label="Score promedio" value={`${kpis.avgScore}%`} color={kpis.avgScore >= 90 ? 'emerald' : kpis.avgScore >= 60 ? 'amber' : 'red'} testId="kpi-avg-score" />
                <KpiCard label="Completos" value={`${kpis.complete}/${kpis.totalScored}`} color="emerald" testId="kpi-complete" />
                <KpiCard label="Evaluados IA" value={`${kpis.aiEvaluated}/${kpis.totalPkgs}`} color="blue" testId="kpi-ai-evaluated" />
                <KpiCard label="Revisión manual" value={`${kpis.manualReviewed}/${kpis.totalPkgs}`} color="violet" testId="kpi-manual-reviewed" />
                <KpiCard label="Discrepancias" value={kpis.discrepancies} color={kpis.discrepancies > 0 ? 'red' : 'emerald'}
                    accent={kpis.discrepancies > 0 ? 'red' : undefined} testId="kpi-discrepancies" />
                <KpiCard label="Confianza prom." value={kpis.avgConfidence != null ? `${kpis.avgConfidence}%` : '—'}
                    color={kpis.avgConfidence >= 70 ? 'emerald' : kpis.avgConfidence >= 30 ? 'amber' : 'red'} testId="kpi-avg-confidence" />
            </div>

            {/* Discrepancy Alert Banner */}
            {kpis.discrepancies > 0 && (
                <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 flex items-start gap-3" data-testid="discrepancy-alert-banner">
                    <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center shrink-0 mt-0.5">
                        <AlertTriangle className="w-4 h-4 text-amber-600" />
                    </div>
                    <div className="flex-1">
                        <p className="text-sm font-semibold text-amber-800">
                            {kpis.discrepancies} guía{kpis.discrepancies !== 1 ? 's' : ''} con discrepancia de estatus detectada
                        </p>
                        <p className="text-xs text-amber-700 mt-0.5">
                            El tracking público de Kosmo reporta "Entregado" pero no se encontraron evidencias fotográficas ni motivo de excepción.
                        </p>
                    </div>
                    <Button variant="outline" size="sm"
                        className="border-amber-400 text-amber-700 hover:bg-amber-100 shrink-0"
                        onClick={() => setSegment('discrepancy')}
                        data-testid="view-discrepancies-btn">
                        Ver discrepancias
                    </Button>
                </div>
            )}

            {/* AI Alert Banner */}
            {aiErrorSummary.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-3" data-testid="ai-alert-banner">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <div className="text-sm">
                        <p className="font-medium text-amber-800">Alertas IA detectadas — Driver: {journey.driver_name || 'N/A'}</p>
                        <div className="flex flex-wrap gap-2 mt-1">
                            {aiErrorSummary.slice(0, 5).map(([error, count]) => (
                                <span key={error} className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">{error} ({count})</span>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Segment Filter Pills */}
            <div className="flex gap-2 flex-wrap" data-testid="segment-filters">
                {SEGMENT_FILTERS.map(f => {
                    const count = segmentCounts[f.key];
                    const isDiscrepancy = f.key === 'discrepancy' && count > 0;
                    return (
                        <button key={f.key}
                            className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                                segment === f.key
                                    ? (isDiscrepancy ? 'bg-amber-600 text-white border-amber-600' : 'bg-slate-900 text-white border-slate-900')
                                    : (isDiscrepancy ? 'bg-amber-50 text-amber-700 border-amber-300 hover:bg-amber-100' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50')
                            }`}
                            onClick={() => setSegment(f.key)}
                            data-testid={`segment-${f.key}`}>
                            {f.label}
                            {f.key !== 'all' && <span className="ml-1 opacity-70">({count})</span>}
                            {f.key === 'all' && <span className="ml-1 opacity-70">({count})</span>}
                        </button>
                    );
                })}
            </div>

            {/* Main Table */}
            <Card>
                <CardContent className="p-0">
                    <div className="max-h-[600px] overflow-y-auto" ref={tableContainerRef}>
                        <table className="data-table w-full text-sm">
                            <thead>
                                <tr>
                                    {canReview && (
                                        <th className="w-8 text-center">
                                            <Checkbox checked={allFilteredSelected} onCheckedChange={toggleSelectAll} data-testid="select-all-checkbox" />
                                        </th>
                                    )}
                                    <th className="w-8"></th>
                                    <th>No. guía</th>
                                    <th>Destinatario</th>
                                    <th>Estado</th>
                                    <th>Confianza</th>
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
                                    const hasDiscrepancy = pkg.discrepancy?.detected;
                                    const reviewDecision = pkg.manual_review?.decision;

                                    return (
                                        <React.Fragment key={pkg.id}>
                                            <tr ref={el => { rowRefs.current[pkg.id] = el; }}
                                                className={`cursor-pointer transition-colors ${
                                                    hasDiscrepancy ? 'bg-amber-50/60 hover:bg-amber-50' :
                                                    isExpanded ? 'bg-slate-50' : 'hover:bg-slate-50'
                                                }`}
                                                onClick={() => setExpandedId(isExpanded ? null : pkg.id)}
                                                data-testid={`guia-row-${pkg.id}`}>

                                                {canReview && (
                                                    <td className="text-center" onClick={e => e.stopPropagation()}>
                                                        <Checkbox checked={!!selectedPkgs[pkg.id]} onCheckedChange={() => togglePkg(pkg.id)} data-testid={`select-pkg-${pkg.id}`} />
                                                    </td>
                                                )}

                                                <td className="text-center">
                                                    {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                                                </td>
                                                <td className="font-mono text-xs">
                                                    {pkg.kosmo_url ? (
                                                        <a href={pkg.kosmo_url} target="_blank" rel="noopener noreferrer"
                                                           className="text-blue-600 hover:underline" onClick={e => e.stopPropagation()}>{guide}</a>
                                                    ) : guide}
                                                </td>
                                                <td className="truncate max-w-[120px] text-xs">{pkg.recipient_name}</td>
                                                <td>
                                                    <StatusPill status={pkg.status} discrepancy={pkg.discrepancy} />
                                                    {pkg.status === 'failed' && pkg.failure_reason && (
                                                        <span className="block text-[10px] text-red-500 mt-0.5 truncate max-w-[100px]" title={pkg.failure_reason_note || pkg.failure_reason}>
                                                            {pkg.failure_reason.replace(/_/g, ' ')}
                                                        </span>
                                                    )}
                                                </td>
                                                <td><ConfidenceBar score={pkg.confidence?.score} /></td>
                                                <td><ScoreCircle score={pkg.ai_score} /></td>
                                                <td>
                                                    {hasErrors ? (
                                                        <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                                                            {pkg.ai_errors[0]}{pkg.ai_errors.length > 1 ? ` +${pkg.ai_errors.length - 1}` : ''}
                                                        </span>
                                                    ) : pkg.ai_score != null ? (
                                                        <span className="text-xs bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded">OK</span>
                                                    ) : <span className="text-xs text-slate-400">—</span>}
                                                </td>
                                                <td>
                                                    {(pkg.photos_count || proofUrls.length) > 0 ? (
                                                        <button className="text-blue-500 hover:text-blue-700 text-xs flex items-center gap-1"
                                                                onClick={e => { e.stopPropagation(); openCarousel(pkg); }}>
                                                            <Camera className="w-3.5 h-3.5" /> {pkg.photos_count || proofUrls.length}
                                                        </button>
                                                    ) : <span className="text-slate-400 text-xs">0</span>}
                                                </td>
                                                <td className="text-center text-xs font-mono">{pkg.delivery_attempt || 1}°</td>
                                                <td className="text-center" onClick={e => e.stopPropagation()}>
                                                    <ReviewIndicator pkg={pkg} />
                                                </td>
                                                <td onClick={e => e.stopPropagation()}>
                                                    <div className="flex items-center gap-1">
                                                        {!isReadOnly && (
                                                            <Button variant="ghost" size="sm" className="h-6 px-1.5" disabled={isEvaluating}
                                                                    onClick={() => handleEvaluatePackage(pkg)} data-testid={`eval-pkg-${pkg.id}`}>
                                                                {isEvaluating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3.5 h-3.5" />}
                                                            </Button>
                                                        )}
                                                        {pkg.kosmo_url && (
                                                            <a href={pkg.kosmo_url} target="_blank" rel="noopener noreferrer"
                                                               className="text-blue-500 hover:text-blue-700 p-1" data-testid={`kosmo-link-${pkg.id}`}>
                                                                <ExternalLink className="w-3.5 h-3.5" />
                                                            </a>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>

                                            {/* ─── Expanded Detail Row ─── */}
                                            {isExpanded && (
                                                <tr data-testid={`guia-detail-${pkg.id}`}>
                                                <td colSpan={canReview ? 12 : 11} className="bg-slate-50 p-0">
                                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
                                                            {/* Col 1: Evidencias Kosmo */}
                                                            <div className="space-y-2">
                                                                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Evidencias Kosmo</p>
                                                                {proofUrls.length > 0 ? (
                                                                    <div className="flex gap-2 flex-wrap">
                                                                        {proofUrls.slice(0, 4).map((url, i) => (
                                                                            <button key={`thumb-${i}`}
                                                                                    className="w-16 h-16 rounded border border-slate-200 overflow-hidden hover:border-blue-400 transition-colors"
                                                                                    onClick={() => openCarousel(pkg, i)}>
                                                                                <img src={url} alt={`Foto ${i + 1}`} className="w-full h-full object-cover"
                                                                                     onError={e => { e.target.src = ''; e.target.className = 'w-full h-full bg-slate-200'; }} />
                                                                            </button>
                                                                        ))}
                                                                        {proofUrls.length > 4 && (
                                                                            <button className="w-16 h-16 rounded border border-slate-200 bg-slate-100 flex items-center justify-center text-xs text-slate-500"
                                                                                    onClick={() => openCarousel(pkg, 4)}>+{proofUrls.length - 4}</button>
                                                                        )}
                                                                    </div>
                                                                ) : <p className="text-xs text-slate-400">Sin fotos disponibles</p>}
                                                                {pkg.delivery_note && <p className="text-xs text-slate-600 bg-white border border-slate-200 rounded p-2">{pkg.delivery_note}</p>}
                                                                {pkg.kosmo_driver_note && !pkg.delivery_note && <p className="text-xs text-slate-600 bg-white border border-slate-200 rounded p-2">{pkg.kosmo_driver_note}</p>}
                                                                {(pkg.failure_reason || pkg.failure_reason_note) && (
                                                                    <div className="bg-red-50 border border-red-200 rounded p-2 space-y-1">
                                                                        {pkg.failure_reason && <p className="text-xs font-medium text-red-700">Motivo: {pkg.failure_reason.replace(/_/g, ' ')}</p>}
                                                                        {pkg.failure_reason_note && <p className="text-xs text-red-600 italic">"{pkg.failure_reason_note}"</p>}
                                                                    </div>
                                                                )}
                                                                <div className="text-xs text-slate-400 flex items-center gap-2">
                                                                    {pkg.kosmo_finished_at && <span>Entrega: {new Date(pkg.kosmo_finished_at).toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}</span>}
                                                                    <span>{pkg.photos_count || proofUrls.length} fotos en Kosmo</span>
                                                                </div>
                                                            </div>

                                                            {/* Col 2: Discrepancy / Evaluación IA */}
                                                            <div className="space-y-2">
                                                                {hasDiscrepancy ? (
                                                                    <>
                                                                        <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider">Discrepancia detectada</p>
                                                                        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-2">
                                                                            <DiscRow label="Tracking público" value={pkg.discrepancy.tracking_says} />
                                                                            <DiscRow label="Estatus interno Kosmo" value={pkg.discrepancy.kosmo_internal_says || 'Desconocido'} danger />
                                                                            <DiscRow label="Evidencias Kosmo" value={`${pkg.photos_count || 0} fotos`} danger={!pkg.photos_count} />
                                                                            <DiscRow label="Motivo excepción" value={pkg.failure_reason || 'Ninguno'} danger={!pkg.failure_reason} />
                                                                            <DiscRow label="Score confianza" value={`${pkg.confidence?.score ?? 0}%`} danger={(pkg.confidence?.score ?? 0) < 30} />
                                                                        </div>
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Evaluación IA</p>
                                                                        {hasErrors ? (
                                                                            <div className="bg-red-50 border border-red-200 rounded p-3 space-y-1">
                                                                                {pkg.ai_errors.map((err, i) => (
                                                                                    <p key={`err-${i}`} className="text-xs text-red-700 flex items-center gap-1"><X className="w-3 h-3 shrink-0" /> {err}</p>
                                                                                ))}
                                                                            </div>
                                                                        ) : pkg.ai_score != null ? (
                                                                            <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
                                                                                <p className="text-xs text-emerald-700 flex items-center gap-1"><ShieldCheck className="w-3.5 h-3.5" /> Sin discrepancias — tracking y evidencias coinciden</p>
                                                                            </div>
                                                                        ) : <p className="text-xs text-slate-400">No evaluado por IA</p>}
                                                                        <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                                                                            {pkg.ai_score != null && <span>Score: <strong className="font-mono">{pkg.ai_score}</strong></span>}
                                                                            {pkg.ai_confidence != null && <span>Confianza: <strong className="font-mono">{Math.round(pkg.ai_confidence * 100)}%</strong></span>}
                                                                        </div>
                                                                    </>
                                                                )}
                                                                {pkg.evidence_detail?.ai_observations && (
                                                                    <p className="text-xs text-slate-500 bg-white border rounded p-2">{pkg.evidence_detail.ai_observations}</p>
                                                                )}
                                                            </div>

                                                            {/* Col 3: Revisión Manual */}
                                                            <div className="space-y-2">
                                                                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Revisión manual</p>

                                                                {/* Discrepancy review (new) */}
                                                                {hasDiscrepancy && !reviewDecision && canReview && (
                                                                    <div className="border-l-[3px] border-red-500 rounded-r-lg bg-red-50 p-3 space-y-3">
                                                                        <p className="text-xs font-semibold text-red-700">
                                                                            Estatus recomendado: {pkg.discrepancy.recommended_status}
                                                                        </p>
                                                                        <p className="text-[11px] text-red-600">
                                                                            El tracking público indica "Entregado" pero no existen evidencias fotográficas ni motivo de excepción registrado.
                                                                        </p>
                                                                        <div className="flex gap-2">
                                                                            <Button size="sm" className="h-7 text-xs bg-red-600 hover:bg-red-700 text-white"
                                                                                    onClick={() => handleDiscrepancyReview(pkg, 'confirm_return')}
                                                                                    disabled={savingReview === pkg.id}
                                                                                    data-testid={`confirm-return-${pkg.id}`}>
                                                                                {savingReview === pkg.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
                                                                                Confirmar devolución
                                                                            </Button>
                                                                            <Button size="sm" variant="outline" className="h-7 text-xs"
                                                                                    onClick={() => handleDiscrepancyReview(pkg, 'mark_valid')}
                                                                                    disabled={savingReview === pkg.id}
                                                                                    data-testid={`mark-valid-${pkg.id}`}>
                                                                                Marcar como válido
                                                                            </Button>
                                                                        </div>
                                                                    </div>
                                                                )}

                                                                {/* Discrepancy already reviewed */}
                                                                {reviewDecision && (
                                                                    <div className={`rounded p-3 border ${reviewDecision === 'confirm_return' ? 'bg-red-50 border-red-200' : 'bg-emerald-50 border-emerald-200'}`}>
                                                                        <p className={`text-xs font-medium ${reviewDecision === 'confirm_return' ? 'text-red-700' : 'text-emerald-700'}`}>
                                                                            {reviewDecision === 'confirm_return' ? 'Devolución confirmada' : 'Marcada como válida'}
                                                                        </p>
                                                                        <p className="text-[10px] text-slate-500 mt-0.5">
                                                                            Por: {pkg.manual_review.reviewed_by} — {pkg.manual_review.reviewed_at ? new Date(pkg.manual_review.reviewed_at).toLocaleString('es-MX') : ''}
                                                                        </p>
                                                                    </div>
                                                                )}

                                                                {/* Standard review (non-discrepancy) */}
                                                                {!hasDiscrepancy && !reviewDecision && (
                                                                    <>
                                                                        {pkg.manually_reviewed && (
                                                                            <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
                                                                                <p className="text-xs text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Entrega verificada</p>
                                                                                <p className="text-[10px] text-slate-500 mt-0.5">Revisado por: {pkg.reviewed_by}</p>
                                                                            </div>
                                                                        )}
                                                                        {pkg.rejection_reason && !pkg.manually_reviewed && (
                                                                            <div className="bg-red-50 border border-red-200 rounded p-3">
                                                                                <p className="text-xs text-red-700">Rechazado: {pkg.rejection_reason}</p>
                                                                            </div>
                                                                        )}
                                                                        {canReview && !pkg.manually_reviewed && !pkg.rejection_reason && (
                                                                            <div className="space-y-2 mt-2">
                                                                                {rejectingPkg === pkg.id ? (
                                                                                    <div className="space-y-2">
                                                                                        <Input placeholder="Motivo de rechazo..." value={rejectNote}
                                                                                            onChange={e => setRejectNote(e.target.value)} className="text-xs h-8"
                                                                                            data-testid={`reject-note-${pkg.id}`}
                                                                                            onKeyDown={e => { if (e.key === 'Enter') handleReject(pkg); }} />
                                                                                        <div className="flex gap-2">
                                                                                            <Button size="sm" variant="destructive" className="h-7 text-xs"
                                                                                                    onClick={() => handleReject(pkg)} disabled={savingReview === pkg.id}
                                                                                                    data-testid={`confirm-reject-${pkg.id}`}>
                                                                                                {savingReview === pkg.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}Confirmar
                                                                                            </Button>
                                                                                            <Button size="sm" variant="ghost" className="h-7 text-xs"
                                                                                                    onClick={() => { setRejectingPkg(null); setRejectNote(''); }}>Cancelar</Button>
                                                                                        </div>
                                                                                    </div>
                                                                                ) : (
                                                                                    <div className="flex gap-2">
                                                                                        <Button size="sm" variant="outline" className="h-7 text-xs border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                                                                                                onClick={() => handleApprove(pkg)} disabled={savingReview === pkg.id}
                                                                                                data-testid={`approve-btn-${pkg.id}`}>
                                                                                            {savingReview === pkg.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Check className="w-3 h-3 mr-1" />}Aprobar
                                                                                        </Button>
                                                                                        <Button size="sm" variant="outline" className="h-7 text-xs border-red-300 text-red-700 hover:bg-red-50"
                                                                                                onClick={() => setRejectingPkg(pkg.id)} data-testid={`reject-btn-${pkg.id}`}>
                                                                                            <X className="w-3 h-3 mr-1" /> Rechazar
                                                                                        </Button>
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                        )}
                                                                    </>
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
                                    <tr><td colSpan={canReview ? 12 : 11} className="text-center py-8 text-slate-400 text-sm">No hay guías que coincidan con el filtro seleccionado.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </CardContent>
            </Card>

            <EvidenceCarousel open={carouselOpen} onClose={() => setCarouselOpen(false)}
                images={carouselImages} initialIndex={carouselIndex} packageInfo={carouselPkgInfo} />

            {/* Floating Bulk Action Bar */}
            {canReview && selectedIds.length > 0 && (
                <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-slate-900 text-white rounded-xl shadow-2xl px-6 py-3 flex items-center gap-4 min-w-[420px]"
                     data-testid="bulk-action-bar">
                    <span className="text-sm font-medium">{selectedIds.length} guía{selectedIds.length !== 1 ? 's' : ''} seleccionada{selectedIds.length !== 1 ? 's' : ''}</span>
                    <div className="h-5 w-px bg-slate-600" />
                    <select value={bulkStatus} onChange={e => setBulkStatus(e.target.value)}
                            className="bg-slate-800 text-white text-sm rounded-lg px-3 py-1.5 border border-slate-600 focus:ring-2 focus:ring-blue-500"
                            data-testid="bulk-status-select">
                        <option value="">Cambiar estado a...</option>
                        <option value="delivered">Exitosa</option>
                        <option value="failed">Fallida</option>
                        <option value="returned">Devuelta</option>
                        <option value="pending">Pendiente</option>
                    </select>
                    <Button size="sm" onClick={handleBulkSave} disabled={!bulkStatus || bulkSaving}
                            className="bg-blue-600 hover:bg-blue-700 text-white h-8 px-4"
                            data-testid="bulk-apply-btn">
                        {bulkSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : <Check className="w-3.5 h-3.5 mr-1.5" />}
                        Aplicar
                    </Button>
                    <button onClick={() => { setSelectedPkgs({}); setBulkStatus(''); }}
                            className="text-slate-400 hover:text-white transition-colors ml-auto"
                            data-testid="bulk-cancel-btn">
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}
        </div>
    );
};

/* ─── Sub-components ─── */

function KpiCard({ label, value, color, accent, testId }) {
    const colorMap = { emerald: 'text-emerald-600', amber: 'text-amber-600', red: 'text-red-600', blue: 'text-blue-600', violet: 'text-violet-600' };
    const accentMap = { red: 'border-t-[3px] border-red-500' };
    return (
        <Card className={accent ? accentMap[accent] : ''}>
            <CardContent className="p-4 text-center">
                <p className="text-xs text-slate-500 uppercase tracking-wider">{label}</p>
                <p className={`text-2xl font-mono font-bold ${colorMap[color] || 'text-slate-800'}`} data-testid={testId}>{value}</p>
            </CardContent>
        </Card>
    );
}

function DiscRow({ label, value, danger }) {
    return (
        <div className="flex items-center justify-between text-xs py-1 border-b border-amber-200 last:border-0">
            <span className="text-amber-700/70">{label}</span>
            <span className={`font-medium ${danger ? 'text-red-700' : 'text-amber-900'}`}>{value}</span>
        </div>
    );
}

export default GuiasTab;
