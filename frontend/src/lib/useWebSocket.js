import { useEffect, useRef, useCallback, useState } from 'react';

const WS_RECONNECT_INTERVAL = 5000;
const WS_PING_INTERVAL = 30000;

/**
 * Hook to connect to the dashboard WebSocket and listen for real-time events.
 * @param {function} onEvent - Callback when an event is received: (event) => void
 * @returns {{ isConnected: boolean, connectionMode: 'websocket'|'polling'|'offline', justRecovered: boolean }}
 *   - connectionMode: 'websocket' cuando el WS está conectado; 'polling' cuando se intenta
 *     reconectar pero el cliente sigue funcionando con la API REST cada 60s; 'offline'
 *     cuando >3 intentos consecutivos fallaron sin éxito.
 *   - justRecovered: true durante 3s tras reconexión exitosa desde polling/offline.
 */
export function useWebSocket(onEvent) {
    const [isConnected, setIsConnected] = useState(false);
    const [connectionMode, setConnectionMode] = useState('polling');
    const [justRecovered, setJustRecovered] = useState(false);
    const wsRef = useRef(null);
    const reconnectTimerRef = useRef(null);
    const pingTimerRef = useRef(null);
    const recoveryTimerRef = useRef(null);
    const onEventRef = useRef(onEvent);
    const failureCountRef = useRef(0);
    const wasConnectedRef = useRef(false);

    // Keep callback reference fresh
    useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

    const connect = useCallback(() => {
        // Build WebSocket URL from the backend URL
        const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
        const wsUrl = backendUrl.replace(/^http/, 'ws') + '/api/ws/dashboard';

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                setIsConnected(true);
                setConnectionMode('websocket');
                // Si veníamos de offline/polling y ya habíamos conectado al menos una vez, mostrar "Conexión restaurada"
                if (wasConnectedRef.current && failureCountRef.current > 0) {
                    setJustRecovered(true);
                    clearTimeout(recoveryTimerRef.current);
                    recoveryTimerRef.current = setTimeout(() => setJustRecovered(false), 3000);
                }
                wasConnectedRef.current = true;
                failureCountRef.current = 0;
                // Start ping interval
                pingTimerRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping');
                    }
                }, WS_PING_INTERVAL);
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'pong') return;
                    onEventRef.current?.(data);
                } catch (err) {
                    console.error('WebSocket message parse error:', err);
                }
            };

            ws.onclose = () => {
                setIsConnected(false);
                failureCountRef.current += 1;
                // Tras >3 fallos consecutivos sin éxito → offline. Mientras tanto: polling.
                setConnectionMode(failureCountRef.current > 3 ? 'offline' : 'polling');
                clearInterval(pingTimerRef.current);
                // Auto-reconnect
                reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL);
            };

            ws.onerror = () => {
                ws.close();
            };
        } catch (err) {
            console.error('WebSocket connection error:', err);
            failureCountRef.current += 1;
            setConnectionMode(failureCountRef.current > 3 ? 'offline' : 'polling');
            // Retry on connection error
            reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL);
        }
    }, []);

    useEffect(() => {
        connect();
        return () => {
            clearTimeout(reconnectTimerRef.current);
            clearTimeout(recoveryTimerRef.current);
            clearInterval(pingTimerRef.current);
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [connect]);

    return { isConnected, connectionMode, justRecovered };
}
