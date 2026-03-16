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
    const provider = journey.provider_name || 'N/A';
    const zone = journey.packages?.[0]?.zone || 'N/A';
    const packagesLoaded = startData.packages_loaded || 0;
    const retryPackages = journey.packages_retry || 0;
    const odometer = startData.odometer_start || 0;
    
    return `📦 INICIO DE RUTA - LastMile OS
━━━━━━━━━━━━━━━━━━
📅 Fecha: ${date}
🚚 Proveedor: ${provider}
📍 Zona: ${zone}
📦 Paquetes cargados: ${packagesLoaded}
🔄 Reintentos: ${retryPackages}
🔢 Odómetro inicial: ${odometer.toLocaleString()} km
━━━━━━━━━━━━━━━━━━
✅ Ruta iniciada correctamente`;
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
    
    return `📦 CIERRE DE RUTA - LastMile OS
━━━━━━━━━━━━━━━━━━
📅 Fecha: ${date}
🚚 Proveedor: ${provider}
━━━━━━━━━━━━━━━━━━
✅ Entregados: ${delivered}
❌ Fallidos: ${failed}
🔄 Para reintento: ${toRetry}
━━━━━━━━━━━━━━━━━━
📊 Tasa de entrega: ${rate}%
🛣️ Km recorridos: ${km.toLocaleString()}
⏱️ Tiempo total: ${totalTime}
⚠️ Incidencias: ${incidents}
━━━━━━━━━━━━━━━━━━
✅ Ruta cerrada correctamente`;
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
