/**
 * Auto-fill structured template for "Nueva incidencia" descriptions.
 *
 * Replaces the old generic placeholder ("Incidencia registrada desde Guias para
 * paquete X") with a structured summary derived from the AI evaluation:
 * delivery type, failed criteria (with critical flag), AI alerts, and score
 * delta. The agent can edit freely before saving.
 *
 * Why a deterministic template (vs an LLM call)?
 *   - Zero cost, zero latency, fully reproducible.
 *   - 80% of agent edits are just "list the failed criteria" — exactly what
 *     this generates. LLM narrative is a separate optional upgrade.
 */
import { CRITERIA, detectDeliveryType } from '../components/ReviewModal';

/* Suggested severity bucket from AI score (0-100). */
export function suggestSeverity(score) {
    if (score == null) return 'Medio';
    if (score < 50) return 'Alto';
    if (score < 80) return 'Medio';
    return 'Bajo';
}

/* Suggested incident_type from delivery type + failed criteria.
 * Maps to the canonical catalog defined in /app/frontend/src/lib/utils.js
 * (INCIDENT_TYPES). Returns '' (empty) if no clear match — agent picks manually.
 */
export function suggestIncidentType(deliveryType, hasCriticalFail, failedKeys = []) {
    const failed = new Set(failedKeys);

    // Tipo C = entrega fallida → siempre ligado a evidencia de incidencia
    if (deliveryType === 'C') return 'evidencia_incidencia_incorrecta';

    // Tipo B + fallo en mensaje_whatsapp/foto_tercero → autorización a tercero
    if (deliveryType === 'B' && (failed.has('mensaje_whatsapp') || failed.has('foto_tercero'))) {
        return 'autorizacion_tercero_incorrecta';
    }

    // Crítico fallido en Tipo A/B → evidencia de entrega incorrecta
    if (hasCriticalFail) return 'evidencia_entrega_incorrecta';

    // Solo nota_driver / timestamp / criterios no críticos → notas incompletas
    if (failed.has('nota_driver') || failed.has('timestamp')) {
        return 'notas_incorrectas';
    }

    return '';  // sin sugerencia clara, dropdown queda vacío
}

function _scoreLine(pkg) {
    const aiScore = pkg.ai_score;
    const ruleScore = pkg.evidence_score;
    if (aiScore != null && ruleScore != null && aiScore !== ruleScore) {
        return `Score IA original: ${aiScore} → recalculado por criterios: ${ruleScore}`;
    }
    if (aiScore != null) return `Score IA: ${aiScore}/100`;
    if (ruleScore != null) return `Score: ${ruleScore}/100`;
    return null;
}

/* Build the structured description string. Returns the text + suggested
 * severity + suggested incident_type; the caller decides whether to apply them. */
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

    const deliveryType = detectDeliveryType(pkg).toUpperCase();
    const criteriaItems = (CRITERIA[deliveryType] || CRITERIA.A).items;
    const criteriaLabel = (CRITERIA[deliveryType] || CRITERIA.A).label;
    const criteriaMet = pkg?.evidence_detail?.criteria_met || {};

    // Collect failed criteria from AI evaluation
    const failed = criteriaItems.filter(it => criteriaMet[it.key] === false);
    const unevaluated = criteriaItems.filter(it => criteriaMet[it.key] == null);
    const hasCriticalFail = failed.some(f => f.critical);

    // Collect alerts (free-text from AI). Different shapes seen in the wild:
    //   evidence_detail.alerts (array of strings)
    //   evidence_detail.warnings (array)
    //   ai_errors (array of strings) — legacy
    const detail = pkg?.evidence_detail || {};
    const alerts = [
        ...(Array.isArray(detail.alerts) ? detail.alerts : []),
        ...(Array.isArray(detail.warnings) ? detail.warnings : []),
        ...(Array.isArray(pkg.ai_errors) ? pkg.ai_errors : []),
    ].filter(Boolean).slice(0, 6);  // cap at 6 to keep the description readable

    const lines = [];
    const score = pkg.ai_score ?? pkg.evidence_score;
    const header = [
        `Faltantes detectados en evaluación IA · Tipo ${deliveryType} (${criteriaLabel})`,
        score != null ? `· Score ${score}/100` : '',
    ].join(' ').trim();
    lines.push(header);
    lines.push('');

    if (failed.length > 0) {
        lines.push('CRITERIOS FALLIDOS:');
        failed.forEach(f => {
            const critTag = f.critical ? ' [CRÍTICO]' : '';
            lines.push(`• ${f.label}${critTag} — ${f.desc}`);
        });
        lines.push('');
    }

    if (alerts.length > 0) {
        lines.push('ALERTAS IA:');
        alerts.forEach(a => lines.push(`• ${String(a).trim()}`));
        lines.push('');
    }

    if (unevaluated.length > 0 && failed.length === 0 && alerts.length === 0) {
        // Edge case: opened modal without evaluation done — keep a useful baseline
        lines.push('Sin criterios evaluados aún — registrar incidencia manual.');
        lines.push('');
    }

    const scoreLine = _scoreLine(pkg);
    if (scoreLine) lines.push(scoreLine);
    lines.push(`Guía: ${guide}${driver ? ` · Driver: ${driver}` : ''}`);

    return {
        description: lines.join('\n').trim(),
        severity: suggestSeverity(score),
        incident_type: suggestIncidentType(deliveryType, hasCriticalFail, failed.map(f => f.key)),
    };
}
