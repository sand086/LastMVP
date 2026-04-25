import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../lib/api';

/**
 * useApi — hook genérico para data fetching con Axios + AbortController + retry.
 *
 * Reemplaza el patrón repetido en muchas páginas:
 *   useEffect(() => { setLoading(true); api.get(url).then(setData)... }, [...])
 *
 * Ventajas:
 *   - Cancela el fetch al desmontar el componente (no setState en componentes muertos)
 *   - 2 reintentos automáticos con 1s entre ellos en errores de red (NO en 4xx auth)
 *   - Refetch manual desde el caller (botones "Actualizar")
 *   - Soporta options.enabled = false para deshabilitar el fetch automático
 *
 * Patrón esperado para migrar otras páginas:
 *   1) Reemplaza useEffect+fetch+setState por:
 *        const { data, loading, error, refetch } = useApi('/journeys', { params: { ... } });
 *   2) Si necesitas múltiples llamadas, hace múltiples useApi (cada uno cancela el suyo).
 *   3) Para POST/PUT/DELETE NO uses este hook — sigue llamando api.post() directo.
 *
 * @param {string|null} url - Path relativo (axios baseURL ya configurado). null/'' deshabilita.
 * @param {object} options - { params, enabled, retries, retryDelayMs }
 * @returns {{ data, loading, error, refetch }}
 */
export function useApi(url, options = {}) {
    const {
        params,
        enabled = true,
        retries = 2,
        retryDelayMs = 1000,
    } = options;

    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(Boolean(enabled && url));
    const [error, setError] = useState(null);

    const abortRef = useRef(null);
    const mountedRef = useRef(true);

    // Stable JSON of params para detectar cambios sin recrear referencia
    const paramsKey = JSON.stringify(params ?? {});

    const fetchData = useCallback(async () => {
        if (!enabled || !url) return;

        // Cancelar fetch anterior si todavía estaba en vuelo
        if (abortRef.current) {
            abortRef.current.abort();
        }
        const ac = new AbortController();
        abortRef.current = ac;

        setLoading(true);
        setError(null);

        let attempt = 0;
        while (attempt <= retries) {
            try {
                const res = await api.get(url, {
                    params,
                    signal: ac.signal,
                });
                if (!mountedRef.current) return;
                setData(res.data);
                setError(null);
                setLoading(false);
                return;
            } catch (err) {
                // Cancelación intencional → silencio
                if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED' || ac.signal.aborted) {
                    return;
                }
                // Errores 4xx (auth, validación) NO deben reintentarse
                const status = err?.response?.status;
                const isClientError = status >= 400 && status < 500;
                if (isClientError || attempt >= retries) {
                    if (!mountedRef.current) return;
                    setError(err);
                    setLoading(false);
                    return;
                }
                attempt += 1;
                await new Promise((r) => setTimeout(r, retryDelayMs));
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [url, paramsKey, enabled, retries, retryDelayMs]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
            if (abortRef.current) abortRef.current.abort();
        };
    }, []);

    return { data, loading, error, refetch: fetchData };
}
