import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Truck, History, Loader2 } from 'lucide-react';
import { formatDate } from '../../lib/utils';

/** Preview de rutas detectadas (aparece despues de subir History Orders). */
export const RoutesPreviewCard = ({ routes }) => {
    if (!routes || routes.length === 0) return null;
    return (
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <Truck className="w-5 h-5" />
                    Rutas Detectadas
                </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
                <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
                    {routes.slice(0, 10).map((route) => (
                        <div key={route.route_id} className="p-3 hover:bg-slate-50">
                            <div className="flex items-center justify-between mb-1">
                                <span className="font-mono text-sm font-medium">{route.route_id}</span>
                                <span className="text-xs bg-slate-100 px-2 py-0.5 rounded">
                                    {route.orders.length} órdenes
                                </span>
                            </div>
                            {route.driver_name && (
                                <p className="text-xs text-slate-500">{route.driver_name}</p>
                            )}
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
};

/** Historial de las ultimas 8 cargas. */
export const UploadHistoryCard = ({ loading, uploadHistory }) => (
    <Card>
        <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
                <History className="w-5 h-5" />
                Historial de Cargas
            </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
            {loading ? (
                <div className="p-4 flex justify-center">
                    <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
                </div>
            ) : uploadHistory.length === 0 ? (
                <div className="text-center py-8 text-slate-500">
                    <History className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Sin cargas recientes</p>
                </div>
            ) : (
                <div className="divide-y divide-slate-100">
                    {uploadHistory.slice(0, 8).map((entry) => (
                        <div key={entry.id} className="p-3 hover:bg-slate-50">
                            <div className="flex items-center justify-between mb-1">
                                <span className="font-mono text-sm">{formatDate(entry.date)}</span>
                                <span className="text-xs text-slate-500">
                                    {entry.package_count} paquetes
                                </span>
                            </div>
                            <p className="text-sm text-slate-600">{entry.provider_name}</p>
                        </div>
                    ))}
                </div>
            )}
        </CardContent>
    </Card>
);
