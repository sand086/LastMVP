import React, { useState, useMemo } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Loader2, Check, X, Minus, AlertTriangle, ChevronDown } from 'lucide-react';

/* ─── Criterion definitions by delivery type ─── */
export const CRITERIA = {
    A: {
        label: 'Entrega Exitosa',
        items: [
            { key: 'foto_fachada', label: 'Foto de fachada', weight: 25, critical: true, desc: 'Fachada visible con numero exterior' },
            { key: 'foto_paquete_guia', label: 'Paquete con guia', weight: 25, critical: true, desc: 'Paquete integro con guia legible' },
            { key: 'foto_receptor', label: 'Foto de receptor', weight: 25, critical: false, desc: 'Persona recibiendo el paquete' },
            { key: 'nota_driver', label: 'Nota del driver', weight: 15, critical: false, desc: 'Nota confirmando a quien se entrego' },
            { key: 'timestamp', label: 'Timestamp visible', weight: 10, critical: false, desc: 'Hora visible en al menos 1 foto' },
        ],
    },
    B: {
        label: 'Entrega a Terceros',
        items: [
            { key: 'foto_fachada', label: 'Foto de fachada', weight: 20, critical: true, desc: 'Fachada visible con numero exterior' },
            { key: 'foto_paquete_guia', label: 'Paquete con guia', weight: 20, critical: true, desc: 'Paquete integro con guia legible' },
            { key: 'foto_tercero', label: 'Tercero recibiendo', weight: 20, critical: false, desc: 'Persona (vecino/familiar/vigilante)' },
            { key: 'mensaje_whatsapp', label: 'Mensaje WhatsApp', weight: 20, critical: true, desc: 'Notificacion al cliente final' },
            { key: 'nota_driver', label: 'Nota del driver', weight: 10, critical: false, desc: 'Nombre/parentesco del receptor' },
            { key: 'timestamp', label: 'Timestamp', weight: 10, critical: false, desc: 'Hora visible' },
        ],
    },
    C: {
        label: 'Entrega Fallida',
        items: [
            { key: 'foto_fachada', label: 'Foto fachada (sin persona)', weight: 25, critical: true, desc: 'Fachada antes de retirarse' },
            { key: 'log_llamadas', label: 'Log de llamadas (3+)', weight: 30, critical: true, desc: '3 intentos de llamada visibles' },
            { key: 'mensaje_notificacion', label: 'Mensaje al cliente', weight: 25, critical: false, desc: 'WhatsApp de intento fallido' },
            { key: 'registro_sistema', label: 'Registro en sistema', weight: 20, critical: false, desc: 'Incidencia activa vinculada' },
        ],
    },
};

/* ─── Rejection reasons catalog (9 options) ─── */
export const REJECTION_REASONS = [
    { value: 'foto_fachada_ausente', label: 'Foto de fachada ausente o inadecuada' },
    { value: 'guia_ilegible', label: 'Guia de envio ilegible' },
    { value: 'foto_receptor_ausente', label: 'Foto de receptor/tercero ausente' },
    { value: 'evidencia_borrosa', label: 'Evidencia borrosa o fuera de foco' },
    { value: 'paquete_no_visible', label: 'Paquete no visible en la entrega' },
    { value: 'llamadas_insuficientes', label: 'Menos de 3 llamadas registradas' },
    { value: 'whatsapp_ausente', label: 'Captura de WhatsApp no proporcionada' },
    { value: 'timestamp_inconsistente', label: 'Timestamp no coincide con hora de entrega' },
    { value: 'otro', label: 'Otro motivo (especificar)' },
];

/* ─── Auto-detect delivery type from package ─── */
export function detectDeliveryType(pkg) {
    if (!pkg) return 'A';
    const status = (pkg.status || '').toLowerCase();
    const evidence = pkg.evidence_detail || {};
    const deliveryType = (evidence.delivery_type_detected || '').toLowerCase();
    const driverNote = (pkg.kosmo_driver_note || pkg.delivery_note || '').toLowerCase();

    // Allow short codes (A/B/C) — used when persisted from manual review.
    if (deliveryType === 'a') return 'A';
    if (deliveryType === 'b') return 'B';
    if (deliveryType === 'c') return 'C';

    if (status === 'failed' || status === 'returned' || deliveryType === 'fallida') return 'C';
    if (deliveryType === 'terceros' || deliveryType === 'tercero' || deliveryType === 'vecino' || deliveryType === 'familiar') return 'B';
    if (driverNote.includes('vecino') || driverNote.includes('tercero') || driverNote.includes('vigilante') || driverNote.includes('familiar') || driverNote.includes('portero')) return 'B';
    return 'A';
}

/* ─── Map AI criteria_met to criterion states ─── */
function mapAiCriteria(pkg, criteria) {
    const detail = pkg?.evidence_detail || {};
    const criteriaMet = detail.criteria_met || {};
    const result = {};
    for (const item of criteria) {
        if (criteriaMet[item.key] === true) result[item.key] = 'pass';
        else if (criteriaMet[item.key] === false) result[item.key] = 'fail';
        else result[item.key] = null; // unevaluated
    }
    return result;
}

/* ─── Calculate score from criteria states ─── */
function calculateScore(criteriaStates, criteriaItems) {
    let score = 0;
    let hasCriticalFail = false;
    for (const item of criteriaItems) {
        if (criteriaStates[item.key] === 'pass') {
            score += item.weight;
        }
        if (item.critical && criteriaStates[item.key] === 'fail') {
            hasCriticalFail = true;
        }
    }
    if (hasCriticalFail && score > 50) score = 50;
    return Math.min(score, 100);
}

/* ─── Criterion Card ─── */
const CriterionCard = ({ item, state, aiState, onChange }) => {
    const colors = {
        pass: { bg: '#F0FDF4', border: '#86EFAC', icon: Check, text: '#16A34A' },
        fail: { bg: '#FEF2F2', border: '#FCA5A5', icon: X, text: '#DC2626' },
        null: { bg: '#F8F7F4', border: '#E2E0DB', icon: Minus, text: '#9C9A92' },
    };
    const c = colors[state] || colors.null;
    const Icon = c.icon;
    const hasDiscrepancy = aiState !== undefined && aiState !== null && state !== null && aiState !== state;

    return (
        <div style={{ padding: '10px 14px', borderRadius: 8, border: `1.5px solid ${c.border}`, background: c.bg, cursor: 'pointer', transition: 'all 0.15s', position: 'relative' }}
             data-testid={`criterion-${item.key}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 24, height: 24, borderRadius: 6, background: c.text + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Icon size={14} color={c.text} strokeWidth={2.5} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#1A1916' }}>{item.label}</span>
                        {item.critical && <span style={{ fontSize: 8, fontWeight: 700, padding: '1px 4px', borderRadius: 3, background: '#FEF2F2', color: '#DC2626', textTransform: 'uppercase' }}>Critico</span>}
                    </div>
                    <p style={{ fontSize: 10, color: '#9C9A92', margin: 0, marginTop: 1 }}>{item.desc}</p>
                </div>
                <div style={{ display: 'flex', gap: 4 }}>
                    <button onClick={() => onChange(item.key, 'pass')} style={{ width: 26, height: 26, borderRadius: 6, border: state === 'pass' ? '2px solid #16A34A' : '1px solid #E2E0DB', background: state === 'pass' ? '#F0FDF4' : '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }} data-testid={`criterion-pass-${item.key}`}>
                        <Check size={13} color={state === 'pass' ? '#16A34A' : '#D4D4D4'} />
                    </button>
                    <button onClick={() => onChange(item.key, 'fail')} style={{ width: 26, height: 26, borderRadius: 6, border: state === 'fail' ? '2px solid #DC2626' : '1px solid #E2E0DB', background: state === 'fail' ? '#FEF2F2' : '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }} data-testid={`criterion-fail-${item.key}`}>
                        <X size={13} color={state === 'fail' ? '#DC2626' : '#D4D4D4'} />
                    </button>
                </div>
            </div>
            {hasDiscrepancy && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 6, padding: '3px 8px', borderRadius: 4, background: '#FFFBEB', fontSize: 10, color: '#D97706' }}>
                    <AlertTriangle size={10} /> Discrepancia: IA dijo {aiState === 'pass' ? 'Cumple' : 'No cumple'}, tu dices {state === 'pass' ? 'Cumple' : 'No cumple'}
                </div>
            )}
        </div>
    );
};

export default function ReviewModal({ open, onClose, pkg, action, onConfirm, saving }) {
    const [deliveryType, setDeliveryType] = useState('A');
    const [criteriaStates, setCriteriaStates] = useState({});
    const [rejectionReason, setRejectionReason] = useState('');
    const [reasonDetail, setReasonDetail] = useState('');
    const [showRejectPanel, setShowRejectPanel] = useState(false);

    const criteria = CRITERIA[deliveryType] || CRITERIA.A;

    const aiCriteriaStates = useMemo(() => {
        return mapAiCriteria(pkg, criteria.items);
    }, [pkg, criteria.items]);

    React.useEffect(() => {
        if (open && pkg) {
            const detected = detectDeliveryType(pkg);
            setDeliveryType(detected);
            const initial = mapAiCriteria(pkg, (CRITERIA[detected] || CRITERIA.A).items);
            setCriteriaStates(initial);
            setRejectionReason('');
            setReasonDetail('');
            setShowRejectPanel(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally depends on pkg.id only, not the full object
    }, [open, pkg?.id]);

    const calculatedScore = useMemo(() => calculateScore(criteriaStates, criteria.items), [criteriaStates, criteria.items]);

    const discrepancies = useMemo(() => {
        const disc = [];
        for (const item of criteria.items) {
            const ai = aiCriteriaStates[item.key];
            const manual = criteriaStates[item.key];
            if (ai !== undefined && ai !== null && manual !== null && ai !== manual) {
                disc.push({ key: item.key, label: item.label, ai_said: ai, human_said: manual });
            }
        }
        return disc;
    }, [aiCriteriaStates, criteriaStates, criteria.items]);

    const hasFailedCritical = criteria.items.some(i => i.critical && criteriaStates[i.key] === 'fail');
    const allEvaluated = criteria.items.every(i => criteriaStates[i.key] === 'pass' || criteriaStates[i.key] === 'fail');
    const isApproval = calculatedScore >= 70 && !hasFailedCritical;

    const handleCriterionChange = (key, state) => {
        setCriteriaStates(prev => ({ ...prev, [key]: prev[key] === state ? null : state }));
    };

    // Bulk toggle: marca todos los criterios como pass / desmarca todos a null en un click.
    // Útil para casos donde el coordinador ya validó visualmente toda la evidencia
    // y solo quiere registrar el "todo OK" sin click por click.
    const allPass = criteria.items.every(i => criteriaStates[i.key] === 'pass');
    const handleToggleAll = () => {
        const next = {};
        if (allPass) {
            // Todos pass → reset a null (desmarcar todos)
            criteria.items.forEach(i => { next[i.key] = null; });
        } else {
            // Marcar todos como pass
            criteria.items.forEach(i => { next[i.key] = 'pass'; });
        }
        setCriteriaStates(next);
    };

    const handleConfirm = () => {
        const decision = showRejectPanel ? 'rejected' : 'approved';
        onConfirm({
            action: decision,
            delivery_type: deliveryType,
            criteria_evaluation: criteriaStates,
            original_ai_score: pkg?.ai_score ?? 0,
            adjusted_score: calculatedScore,
            reason_category: rejectionReason || (isApproval ? 'aprobado_por_criterios' : ''),
            reason_detail: reasonDetail,
            ai_evaluation_incorrect: discrepancies.length > 0,
            discrepancies: discrepancies,
        });
    };

    const guide = pkg?.order_reference_id || pkg?.tracking_number || '';
    const scoreColor = calculatedScore >= 90 ? '#16A34A' : calculatedScore >= 70 ? '#EF9F27' : '#E24B4A';

    return (
        <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
            <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="review-modal">
                <DialogHeader>
                    <DialogTitle className="text-base flex items-center gap-2">
                        Evaluacion de evidencia — <span className="font-mono text-sm text-slate-500">{guide}</span>
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-1">
                    {/* Delivery type selector */}
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-slate-500">Tipo de entrega:</span>
                        {['A', 'B', 'C'].map(t => (
                            <button key={t} onClick={() => { setDeliveryType(t); setCriteriaStates(mapAiCriteria(pkg, CRITERIA[t].items)); }}
                                    className={`px-3 py-1 rounded-md text-xs font-semibold transition-colors ${deliveryType === t ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                                    data-testid={`delivery-type-${t}`}>
                                {t} — {CRITERIA[t].label}
                            </button>
                        ))}
                    </div>

                    {/* Score display */}
                    <div className="flex items-center gap-4 p-3 rounded-lg" style={{ background: '#F8F7F4', border: '1px solid #E2E0DB' }}>
                        <div style={{ width: 52, height: 52, borderRadius: '50%', border: `3px solid ${scoreColor}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <span style={{ fontSize: 18, fontWeight: 700, fontFamily: "'DM Mono', monospace", color: scoreColor }}>{calculatedScore}</span>
                        </div>
                        <div>
                            <p className="text-xs font-semibold text-slate-700">Score calculado por criterios</p>
                            {pkg?.ai_score != null && (
                                <p className="text-[10px] text-slate-400">Score IA original: {pkg.ai_score}</p>
                            )}
                            {hasFailedCritical && (
                                <p className="text-[10px] text-red-500 font-semibold mt-0.5">Criterio critico fallido — cap 50pts</p>
                            )}
                        </div>
                        <div className="ml-auto text-right">
                            {allEvaluated ? (
                                <span className={`text-xs font-bold px-2.5 py-1 rounded ${isApproval ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                                    {isApproval ? 'APROBADO' : 'RECHAZADO'}
                                </span>
                            ) : (
                                <span className="text-[10px] text-slate-400">Evalua todos los criterios</span>
                            )}
                        </div>
                    </div>

                    {/* Criteria cards */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{criteria.label} — {criteria.items.length} criterios</p>
                            <label
                                className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer select-none hover:text-slate-900 transition-colors"
                                data-testid="criteria-toggle-all-label"
                                title={allPass ? 'Desmarcar todos los criterios' : 'Marcar todos como Cumple'}
                            >
                                <input
                                    type="checkbox"
                                    checked={allPass}
                                    onChange={handleToggleAll}
                                    className="w-4 h-4 rounded border-slate-300 cursor-pointer"
                                    data-testid="criteria-toggle-all"
                                />
                                <span className="font-medium">{allPass ? 'Desmarcar todos' : 'Marcar todos como Cumple'}</span>
                            </label>
                        </div>
                        {criteria.items.map(item => (
                            <CriterionCard key={item.key} item={item} state={criteriaStates[item.key] || null} aiState={aiCriteriaStates[item.key]} onChange={handleCriterionChange} />
                        ))}
                    </div>

                    {/* Discrepancy summary */}
                    {discrepancies.length > 0 && (
                        <div className="p-3 rounded-lg bg-amber-50 border border-amber-200">
                            <p className="text-xs font-bold text-amber-700 mb-1">{discrepancies.length} discrepancia(s) IA vs Manual</p>
                            {discrepancies.map(d => (
                                <p key={d.key} className="text-[10px] text-amber-600">• {d.label}: IA={d.ai_said === 'pass' ? 'Cumple' : 'No cumple'} → Manual={d.human_said === 'pass' ? 'Cumple' : 'No cumple'}</p>
                            ))}
                        </div>
                    )}

                    {/* Rejection panel */}
                    {!isApproval && allEvaluated && (
                        <div className="space-y-3 p-3 rounded-lg bg-red-50 border border-red-200">
                            <p className="text-xs font-bold text-red-700">Motivo de rechazo</p>
                            <select value={rejectionReason} onChange={e => setRejectionReason(e.target.value)}
                                    className="w-full border border-red-200 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-red-400"
                                    data-testid="rejection-reason-select">
                                <option value="">Seleccionar motivo...</option>
                                {REJECTION_REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                            </select>
                            <textarea value={reasonDetail} onChange={e => setReasonDetail(e.target.value)}
                                      placeholder="Detalle adicional (opcional)..."
                                      className="w-full border border-red-200 rounded-lg px-3 py-2 text-sm h-14 resize-none bg-white focus:ring-2 focus:ring-red-400"
                                      data-testid="rejection-detail-input" />
                        </div>
                    )}

                    {/* Override: force reject even if score >=70 */}
                    {isApproval && allEvaluated && (
                        <button onClick={() => setShowRejectPanel(!showRejectPanel)}
                                className="w-full text-left text-xs text-red-600 hover:text-red-700 flex items-center gap-1 py-1"
                                data-testid="force-reject-toggle">
                            <ChevronDown size={12} className={`transition-transform ${showRejectPanel ? 'rotate-180' : ''}`} />
                            Rechazar manualmente (override)
                        </button>
                    )}
                    {showRejectPanel && (
                        <div className="space-y-3 p-3 rounded-lg bg-red-50 border border-red-200">
                            <p className="text-xs font-bold text-red-700">Rechazo manual (override de score {calculatedScore})</p>
                            <select value={rejectionReason} onChange={e => setRejectionReason(e.target.value)}
                                    className="w-full border border-red-200 rounded-lg px-3 py-2 text-sm bg-white"
                                    data-testid="override-rejection-select">
                                <option value="">Seleccionar motivo...</option>
                                {REJECTION_REASONS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                            </select>
                            <textarea value={reasonDetail} onChange={e => setReasonDetail(e.target.value)}
                                      placeholder="Detalle..." className="w-full border border-red-200 rounded-lg px-3 py-2 text-sm h-14 resize-none bg-white"
                                      data-testid="override-rejection-detail" />
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" size="sm" onClick={onClose} data-testid="review-modal-cancel">Cancelar</Button>
                    <Button size="sm" onClick={handleConfirm}
                            disabled={saving || !allEvaluated || (showRejectPanel && !rejectionReason) || (!isApproval && allEvaluated && !rejectionReason)}
                            className={(!showRejectPanel && isApproval) ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-red-600 hover:bg-red-700 text-white'}
                            data-testid="review-modal-confirm">
                        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />}
                        {showRejectPanel ? 'Confirmar rechazo' : isApproval ? 'Confirmar aprobacion' : allEvaluated ? 'Confirmar rechazo' : 'Evalua todos los criterios'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
