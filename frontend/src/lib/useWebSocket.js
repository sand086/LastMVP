import { useEffect, useRef, useCallback, useState } from 'react';

const WS_RECONNECT_INTERVAL = 5000;
const WS_PING_INTERVAL = 30000;

/**
 * Hook to connect to the dashboard WebSocket and listen for real-time events.
 * @param {function} onEvent - Callback when an event is received: (event) => void
 * @returns {{ isConnected: boolean, connectionCount: number }}
 */
export function useWebSocket(onEvent) {
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef(null);
    const reconnectTimerRef = useRef(null);
    const pingTimerRef = useRef(null);
    const onEventRef = useRef(onEvent);

    // Keep callback reference fresh
    useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

    const connect = useCallback(() => {
        // Build WebSocket URL from the backend URL
        const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
        const wsUrl = backendUrl.replace(/^http/, 'ws') + '/ws/dashboard';

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                setIsConnected(true);
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
                } catch {
                    // ignore parse errors
                }
            };

            ws.onclose = () => {
                setIsConnected(false);
                clearInterval(pingTimerRef.current);
                // Auto-reconnect
                reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL);
            };

            ws.onerror = () => {
                ws.close();
            };
        } catch {
            // Retry on connection error
            reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_INTERVAL);
        }
    }, []);

    useEffect(() => {
        connect();
        return () => {
            clearTimeout(reconnectTimerRef.current);
            clearInterval(pingTimerRef.current);
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [connect]);

    return { isConnected };
}
