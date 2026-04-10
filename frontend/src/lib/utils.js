import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
    return twMerge(clsx(inputs));
}

export function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('es-MX', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
    });
}

export function formatDateTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString('es-MX', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

export function formatTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString('es-MX', {
        hour: '2-digit',
        minute: '2-digit',
    });
}

export function getTodayDate() {
    return new Date().toISOString().split('T')[0];
}

export function getStatusColor(status) {
    switch (status) {
        case 'in_progress':
            return 'status-in_progress';
        case 'closed':
            return 'status-closed';
        case 'scheduled':
            return 'status-scheduled';
        case 'open':
            return 'status-open';
        case 'resolved':
            return 'status-resolved';
        default:
            return 'status-scheduled';
    }
}

export function getStatusLabel(status) {
    const labels = {
        scheduled: 'Programada',
        in_progress: 'En Progreso',
        closed: 'Cerrada',
        open: 'Abierta',
        resolved: 'Resuelta',
        pending: 'Pendiente',
        delivered: 'Entregado',
        failed: 'Fallido',
        returned: 'Devuelto',
        retry: 'Reintento',
    };
    return labels[status] || status;
}

export function getSeverityColor(severity) {
    switch (severity?.toLowerCase()) {
        case 'alto':
            return 'severity-alto';
        case 'medio':
            return 'severity-medio';
        case 'bajo':
            return 'severity-bajo';
        default:
            return 'severity-bajo';
    }
}

export function getProgressColor(percentage) {
    if (percentage >= 70) return 'progress-high';
    if (percentage >= 40) return 'progress-medium';
    return 'progress-low';
}

export function calculateDeliveryRate(delivered, total) {
    if (!total || total === 0) return 0;
    return Math.round((delivered / total) * 100);
}

export function generateWhatsAppStartSummary(journey, startData) {
    const date = formatDate(journey.date);
    const driverName = journey.driver_name || 'Sin asignar';
    const provider = journey.provider_name || 'N/A';
    const zone = journey.packages?.[0]?.zone || 'N/A';
    const packagesLoaded = startData.packages_loaded || 0;
    const retryPackages = journey.packages_retry || 0;
    const odometer = startData.odometer_start || 0;
    
    return `INICIO DE RUTA - LastMile OS
━━━━━━━━━━━━━━━━━━
Fecha: ${date}
Driver: ${driverName}
Proveedor: ${provider}
Zona: ${zone}
Paquetes cargados: ${packagesLoaded}
Reintentos: ${retryPackages}
Odómetro inicial: ${odometer.toLocaleString()} km
━━━━━━━━━━━━━━━━━━
Ruta iniciada correctamente`;
}

export function generateWhatsAppCloseSummary(journey, closeData) {
    const date = formatDate(journey.date);
    const provider = journey.provider_name || 'N/A';
    const delivered = closeData.packages_delivered || 0;
    const failed = closeData.packages_failed || 0;
    const toRetry = closeData.packages_to_retry || 0;
    const km = closeData.km_traveled || 0;
    const rate = closeData.delivery_rate || 0;
    const incidents = journey.incidents_count || 0;
    
    // Calculate time
    const startTime = journey.start_data?.departure_time || '';
    const endTime = closeData.closed_at || '';
    let totalTime = 'N/A';
    if (startTime && endTime) {
        const start = new Date(startTime);
        const end = new Date(endTime);
        const diff = Math.round((end - start) / (1000 * 60));
        const hours = Math.floor(diff / 60);
        const mins = diff % 60;
        totalTime = `${hours}h ${mins}m`;
    }

    // Quality stats from packages
    const packages = journey.packages || [];
    const scored = packages.filter(p => p.evidence_score != null);
    const avgScore = scored.length > 0 ? Math.round(scored.reduce((a, p) => a + p.evidence_score, 0) / scored.length) : 0;
    const complete = scored.filter(p => p.evidence_score === 100).length;
    const partial = scored.filter(p => p.evidence_score >= 60 && p.evidence_score < 100).length;
    const incomplete = scored.filter(p => p.evidence_score < 60).length;
    const attentionPkgs = packages.filter(p => p.evidence_score != null && p.evidence_score < 60);

    let qualityBlock = '';
    if (scored.length > 0) {
        qualityBlock = `
━━━━━━━━━━━━━━━━━━
Calidad de soporte:
Soporte completo: ${complete} paquetes
Soporte parcial: ${partial} paquetes
Sin soporte: ${incomplete} paquetes
Score promedio: ${avgScore}%`;

        if (attentionPkgs.length > 0) {
            qualityBlock += '\n\nPaquetes que requieren atención:';
            attentionPkgs.slice(0, 5).forEach(p => {
                const missing = (p.evidence_detail?.missing_items || []).join(', ');
                qualityBlock += `\n- ${p.tracking_number || p.order_reference_id} Falta: ${missing || 'Sin detalle'}`;
            });
        }
    }
    
    // Delivery attempts stats
    const multiAttemptPkgs = packages.filter(p => (p.delivery_attempt || 1) > 1);
    const attemptRate = packages.length > 0 
        ? Math.round((multiAttemptPkgs.length / packages.length) * 100) 
        : 0;
    
    const driverName = journey.driver_name || 'Sin asignar';
    
    return `CIERRE DE RUTA - LastMile OS
━━━━━━━━━━━━━━━━━━
Fecha: ${date}
Driver: ${driverName}
Proveedor: ${provider}
━━━━━━━━━━━━━━━━━━
Entregados: ${delivered}
Fallidos: ${failed}
Devoluciones: ${toRetry}
━━━━━━━━━━━━━━━━━━
Tasa de entrega: ${rate}%
Reintentos: ${multiAttemptPkgs.length} paquetes (${attemptRate}%)
Km recorridos: ${km.toLocaleString()}
Tiempo total: ${totalTime}
Incidencias: ${incidents}${qualityBlock}
━━━━━━━━━━━━━━━━━━
Ruta cerrada correctamente`;
}

export function copyToClipboard(text) {
    navigator.clipboard.writeText(text);
}

export function downloadFile(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
}

export const INCIDENT_TYPES = [
    'Tiempo excesivo por entrega',
    'Driver sin movimiento',
    'Evidencia incorrecta',
    'Evidencia Insuficiente',
    'Paquete dañado',
    'Destinatario ausente',
    'Dirección no encontrada',
    'Accidente o incidente vehicular',
    'Llanta ponchada',
    'Problema en Cosmo',
    'Otro',
];

export const FUEL_LEVELS = [
    'Lleno',
    '3/4',
    '1/2',
    '1/4',
    'Reserva',
];

export const VEHICLE_CONDITIONS = [
    'Bueno',
    'Con observación',
];

export const FAILURE_REASONS = [
    'Destinatario ausente',
    'Dirección incorrecta',
    'Paquete dañado',
    'Otro',
];

export const SEVERITY_OPTIONS = [
    'Alto',
    'Medio',
    'Bajo',
];

export const IMPUTABILITY_OPTIONS = [
    'ME / Mensajero',
    'Cliente (destinatario)',
    'Por definir',
];

export const getImputabilityColor = (imputability) => {
    switch (imputability) {
        case 'ME / Mensajero': return 'bg-red-100 text-red-700 border-red-200';
        case 'Cliente (destinatario)': return 'bg-amber-100 text-amber-700 border-amber-200';
        default: return 'bg-slate-100 text-slate-600 border-slate-200';
    }
};
