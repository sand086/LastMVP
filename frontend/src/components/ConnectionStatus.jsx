import React from 'react';
import { Wifi, WifiOff, RefreshCw, CheckCircle2 } from 'lucide-react';

/**
 * Indicador discreto de estado de conexión (esquina superior derecha del Dashboard).
 *
 * Estados:
 *   - websocket: punto verde "En vivo"
 *   - polling: punto ámbar "Actualización cada 60s"
 *   - offline: punto coral "Sin conexión"
 *   - justRecovered: badge azul transitorio "Conexión restaurada"
 */
const ConnectionStatus = ({ connectionMode = 'polling', justRecovered = false }) => {
    if (justRecovered) {
        return (
            <div
                data-testid="connection-status"
                data-connection-mode="recovered"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200"
                style={{ fontSize: 11, fontWeight: 600, color: '#047857' }}
                title="WebSocket reconectado exitosamente"
            >
                <CheckCircle2 className="w-3 h-3" />
                <span>Conexión restaurada</span>
            </div>
        );
    }

    if (connectionMode === 'websocket') {
        return (
            <div
                data-testid="connection-status"
                data-connection-mode="websocket"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-100"
                style={{ fontSize: 11, fontWeight: 600, color: '#047857' }}
                title="Conexión en tiempo real activa (WebSocket)"
            >
                <span
                    className="w-2 h-2 rounded-full bg-emerald-500"
                    style={{ animation: 'cs-pulse 1.8s ease-in-out infinite' }}
                />
                <span>En vivo</span>
                <style>{`
                    @keyframes cs-pulse {
                        0%, 100% { transform: scale(1); opacity: 1; }
                        50% { transform: scale(1.4); opacity: 0.55; }
                    }
                `}</style>
            </div>
        );
    }

    if (connectionMode === 'offline') {
        return (
            <div
                data-testid="connection-status"
                data-connection-mode="offline"
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-50 border border-red-200"
                style={{ fontSize: 11, fontWeight: 600, color: '#B91C1C' }}
                title="Sin conexión al servidor. Verifica tu red."
            >
                <WifiOff className="w-3 h-3" />
                <span>Sin conexión</span>
            </div>
        );
    }

    // polling (default)
    return (
        <div
            data-testid="connection-status"
            data-connection-mode="polling"
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200"
            style={{ fontSize: 11, fontWeight: 600, color: '#92400E' }}
            title="WebSocket no disponible — datos actualizados cada 60s vía polling"
        >
            <RefreshCw className="w-3 h-3" />
            <span>Actualización cada 60s</span>
        </div>
    );
};

export default ConnectionStatus;
