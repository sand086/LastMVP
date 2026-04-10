import React from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
    Loader2, Check, X, CheckCircle2, ShieldCheck, FileWarning,
} from 'lucide-react';
import { SeverityBadge, getMaxSeverity, getErrorSeverity, DiscRow } from './GuiasHelpers';

const GuiasPackageDetail = ({
    pkg,
    proofUrls,
    hasErrors,
    hasDiscrepancy,
    reviewDecision,
    canReview,
    isReadOnly,
    savingReview,
    rejectingPkg,
    rejectNote,
    setRejectNote,
    setRejectingPkg,
    onApprove,
    onReject,
    onDiscrepancyReview,
    onRegisterIncident,
    onOpenReviewModal,
    openCarousel,
}) => {
    return (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
            {/* Col 1: Evidencias Kosmo */}
            <div className="space-y-2">
                <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Evidencias Kosmo</p>
                {proofUrls.length > 0 ? (
                    <div className="flex gap-2 flex-wrap">
                        {proofUrls.slice(0, 4).map((url, i) => (
                            <button key={`thumb-${pkg.id}-${i}`}
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
                                    <div key={`err-${pkg.id}-${i}`} className="flex items-center gap-1.5">
                                        <X className="w-3 h-3 shrink-0 text-red-600" />
                                        <span className="text-xs text-red-700 flex-1">{err}</span>
                                        <SeverityBadge level={getErrorSeverity(err, pkg.ia_errors_raw, pkg.ia_severity)} />
                                    </div>
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

                {/* Discrepancy review */}
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
                                    onClick={() => onDiscrepancyReview(pkg, 'confirm_return')}
                                    disabled={savingReview === pkg.id}
                                    data-testid={`confirm-return-${pkg.id}`}>
                                {savingReview === pkg.id ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
                                Confirmar devolución
                            </Button>
                            <Button size="sm" variant="outline" className="h-7 text-xs"
                                    onClick={() => onDiscrepancyReview(pkg, 'mark_valid')}
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
                                            onKeyDown={e => { if (e.key === 'Enter') onReject(pkg); }} />
                                        <div className="flex gap-2">
                                            <Button size="sm" variant="destructive" className="h-7 text-xs"
                                                    onClick={() => onReject(pkg)} disabled={savingReview === pkg.id}
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
                                                onClick={() => onOpenReviewModal(pkg, 'approve')} disabled={savingReview === pkg.id}
                                                data-testid={`approve-btn-${pkg.id}`}>
                                            <Check className="w-3 h-3 mr-1" />Aprobar
                                        </Button>
                                        <Button size="sm" variant="outline" className="h-7 text-xs border-red-300 text-red-700 hover:bg-red-50"
                                                onClick={() => onOpenReviewModal(pkg, 'reject')} data-testid={`reject-btn-${pkg.id}`}>
                                            <X className="w-3 h-3 mr-1" /> Rechazar
                                        </Button>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}

                {/* Inline incident registration button */}
                {canReview && onRegisterIncident && (
                    <div className="mt-3 pt-3 border-t border-slate-200">
                        <Button size="sm" variant="outline" className="h-7 text-xs border-amber-300 text-amber-700 hover:bg-amber-50 w-full justify-center"
                                onClick={() => onRegisterIncident(pkg)}
                                data-testid={`register-incident-btn-${pkg.id}`}>
                            <FileWarning className="w-3 h-3 mr-1" /> Registrar Incidencia
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default GuiasPackageDetail;
