import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
    getQualityCriteria, updateQualityCriteria, resetQualityCriteria,
    getQualitySettings, patchQualitySettings,
} from '../lib/api';
import {
    Save, RotateCcw, Plus, Trash2, Camera, ShieldCheck, Sparkles,
    AlertTriangle, Info, Target, BarChart3, Zap, BookOpen, CheckCircle2,
    RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';

const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF', green: '#16A34A', greenLt: '#F0FDF4',
    amber: '#D97706', amberLt: '#FFFBEB', coral: '#DC2626', coralLt: '#FEF2F2',
    teal: '#0D9488', tealLt: '#F0FDFA', purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

const inp = { padding: '7px 10px', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, fontSize: 13, fontFamily: "'DM Mono', monospace", outline: 'none', width: '100%', background: T.surface, color: T.textPri };
const inpSm = { ...inp, width: 64, textAlign: 'center' };
const sel = { ...inp, fontFamily: "'DM Sans', sans-serif", appearance: 'none', backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B6960' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center', paddingRight: 28 };

const Toggle = ({ checked, onChange, disabled, testId }) => (
    <button
        type="button" role="switch" aria-checked={checked}
        onClick={() => !disabled && onChange(!checked)}
        data-testid={testId}
        style={{ width: 40, height: 22, borderRadius: 11, background: checked ? T.green : T.borderStrong, border: 'none', cursor: disabled ? 'default' : 'pointer', position: 'relative', transition: 'background 0.2s', opacity: disabled ? 0.5 : 1 }}>
        <span style={{ position: 'absolute', top: 2, left: checked ? 20 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.15)' }} />
    </button>
);

const Pill = ({ children, bg, color }) => (
    <span style={{ padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 500, background: bg, color, whiteSpace: 'nowrap' }}>{children}</span>
);

/* ═══════════════ TAB 1: EVIDENCIAS ═══════════════ */
const EvidenciasTab = ({ criteria, setCriteria, setDirty, canEdit }) => {
    if (!criteria) return null;
    const updateDT = (dtype, field, value) => {
        setCriteria(prev => ({ ...prev, delivery_types: { ...prev.delivery_types, [dtype]: { ...prev.delivery_types[dtype], [field]: value } } }));
        setDirty(true);
    };
    const updateEv = (dtype, idx, item) => { const arr = [...criteria.delivery_types[dtype].required_evidence]; arr[idx] = item; updateDT(dtype, 'required_evidence', arr); };
    const removeEv = (dtype, key) => updateDT(dtype, 'required_evidence', criteria.delivery_types[dtype].required_evidence.filter(e => e.key !== key));
    const addEv = (dtype) => updateDT(dtype, 'required_evidence', [...criteria.delivery_types[dtype].required_evidence, { key: `custom_${Date.now()}`, label: 'Nueva evidencia', required: true, weight: 0 }]);
    const updateRule = (dtype, rk, rule) => updateDT(dtype, 'scoring_rules', { ...criteria.delivery_types[dtype].scoring_rules, [rk]: rule });

    const typeInfo = { exitosa: { label: 'Entrega Exitosa', pill: T.greenLt, pillC: T.green }, terceros: { label: 'Entrega a Terceros', pill: T.blueLt, pillC: T.blue }, fallida: { label: 'Entrega Fallida', pill: T.coralLt, pillC: T.coral } };

    return (
        <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Keywords */}
            <div style={{ padding: 16, border: `1px solid ${T.border}`, borderRadius: T.radiusSm, background: T.blueLt }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Info size={15} color={T.blue} /><span style={{ fontSize: 13, fontWeight: 600 }}>Keywords de detección de terceros</span>
                </div>
                <p style={{ fontSize: 12, color: T.textTer, marginBottom: 8 }}>Palabras clave en la nota del driver que indican entrega a terceros.</p>
                <input
                    type="text" value={(criteria.third_party_keywords || []).join(', ')}
                    onChange={e => { setCriteria(p => ({ ...p, third_party_keywords: e.target.value.split(',').map(k => k.trim()).filter(Boolean) })); setDirty(true); }}
                    style={inp} disabled={!canEdit} data-testid="third-party-keywords-input"
                />
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
                    {(criteria.third_party_keywords || []).map((kw, i) => <Pill key={i} bg={T.blueLt} color={T.blue}>{kw}</Pill>)}
                </div>
            </div>
            {/* Delivery types */}
            {Object.entries(criteria.delivery_types || {}).map(([dtype, cfg]) => {
                const ti = typeInfo[dtype] || {};
                return (
                    <div key={dtype} style={{ border: `1px solid ${T.border}`, borderRadius: T.radius, overflow: 'hidden' }} data-testid={`delivery-type-${dtype}`}>
                        <div style={{ padding: '14px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: T.surface2 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <Pill bg={ti.pill} color={ti.pillC}>{dtype}</Pill>
                                <span style={{ fontWeight: 600, fontSize: 14 }}>{ti.label}</span>
                                <span style={{ fontSize: 12, color: T.textTer }}>{cfg.required_evidence?.length || 0} evidencias</span>
                            </div>
                            {canEdit && <button onClick={() => addEv(dtype)} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, background: T.surface, fontSize: 12, cursor: 'pointer', fontFamily: "'DM Sans'" }} data-testid={`add-evidence-${dtype}`}><Plus size={13} />Agregar evidencia</button>}
                        </div>
                        {cfg.notes && (
                            <div style={{ padding: '10px 20px', background: T.amberLt, borderBottom: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', gap: 8 }}>
                                <AlertTriangle size={14} color={T.amber} /><span style={{ fontSize: 12, color: T.amber }}>{cfg.notes}</span>
                            </div>
                        )}
                        <div style={{ padding: '0 20px' }}>
                            {/* Header row */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 140px 70px 40px', gap: 8, padding: '10px 0', fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.03em', borderBottom: `1px solid ${T.border}` }}>
                                <span>Descripción</span><span>Clave</span><span style={{ textAlign: 'center' }}>Peso</span><span />
                            </div>
                            {(cfg.required_evidence || []).map((ev, idx) => (
                                <div key={ev.key} style={{ display: 'grid', gridTemplateColumns: '1fr 140px 70px 40px', gap: 8, padding: '8px 0', alignItems: 'center', borderBottom: `1px solid ${T.border}` }}>
                                    <input type="text" value={ev.label} onChange={e => updateEv(dtype, idx, { ...ev, label: e.target.value })} style={inp} disabled={!canEdit} data-testid={`ev-label-${ev.key}`} />
                                    <span style={{ fontSize: 12, fontFamily: "'DM Mono'", color: T.textSec, padding: '7px 10px', background: T.surface2, borderRadius: T.radiusSm }}>{ev.key}</span>
                                    <input type="number" value={ev.weight} onChange={e => updateEv(dtype, idx, { ...ev, weight: parseInt(e.target.value) || 0 })} style={inpSm} disabled={!canEdit} min={0} max={100} />
                                    {canEdit && <button onClick={() => removeEv(dtype, ev.key)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textTer, padding: 4 }}><Trash2 size={14} /></button>}
                                </div>
                            ))}
                        </div>
                        {/* Scoring rules */}
                        <div style={{ padding: '12px 20px', background: T.surface2 }}>
                            <p style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Reglas de puntuación</p>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                {Object.entries(cfg.scoring_rules || {}).map(([rk, rule]) => (
                                    <div key={rk} style={{ padding: '6px 12px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radiusSm, fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                                        <span style={{ fontFamily: "'DM Mono'", fontWeight: 500 }}>{rule.score}%</span>
                                        <span style={{ color: T.textSec }}>{rule.label}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

/* ═══════════════ TAB 2: KPIs ═══════════════ */
const KpiTab = ({ data, setData, setDirty, canEdit }) => {
    if (!data) return null;
    const w = data.weights || {};
    const total = (w.delivery_rate || 0) + (w.visit_rate || 0) + (w.evidence_quality || 0);
    const valid = total === 100;
    const minV = data.score_min_acceptable || 0;
    const tgtV = data.score_target || 0;
    const excV = data.score_excellent || 0;

    const upd = (key, val) => { setData(p => ({ ...p, [key]: val })); setDirty(true); };
    const updW = (key, val) => { setData(p => ({ ...p, weights: { ...p.weights, [key]: val } })); setDirty(true); };

    return (
        <div style={{ padding: 24 }}>
            <div style={{ padding: '12px 16px', background: T.blueLt, borderRadius: T.radiusSm, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <Info size={15} color={T.blue} /><span>Define los umbrales que determinan los colores de pills en Dashboard y Reportes, y la ponderación del KPI compuesto.</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
                {/* Left: Targets */}
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Targets globales de calidad</h4>
                    {[
                        { key: 'score_min_acceptable', label: 'Mínimo aceptable', desc: 'Debajo de este valor → alerta coral', color: T.coral },
                        { key: 'score_target', label: 'Target operativo', desc: 'Objetivo estándar → verde', color: T.green },
                        { key: 'score_excellent', label: 'Excelente', desc: 'Rendimiento sobresaliente → teal', color: T.teal },
                    ].map(f => (
                        <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                            <div style={{ width: 10, height: 10, borderRadius: '50%', background: f.color, flexShrink: 0 }} />
                            <div style={{ flex: 1 }}>
                                <p style={{ fontSize: 13, fontWeight: 500 }}>{f.label}</p>
                                <p style={{ fontSize: 11, color: T.textTer }}>{f.desc}</p>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <input type="number" value={data[f.key] || 0} onChange={e => upd(f.key, Number(e.target.value))} style={inpSm} disabled={!canEdit} data-testid={`kpi-${f.key}`} min={0} max={100} />
                                <span style={{ fontSize: 12, color: T.textTer }}>%</span>
                            </div>
                        </div>
                    ))}
                    {/* Scale bar */}
                    <div style={{ marginTop: 16, height: 20, borderRadius: 4, display: 'flex', overflow: 'hidden', border: `1px solid ${T.border}` }} data-testid="scale-bar">
                        <div style={{ width: `${minV}%`, background: T.coral, transition: 'width 0.3s' }} />
                        <div style={{ width: `${Math.max(0, tgtV - minV)}%`, background: T.amber, transition: 'width 0.3s' }} />
                        <div style={{ width: `${Math.max(0, excV - tgtV)}%`, background: T.green, transition: 'width 0.3s' }} />
                        <div style={{ flex: 1, background: T.teal }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: T.textTer, marginTop: 4 }}>
                        <span>0</span><span>{minV}</span><span>{tgtV}</span><span>{excV}</span><span>100</span>
                    </div>
                </div>
                {/* Right: Weights */}
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Ponderación de rubros en el KPI global</h4>
                    {[
                        { key: 'delivery_rate', label: 'Tasa de entrega exitosa', color: T.green },
                        { key: 'visit_rate', label: 'Tasa de visita efectiva', color: T.blue },
                        { key: 'evidence_quality', label: 'Calidad de evidencias', color: T.purple },
                    ].map(f => (
                        <div key={f.key} style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                <span style={{ fontSize: 13, color: T.textSec }}>{f.label}</span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <input type="number" value={w[f.key] || 0} onChange={e => updW(f.key, Number(e.target.value))} style={inpSm} disabled={!canEdit} min={0} max={100} data-testid={`weight-${f.key}`} />
                                    <span style={{ fontSize: 12, color: T.textTer }}>%</span>
                                </div>
                            </div>
                            <div style={{ height: 8, borderRadius: 4, background: T.surface2 }}>
                                <div style={{ height: '100%', borderRadius: 4, width: `${w[f.key] || 0}%`, background: f.color, transition: 'width 0.3s' }} />
                            </div>
                        </div>
                    ))}
                    <div style={{ padding: '10px 14px', borderRadius: T.radiusSm, background: valid ? T.greenLt : T.amberLt, display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }} data-testid="weights-validation">
                        {valid ? <CheckCircle2 size={14} color={T.green} /> : <AlertTriangle size={14} color={T.amber} />}
                        <span style={{ fontSize: 12, fontWeight: 500, color: valid ? T.green : T.amber }}>
                            {valid ? `Total: ${total}% — Ponderación válida` : `Total: ${total}% — Debe sumar 100%`}
                        </span>
                    </div>
                    {/* Critical failure */}
                    <div style={{ marginTop: 20, padding: 14, border: `1px solid ${T.border}`, borderRadius: T.radiusSm }}>
                        <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Regla de falla crítica</p>
                        <p style={{ fontSize: 12, color: T.textTer, marginBottom: 8 }}>Si la evidencia clave falta, el score máximo se limita a:</p>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 12, fontFamily: "'DM Mono'", color: T.coral, background: T.coralLt, padding: '2px 8px', borderRadius: 4 }}>{data.critical_failure_cap?.trigger_key || 'foto_paquete_guia'}</span>
                            <span style={{ fontSize: 12, color: T.textTer }}>→ Max score:</span>
                            <input type="number" value={data.critical_failure_cap?.max_score_if_failed || 40} onChange={e => upd('critical_failure_cap', { ...data.critical_failure_cap, max_score_if_failed: Number(e.target.value) })} style={inpSm} disabled={!canEdit} data-testid="critical-cap-score" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

/* ═══════════════ TAB 3: SLA ═══════════════ */
const SlaTab = ({ brackets, setBrackets, rubroTargets, setRubroTargets, penalties, setPenalties, strikePolicy, setStrikePolicy, setDirty, canEdit }) => {
    const addBracket = () => { setBrackets(p => [...p, { id: `bracket_${Date.now()}`, label: 'Nuevo', description: '', target: 80, status: 'pending' }]); setDirty(true); };
    const updBracket = (i, f, v) => { setBrackets(p => { const a = [...p]; a[i] = { ...a[i], [f]: v }; return a; }); setDirty(true); };
    const addPenalty = () => { setPenalties(p => [...p, { id: `p${Date.now()}`, label: '', discount_pct: 0, applies_to: 'provider' }]); setDirty(true); };
    const updPenalty = (i, f, v) => { setPenalties(p => { const a = [...p]; a[i] = { ...a[i], [f]: v }; return a; }); setDirty(true); };
    const removePenalty = (i) => { setPenalties(p => p.filter((_, j) => j !== i)); setDirty(true); };
    const updRubro = (key, val) => { setRubroTargets(p => ({ ...p, [key]: { ...p[key], target: val } })); setDirty(true); };
    const updStrike = (key, val) => { setStrikePolicy(p => ({ ...p, [key]: val })); setDirty(true); };

    const bracketStatusColors = { exceeded: T.green, active: T.amber, pending: T.textTer };
    const bracketStatusLabels = { exceeded: 'Superado', active: 'En curso', pending: 'Pendiente' };

    return (
        <div style={{ padding: 24 }}>
            <div style={{ padding: '12px 16px', background: T.blueLt, borderRadius: T.radiusSm, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <Info size={15} color={T.blue} /><span>Define targets de SLA por período de madurez, penalizaciones por tipo de fallo, y la política de strikes.</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
                {/* Left */}
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Brackets de escalamiento SLA</h4>
                    {(brackets || []).map((b, i) => (
                        <div key={b.id} style={{ padding: 12, borderRadius: T.radiusSm, background: b.status === 'active' ? T.surface2 : T.surface, border: `1px solid ${b.status === 'active' ? T.blue : T.border}`, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 12 }} data-testid={`bracket-${b.id}`}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <input type="text" value={b.label} onChange={e => updBracket(i, 'label', e.target.value)} style={{ ...inp, fontWeight: 500, marginBottom: 4 }} disabled={!canEdit} />
                                <input type="text" value={b.description || ''} onChange={e => updBracket(i, 'description', e.target.value)} style={{ ...inp, fontSize: 12, color: T.textTer }} disabled={!canEdit} placeholder="Descripción" />
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                                <input type="number" value={b.target} onChange={e => updBracket(i, 'target', Number(e.target.value))} style={{ ...inpSm, borderColor: b.status === 'active' ? T.blue : T.border }} disabled={!canEdit} data-testid={`bracket-target-${i}`} />
                                <span style={{ fontSize: 10, color: bracketStatusColors[b.status], fontWeight: 600 }}>{bracketStatusLabels[b.status]}</span>
                            </div>
                        </div>
                    ))}
                    {canEdit && <button onClick={addBracket} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', border: `1px dashed ${T.border}`, borderRadius: T.radiusSm, background: 'transparent', fontSize: 12, cursor: 'pointer', color: T.textSec, width: '100%', justifyContent: 'center', fontFamily: "'DM Sans'" }} data-testid="add-bracket-btn"><Plus size={13} />Agregar bracket</button>}

                    <h4 style={{ fontSize: 14, fontWeight: 600, marginTop: 24, marginBottom: 12 }}>SLA por rubro (período activo)</h4>
                    {Object.entries(rubroTargets || {}).map(([key, cfg]) => (
                        <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: `1px solid ${T.border}` }}>
                            <span style={{ fontSize: 13, color: T.textSec }}>{cfg.label}</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <input type="number" value={cfg.target} onChange={e => updRubro(key, Number(e.target.value))} style={inpSm} disabled={!canEdit} data-testid={`rubro-${key}`} />
                                <span style={{ fontSize: 12, color: T.textTer }}>%</span>
                            </div>
                        </div>
                    ))}
                </div>
                {/* Right */}
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Penalizaciones</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 30px', gap: 8, padding: '8px 0', fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
                        <span>Fallo</span><span style={{ textAlign: 'center' }}>Descuento</span><span style={{ textAlign: 'center' }}>Aplica a</span><span />
                    </div>
                    {(penalties || []).map((p, i) => (
                        <div key={p.id} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 30px', gap: 8, padding: '8px 0', alignItems: 'center', borderBottom: `1px solid ${T.border}` }}>
                            <input type="text" value={p.label} onChange={e => updPenalty(i, 'label', e.target.value)} style={inp} disabled={!canEdit} />
                            <input type="number" value={p.discount_pct} onChange={e => updPenalty(i, 'discount_pct', Number(e.target.value))} style={inpSm} disabled={!canEdit} />
                            <select value={p.applies_to} onChange={e => updPenalty(i, 'applies_to', e.target.value)} style={{ ...sel, padding: '5px 24px 5px 8px', fontSize: 12 }} disabled={!canEdit}>
                                <option value="provider">Prov.</option><option value="driver">Driver</option>
                            </select>
                            {canEdit && <button onClick={() => removePenalty(i)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textTer }}><Trash2 size={13} /></button>}
                        </div>
                    ))}
                    {canEdit && <button onClick={addPenalty} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px', border: `1px dashed ${T.border}`, borderRadius: T.radiusSm, background: 'transparent', fontSize: 12, cursor: 'pointer', color: T.textSec, width: '100%', justifyContent: 'center', marginTop: 8, fontFamily: "'DM Sans'" }} data-testid="add-penalty-btn"><Plus size={13} />Agregar regla</button>}

                    <h4 style={{ fontSize: 14, fontWeight: 600, marginTop: 24, marginBottom: 12 }}>Política de strikes</h4>
                    {[
                        { key: 'days_below_min_for_strike', label: 'Días consecutivos bajo mínimo para strike' },
                        { key: 'strikes_for_formal_warning', label: 'Strikes para aviso formal' },
                        { key: 'strikes_for_cubbo_escalation', label: 'Strikes para escalamiento Cubbo' },
                    ].map(f => (
                        <div key={f.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: `1px solid ${T.border}` }}>
                            <span style={{ fontSize: 13, color: T.textSec }}>{f.label}</span>
                            <input type="number" value={strikePolicy?.[f.key] || 0} onChange={e => updStrike(f.key, Number(e.target.value))} style={inpSm} disabled={!canEdit} data-testid={`strike-${f.key}`} />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

/* ═══════════════ TAB 4: CONFIG IA ═══════════════ */
const IaTab = ({ data, setData, setDirty, canEdit }) => {
    if (!data) return null;
    const upd = (key, val) => { setData(p => ({ ...p, [key]: val })); setDirty(true); };
    const vars = ['{{tipo_entrega}}', '{{cliente}}', '{{criterios}}', '{{guia}}', '{{n_fotos}}'];

    return (
        <div style={{ padding: 24 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Proveedor y modelo</h4>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ fontSize: 12, color: T.textTer, display: 'block', marginBottom: 4 }}>Proveedor IA</label>
                        <select value={data.provider || 'anthropic'} onChange={e => upd('provider', e.target.value)} style={sel} disabled={!canEdit} data-testid="ia-provider">
                            <option value="anthropic">Anthropic (Claude)</option><option value="openai">OpenAI (GPT)</option>
                        </select>
                    </div>
                    <div style={{ marginBottom: 14 }}>
                        <label style={{ fontSize: 12, color: T.textTer, display: 'block', marginBottom: 4 }}>Modelo</label>
                        <select value={data.model || 'claude-sonnet-4-5-20250929'} onChange={e => upd('model', e.target.value)} style={sel} disabled={!canEdit} data-testid="ia-model">
                            <option value="claude-opus-4-5">claude-opus-4-5 (recomendado imágenes)</option>
                            <option value="claude-sonnet-4-5-20250929">claude-sonnet-4-5 (rápido)</option>
                        </select>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: `1px solid ${T.border}` }}>
                        <div><p style={{ fontSize: 13, fontWeight: 500 }}>Evaluación IA habilitada</p><p style={{ fontSize: 11, color: T.textTer }}>Activa la evaluación automática de evidencias</p></div>
                        <Toggle checked={data.enabled !== false} onChange={v => upd('enabled', v)} disabled={!canEdit} testId="ia-enabled-toggle" />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 0', borderBottom: `1px solid ${T.border}` }}>
                        <div><p style={{ fontSize: 13, fontWeight: 500 }}>Modo: evaluación automática continua</p><p style={{ fontSize: 11, color: T.textTer }}>Ejecuta al cerrar cada ruta, sin acción manual</p></div>
                        <Toggle checked={data.auto_eval_on_close || false} onChange={v => upd('auto_eval_on_close', v)} disabled={!canEdit} testId="ia-auto-eval-toggle" />
                    </div>
                </div>
                <div>
                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Umbrales de confianza</h4>
                    {[
                        { key: 'confidence_approve', label: 'Aprobar automáticamente si score ≥', desc: 'Resultado = aprobado', color: T.green },
                        { key: 'confidence_review', label: 'Revisión manual si score ≥', desc: 'Resultado = requiere revisión', color: T.amber },
                    ].map(f => (
                        <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, padding: 12, borderRadius: T.radiusSm, border: `1px solid ${T.border}` }}>
                            <div style={{ width: 8, height: 8, borderRadius: '50%', background: f.color, flexShrink: 0 }} />
                            <div style={{ flex: 1 }}><p style={{ fontSize: 13, fontWeight: 500 }}>{f.label}</p><p style={{ fontSize: 11, color: T.textTer }}>{f.desc}</p></div>
                            <input type="number" value={data[f.key] || 0} onChange={e => upd(f.key, Number(e.target.value))} style={inpSm} disabled={!canEdit} data-testid={`ia-${f.key}`} />
                        </div>
                    ))}
                    <div style={{ marginTop: 8, padding: '10px 14px', borderRadius: T.radiusSm, background: T.coralLt, fontSize: 12, color: T.coral }}>
                        Score &lt; {data.confidence_review || 60} → Rechazado automáticamente
                    </div>

                    <h4 style={{ fontSize: 14, fontWeight: 600, marginTop: 24, marginBottom: 8 }}>Variables de prompt disponibles</h4>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {vars.map(v => <span key={v} style={{ padding: '3px 10px', borderRadius: 4, fontSize: 12, fontFamily: "'DM Mono'", background: T.surface2, color: T.textSec }}>{v}</span>)}
                    </div>
                </div>
            </div>
            {/* System prompt */}
            <div style={{ marginTop: 20 }}>
                <label style={{ fontSize: 12, color: T.textTer, display: 'block', marginBottom: 4 }}>System prompt</label>
                <textarea value={data.system_prompt || ''} onChange={e => upd('system_prompt', e.target.value)} style={{ ...inp, height: 100, resize: 'vertical', fontFamily: "'DM Mono'", fontSize: 12 }} disabled={!canEdit} placeholder="Instrucciones adicionales para la evaluación IA..." data-testid="ia-system-prompt" />
            </div>
            {/* Supervised training */}
            <div style={{ marginTop: 20, padding: 14, borderRadius: T.radiusSm, border: `1px dashed ${T.border}` }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div><p style={{ fontSize: 13, fontWeight: 500 }}>Entrenamiento supervisado</p><p style={{ fontSize: 11, color: T.textTer }}>Los coordinadores marcan evaluaciones como correctas/incorrectas para mejorar el modelo.</p></div>
                    <Toggle checked={data.supervised_training_enabled || false} onChange={v => upd('supervised_training_enabled', v)} disabled={!canEdit} testId="ia-supervised-toggle" />
                </div>
            </div>
        </div>
    );
};

/* ═══════════════ TAB 5: ERRORES ═══════════════ */
const ErroresTab = ({ catalog, setCatalog, setDirty, canEdit }) => {
    const sorted = useMemo(() => [...(catalog || [])].sort((a, b) => (b.frequency_last_30d || 0) - (a.frequency_last_30d || 0)), [catalog]);
    const top2Keys = useMemo(() => sorted.slice(0, 2).map(e => e.key), [sorted]);
    const addError = () => { setCatalog(p => [...p, { id: `err_${Date.now()}`, key: '', label: '', applies_to: ['exitosa', 'terceros', 'fallida'], active: true, frequency_last_30d: 0 }]); setDirty(true); };
    const updErr = (i, f, v) => { setCatalog(p => { const a = [...p]; a[i] = { ...a[i], [f]: v }; return a; }); setDirty(true); };
    const removeErr = (i) => { setCatalog(p => p.filter((_, j) => j !== i)); setDirty(true); };
    const appliesToLabel = (arr) => { if (!arr) return '—'; if (arr.length >= 3) return 'Todas'; return arr.join(' · '); };

    return (
        <div style={{ padding: 24 }}>
            <div style={{ padding: '12px 16px', background: T.blueLt, borderRadius: T.radiusSm, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                <Info size={15} color={T.blue} /><span>Catálogo estandarizado de tipos de error de evidencia. Fuente única para Reportes, Rutas y Lumi.</span>
            </div>
            {/* Header */}
            <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr 100px 60px 40px', gap: 8, padding: '10px 0', fontSize: 11, color: T.textTer, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.03em', borderBottom: `1px solid ${T.border}` }}>
                <span>Clave del error</span><span>Descripción</span><span>Aplica a</span><span style={{ textAlign: 'center' }}>Activo</span><span />
            </div>
            {(catalog || []).map((err, i) => (
                <div key={err.id} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 100px 60px 40px', gap: 8, padding: '10px 0', alignItems: 'center', borderBottom: `1px solid ${T.border}` }} data-testid={`error-row-${err.key || i}`}>
                    <span style={{ fontSize: 12, fontFamily: "'DM Mono'", fontWeight: 500, color: top2Keys.includes(err.key) ? T.coral : T.textPri }}>
                        {err.key || <input type="text" value="" onChange={e => updErr(i, 'key', e.target.value.replace(/\s+/g, '_').toLowerCase())} style={{ ...inp, fontSize: 12 }} placeholder="clave_error" />}
                    </span>
                    <input type="text" value={err.label} onChange={e => updErr(i, 'label', e.target.value)} style={inp} disabled={!canEdit} />
                    <Pill bg={T.surface2} color={T.textSec}>{appliesToLabel(err.applies_to)}</Pill>
                    <div style={{ display: 'flex', justifyContent: 'center' }}>
                        <Toggle checked={err.active} onChange={v => updErr(i, 'active', v)} disabled={!canEdit} testId={`error-active-${err.key || i}`} />
                    </div>
                    {canEdit && (err.frequency_last_30d || 0) === 0 && (
                        <button onClick={() => removeErr(i)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.textTer }}><Trash2 size={13} /></button>
                    )}
                </div>
            ))}
            {canEdit && <button onClick={addError} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '8px 12px', border: `1px dashed ${T.border}`, borderRadius: T.radiusSm, background: 'transparent', fontSize: 12, cursor: 'pointer', color: T.textSec, width: '100%', justifyContent: 'center', marginTop: 12, fontFamily: "'DM Sans'" }} data-testid="add-error-btn"><Plus size={13} />Agregar tipo de error</button>}
            {/* Footer hint */}
            {sorted.length >= 2 && (
                <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: T.radiusSm, background: T.amberLt, fontSize: 12, color: T.amber }}>
                    Errores más frecuentes (último mes): <strong>{sorted[0]?.label}</strong> y <strong>{sorted[1]?.label}</strong>. Considerar refuerzo de capacitación.
                </div>
            )}
        </div>
    );
};


/* ═══════════════════════════════════════════════════════ */
/*                  QUALITY CRITERIA PAGE                  */
/* ═══════════════════════════════════════════════════════ */

const TABS = [
    { id: 'evidencias', label: 'Evidencias por tipo', icon: Camera },
    { id: 'kpi', label: 'KPIs de calidad', icon: BarChart3, isNew: true },
    { id: 'sla', label: 'SLA & Penalizaciones', icon: Target, isNew: true },
    { id: 'ia', label: 'Configuración IA', icon: Sparkles },
    { id: 'errores', label: 'Tipos de error', icon: BookOpen, isNew: true },
];

const QualityCriteria = () => {
    const { user } = useAuth();
    const canEdit = ['coordinator', 'developer'].includes(user?.role);
    const [activeTab, setActiveTab] = useState('evidencias');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);

    // Tab 1 state
    const [criteria, setCriteria] = useState(null);
    // Tab 2-5 state
    const [kpiTargets, setKpiTargets] = useState(null);
    const [slaBrackets, setSlaBrackets] = useState([]);
    const [rubroTargets, setRubroTargets] = useState({});
    const [penalties, setPenalties] = useState([]);
    const [strikePolicy, setStrikePolicy] = useState({});
    const [iaConfig, setIaConfig] = useState(null);
    const [errorCatalog, setErrorCatalog] = useState([]);
    const [meta, setMeta] = useState({ version: 1, updated_by: '' });

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [criteriaRes, settingsRes] = await Promise.all([
                getQualityCriteria(),
                getQualitySettings(),
            ]);
            setCriteria(criteriaRes.data);
            const s = settingsRes.data;
            setKpiTargets(s.kpi_targets);
            setSlaBrackets(s.sla_brackets);
            setRubroTargets(s.sla_targets_by_rubro);
            setPenalties(s.penalty_rules);
            setStrikePolicy(s.strike_policy);
            setIaConfig(s.ia_config);
            setErrorCatalog(s.error_catalog);
            setMeta(s._meta || {});
            setDirty(false);
        } catch {
            toast.error('Error al cargar configuración');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    const handleSave = async () => {
        // KPI weight validation
        if (activeTab === 'kpi') {
            const w = kpiTargets?.weights || {};
            const total = (w.delivery_rate || 0) + (w.visit_rate || 0) + (w.evidence_quality || 0);
            if (total !== 100) { toast.error('Los pesos de KPI deben sumar 100%'); return; }
        }

        setSaving(true);
        try {
            if (activeTab === 'evidencias') {
                await updateQualityCriteria(criteria);
            } else {
                const sectionMap = {
                    kpi: { section: 'kpi_targets', value: kpiTargets },
                    sla: null, // Save multiple sections
                    ia: { section: 'ia_config', value: iaConfig },
                    errores: { section: 'error_catalog', value: errorCatalog },
                };
                if (activeTab === 'sla') {
                    await Promise.all([
                        patchQualitySettings('sla_brackets', slaBrackets),
                        patchQualitySettings('sla_targets_by_rubro', rubroTargets),
                        patchQualitySettings('penalty_rules', penalties),
                        patchQualitySettings('strike_policy', strikePolicy),
                    ]);
                } else {
                    const cfg = sectionMap[activeTab];
                    if (cfg) await patchQualitySettings(cfg.section, cfg.value);
                }
            }
            toast.success('Configuración guardada');
            setDirty(false);
            fetchAll(); // Reload for fresh version
        } catch {
            toast.error('Error al guardar');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = async () => {
        if (!window.confirm('¿Restablecer toda la configuración a valores predeterminados?')) return;
        try {
            await resetQualityCriteria();
            fetchAll();
            toast.success('Configuración restablecida');
        } catch { toast.error('Error al restablecer'); }
    };

    if (loading) return <div style={{ padding: 60, textAlign: 'center', color: T.textTer }}>Cargando configuración...</div>;

    return (
        <div data-testid="quality-criteria-page">
            <style>{`
                :root { --bg: #F5F4F1; --surface: #FFFFFF; --surface-2: #F0EFEC; --border: #E2E0DB; --text-primary: #1A1916; --text-secondary: #6B6960; --text-tertiary: #9C9A92; }
            `}</style>

            {/* Topbar */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }} data-testid="qc-topbar">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <h1 style={{ fontSize: 20, fontWeight: 600, color: T.textPri, margin: 0 }}>Criterios de Calidad</h1>
                    <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, fontFamily: "'DM Mono'", background: T.surface2, color: T.textSec, fontWeight: 500 }} data-testid="version-badge">v{meta.version}</span>
                    {meta.updated_by && <span style={{ fontSize: 12, color: T.textTer }}>Última edición: {meta.updated_by}</span>}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                    {canEdit && (
                        <>
                            <button onClick={handleReset} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: `1px solid ${T.border}`, borderRadius: T.radiusSm, background: T.surface, fontSize: 13, cursor: 'pointer', fontFamily: "'DM Sans'", color: T.textPri }} data-testid="reset-btn">
                                <RotateCcw size={14} />Restablecer
                            </button>
                            <button onClick={handleSave} disabled={!dirty || saving} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', border: 'none', borderRadius: T.radiusSm, background: dirty ? T.textPri : T.borderStrong, color: '#fff', fontSize: 13, cursor: dirty ? 'pointer' : 'default', fontFamily: "'DM Sans'", opacity: dirty ? 1 : 0.5 }} data-testid="save-btn">
                                <Save size={14} />{saving ? 'Guardando...' : 'Guardar cambios'}
                            </button>
                        </>
                    )}
                </div>
            </div>

            {/* Tab card */}
            <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radius, overflow: 'hidden' }}>
                {/* Tab row */}
                <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}`, background: T.surface2, overflow: 'auto' }}>
                    {TABS.map(t => {
                        const Icon = t.icon;
                        const isActive = activeTab === t.id;
                        return (
                            <button key={t.id} onClick={() => setActiveTab(t.id)} data-testid={`tab-${t.id}`}
                                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '12px 20px', fontSize: 13, fontWeight: isActive ? 600 : 400, color: isActive ? T.textPri : T.textSec, background: isActive ? T.surface : 'transparent', border: 'none', borderBottom: isActive ? `2px solid ${T.textPri}` : '2px solid transparent', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", whiteSpace: 'nowrap', transition: 'all 0.15s' }}>
                                <Icon size={14} />{t.label}
                                {t.isNew && <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 5px', borderRadius: 3, background: T.tealLt, color: T.teal }}>Nuevo</span>}
                            </button>
                        );
                    })}
                </div>

                {/* Tab content */}
                <div style={{ minHeight: 400 }}>
                    {activeTab === 'evidencias' && <EvidenciasTab criteria={criteria} setCriteria={setCriteria} setDirty={setDirty} canEdit={canEdit} />}
                    {activeTab === 'kpi' && <KpiTab data={kpiTargets} setData={setKpiTargets} setDirty={setDirty} canEdit={canEdit} />}
                    {activeTab === 'sla' && <SlaTab brackets={slaBrackets} setBrackets={setSlaBrackets} rubroTargets={rubroTargets} setRubroTargets={setRubroTargets} penalties={penalties} setPenalties={setPenalties} strikePolicy={strikePolicy} setStrikePolicy={setStrikePolicy} setDirty={setDirty} canEdit={canEdit} />}
                    {activeTab === 'ia' && <IaTab data={iaConfig} setData={setIaConfig} setDirty={setDirty} canEdit={canEdit} />}
                    {activeTab === 'errores' && <ErroresTab catalog={errorCatalog} setCatalog={setErrorCatalog} setDirty={setDirty} canEdit={canEdit} />}
                </div>
            </div>

            {/* Role info */}
            {!canEdit && (
                <div style={{ marginTop: 16, padding: '12px 16px', borderRadius: T.radiusSm, background: T.amberLt, display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: T.amber }}>
                    <AlertTriangle size={15} />Tu rol ({user?.role}) permite ver la configuración pero no editarla.
                </div>
            )}
        </div>
    );
};

export default QualityCriteria;
