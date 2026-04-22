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
    getAiEvalStatus,
} from '../lib/api';
import { Card, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import {
    RefreshCw, Search, Loader2, ChevronDown, ChevronRight, Camera,
    ExternalLink, Eye, ShieldAlert, Check, X, CheckCircle2, XCircle, AlertTriangle,
} from 'lucide-react';
import { toast } from 'sonner';
import EvidenceCarousel from './EvidenceCarousel';
import ReviewModal from './ReviewModal';
import {
    ScoreCircle, ConfidenceBar, StatusPill, ReviewIndicator,
    SeverityBadge, getMaxSeverity,
} from './guias/GuiasHelpers';
import { GuiasKpisRow, GuiasSegmentFilters } from './guias/GuiasKpisRow';
import { useGuiasMetrics } from './guias/useGuiasMetrics';
import GuiasPackageDetail from './guias/GuiasPackageDetail';

/* ─── Main component ─── */
const GuiasTab = ({ journey, packages, onRefreshJourney, onRegisterIncident }) => {
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

    // ReviewModal state
    const [reviewModalOpen, setReviewModalOpen] = useState(false);
    const [reviewModalPkg, setReviewModalPkg] = useState(null);
    const [reviewModalAction, setReviewModalAction] = useState('approve');

    // AI eval polling state
    const [aiEvalProgress, setAiEvalProgress] = useState(null);
    const pollingRef = useRef(null);

    useEffect(() => { setReviewOverrides({}); setSelectedPkgs({}); }, [packages]);

    // Derived metrics + filtered list (memoized via custom hook)
    const { mergedPackages, kpis, aiErrorSummary, segmentCounts, filteredPackages } = useGuiasMetrics(
        packages,
        reviewOverrides,
        segment,
    );

    const startPolling = useCallback(() => {
        if (pollingRef.current) return;
        pollingRef.current = setInterval(async () => {
            try {
                const res = await getAiEvalStatus(journey.id);
                const status = res.data;
                setAiEvalProgress(status);
                if (status.status === 'completed' || status.status === 'error') {
                    clearInterval(pollingRef.current);
                    pollingRef.current = null;
                    setEvaluatingAll(false);
                    onRefreshJourney?.();
                    if (status.status === 'completed') {
                        toast.success(`Evaluación IA completada: ${status.evaluated}/${status.total} paquetes`);
                    } else {
                        toast.error('Evaluación IA terminó con errores');
                    }
                    setTimeout(() => setAiEvalProgress(null), 5000);
                }
            } catch { /* silently ignore polling errors */ }
        }, 3000);
    }, [journey.id, onRefreshJourney]);

    useEffect(() => {
        return () => {
            if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
        };
    }, []);

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

    const openReviewModal = (pkg, action) => {
        setReviewModalPkg(pkg);
        setReviewModalAction(action);
        setReviewModalOpen(true);
    };

    const handleReviewModalConfirm = async (reviewData) => {
        const pkg = reviewModalPkg;
        if (!pkg) return;
        setSavingReview(pkg.id);
        try {
            const isApproval = reviewData.action === 'approved';
            await reviewPackageWithNote(pkg.id, {
                manually_reviewed: isApproval,
                manually_reviewed_note: reviewData.reason_detail
                    ? `${reviewData.reason_category}: ${reviewData.reason_detail}`
                    : reviewData.reason_category || (isApproval ? 'Aprobado por criterios' : 'Rechazado'),
                adjusted_score: reviewData.adjusted_score,
                ai_evaluation_incorrect: reviewData.ai_evaluation_incorrect,
                delivery_type: reviewData.delivery_type,
                criteria_evaluation: reviewData.criteria_evaluation,
                discrepancies: reviewData.discrepancies,
            });
            setReviewOverrides(prev => ({
                ...prev,
                [pkg.id]: {
                    manually_reviewed: isApproval,
                    rejection_reason: isApproval ? null : `${reviewData.reason_category}: ${reviewData.reason_detail || ''}`,
                    reviewed_by: 'Tu',
                    ...(reviewData.adjusted_score != null ? { ai_score: reviewData.adjusted_score, evidence_score: reviewData.adjusted_score } : {}),
                },
            }));
            toast.success(isApproval ? 'Guia aprobada' : 'Guia rechazada');
            setReviewModalOpen(false);
            setReviewModalPkg(null);
            advanceToNext(pkg.id);
            onRefreshJourney?.();
        } catch (err) { console.error("GuiasTab error:", err);
            toast.error('Error al guardar revision');
        } finally {
            setSavingReview(null);
        }
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
        setAiEvalProgress({ status: 'starting', total: 0, evaluated: 0, errors: 0 });
        try {
            const res = await evaluateAllEvidence(journey.id);
            const total = res?.data?.total_enqueued ?? 0;
            const jobId = res?.data?.job_id;
            if (jobId) {
                toast.success(`Evaluacion IA encolada (${total} guias) — seguimiento en Monitor IA`);
            } else {
                toast.success('Evaluacion IA iniciada en segundo plano');
            }
            startPolling();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al evaluar con IA');
            setEvaluatingAll(false);
            setAiEvalProgress(null);
        }
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

            {/* KPI Cards + Alert Banners */}
            <GuiasKpisRow
                kpis={kpis}
                aiErrorSummary={aiErrorSummary}
                driverName={journey.driver_name}
                onViewDiscrepancies={() => setSegment('discrepancy')}
            />

            {/* Segment Filter Pills */}
            <GuiasSegmentFilters
                segment={segment}
                segmentCounts={segmentCounts}
                onSegmentChange={setSegment}
            />

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
                                                        <Checkbox checked={!!selectedPkgs[pkg.id]} onCheckedChange={() => setSelectedPkgs(prev => ({ ...prev, [pkg.id]: !prev[pkg.id] }))} data-testid={`select-pkg-${pkg.id}`} />
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
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded">
                                                                {pkg.ai_errors[0]}{pkg.ai_errors.length > 1 ? ` +${pkg.ai_errors.length - 1}` : ''}
                                                            </span>
                                                            {getMaxSeverity(pkg.ia_severity) && (
                                                                <SeverityBadge level={getMaxSeverity(pkg.ia_severity)} />
                                                            )}
                                                        </div>
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

                                            {/* Expanded Detail Row */}
                                            {isExpanded && (
                                                <tr data-testid={`guia-detail-${pkg.id}`}>
                                                    <td colSpan={canReview ? 12 : 11} className="bg-slate-50 p-0">
                                                        <GuiasPackageDetail
                                                            pkg={pkg}
                                                            proofUrls={proofUrls}
                                                            hasErrors={hasErrors}
                                                            hasDiscrepancy={hasDiscrepancy}
                                                            reviewDecision={reviewDecision}
                                                            canReview={canReview}
                                                            isReadOnly={isReadOnly}
                                                            savingReview={savingReview}
                                                            rejectingPkg={rejectingPkg}
                                                            rejectNote={rejectNote}
                                                            setRejectNote={setRejectNote}
                                                            setRejectingPkg={setRejectingPkg}
                                                            onApprove={handleApprove}
                                                            onReject={handleReject}
                                                            onDiscrepancyReview={handleDiscrepancyReview}
                                                            onRegisterIncident={onRegisterIncident}
                                                            onOpenReviewModal={openReviewModal}
                                                            openCarousel={openCarousel}
                                                        />
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

            {/* AI Evaluation Progress Banner */}
            {aiEvalProgress && aiEvalProgress.status !== 'idle' && (
                <div className="fixed top-4 right-4 z-50 bg-white border border-blue-200 rounded-xl shadow-lg p-4 w-80 animate-in slide-in-from-right"
                     data-testid="ai-eval-progress-banner">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            {(aiEvalProgress.status === 'running' || aiEvalProgress.status === 'starting') && <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />}
                            {aiEvalProgress.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
                            {aiEvalProgress.status === 'error' && <XCircle className="w-4 h-4 text-red-600" />}
                            <span className="text-sm font-semibold text-slate-800">
                                {aiEvalProgress.status === 'starting' && 'Iniciando evaluación IA...'}
                                {aiEvalProgress.status === 'running' && 'Evaluación IA en progreso'}
                                {aiEvalProgress.status === 'completed' && 'Evaluación IA completada'}
                                {aiEvalProgress.status === 'error' && 'Evaluación IA con errores'}
                            </span>
                        </div>
                        <button onClick={() => setAiEvalProgress(null)} className="text-slate-400 hover:text-slate-600">
                            <X className="w-3.5 h-3.5" />
                        </button>
                    </div>
                    {aiEvalProgress.total > 0 && (
                        <>
                            <div className="h-2 bg-slate-100 rounded-full overflow-hidden mb-1.5">
                                <div className="h-full rounded-full transition-all duration-500"
                                     style={{
                                         width: `${Math.round((aiEvalProgress.evaluated / aiEvalProgress.total) * 100)}%`,
                                         backgroundColor: aiEvalProgress.status === 'error' ? '#EF4444' :
                                                         aiEvalProgress.status === 'completed' ? '#10B981' : '#3B82F6',
                                     }} />
                            </div>
                            <div className="flex items-center justify-between text-xs text-slate-500">
                                <span>{aiEvalProgress.evaluated} / {aiEvalProgress.total} paquetes</span>
                                <span className="font-mono">{Math.round((aiEvalProgress.evaluated / aiEvalProgress.total) * 100)}%</span>
                            </div>
                            {aiEvalProgress.errors > 0 && (
                                <p className="text-[10px] text-red-500 mt-1">{aiEvalProgress.errors} error(es) durante evaluación</p>
                            )}
                        </>
                    )}
                </div>
            )}

            {/* ReviewModal */}
            <ReviewModal
                open={reviewModalOpen}
                onClose={() => { setReviewModalOpen(false); setReviewModalPkg(null); }}
                pkg={reviewModalPkg}
                action={reviewModalAction}
                onConfirm={handleReviewModalConfirm}
                saving={savingReview === reviewModalPkg?.id}
            />

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

export default GuiasTab;
