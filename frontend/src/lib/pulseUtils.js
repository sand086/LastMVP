/**
 * Pulse — Real-time feasibility monitor utilities
 * Calculates whether an active route can finish within the operational window.
 */

const PULSE_DEFAULTS = {
    hora_limite: { hour: 21, minute: 30 },
    tiempo_promedio_entrega: 5,
    umbral_ok: 10,
    umbral_warn: 5,
};

/**
 * Parse a departure_time string into total minutes since midnight.
 * Accepts: "HH:MM", "YYYY-MM-DDTHH:MM", ISO datetime, etc.
 */
function parseDepartureMinutes(dt) {
    if (!dt) return null;
    try {
        // If it's an ISO datetime or "YYYY-MM-DDTHH:MM" format
        if (dt.includes('T')) {
            const d = new Date(dt);
            if (isNaN(d.getTime())) return null;
            return d.getHours() * 60 + d.getMinutes();
        }
        // Plain "HH:MM"
        const parts = dt.split(':');
        if (parts.length >= 2) {
            return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
        }
    } catch (err) { console.error('Pulse config parse error:', err); }
    return null;
}

/**
 * Core feasibility computation for a single journey.
 *
 * @param {Object} journey - Journey object from API
 * @param {Object} pulseConfig - Pulse configuration from Admin IA config
 * @returns {Object|null} - Feasibility data or null if not applicable
 */
export function computeFeasibility(journey, pulseConfig) {
    const cfg = { ...PULSE_DEFAULTS, ...(pulseConfig || {}) };

    // Only compute for in_progress routes
    if (!journey || journey.status !== 'in_progress') return null;

    // Need start_data with departure_time
    const startData = journey.start_data;
    if (!startData) return null;
    const departureStr = startData.departure_time;
    const departureMin = parseDepartureMinutes(departureStr);
    if (departureMin === null) return null;

    const pkgsTotal = journey.packages_total || 0;
    const pkgsDelivered = journey.packages_delivered || 0;
    const pkgsFailed = journey.packages_failed || 0;
    const remaining = Math.max(0, pkgsTotal - pkgsDelivered - pkgsFailed);

    // All done
    if (remaining === 0) return null;

    // Resolve transit time from journey's start_data (per-route)
    let trasladoMin = journey.start_data?.traslado_primer_punto;
    if (trasladoMin === undefined || trasladoMin === null) {
        trasladoMin = 40; // fallback
    }

    const horaLimite = (cfg.hora_limite?.hour || 21) * 60 + (cfg.hora_limite?.minute || 30);
    const tiempoEntrega = cfg.tiempo_promedio_entrega || 5;
    const umbralOk = cfg.umbral_ok || 10;
    const umbralWarn = cfg.umbral_warn || 5;

    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();

    // Time remaining in the operational window
    const ventana = horaLimite - nowMin;

    // Time needed for deliveries
    const tiempoEntregas = remaining * tiempoEntrega;

    // Transit slots between remaining delivery points
    const slotsTraslado = Math.max(remaining - 1, 1);

    // Max time available per transit between points
    const tiempoMaxEntrePuntos = (ventana - tiempoEntregas) / slotsTraslado;

    // Pace calculation
    const ventanaTotal = horaLimite - (departureMin + trasladoMin);
    const tiempoTranscurrido = nowMin - (departureMin + trasladoMin);
    const pctIdeal = ventanaTotal > 0
        ? Math.min(Math.max((tiempoTranscurrido / ventanaTotal) * 100, 0), 100)
        : 0;
    const processed = pkgsDelivered + pkgsFailed;
    const pctReal = pkgsTotal > 0 ? (processed / pkgsTotal) * 100 : 0;
    const paceDelta = pctReal - pctIdeal;

    // Estimated finish time
    const elapsedSinceStart = Math.max(nowMin - departureMin, 1);
    const avgPerPkg = processed > 0 ? elapsedSinceStart / processed : tiempoEntrega + 8;
    const estRemainingMin = remaining * avgPerPkg;
    const estFinishMin = nowMin + estRemainingMin;
    const estFinishH = Math.floor(estFinishMin / 60);
    const estFinishM = Math.round(estFinishMin % 60);

    // Time left to deadline
    const timeLeftMin = Math.max(0, horaLimite - nowMin);
    const timeLeftH = Math.floor(timeLeftMin / 60);
    const timeLeftM = Math.round(timeLeftMin % 60);

    // Status classification
    let status, label, alertMsg;
    if (tiempoMaxEntrePuntos >= umbralOk) {
        status = 'ok';
        label = 'En tiempo';
        alertMsg = `Holgura suficiente — ${Math.round(tiempoMaxEntrePuntos * 10) / 10} min max entre puntos`;
    } else if (tiempoMaxEntrePuntos >= umbralWarn) {
        status = 'warn';
        label = 'Ajustada';
        alertMsg = `Ritmo ajustado — ${Math.round(tiempoMaxEntrePuntos * 10) / 10} min max entre puntos`;
    } else if (tiempoMaxEntrePuntos > 0) {
        status = 'danger';
        label = 'Critica';
        alertMsg = `Riesgo de incumplimiento — solo ${Math.round(tiempoMaxEntrePuntos * 10) / 10} min entre puntos`;
    } else {
        status = 'danger';
        label = 'Inviable';
        alertMsg = 'Inviable — no queda tiempo suficiente para completar entregas';
    }

    return {
        remaining,
        delivered: pkgsDelivered,
        failed: pkgsFailed,
        total: pkgsTotal,
        pctDone: Math.round(pctReal),
        timeLeftStr: `${timeLeftH}h ${timeLeftM}m`,
        timeLeftMin,
        maxTransit: Math.round(tiempoMaxEntrePuntos * 10) / 10,
        estFinish: `${String(estFinishH).padStart(2, '0')}:${String(estFinishM).padStart(2, '0')}`,
        idealPct: Math.round(pctIdeal),
        paceDelta: Math.round(paceDelta),
        status,
        label,
        alertMsg,
        departureMin,
        horaLimite,
        trasladoMin,
    };
}

/** Color map for pulse statuses */
export const PULSE_COLORS = {
    ok: '#10B981',
    warn: '#D97706',
    danger: '#EF4444',
};

/** Background colors (light) */
export const PULSE_BG = {
    ok: '#ECFDF5',
    warn: '#FFFBEB',
    danger: '#FEF2F2',
};
