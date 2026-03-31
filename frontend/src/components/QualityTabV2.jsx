import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
    getQualitySummary, getPackagesQuality, getQualitySettings,
    evaluateAllEvidence, evaluatePackageEvidence, saveTrainingSample,
} from '../lib/api';
import {
    Camera, Search, Loader2, ExternalLink, Info, AlertTriangle,
    ChevronLeft, ChevronRight, CheckCircle2, XCircle, Filter,
    BookOpen, Sparkles, RefreshCw, Check, X,
} from 'lucide-react';
import { toast } from 'sonner';
import EvidenceCarousel from '../components/EvidenceCarousel';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF', green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB', coral: '#DC2626', coralLt: '#FEF2F2',
    teal: '#0D9488', tealLt: '#F0FDFA', purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

const scoreColor = (s) => s >= 90 ? T.green : s >= 70 ? T.amber : T.coral;
const confColor = (c) => c >= 80 ? T.green : c >= 60 ? T.amber : T.coral;
const attemptColor = (n) => n === 1 ? T.green : n === 2 ? T.amber : T.coral;
const attemptLabel = (n) => n === 1 ? '1º' : n === 2 ? '2º' : '3er';

const ScoreCircle = ({ score }) => {
    const c = scoreColor(score);
    return (
        <div data-testid="score-circle" style={{ width: 36, height: 36, borderRadius: '50%', background: c + '18', border: `2px solid ${c}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: c }}>{score}</span>
        </div>
    );
};

const ConfidenceBar = ({ confidence }) => {
    const pct = Math.round((confidence || 0) * 100);
    const c = confColor(pct);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, fontFamily: "'DM Mono',monospace", fontWeight: 600, color: c, minWidth: 32 }}>{pct}%</span>
            <div style={{ width: 50, height: 6, borderRadius: 3, background: T.surface2 }}>
                <div style={{ height: '100%', borderRadius: 3, width: `${pct}%`, background: c, transition: 'width 0.3s' }} />
            </div>
        </div>
    );
};

const IntentBadge = ({ n }) => {
    const c = attemptColor(n);
    return (
        <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: c + '18', color: c }}>{attemptLabel(n)}</span>
    );
};

const ReviewStatus = ({ status }) => {
    if (status === 'approved') return <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.green }}><CheckCircle2 size={14} /> Aprobada</span>;
    if (status === 'rejected') return <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.coral }}><XCircle size={14} /> Rechazada</span>;
    return <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.textTer }}><div style={{ width: 12, height: 12, borderRadius: '50%', border: `2px solid ${T.borderStrong}` }} /> Pendiente</span>;
};

const ErrorChip = ({ errKey, severity, label }) => {
    const isCrit = severity === 'critical';
    const bg = isCrit ? T.coralLt : T.amberLt;
    const border = isCrit ? T.coral + '40' : T.amber + '40';
    const color = isCrit ? T.coral : T.amber;
    return (
        <span data-testid={`error-chip-${errKey}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500, background: bg, border: `1px solid ${border}`, color, whiteSpace: 'nowrap' }}>
            {isCrit ? <AlertTriangle size={10} /> : <Info size={10} />}
            {label}
        </span>
    );
};

const OkChip = () => (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 500, background: T.greenLt, border: `1px solid ${T.green}30`, color: T.green }}>
        <Check size={10} /> Todas correctas
    </span>
);

/* ═══════ EXPANDED DETAIL PANEL ═══════ */
const ExpandedPanel = ({ pkg, catalogMap, journeyId, onTrainingDone, canEdit }) => {
    const [trainingState, setTrainingState] = useState(pkg.review_status === 'approved' ? 'correct' : pkg.review_status === 'rejected' ? 'incorrect' : null);
    const [feedbackMode, setFeedbackMode] = useState(null); // null | 'correct' | 'incorrect'
    const [humanNote, setHumanNote] = useState('');
    const [correctedScore, setCorrectedScore] = useState(pkg.ia_score ?? 0);
    const [correctedErrors, setCorrectedErrors] = useState([]);
    const [saving, setSaving] = useState(false);

    const errors = pkg.ia_errors || [];
    const feedback = pkg.ia_feedback || '';
    const photos = pkg.kosmo_proof_urls || [];
    const detail = pkg.evidence_detail || {};
    const photosAnalysis = detail.photos_analysis || [];

    const submitTraining = async (label) => {
        setSaving(true);
        try {
            await saveTrainingSample({
                journey_id: journeyId,
                guide: pkg.guide,
                delivery_type: pkg.delivery_type,
                human_label: label,
                human_note: humanNote,
                corrected_score: label === 'incorrect' ? correctedScore : undefined,
                corrected_errors: label === 'incorrect' ? correctedErrors : [],
            });
            setTrainingState(label);
            setFeedbackMode(null);
            toast.success(label === 'correct' ? 'Evaluación marcada como correcta' : 'Corrección registrada para entrenamiento IA');
            if (onTrainingDone) onTrainingDone(pkg.guide, label === 'correct' ? 'approved' : 'rejected');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Error al guardar muestra');
        } finally {
            setSaving(false);
        }
    };

    const getPhotoType = (index) => {
        if (photosAnalysis[index]) return photosAnalysis[index].photo_type || 'foto';
        if (index === 0) return 'fachada';
        if (index === 1) return 'paquete';
        if (index === 2) return 'receptor';
        return 'foto';
    };

    const getPhotoStatus = (index) => {
        if (!photosAnalysis[index]) return 'unknown';
        const q = photosAnalysis[index].quality;
        if (q === 'buena') return 'ok';
        if (q === 'aceptable') return 'warn';
        return 'fail';
    };

    const photoStatusBorder = (s) => s === 'ok' ? T.green : s === 'warn' ? T.amber : s === 'fail' ? T.coral : T.border;
    const photoStatusIcon = (s) => s === 'ok' ? '✓' : s === 'warn' ? '⚠' : s === 'fail' ? '✗' : '';

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, padding: '16px 20px', background: T.surface2, borderTop: `1px solid ${T.border}` }} data-testid={`expanded-${pkg.guide}`}>
            {/* Left: Evaluation details */}
            <div>
                <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: T.textPri }}>Evaluación IA detallada</p>
                {errors.length > 0 ? errors.map((errKey) => {
                    const cat = catalogMap[errKey] || {};
                    const sev = (pkg.ia_severity || {})[errKey] || 'warning';
                    return (
                        <div key={errKey} style={{ padding: '10px 12px', borderRadius: T.radiusSm, border: `1px solid ${sev === 'critical' ? T.coral + '30' : T.amber + '30'}`, background: sev === 'critical' ? T.coralLt : T.amberLt, marginBottom: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                {sev === 'critical' ? <AlertTriangle size={13} color={T.coral} /> : <Info size={13} color={T.amber} />}
                                <span style={{ fontSize: 13, fontWeight: 600, color: sev === 'critical' ? T.coral : T.amber }}>{cat.label || errKey.replace(/_/g, ' ')}</span>
                            </div>
                        </div>
                    );
                }) : (
                    <div style={{ padding: '10px 12px', borderRadius: T.radiusSm, border: `1px solid ${T.green}30`, background: T.greenLt, marginBottom: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <CheckCircle2 size={13} color={T.green} />
                            <span style={{ fontSize: 13, fontWeight: 600, color: T.green }}>Todas las evidencias correctas</span>
                        </div>
                    </div>
                )}
                {feedback && (
                    <p style={{ fontSize: 12, color: T.textSec, marginTop: 8, lineHeight: 1.5 }}>{feedback}</p>
                )}
                {pkg.kosmo_note && (
                    <p style={{ fontSize: 12, color: T.textTer, marginTop: 6 }}>Nota Kosmo: "{pkg.kosmo_note}"</p>
                )}

                {/* ══ TRAINING SECTION — always visible for coordinators/developers ══ */}
                {canEdit && (
                    <div style={{ marginTop: 16, padding: 14, border: `1px solid ${T.purple}30`, borderRadius: T.radius, background: T.surface }} data-testid={`training-section-${pkg.guide}`}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                            <BookOpen size={14} color={T.purple} />
                            <span style={{ fontSize: 13, fontWeight: 600, color: T.textPri }}>Entrenamiento supervisado</span>
                            <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, background: T.purpleLt, color: T.purple, fontWeight: 600 }}>IA Learning</span>
                        </div>

                        {/* Already submitted state */}
                        {trainingState === 'correct' && !feedbackMode ? (
                            <div style={{ padding: '10px 14px', borderRadius: T.radiusSm, background: T.greenLt, border: `1px solid ${T.green}30` }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                    <CheckCircle2 size={14} color={T.green} />
                                    <span style={{ fontSize: 13, fontWeight: 600, color: T.green }}>Evaluación aprobada</span>
                                </div>
                                <p style={{ fontSize: 11, color: T.textSec }}>Contribuye al entrenamiento del modelo IA</p>
                                <button onClick={() => { setTrainingState(null); setFeedbackMode(null); }} style={{ marginTop: 8, fontSize: 11, color: T.textTer, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Cambiar decisión</button>
                            </div>
                        ) : trainingState === 'incorrect' && !feedbackMode ? (
                            <div style={{ padding: '10px 14px', borderRadius: T.radiusSm, background: T.coralLt, border: `1px solid ${T.coral}30` }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                    <XCircle size={14} color={T.coral} />
                                    <span style={{ fontSize: 13, fontWeight: 600, color: T.coral }}>Evaluación corregida</span>
                                </div>
                                <p style={{ fontSize: 11, color: T.textSec }}>Registrada en banco de entrenamiento para mejorar el modelo</p>
                                <button onClick={() => { setTrainingState(null); setFeedbackMode(null); }} style={{ marginTop: 8, fontSize: 11, color: T.textTer, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Cambiar decisión</button>
                            </div>

                        /* ── FEEDBACK FORM: Incorrect ── */
                        ) : feedbackMode === 'incorrect' ? (
                            <div>
                                <p style={{ fontSize: 12, fontWeight: 500, color: T.textPri, marginBottom: 10 }}>¿Por qué la evaluación es incorrecta?</p>

                                {/* Natural language explanation */}
                                <textarea
                                    value={humanNote}
                                    onChange={e => setHumanNote(e.target.value)}
                                    placeholder="Explica en lenguaje natural qué observas diferente a lo que evaluó la IA. Ej: 'Sí hay foto del receptor, es la segunda imagen donde se ve a una persona recibiendo el paquete...'"
                                    style={{ width: '100%', minHeight: 70, padding: 10, borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, fontFamily: "'DM Sans',sans-serif", resize: 'vertical', lineHeight: 1.5, color: T.textPri, background: T.surface }}
                                    data-testid={`training-note-${pkg.guide}`}
                                />

                                {/* Score override */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, padding: '10px 14px', borderRadius: T.radiusSm, background: T.surface2 }}>
                                    <span style={{ fontSize: 12, fontWeight: 500, color: T.textSec, whiteSpace: 'nowrap' }}>Modificar Score a:</span>
                                    <input
                                        type="range"
                                        min={0}
                                        max={100}
                                        value={correctedScore}
                                        onChange={e => setCorrectedScore(Number(e.target.value))}
                                        style={{ flex: 1, accentColor: scoreColor(correctedScore) }}
                                        data-testid={`training-score-slider-${pkg.guide}`}
                                    />
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <input
                                            type="number"
                                            min={0}
                                            max={100}
                                            value={correctedScore}
                                            onChange={e => setCorrectedScore(Math.max(0, Math.min(100, Number(e.target.value))))}
                                            style={{ width: 52, padding: '4px 6px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 14, fontWeight: 700, fontFamily: "'DM Mono',monospace", textAlign: 'center', color: scoreColor(correctedScore) }}
                                            data-testid={`training-score-input-${pkg.guide}`}
                                        />
                                        <span style={{ fontSize: 14, fontWeight: 600, color: T.textTer }}>%</span>
                                    </div>
                                </div>

                                {/* Error checkboxes */}
                                <p style={{ fontSize: 12, color: T.textSec, marginTop: 12, marginBottom: 6 }}>Errores reales (selecciona los que aplican):</p>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
                                    {Object.values(catalogMap).filter(e => e.active !== false).map(e => (
                                        <label key={e.key} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 8px', borderRadius: 4, fontSize: 11, cursor: 'pointer', background: correctedErrors.includes(e.key) ? T.coralLt : T.surface2, border: `1px solid ${correctedErrors.includes(e.key) ? T.coral + '50' : T.border}`, transition: 'all 0.15s' }}>
                                            <input type="checkbox" checked={correctedErrors.includes(e.key)} onChange={(ev) => {
                                                setCorrectedErrors(prev => ev.target.checked ? [...prev, e.key] : prev.filter(k => k !== e.key));
                                            }} style={{ width: 12, height: 12 }} />
                                            {e.label}
                                        </label>
                                    ))}
                                </div>

                                {/* Actions */}
                                <div style={{ display: 'flex', gap: 8 }}>
                                    <button
                                        onClick={() => submitTraining('incorrect')}
                                        disabled={saving}
                                        style={{ flex: 1, padding: '8px 14px', borderRadius: T.radiusSm, background: T.coral, color: '#fff', border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: "'DM Sans'", opacity: saving ? 0.6 : 1 }}
                                        data-testid={`training-submit-incorrect-${pkg.guide}`}
                                    >
                                        {saving ? 'Guardando...' : 'Confirmar corrección'}
                                    </button>
                                    <button
                                        onClick={() => { setFeedbackMode(null); setHumanNote(''); setCorrectedScore(pkg.ia_score ?? 0); setCorrectedErrors([]); }}
                                        style={{ padding: '8px 14px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, background: T.surface, color: T.textSec, fontSize: 12, cursor: 'pointer', fontFamily: "'DM Sans'" }}
                                    >
                                        Cancelar
                                    </button>
                                </div>
                            </div>

                        /* ── FEEDBACK FORM: Correct ── */
                        ) : feedbackMode === 'correct' ? (
                            <div>
                                <p style={{ fontSize: 12, fontWeight: 500, color: T.textPri, marginBottom: 10 }}>¿Algún comentario adicional? <span style={{ color: T.textTer }}>(opcional)</span></p>
                                <textarea
                                    value={humanNote}
                                    onChange={e => setHumanNote(e.target.value)}
                                    placeholder="Ej: 'La IA evaluó correctamente, la foto del receptor se ve claramente en la imagen 3...'"
                                    style={{ width: '100%', minHeight: 50, padding: 10, borderRadius: T.radiusSm, border: `1px solid ${T.border}`, fontSize: 12, fontFamily: "'DM Sans',sans-serif", resize: 'vertical', lineHeight: 1.5, color: T.textPri, background: T.surface }}
                                    data-testid={`training-note-correct-${pkg.guide}`}
                                />
                                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                                    <button
                                        onClick={() => submitTraining('correct')}
                                        disabled={saving}
                                        style={{ flex: 1, padding: '8px 14px', borderRadius: T.radiusSm, background: T.green, color: '#fff', border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: "'DM Sans'", opacity: saving ? 0.6 : 1 }}
                                        data-testid={`training-submit-correct-${pkg.guide}`}
                                    >
                                        {saving ? 'Guardando...' : 'Confirmar aprobación'}
                                    </button>
                                    <button
                                        onClick={() => { setFeedbackMode(null); setHumanNote(''); }}
                                        style={{ padding: '8px 14px', borderRadius: T.radiusSm, border: `1px solid ${T.border}`, background: T.surface, color: T.textSec, fontSize: 12, cursor: 'pointer', fontFamily: "'DM Sans'" }}
                                    >
                                        Cancelar
                                    </button>
                                </div>
                            </div>

                        /* ── INITIAL BUTTONS ── */
                        ) : (
                            <div>
                                <p style={{ fontSize: 12, color: T.textSec, marginBottom: 10 }}>¿La evaluación de IA (Score: <strong style={{ fontFamily: "'DM Mono'", color: scoreColor(pkg.ia_score || 0) }}>{pkg.ia_score ?? '—'}%</strong>) es correcta?</p>
                                <div style={{ display: 'flex', gap: 8 }}>
                                    <button
                                        onClick={() => { setFeedbackMode('correct'); setHumanNote(''); }}
                                        style={{ flex: 1, padding: '10px', borderRadius: T.radiusSm, border: `1.5px solid ${T.green}50`, background: T.greenLt, color: T.green, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: "'DM Sans'", transition: 'all 0.15s' }}
                                        data-testid={`training-correct-${pkg.guide}`}
                                    >
                                        <CheckCircle2 size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }} />
                                        Sí, es correcta
                                    </button>
                                    <button
                                        onClick={() => { setFeedbackMode('incorrect'); setHumanNote(''); setCorrectedScore(pkg.ia_score ?? 0); setCorrectedErrors(errors); }}
                                        style={{ flex: 1, padding: '10px', borderRadius: T.radiusSm, border: `1.5px solid ${T.coral}50`, background: T.coralLt, color: T.coral, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: "'DM Sans'", transition: 'all 0.15s' }}
                                        data-testid={`training-incorrect-${pkg.guide}`}
                                    >
                                        <XCircle size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }} />
                                        No, corregir
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Right: Photos & metadata */}
            <div>
                <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: T.textPri }}>Fotos de evidencia ({photos.length})</p>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
                    {photos.map((url, i) => {
                        const type = getPhotoType(i);
                        const status = getPhotoStatus(i);
                        const borderC = photoStatusBorder(status);
                        return (
                            <div key={`photo-${type}-${i}`} style={{ position: 'relative', width: 64, height: 64, borderRadius: T.radiusSm, border: `2px solid ${borderC}`, overflow: 'hidden', cursor: 'pointer' }}>
                                <img src={url} alt={type} style={{ width: '100%', height: '100%', objectFit: 'cover' }} loading="lazy" />
                                <span style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '1px 4px', fontSize: 9, background: 'rgba(0,0,0,0.7)', color: '#fff', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden' }}>
                                    {type.replace(/_/g, ' ')} {photoStatusIcon(status)}
                                </span>
                            </div>
                        );
                    })}
                </div>
                {/* Metadata */}
                <div style={{ fontSize: 12, color: T.textSec }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '6px 12px' }}>
                        <span style={{ color: T.textTer }}>Método</span>
                        <span style={{ fontWeight: 500 }}>
                            <span style={{ padding: '2px 6px', borderRadius: 3, fontSize: 10, background: T.blueLt, color: T.blue, fontWeight: 600 }}>
                                IA · {pkg.evidence_method === 'ai' ? 'Claude' : 'Reglas'}
                            </span>
                        </span>
                        <span style={{ color: T.textTer }}>Confianza</span>
                        <span>{pkg.ia_confidence ? `${Math.round(pkg.ia_confidence * 100)}%` : '—'}</span>
                        {pkg.ia_evaluated_at && <>
                            <span style={{ color: T.textTer }}>Evaluado el</span>
                            <span>{new Date(pkg.ia_evaluated_at).toLocaleString('es-MX', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                        </>}
                        <span style={{ color: T.textTer }}>Intento</span>
                        <span>{attemptLabel(pkg.attempt_number)} intento</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

/* ═══════════════════════════════════════════ */
/*           QUALITY TAB V2 MAIN              */
/* ═══════════════════════════════════════════ */

const QualityTabV2 = ({ journeyId, journeyData, onRefreshJourney }) => {
    const { user } = useAuth();
    const canEdit = ['coordinator', 'developer'].includes(user?.role);

    const [summary, setSummary] = useState(null);
    const [packages, setPackages] = useState([]);
    const [totalPkgs, setTotalPkgs] = useState(0);
    const [page, setPage] = useState(1);
    const [pages, setPages] = useState(1);
    const [expandedRow, setExpandedRow] = useState(null);
    const [alertsOnly, setAlertsOnly] = useState(false);
    const [loading, setLoading] = useState(true);
    const [evaluating, setEvaluating] = useState(false);
    const [evaluatingPkg, setEvaluatingPkg] = useState(null);
    const [iaConfig, setIaConfig] = useState(null);
    const [catalogMap, setCatalogMap] = useState({});

    // Carousel
    const [carouselOpen, setCarouselOpen] = useState(false);
    const [carouselImages, setCarouselImages] = useState([]);
    const [carouselIndex, setCarouselIndex] = useState(0);
    const [carouselPkgInfo, setCarouselPkgInfo] = useState(null);

    const fetchData = useCallback(async (p = 1) => {
        setLoading(true);
        try {
            const [sumRes, pkgRes, cfgRes] = await Promise.all([
                getQualitySummary(journeyId),
                getPackagesQuality(journeyId, { page: p, page_size: 25, alerts_only: alertsOnly }),
                getQualitySettings(),
            ]);
            setSummary(sumRes.data);
            setPackages(pkgRes.data.packages);
            setTotalPkgs(pkgRes.data.total);
            setPages(pkgRes.data.pages);
            setPage(pkgRes.data.page);

            const cfg = cfgRes.data;
            setIaConfig(cfg.ia_config || {});
            const catMap = {};
            (cfg.error_catalog || []).forEach(e => { catMap[e.key] = e; });
            setCatalogMap(catMap);
        } catch {
            toast.error('Error al cargar datos de calidad');
        } finally {
            setLoading(false);
        }
    }, [journeyId, alertsOnly]);

    useEffect(() => { fetchData(1); }, [fetchData]);

    const handleEvaluateAll = async () => {
        setEvaluating(true);
        try {
            await evaluateAllEvidence(journeyId);
            toast.success('Evaluación IA iniciada');
            setTimeout(() => { fetchData(page); if (onRefreshJourney) onRefreshJourney(); }, 3000);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Error al evaluar con IA');
        } finally {
            setEvaluating(false);
        }
    };

    const handleEvaluatePkg = async (pkg) => {
        setEvaluatingPkg(pkg.guide);
        try {
            await evaluatePackageEvidence(journeyId, pkg.guide);
            toast.success(`Evaluación completada para ${pkg.guide}`);
            fetchData(page);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Error al evaluar');
        } finally {
            setEvaluatingPkg(null);
        }
    };

    const handleTrainingDone = (guide, newStatus) => {
        setPackages(prev => prev.map(p => p.guide === guide ? { ...p, review_status: newStatus } : p));
        if (summary) setSummary(prev => ({ ...prev, reviewed_count: (prev.reviewed_count || 0) + 1 }));
    };

    const openCarousel = (pkg, startIndex = 0) => {
        const urls = pkg.kosmo_proof_urls || [];
        const imgs = urls.map((url, i) => ({ url, analysis: (pkg.evidence_detail?.photos_analysis || [])[i] || null }));
        if (!imgs.length) return;
        setCarouselImages(imgs);
        setCarouselIndex(startIndex);
        setCarouselPkgInfo({ guide: pkg.guide, deliveryType: pkg.delivery_type, score: pkg.ia_score });
        setCarouselOpen(true);
    };

    if (loading) return <div style={{ padding: 60, textAlign: 'center', color: T.textTer }}>Cargando calidad...</div>;

    if (!summary || summary.total === 0) {
        return (
            <div style={{ padding: 40, textAlign: 'center' }}>
                <Sparkles size={40} color={T.borderStrong} style={{ margin: '0 auto 12px' }} />
                <p style={{ color: T.textSec, marginBottom: 16 }}>No hay evaluaciones de calidad disponibles.</p>
                {journeyData?.status === 'closed' && (
                    <button onClick={handleEvaluateAll} disabled={evaluating} style={{ padding: '10px 20px', borderRadius: T.radiusSm, border: 'none', background: T.textPri, color: '#fff', fontSize: 13, cursor: 'pointer', fontFamily: "'DM Sans'" }} data-testid="evaluate-empty-btn">
                        {evaluating ? 'Evaluando...' : 'Evaluar con IA'}
                    </button>
                )}
            </div>
        );
    }

    const s = summary;
    const d = s.distribution;
    const scoreDelta = s.score_avg - s.score_target;

    return (
        <div data-testid="quality-tab-v2">
            {/* KPI Strip */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, overflow: 'hidden', marginBottom: 16 }} data-testid="quality-kpi-strip">
                {/* Score Avg */}
                <div style={{ padding: '16px 20px', borderRight: `1px solid ${T.border}` }}>
                    <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Score promedio</p>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                        <span style={{ fontSize: 28, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: scoreColor(s.score_avg) }}>{s.score_avg}%</span>
                        <span style={{ fontSize: 11, color: T.textTer }}>Target: {s.score_target}%</span>
                    </div>
                    <div style={{ height: 6, borderRadius: 3, background: T.surface2, marginTop: 8 }}>
                        <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(s.score_avg, 100)}%`, background: scoreColor(s.score_avg), transition: 'width 0.3s' }} />
                    </div>
                </div>
                {/* Completos */}
                <div style={{ padding: '16px 20px', borderRight: `1px solid ${T.border}` }}>
                    <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Completos</p>
                    <span style={{ fontSize: 28, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.green }}>{d.complete}<span style={{ fontSize: 16, color: T.textTer }}>/{s.total}</span></span>
                    <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>Todas las evidencias correctas</p>
                </div>
                {/* Incompletos */}
                <div style={{ padding: '16px 20px', borderRight: `1px solid ${T.border}` }}>
                    <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Incompletos</p>
                    <span style={{ fontSize: 28, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.coral }}>{d.incomplete}</span>
                    <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>Sin ninguna evidencia</p>
                </div>
                {/* Evaluados IA */}
                <div style={{ padding: '16px 20px' }}>
                    <p style={{ fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Evaluados IA</p>
                    <span style={{ fontSize: 28, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.blue }}>{s.evaluated_ia}<span style={{ fontSize: 16, color: T.textTer }}>/{s.total}</span></span>
                    <p style={{ fontSize: 11, color: T.textTer, marginTop: 4 }}>Confianza prom: <strong>{s.confidence_avg}%</strong></p>
                </div>
            </div>

            {/* Distribution Bar */}
            <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, padding: '14px 20px', marginBottom: 16 }}>
                <p style={{ fontSize: 12, fontWeight: 600, color: T.textSec, marginBottom: 8 }}>Distribución de calidad</p>
                <div style={{ display: 'flex', height: 20, borderRadius: 4, overflow: 'hidden', border: `1px solid ${T.border}` }} data-testid="distribution-bar">
                    {d.complete_pct > 0 && <div style={{ width: `${d.complete_pct}%`, background: T.green, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 10, fontWeight: 600, fontFamily: "'DM Mono'" }}>{d.complete_pct}%</div>}
                    {d.partial_pct > 0 && <div style={{ width: `${d.partial_pct}%`, background: T.amber, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 10, fontWeight: 600, fontFamily: "'DM Mono'" }}>{d.partial_pct}%</div>}
                    {d.incomplete_pct > 0 && <div style={{ width: `${d.incomplete_pct}%`, background: T.coral, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 10, fontWeight: 600, fontFamily: "'DM Mono'" }}>{d.incomplete_pct}%</div>}
                </div>
                <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11, color: T.textSec }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: T.green }} /> Completos ({d.complete}) · {d.complete_pct}%</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: T.amber }} /> Parciales ({d.partial}) · {d.partial_pct}%</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: T.coral }} /> Incompletos ({d.incomplete}) · {d.incomplete_pct}%</span>
                </div>
            </div>

            {/* Error Summary Banner */}
            {s.error_summary && s.error_summary.length > 0 && (
                <div style={{ border: `1px solid ${T.purple}30`, borderRadius: T.radius, background: T.purpleLt, padding: '14px 20px', marginBottom: 16 }} data-testid="error-summary-banner">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                        <Sparkles size={15} color={T.purple} />
                        <span style={{ fontSize: 13, fontWeight: 600, color: T.purple }}>Errores detectados por IA en esta ruta</span>
                        <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, background: T.tealLt, color: T.teal, fontWeight: 600 }}>Nuevo</span>
                    </div>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                        {s.error_summary.map(e => (
                            <div key={e.key} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: T.radiusSm, background: T.surface, border: `1px solid ${T.purple}20` }}>
                                <span style={{ fontSize: 12, color: T.textSec }}>{e.label}</span>
                                <span style={{ fontSize: 13, fontWeight: 700, fontFamily: "'DM Mono',monospace", color: T.purple }}>{e.count}</span>
                            </div>
                        ))}
                    </div>
                    {s.action_suggestion && (
                        <p style={{ fontSize: 12, color: T.textSec }}>Acción sugerida: <strong>{s.action_suggestion}</strong></p>
                    )}
                </div>
            )}

            {/* Table Controls */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: T.textPri }}>Detalle por paquete</span>
                    <span style={{ fontSize: 12, color: T.textTer }}>{s.reviewed_count}/{s.total} revisados manualmente</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer', fontSize: 12, color: T.textSec }}>
                        <input type="checkbox" checked={alertsOnly} onChange={e => setAlertsOnly(e.target.checked)} style={{ width: 14, height: 14 }} data-testid="alerts-only-checkbox" />
                        Solo con alertas
                    </label>
                    <div style={{ width: 1, height: 20, background: T.border }} />
                    <button onClick={handleEvaluateAll} disabled={evaluating} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', borderRadius: T.radiusSm, border: 'none', background: T.textPri, color: '#fff', fontSize: 12, cursor: 'pointer', fontFamily: "'DM Sans'", opacity: evaluating ? 0.6 : 1 }} data-testid="evaluate-ia-btn">
                        {evaluating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                        Evaluar IA
                    </button>
                </div>
            </div>

            {/* Packages Table */}
            <div style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, background: T.surface, overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                        <thead>
                            <tr style={{ background: T.surface2, borderBottom: `1px solid ${T.border}` }}>
                                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase', letterSpacing: '0.03em' }}>Guía</th>
                                <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Tipo</th>
                                <th style={{ padding: '10px 12px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Score IA</th>
                                <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Confianza</th>
                                <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Errores detectados</th>
                                <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Fotos</th>
                                <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Intento</th>
                                <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Revisión</th>
                                <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: T.textTer, textTransform: 'uppercase' }}>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            {packages.map(pkg => {
                                const isExpanded = expandedRow === pkg.guide;
                                const isEval = evaluatingPkg === pkg.guide;
                                const errors = pkg.ia_errors || [];
                                const typeColors = { exitosa: { bg: T.greenLt, c: T.green }, terceros: { bg: T.blueLt, c: T.blue }, fallida: { bg: T.coralLt, c: T.coral } };
                                const tc = typeColors[pkg.delivery_type] || { bg: T.surface2, c: T.textSec };

                                return (
                                    <React.Fragment key={pkg.id || pkg.guide}>
                                        <tr
                                            onClick={() => setExpandedRow(isExpanded ? null : pkg.guide)}
                                            style={{ cursor: 'pointer', borderBottom: `1px solid ${T.border}`, background: isExpanded ? T.surface2 : 'transparent', transition: 'background 0.15s' }}
                                            data-testid={`quality-row-${pkg.guide}`}
                                            onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.background = T.surface2; }}
                                            onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.background = 'transparent'; }}
                                        >
                                            <td style={{ padding: '10px 16px', fontFamily: "'DM Mono',monospace", fontSize: 12 }}>{pkg.guide}</td>
                                            <td style={{ padding: '10px 12px' }}>
                                                <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 500, background: tc.bg, color: tc.c }}>{pkg.delivery_type === 'exitosa' ? 'Exitosa' : pkg.delivery_type === 'terceros' ? 'Terceros' : 'Fallida'}</span>
                                            </td>
                                            <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                                                {pkg.ia_score != null ? <ScoreCircle score={pkg.ia_score} /> : <span style={{ color: T.textTer }}>—</span>}
                                            </td>
                                            <td style={{ padding: '10px 12px' }}>
                                                {pkg.ia_confidence != null ? <ConfidenceBar confidence={pkg.ia_confidence} /> : <span style={{ fontSize: 12, color: T.textTer }}>—</span>}
                                            </td>
                                            <td style={{ padding: '10px 12px' }}>
                                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                                    {errors.length > 0 ? errors.slice(0, 3).map(ek => (
                                                        <ErrorChip key={ek} errKey={ek} severity={(pkg.ia_severity || {})[ek] || 'warning'} label={catalogMap[ek]?.label || ek.replace(/_/g, ' ')} />
                                                    )) : (pkg.ia_score != null && <OkChip />)}
                                                    {errors.length > 3 && <span style={{ fontSize: 11, color: T.textTer, alignSelf: 'center' }}>+{errors.length - 3}</span>}
                                                </div>
                                            </td>
                                            <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                                                <button onClick={e => { e.stopPropagation(); openCarousel(pkg); }} style={{ display: 'flex', alignItems: 'center', gap: 3, background: 'none', border: 'none', color: T.blue, cursor: 'pointer', fontSize: 12, margin: '0 auto' }} data-testid={`photos-btn-${pkg.guide}`}>
                                                    <Camera size={13} /> {pkg.photo_count}
                                                </button>
                                            </td>
                                            <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                                                <IntentBadge n={pkg.attempt_number || 1} />
                                            </td>
                                            <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                                                <ReviewStatus status={pkg.review_status} />
                                            </td>
                                            <td style={{ padding: '10px 8px', textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                                                <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                                                    <button onClick={() => handleEvaluatePkg(pkg)} disabled={isEval} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 6px', cursor: 'pointer' }} data-testid={`eval-pkg-${pkg.guide}`}>
                                                        {isEval ? <Loader2 size={13} className="animate-spin" color={T.textTer} /> : <Search size={13} color={T.textSec} />}
                                                    </button>
                                                    {pkg.tracking_url && (
                                                        <a href={pkg.tracking_url} target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 6px' }}>
                                                            <ExternalLink size={13} color={T.blue} />
                                                        </a>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                        {/* Expanded row */}
                                        {isExpanded && (
                                            <tr>
                                                <td colSpan={9} style={{ padding: 0 }}>
                                                    <ExpandedPanel
                                                        pkg={pkg}
                                                        catalogMap={catalogMap}
                                                        journeyId={journeyId}
                                                        onTrainingDone={handleTrainingDone}
                                                        canEdit={canEdit}
                                                    />
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
                {/* Pagination */}
                {pages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '12px 20px', borderTop: `1px solid ${T.border}` }}>
                        <button onClick={() => fetchData(page - 1)} disabled={page <= 1} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 8px', cursor: page <= 1 ? 'default' : 'pointer', opacity: page <= 1 ? 0.4 : 1 }}>
                            <ChevronLeft size={14} />
                        </button>
                        <span style={{ fontSize: 12, color: T.textSec }}>Página {page} de {pages}</span>
                        <button onClick={() => fetchData(page + 1)} disabled={page >= pages} style={{ background: 'none', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, padding: '4px 8px', cursor: page >= pages ? 'default' : 'pointer', opacity: page >= pages ? 0.4 : 1 }}>
                            <ChevronRight size={14} />
                        </button>
                    </div>
                )}
            </div>

            {/* Footer note */}
            <p style={{ fontSize: 11, color: T.textTer, marginTop: 8, textAlign: 'center' }}>
                Mostrando {packages.length} de {totalPkgs} paquetes · Click en una fila para ver el detalle IA
            </p>

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

export default QualityTabV2;
