import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Upload, FileSpreadsheet, CheckCircle2, Loader2, Truck, Users, AlertCircle } from 'lucide-react';

export const LayoutStep2Route = ({
    currentStep,
    routeFile,
    routeData,
    routeUploading,
    routeError,
    routeFileRef,
    onFileSelect,
}) => (
    <Card className={currentStep === 2 ? 'ring-2 ring-slate-900' : ''}>
        <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
                <Truck className="w-5 h-5" />
                Paso 2: Archivo Route Summary
            </CardTitle>
        </CardHeader>
        <CardContent>
            {currentStep < 2 ? (
                <div className="text-center py-8 text-slate-400">
                    <Truck className="w-10 h-10 mx-auto mb-2 opacity-50" />
                    <p>Primero carga el archivo history-orders</p>
                </div>
            ) : !routeFile ? (
                <div
                    className="drop-zone cursor-pointer"
                    onClick={() => routeFileRef.current?.click()}
                    data-testid="route-file-zone"
                >
                    <input
                        ref={routeFileRef}
                        type="file"
                        accept=".csv,.xlsx"
                        onChange={onFileSelect}
                        className="hidden"
                        data-testid="route-file-input"
                    />
                    <Upload className="w-10 h-10 text-slate-400 mx-auto mb-3" />
                    <p className="text-slate-700 font-medium">
                        Selecciona archivo route-summary
                    </p>
                    <p className="text-slate-500 text-sm mt-1">
                        Formato: route-summary-aaaa-mm-dd-aaaa-mm-dd.xlsx
                    </p>
                    <p className="text-slate-400 text-xs mt-2">
                        CSV o XLSX • Máximo 10MB
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="flex items-center justify-between p-3 bg-slate-50 rounded-sm">
                        <div className="flex items-center gap-3">
                            <FileSpreadsheet className="w-8 h-8 text-emerald-600" />
                            <div>
                                <p className="font-medium text-slate-900">{routeFile.name}</p>
                                <p className="text-sm text-slate-500">
                                    {(routeFile.size / 1024).toFixed(1)} KB
                                </p>
                            </div>
                        </div>
                        {routeUploading ? (
                            <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                        ) : (
                            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        )}
                    </div>

                    {routeData && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-sm">
                            <div className="flex items-center gap-2 text-emerald-700 mb-2">
                                <Users className="w-5 h-5" />
                                <span className="font-medium">
                                    {routeData.total_routes} rutas con {routeData.drivers.length} mensajeros
                                </span>
                            </div>
                            <p className="text-sm text-emerald-600">
                                Columnas detectadas: Order ID, Driver, Team, Total Stops
                            </p>
                        </div>
                    )}
                </div>
            )}

            {routeError && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-sm flex items-center gap-2 text-red-700">
                    <AlertCircle className="w-5 h-5" />
                    <span>{routeError}</span>
                </div>
            )}
        </CardContent>
    </Card>
);
