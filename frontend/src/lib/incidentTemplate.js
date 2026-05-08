/**
 * Auto-fill structured template for "Nueva incidencia" descriptions.
 *
 * Replaces the old generic placeholder with a structured summary derived from
 * whatever evaluation data is available on the package:
 *   1. AI evaluation (evidence_detail.criteria_met)  — preferred
 *   2. Manual review (manually_reviewed_note + review_note) — fallback when AI
 *      didn't evaluate or when a coordinator rejected/observed manually
 *   3. Generic placeholder — last resort if no evaluation exists at all
 *
 * Why a deterministic template (vs an LLM call)?
 *   - Zero cost, zero latency, fully reproducible.
 *   - 80% of agent edits are just "list the failed criteria" — exactly what
 *     this generates. LLM narrative is a separate optional upgrade.
 */
import { CRITERIA, detectDeliveryType, REJECTION_REASONS } from '../components/ReviewModal';

/* Map rejection reason slug → criterion key (best-effort). Used to map manual
 * review notes back to the canonical criterion catalog so the description can
 * present a unified vocabulary. */
const REJECTION_TO_CRITERION = {
    foto_fachada_ausente: 'foto_fachada',
    guia_ilegible: 'foto_paquete_guia',
    foto_receptor_ausente: 'foto_tercero',
    paquete_no_visible: 'foto_paquete_guia',
    whatsapp_ausente: 'mensaje_whatsapp',
    timestamp_inconsistente: 'timestamp',
    llamadas_insuficientes: null,    // criterion-less for now
    evidencia_borrosa: null,         // generic alert, no specific criterion
    otro: null,
};

const REJECTION_LABEL = Object.fromEntries(REJECTION_REASONS.map(r => [r.value, r.label]));

/* Suggested severity bucket from AI score (0-100). */
export function suggestSeverity(score) {
    if (score == null) return 'Medio';
    if (score < 50) return 'Alto';
    if (score < 80) return 'Medio';
    return 'Bajo';
}

/* Suggested incident_type from delivery type + failed criteria.
 * Maps to the canonical catalog (INCIDENT_TYPES in lib/utils.js). Returns ''
 * if no clear match — agent picks manually. */
export function suggestIncidentType(deliveryType, hasCriticalFail, failedKeys = []) {
    const failed = new Set(failedKeys);
    if (deliveryType === 'C') return 'evidencia_incidencia_incorrecta';
    if (deliveryType === 'B' && (failed.has('mensaje_whatsapp') || failed.has('foto_tercero'))) {
        return 'autorizacion_tercero_incorrecta';
    }
    if (hasCriticalFail) return 'evidencia_entrega_incorrecta';
    if (failed.has('nota_driver') || failed.has('timestamp')) return 'notas_incorrectas';
    return '';
}

function _scoreLine(pkg) {
    const aiScore = pkg.ai_score;
    const ruleScore = pkg.evidence_score;
    const adjusted = pkg.adjusted_score;
    if (aiScore != null && ruleScore != null && aiScore !== ruleScore) {
        return `Score IA original: ${aiScore} → recalculado por criterios: ${ruleScore}`;
    }
    if (adjusted != null && aiScore != null && adjusted !== aiScore) {
        return `Score IA: ${aiScore}/100 → ajustado en revisión: ${adjusted}/100`;
    }
    if (aiScore != null) return `Score IA: ${aiScore}/100`;
    if (adjusted != null) return `Score (ajustado): ${adjusted}/100`;
    if (ruleScore != null) return `Score: ${ruleScore}/100`;
    return null;
}

/* Parse manual review note: it can come as "category: detail" (composite, see
 * GuiasTab.jsx:170) or just a slug. Returns { slug, freeText, label }. */
function _parseManualNote(note) {
    if (!note) return null;
    const s = String(note).trim();
    if (!s) return null;
    // Composite: "slug: free text"
    const colonIdx = s.indexOf(':');
    let slug = s, freeText = '';
    if (colonIdx > 0) {
        const head = s.slice(0, colonIdx).trim();
        const rest = s.slice(colonIdx + 1).trim();
        if (REJECTION_LABEL[head]) {
            slug = head;
            freeText = rest;
        }
    }
    const knownLabel = REJECTION_LABEL[slug];
    return { slug: knownLabel ? slug : null, freeText: knownLabel ? freeText : s, label: knownLabel || null };
}

/* Build the structured description string. */
export function buildIncidentDescription(pkg, journey) {
    const guide = pkg?.tracking_number || pkg?.order_reference_id || '';
    const driver = journey?.driver_name || '';

    if (!pkg) {
        return {
            description: `Incidencia registrada desde Guías${guide ? ` para paquete ${guide}` : ''}`,
            severity: 'Medio',
            incident_type: '',
        };
    }

    // Pre-parse manual review note FIRST so we can use it to refine delivery type detection.
    const noteRaw = pkg.manually_reviewed_note || pkg.review_note || pkg.rejection_reason || '';
    const parsedNote = _parseManualNote(noteRaw);

    // Refine delivery type when AI didn't detect it but the manual review slug
    // strongly suggests a third-party delivery (Tipo B).
    let deliveryType = detectDeliveryType(pkg).toUpperCase();
    if (deliveryType === 'A' && parsedNote?.slug) {
        if (parsedNote.slug === 'whatsapp_ausente' || parsedNote.slug === 'foto_receptor_ausente') {
            deliveryType = 'B';
        }
    }

    const criteriaItems = (CRITERIA[deliveryType] || CRITERIA.A).items;
    const criteriaLabel = (CRITERIA[deliveryType] || CRITERIA.A).label;
    const criteriaMet = pkg?.evidence_detail?.criteria_met || {};

    // 1. AI-evaluated failed criteria
    const aiFailed = criteriaItems.filter(it => criteriaMet[it.key] === false);
    const aiUnevaluated = criteriaItems.filter(it => criteriaMet[it.key] == null);

    // 2. Manual review → criterion mapping (for the refined delivery type catalog)
    const manualFailedItem = parsedNote?.slug
        ? criteriaItems.find(it => it.key === REJECTION_TO_CRITERION[parsedNote.slug])
        : null;

    // 3. Combined failed criteria (no duplicates)
    const failed = [...aiFailed];
    if (manualFailedItem && !failed.find(f => f.key === manualFailedItem.key)) {
        failed.push(manualFailedItem);
    }
    const hasCriticalFail = failed.some(f => f.critical);

    // 4. Free-text alerts (cap 6 to keep readable)
    const detail = pkg?.evidence_detail || {};
    const alerts = [
        ...(Array.isArray(detail.alerts) ? detail.alerts : []),
        ...(Array.isArray(detail.warnings) ? detail.warnings : []),
        ...(Array.isArray(pkg.ai_errors) ? pkg.ai_errors : []),
    ].filter(Boolean).slice(0, 6);

    const score = pkg.ai_score ?? pkg.adjusted_score ?? pkg.evidence_score;
    const lines = [];

    // Header
    const headerParts = [`Faltantes detectados · Tipo ${deliveryType} (${criteriaLabel})`];
    if (score != null) headerParts.push(`Score ${score}/100`);
    lines.push(headerParts.join(' · '));
    lines.push('');

    // Failed criteria block
    if (failed.length > 0) {
        lines.push('CRITERIOS FALLIDOS:');
        failed.forEach(f => {
            const critTag = f.critical ? ' [CRÍTICO]' : '';
            lines.push(`• ${f.label}${critTag} — ${f.desc}`);
        });
        lines.push('');
    }

    // Manual review block (when not already mapped to a criterion, or when
    // there's free-text added by the reviewer)
    if (parsedNote && (!manualFailedItem || parsedNote.freeText)) {
        lines.push('REVISIÓN MANUAL:');
        if (parsedNote.label) {
            lines.push(`• ${parsedNote.label}`);
        }
        if (parsedNote.freeText) {
            lines.push(`• ${parsedNote.freeText}`);
        }
        if (pkg.reviewed_by) {
            lines.push(`Revisado por: ${pkg.reviewed_by}`);
        }
        lines.push('');
    }

    // AI alerts block
    if (alerts.length > 0) {
        lines.push('ALERTAS IA:');
        alerts.forEach(a => lines.push(`• ${String(a).trim()}`));
        lines.push('');
    }

    // Edge: nothing to show — fallback to generic placeholder
    const nothingToReport = failed.length === 0 && alerts.length === 0 && !parsedNote;
    if (nothingToReport && aiUnevaluated.length === criteriaItems.length && score == null) {
        return {
            description: `Incidencia registrada desde Guías${guide ? ` para paquete ${guide}` : ''}`,
            severity: 'Medio',
            incident_type: '',
        };
    }

    const scoreLine = _scoreLine(pkg);
    if (scoreLine) lines.push(scoreLine);
    lines.push(`Guía: ${guide}${driver ? ` · Driver: ${driver}` : ''}`);

    // Suggest incident_type using BOTH AI failed and manual-mapped criteria
    const allFailedKeys = failed.map(f => f.key);

    return {
        description: lines.join('\n').trim(),
        severity: suggestSeverity(score),
        incident_type: suggestIncidentType(deliveryType, hasCriticalFail, allFailedKeys),
    };
}
