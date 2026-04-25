import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

const isDev = process.env.NODE_ENV === 'development';

/**
 * React error boundary — captura errores no manejados de los hijos y muestra UI
 * de fallback. Mantiene la app navegable cuando una página específica falla.
 *
 * Props:
 *   - fallbackMessage: mensaje custom (opcional)
 *   - children: componentes React a proteger
 */
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null, showStack: false };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        this.setState({ errorInfo });
        if (isDev) {
            // dev: stack completo en consola para debug
            console.error('[ErrorBoundary] Caught:', error, errorInfo);
        } else {
            // prod: solo mensaje (sin stack al cliente)
            console.error('[ErrorBoundary] Error:', error?.message || String(error));
        }
    }

    handleReload = () => {
        window.location.reload();
    };

    handleReset = () => {
        this.setState({ hasError: false, error: null, errorInfo: null, showStack: false });
    };

    render() {
        if (!this.state.hasError) {
            return this.props.children;
        }

        const { fallbackMessage } = this.props;
        const message = fallbackMessage || 'Ocurrió un error inesperado en esta sección.';

        return (
            <div
                data-testid="error-boundary-fallback"
                role="alert"
                style={{
                    padding: '32px 24px',
                    margin: 16,
                    background: '#FEF2F2',
                    border: '1px solid #FCA5A5',
                    borderRadius: 8,
                    maxWidth: 720,
                    marginLeft: 'auto',
                    marginRight: 'auto',
                    fontFamily: "'DM Sans', sans-serif",
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                    <AlertTriangle style={{ width: 22, height: 22, color: '#B91C1C' }} />
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#991B1B' }}>
                        Algo salió mal
                    </h3>
                </div>
                <p style={{ margin: '0 0 16px 0', fontSize: 13, color: '#7F1D1D', lineHeight: 1.5 }}>
                    {message}
                </p>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <button
                        onClick={this.handleReload}
                        data-testid="error-boundary-reload"
                        style={{
                            padding: '8px 14px', fontSize: 12, fontWeight: 600,
                            background: '#B91C1C', color: '#fff', border: 'none',
                            borderRadius: 6, cursor: 'pointer',
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                        }}
                    >
                        <RefreshCw style={{ width: 13, height: 13 }} />
                        Recargar página
                    </button>
                    <button
                        onClick={this.handleReset}
                        data-testid="error-boundary-retry"
                        style={{
                            padding: '8px 14px', fontSize: 12, fontWeight: 600,
                            background: '#fff', color: '#7F1D1D', border: '1px solid #FCA5A5',
                            borderRadius: 6, cursor: 'pointer',
                        }}
                    >
                        Reintentar sin recargar
                    </button>
                </div>

                {isDev && this.state.error && (
                    <details
                        style={{ marginTop: 12, fontSize: 11, color: '#7F1D1D' }}
                        onToggle={(e) => this.setState({ showStack: e.target.open })}
                    >
                        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
                            Stack trace (solo en desarrollo)
                        </summary>
                        <pre
                            style={{
                                marginTop: 8, padding: 10, background: '#fff',
                                border: '1px solid #FCA5A5', borderRadius: 4,
                                fontSize: 10.5, overflow: 'auto', maxHeight: 280,
                                fontFamily: "'DM Mono', Menlo, monospace",
                            }}
                        >
                            {this.state.error.toString()}
                            {this.state.errorInfo?.componentStack || ''}
                        </pre>
                    </details>
                )}
            </div>
        );
    }
}

export default ErrorBoundary;
