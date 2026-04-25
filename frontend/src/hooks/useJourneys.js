import { useApi } from './useApi';

/**
 * useJourneys — wrapper específico para el endpoint /journeys.
 *
 * Acepta los mismos filtros que getJourneys() en lib/api.js:
 *   { date_from, date_to, client_id, provider_id, status, page, page_size, q }
 *
 * Devuelve { data, loading, error, refetch }.
 *
 * Notas:
 *   - Se omiten valores 'all' o vacíos para no enviarlos al backend.
 *   - El componente puede deshabilitar el fetch inicial con `enabled: false`.
 */
export function useJourneys(filters = {}, options = {}) {
    const cleanParams = {};
    Object.entries(filters || {}).forEach(([k, v]) => {
        if (v === undefined || v === null || v === '' || v === 'all') return;
        cleanParams[k] = v;
    });

    return useApi('/journeys', { params: cleanParams, ...options });
}
