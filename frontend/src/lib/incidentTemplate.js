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

function _scoreLine() {
    // Deprecated: score line removed from auto-filled description per product
    // request (2026-05-13). Kept as no-op to avoid breaking external imports.
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
    const criteriaMet = pkg?.evidence_detail?.criteria_met || {};

    // 1. AI-evaluated failed criteria
    const aiFailed = criteriaItems.filter(it => criteriaMet[it.key] === false);

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

    const score = pkg.ai_score ?? pkg.adjusted_score ?? pkg.evidence_score;
    const lines = [];

    // Solo bloque CRITERIOS FALLIDOS. Petición explícita del usuario: la
    // descripción auto-rellenada debe contener ÚNICAMENTE los criterios del
    // catálogo que fallaron, sin header, score, alertas IA, revisión manual,
    // ni metadatos de guía/driver (esa info ya vive en otros campos del
    // formulario y en el panel de evidencias de la guía).
    if (failed.length > 0) {
        lines.push('CRITERIOS FALLIDOS:');
        failed.forEach(f => {
            const critTag = f.critical ? ' [CRÍTICO]' : '';
            lines.push(`• ${f.label}${critTag} — ${f.desc}`);
        });
    }

    // Edge: nada que reportar → placeholder genérico. Mantenemos el fallback
    // para que el formulario nunca quede vacío y el operador pueda llenar.
    if (failed.length === 0) {
        return {
            description: `Incidencia registrada desde Guías${guide ? ` para paquete ${guide}` : ''}`,
            severity: suggestSeverity(score),
            incident_type: suggestIncidentType(deliveryType, false, []),
        };
    }

    // Suggest incident_type using failed criteria
    const allFailedKeys = failed.map(f => f.key);

    return {
        description: lines.join('\n').trim(),
        severity: suggestSeverity(score),
        incident_type: suggestIncidentType(deliveryType, hasCriticalFail, allFailedKeys),
    };
}
