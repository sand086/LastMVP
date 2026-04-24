import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { CheckCircle2 } from 'lucide-react';

export const LayoutCreationResult = ({ result }) => {
    if (!result) return null;
    return (
        <Card className="border-emerald-200 bg-emerald-50">
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2 text-emerald-700">
                    <CheckCircle2 className="w-5 h-5" />
                    {result.message}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {result.created_journeys?.length > 0 && (
                    <div>
                        <p className="text-sm font-medium text-emerald-800 mb-2">Rutas creadas:</p>
                        <ul className="space-y-1 text-sm text-emerald-700">
                            {result.created_journeys.map((j) => (
                                <li key={`created-${j.route_id}`}>
                                    • {j.driver} - {j.packages} paquetes nuevos (Ruta: {j.route_id})
                                    {j.duplicates_updated > 0 && (
                                        <span className="text-blue-600 ml-2">
                                            ({j.duplicates_updated} paquetes actualizados)
                                        </span>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {result.updated_journeys?.length > 0 && (
                    <div>
                        <p className="text-sm font-medium text-blue-700 mb-2">Rutas con paquetes actualizados:</p>
                        <ul className="space-y-1 text-sm text-blue-600">
                            {result.updated_journeys.map((j) => (
                                <li key={`updated-${j.route_id || j.driver}`}>
                                    • {j.driver || j.route_id} - {j.packages_updated} paquetes actualizados
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {(result.total_new_packages > 0 || result.total_updated_packages > 0) && (
                    <div className="p-3 bg-white border border-emerald-200 rounded-sm">
                        <p className="text-sm font-medium text-slate-800">
                            Resumen: {result.total_new_packages || 0} nuevos paquetes creados, {result.total_updated_packages || 0} paquetes actualizados
                        </p>
                    </div>
                )}

                {result.skipped_duplicates?.length > 0 && (
                    <div>
                        <p className="text-sm font-medium text-amber-700 mb-2">Rutas duplicadas omitidas:</p>
                        <ul className="space-y-1 text-sm text-amber-600">
                            {result.skipped_duplicates.map((id) => (
                                <li key={`skip-${id}`}>• {id}</li>
                            ))}
                        </ul>
                    </div>
                )}

                {result.errors?.length > 0 && (
                    <div>
                        <p className="text-sm font-medium text-red-700 mb-2">Errores:</p>
                        <ul className="space-y-1 text-sm text-red-600">
                            {result.errors.map((err, idx) => (
                                <li key={`err-${idx}-${err.slice(0, 12)}`}>• {err}</li>
                            ))}
                        </ul>
                    </div>
                )}
            </CardContent>
        </Card>
    );
};
