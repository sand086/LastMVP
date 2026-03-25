import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getQualityCriteria, updateQualityCriteria, resetQualityCriteria } from '../lib/api';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';
import {
    Settings2, Save, RotateCcw, Plus, Trash2, GripVertical,
    Camera, FileText, ShieldCheck, Sparkles, AlertTriangle,
    ChevronDown, ChevronUp, Info,
} from 'lucide-react';

const DELIVERY_TYPE_ICONS = {
    exitosa: <ShieldCheck className="w-5 h-5 text-emerald-600" />,
    terceros: <FileText className="w-5 h-5 text-blue-600" />,
    fallida: <AlertTriangle className="w-5 h-5 text-red-600" />,
};

const EvidenceItem = ({ item, onUpdate, onRemove }) => {
    return (
        <div className="flex items-center gap-3 p-3 bg-white border border-slate-200 rounded-md group" data-testid={`evidence-item-${item.key}`}>
            <GripVertical className="w-4 h-4 text-slate-300 flex-shrink-0" />
            <Camera className="w-4 h-4 text-slate-400 flex-shrink-0" />
            <div className="flex-1 grid grid-cols-12 gap-2 items-center">
                <input
                    type="text"
                    value={item.label}
                    onChange={(e) => onUpdate({ ...item, label: e.target.value })}
                    className="col-span-6 px-2 py-1 border border-slate-200 rounded text-sm focus:ring-1 focus:ring-slate-400 focus:border-slate-400 outline-none"
                    data-testid={`evidence-label-${item.key}`}
                />
                <input
                    type="text"
                    value={item.key}
                    onChange={(e) => onUpdate({ ...item, key: e.target.value.replace(/\s+/g, '_').toLowerCase() })}
                    className="col-span-3 px-2 py-1 border border-slate-200 rounded text-sm font-mono text-slate-500 focus:ring-1 focus:ring-slate-400 focus:border-slate-400 outline-none"
                    placeholder="clave"
                />
                <div className="col-span-2 flex items-center gap-1">
                    <input
                        type="number"
                        value={item.weight}
                        onChange={(e) => onUpdate({ ...item, weight: parseInt(e.target.value) || 0 })}
                        className="w-14 px-2 py-1 border border-slate-200 rounded text-sm text-center focus:ring-1 focus:ring-slate-400 focus:border-slate-400 outline-none"
                        min="0"
                        max="100"
                    />
                    <span className="text-xs text-slate-400">%</span>
                </div>
                <div className="col-span-1 flex justify-end">
                    <button
                        onClick={() => onRemove(item.key)}
                        className="p-1 text-slate-300 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                        data-testid={`remove-evidence-${item.key}`}
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>
        </div>
    );
};

const ScoringRuleItem = ({ ruleKey, rule, onUpdate }) => {
    return (
        <div className="flex items-center gap-3 p-2 bg-slate-50 rounded text-sm">
            <span className="text-slate-500 font-mono text-xs w-32 flex-shrink-0">{ruleKey}</span>
            <div className="flex items-center gap-2 flex-1">
                <label className="text-slate-600 text-xs">Min fotos:</label>
                <input
                    type="number"
                    value={rule.min_photos}
                    onChange={(e) => onUpdate(ruleKey, { ...rule, min_photos: parseInt(e.target.value) || 0 })}
                    className="w-12 px-1 py-0.5 border rounded text-center text-xs"
                    min="0"
                />
                {rule.requires_note !== undefined && (
                    <>
                        <label className="text-slate-600 text-xs ml-2">Requiere nota:</label>
                        <input
                            type="checkbox"
                            checked={rule.requires_note}
                            onChange={(e) => onUpdate(ruleKey, { ...rule, requires_note: e.target.checked })}
                            className="w-4 h-4"
                        />
                    </>
                )}
                <label className="text-slate-600 text-xs ml-2">Score:</label>
                <input
                    type="number"
                    value={rule.score}
                    onChange={(e) => onUpdate(ruleKey, { ...rule, score: parseInt(e.target.value) || 0 })}
                    className="w-14 px-1 py-0.5 border rounded text-center text-xs"
                    min="0"
                    max="100"
                />
                <input
                    type="text"
                    value={rule.label}
                    onChange={(e) => onUpdate(ruleKey, { ...rule, label: e.target.value })}
                    className="flex-1 px-2 py-0.5 border rounded text-xs text-slate-600"
                />
            </div>
        </div>
    );
};

const QualityCriteria = () => {
    const { user } = useAuth();
    const [criteria, setCriteria] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [expandedType, setExpandedType] = useState('exitosa');
    const [hasChanges, setHasChanges] = useState(false);

    const canEdit = user?.role === 'coordinator' || user?.role === 'developer';

    const fetchCriteria = useCallback(async () => {
        try {
            setLoading(true);
            const res = await getQualityCriteria();
            setCriteria(res.data);
            setHasChanges(false);
        } catch (err) {
            toast.error('Error al cargar criterios de calidad');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchCriteria(); }, [fetchCriteria]);

    if (!canEdit) {
        return (
            <div className="p-8 text-center">
                <ShieldCheck className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-500">Solo Coordinadores y Developers pueden modificar los criterios de calidad.</p>
            </div>
        );
    }

    if (loading || !criteria) {
        return <div className="p-8 text-center text-slate-400">Cargando criterios...</div>;
    }

    const updateDeliveryType = (dtype, field, value) => {
        setCriteria(prev => ({
            ...prev,
            delivery_types: {
                ...prev.delivery_types,
                [dtype]: { ...prev.delivery_types[dtype], [field]: value },
            },
        }));
        setHasChanges(true);
    };

    const updateEvidence = (dtype, index, newItem) => {
        const items = [...criteria.delivery_types[dtype].required_evidence];
        items[index] = newItem;
        updateDeliveryType(dtype, 'required_evidence', items);
    };

    const removeEvidence = (dtype, key) => {
        const items = criteria.delivery_types[dtype].required_evidence.filter(e => e.key !== key);
        updateDeliveryType(dtype, 'required_evidence', items);
    };

    const addEvidence = (dtype) => {
        const items = [...criteria.delivery_types[dtype].required_evidence];
        const newKey = `custom_${Date.now()}`;
        items.push({ key: newKey, label: 'Nueva evidencia', required: true, weight: 0 });
        updateDeliveryType(dtype, 'required_evidence', items);
    };

    const updateScoringRule = (dtype, ruleKey, newRule) => {
        const rules = { ...criteria.delivery_types[dtype].scoring_rules, [ruleKey]: newRule };
        updateDeliveryType(dtype, 'scoring_rules', rules);
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            await updateQualityCriteria(criteria);
            toast.success('Criterios de calidad actualizados');
            setHasChanges(false);
        } catch (err) {
            toast.error('Error al guardar criterios');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = async () => {
        if (!window.confirm('¿Restablecer criterios a valores predeterminados? Esta acción no se puede deshacer.')) return;
        try {
            const res = await resetQualityCriteria();
            setCriteria(res.data.criteria);
            toast.success('Criterios restablecidos');
            setHasChanges(false);
        } catch (err) {
            toast.error('Error al restablecer criterios');
        }
    };

    return (
        <div className="space-y-6" data-testid="quality-criteria-section">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Settings2 className="w-5 h-5 text-slate-700" />
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Criterios de Evaluación de Calidad</h2>
                        <p className="text-sm text-slate-500">
                            Configura las reglas y criterios para la evaluación de evidencias de entrega.
                            {criteria.version && <span className="ml-2 text-xs text-slate-400">v{criteria.version}</span>}
                            {criteria.updated_by && <span className="ml-2 text-xs text-slate-400">· Última edición: {criteria.updated_by}</span>}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={handleReset}
                        data-testid="reset-criteria-btn"
                    >
                        <RotateCcw className="w-4 h-4 mr-1" /> Restablecer
                    </Button>
                    <Button
                        size="sm"
                        onClick={handleSave}
                        disabled={!hasChanges || saving}
                        data-testid="save-criteria-btn"
                        className={hasChanges ? 'bg-emerald-600 hover:bg-emerald-700' : ''}
                    >
                        <Save className="w-4 h-4 mr-1" /> {saving ? 'Guardando...' : 'Guardar cambios'}
                    </Button>
                </div>
            </div>

            {/* Keywords de terceros */}
            <div className="border border-slate-200 rounded-lg p-4 space-y-3">
                <h3 className="text-sm font-medium text-slate-700 flex items-center gap-2">
                    <Info className="w-4 h-4 text-blue-500" />
                    Keywords de detección de terceros
                </h3>
                <p className="text-xs text-slate-400">
                    Palabras clave en la nota del driver que indican entrega a terceros. Separar con comas.
                </p>
                <input
                    type="text"
                    value={(criteria.third_party_keywords || []).join(', ')}
                    onChange={(e) => {
                        const kw = e.target.value.split(',').map(k => k.trim()).filter(Boolean);
                        setCriteria(prev => ({ ...prev, third_party_keywords: kw }));
                        setHasChanges(true);
                    }}
                    className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm focus:ring-1 focus:ring-slate-400 focus:border-slate-400 outline-none"
                    data-testid="third-party-keywords-input"
                />
                <div className="flex flex-wrap gap-1.5">
                    {(criteria.third_party_keywords || []).map((kw, i) => (
                        <span key={i} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-700 border border-blue-200">
                            {kw}
                        </span>
                    ))}
                </div>
            </div>

            {/* Delivery Types */}
            {Object.entries(criteria.delivery_types || {}).map(([dtype, config]) => (
                <div key={dtype} className="border border-slate-200 rounded-lg overflow-hidden" data-testid={`delivery-type-${dtype}`}>
                    <button
                        className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                        onClick={() => setExpandedType(expandedType === dtype ? null : dtype)}
                    >
                        <div className="flex items-center gap-3">
                            {DELIVERY_TYPE_ICONS[dtype]}
                            <div>
                                <span className="font-medium text-slate-900">{config.label}</span>
                                <span className="ml-2 text-xs text-slate-400 font-mono">{dtype}</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="text-xs text-slate-500">{config.required_evidence?.length || 0} criterios</span>
                            {expandedType === dtype ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                        </div>
                    </button>

                    {expandedType === dtype && (
                        <div className="p-4 space-y-4 border-t border-slate-200">
                            {/* Notes */}
                            {config.notes && (
                                <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-md">
                                    <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                                    <p className="text-xs text-amber-700">{config.notes}</p>
                                </div>
                            )}

                            {/* Required Evidence */}
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <h4 className="text-sm font-medium text-slate-600">Evidencias requeridas</h4>
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs text-slate-400">
                                            Total peso: {config.required_evidence?.reduce((s, e) => s + (e.weight || 0), 0)}%
                                        </span>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => addEvidence(dtype)}
                                            data-testid={`add-evidence-${dtype}`}
                                        >
                                            <Plus className="w-3 h-3 mr-1" /> Agregar
                                        </Button>
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <div className="grid grid-cols-12 gap-2 px-10 text-xs text-slate-400 font-medium">
                                        <span className="col-span-6">Descripción</span>
                                        <span className="col-span-3">Clave</span>
                                        <span className="col-span-2">Peso</span>
                                        <span className="col-span-1"></span>
                                    </div>
                                    {(config.required_evidence || []).map((item, idx) => (
                                        <EvidenceItem
                                            key={item.key}
                                            item={item}
                                            onUpdate={(newItem) => updateEvidence(dtype, idx, newItem)}
                                            onRemove={(key) => removeEvidence(dtype, key)}
                                        />
                                    ))}
                                </div>
                            </div>

                            {/* Scoring Rules */}
                            <div>
                                <h4 className="text-sm font-medium text-slate-600 mb-2">Reglas de puntuación</h4>
                                <div className="space-y-1.5">
                                    {Object.entries(config.scoring_rules || {}).map(([ruleKey, rule]) => (
                                        <ScoringRuleItem
                                            key={ruleKey}
                                            ruleKey={ruleKey}
                                            rule={rule}
                                            onUpdate={(rk, nr) => updateScoringRule(dtype, rk, nr)}
                                        />
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            ))}

            {/* AI Config */}
            <div className="border border-slate-200 rounded-lg p-4 space-y-3">
                <h3 className="text-sm font-medium text-slate-700 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-500" />
                    Configuración de evaluación IA
                </h3>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className="block text-xs text-slate-500 mb-1">Proveedor IA</label>
                        <select
                            value={criteria.ai_evaluation?.provider || 'anthropic'}
                            onChange={(e) => {
                                setCriteria(prev => ({
                                    ...prev,
                                    ai_evaluation: { ...prev.ai_evaluation, provider: e.target.value },
                                }));
                                setHasChanges(true);
                            }}
                            className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm"
                            data-testid="ai-provider-select"
                        >
                            <option value="anthropic">Anthropic (Claude)</option>
                            <option value="openai">OpenAI (GPT)</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs text-slate-500 mb-1">Evaluación IA</label>
                        <label className="flex items-center gap-2 mt-2 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={criteria.ai_evaluation?.enabled !== false}
                                onChange={(e) => {
                                    setCriteria(prev => ({
                                        ...prev,
                                        ai_evaluation: { ...prev.ai_evaluation, enabled: e.target.checked },
                                    }));
                                    setHasChanges(true);
                                }}
                                className="w-4 h-4"
                                data-testid="ai-enabled-toggle"
                            />
                            <span className="text-sm text-slate-700">Habilitada</span>
                        </label>
                    </div>
                </div>
                <div>
                    <label className="block text-xs text-slate-500 mb-1">Instrucciones adicionales para IA</label>
                    <textarea
                        value={criteria.ai_evaluation?.custom_instructions || ''}
                        onChange={(e) => {
                            setCriteria(prev => ({
                                ...prev,
                                ai_evaluation: { ...prev.ai_evaluation, custom_instructions: e.target.value },
                            }));
                            setHasChanges(true);
                        }}
                        className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm h-20 resize-y"
                        placeholder="Instrucciones personalizadas que se añadirán al prompt de evaluación IA..."
                        data-testid="ai-custom-instructions"
                    />
                </div>
            </div>
        </div>
    );
};

export default QualityCriteria;
