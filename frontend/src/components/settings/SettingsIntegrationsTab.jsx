import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, AlertTriangle, ShieldAlert } from 'lucide-react';
import { listIntegrations, getClients } from '../../lib/api';
import ClientIntegrationCard from './ClientIntegrationCard';

const SettingsIntegrationsTab = ({ isDeveloper }) => {
    const [clients, setClients] = useState([]);
    const [integrations, setIntegrations] = useState({}); // by client_id
    const [loading, setLoading] = useState(true);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [clientsRes, integRes] = await Promise.allSettled([
                getClients(),
                listIntegrations(),
            ]);
            if (clientsRes.status === 'fulfilled') setClients(clientsRes.value.data || []);
            if (integRes.status === 'fulfilled') {
                const map = {};
                (integRes.value.data?.data || []).forEach(i => { map[i.client_id] = i; });
                setIntegrations(map);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { if (isDeveloper) fetchAll(); }, [isDeveloper, fetchAll]);

    if (!isDeveloper) {
        return (
            <div
                data-testid="integrations-restricted"
                className="bg-amber-50 border border-amber-200 rounded-md p-6 text-center"
            >
                <ShieldAlert className="w-10 h-10 text-amber-600 mx-auto mb-3" />
                <h3 className="font-semibold text-amber-900 mb-1">Acceso restringido</h3>
                <p className="text-sm text-amber-800">Solo desarrolladores pueden gestionar integraciones de terceros.</p>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12 text-slate-500" data-testid="integrations-loading">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                Cargando integraciones...
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="integrations-tab">
            {/* Info banner */}
            <div className="bg-blue-50 border border-blue-200 rounded-md p-4 text-sm text-blue-900">
                <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5 text-blue-600" />
                    <div>
                        <p className="font-semibold mb-1">Integraciones por cliente (multi-fuente)</p>
                        <p className="text-xs leading-relaxed">
                            Cada cliente puede usar Kosmo, Routal o Manual. Las credenciales se cifran con AES (Fernet) y se enmascaran al cargarlas.
                            Los webhooks de Routal validan firma HMAC-SHA256 automáticamente. Configura un cliente para Routal cuando obtengas el API key + Project ID + Webhook secret.
                        </p>
                    </div>
                </div>
            </div>

            {clients.length === 0 ? (
                <div className="text-center py-12 text-slate-500" data-testid="integrations-empty">
                    No hay clientes configurados. Crea uno desde la pestaña <strong>Clientes</strong> primero.
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {clients.map(client => (
                        <ClientIntegrationCard
                            key={client.id}
                            client={client}
                            integration={integrations[client.id]}
                            onChanged={fetchAll}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default SettingsIntegrationsTab;
