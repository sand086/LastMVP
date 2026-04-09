import React, { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Loader2 } from 'lucide-react';

const REJECT_REASONS = [
    { value: 'evidencia_insuficiente', label: 'Evidencia insuficiente' },
    { value: 'fotos_no_corresponden', label: 'Fotos no corresponden a la entrega' },
    { value: 'guia_ilegible', label: 'Guía ilegible' },
    { value: 'falta_foto_receptor', label: 'Falta foto de receptor' },
    { value: 'score_ia_alto', label: 'Score de IA demasiado alto' },
    { value: 'otro', label: 'Otro' },
];

const APPROVE_REASONS = [
    { value: 'evidencia_suficiente', label: 'Evidencia suficiente a pesar del score bajo' },
    { value: 'contexto_operativo_valido', label: 'Contexto operativo válido (tercero autorizado)' },
    { value: 'score_ia_bajo', label: 'Score de IA demasiado bajo' },
    { value: 'otro', label: 'Otro' },
];

export default function ReviewModal({ open, onClose, pkg, action, onConfirm, saving }) {
    const isApproval = action === 'approve';
    const reasons = isApproval ? APPROVE_REASONS : REJECT_REASONS;

    const [adjustedScore, setAdjustedScore] = useState(pkg?.ai_score ?? 0);
    const [reasonCategory, setReasonCategory] = useState('');
    const [reasonDetail, setReasonDetail] = useState('');
    const [aiIncorrect, setAiIncorrect] = useState(false);

    // Reset state when package or action changes
    React.useEffect(() => {
        if (open && pkg) {
            setAdjustedScore(pkg.ai_score ?? 0);
            setReasonCategory('');
            setReasonDetail('');
            setAiIncorrect(false);
        }
    }, [open, pkg?.id, action]);

    const handleConfirm = () => {
        onConfirm({
            action: isApproval ? 'approved' : 'rejected',
            original_ai_score: pkg?.ai_score ?? 0,
            adjusted_score: adjustedScore,
            reason_category: reasonCategory,
            reason_detail: reasonDetail,
            ai_evaluation_incorrect: aiIncorrect,
        });
    };

    const guide = pkg?.order_reference_id || pkg?.tracking_number || '';

    return (
        <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
            <DialogContent className="max-w-md" data-testid="review-modal">
                <DialogHeader>
                    <DialogTitle className="text-base">
                        {isApproval ? 'Confirmar aprobación' : 'Confirmar rechazo'} — {guide}
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    {/* Score slider */}
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Score ajustado</label>
                        <div className="flex items-center gap-3">
                            <input type="range" min={0} max={100} value={adjustedScore}
                                   onChange={e => setAdjustedScore(Number(e.target.value))}
                                   className="flex-1 accent-blue-600 h-2" data-testid="adjusted-score-slider" />
                            <Input type="number" min={0} max={100} value={adjustedScore}
                                   onChange={e => setAdjustedScore(Math.max(0, Math.min(100, Number(e.target.value))))}
                                   className="w-16 text-center font-mono font-bold text-sm h-8"
                                   data-testid="adjusted-score-input" />
                        </div>
                        {pkg?.ai_score != null && adjustedScore !== pkg.ai_score && (
                            <p className="text-[10px] text-slate-400 mt-1">Score original IA: {pkg.ai_score} → Ajustado: {adjustedScore}</p>
                        )}
                    </div>

                    {/* Reason dropdown */}
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Motivo</label>
                        <select value={reasonCategory} onChange={e => setReasonCategory(e.target.value)}
                                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500"
                                data-testid="reason-category-select">
                            <option value="">Seleccionar motivo...</option>
                            {reasons.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                        </select>
                    </div>

                    {/* Free text detail */}
                    <div>
                        <label className="text-xs font-semibold text-slate-600 block mb-1">Detalle (opcional)</label>
                        <textarea value={reasonDetail} onChange={e => setReasonDetail(e.target.value)}
                                  placeholder="Observaciones adicionales..."
                                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm h-16 resize-none focus:ring-2 focus:ring-blue-500"
                                  data-testid="reason-detail-input" />
                    </div>

                    {/* AI incorrect toggle */}
                    <div className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2.5 border border-slate-200">
                        <div>
                            <p className="text-xs font-semibold text-slate-700">Evaluación IA incorrecta</p>
                            <p className="text-[10px] text-slate-400">Marca si la IA cometió un error (falso positivo/negativo)</p>
                        </div>
                        <button onClick={() => setAiIncorrect(!aiIncorrect)}
                                className={`relative w-10 h-5 rounded-full transition-colors ${aiIncorrect ? 'bg-red-500' : 'bg-slate-300'}`}
                                data-testid="ai-incorrect-toggle">
                            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${aiIncorrect ? 'left-5' : 'left-0.5'}`} />
                        </button>
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" size="sm" onClick={onClose} data-testid="review-modal-cancel">Cancelar</Button>
                    <Button size="sm" onClick={handleConfirm} disabled={saving || !reasonCategory}
                            className={isApproval ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-red-600 hover:bg-red-700 text-white'}
                            data-testid="review-modal-confirm">
                        {saving && <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />}
                        {isApproval ? 'Confirmar aprobación' : 'Confirmar rechazo'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
