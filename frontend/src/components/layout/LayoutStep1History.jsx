import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Upload, FileSpreadsheet, CheckCircle2, Loader2, Package, AlertCircle } from 'lucide-react';

export const LayoutStep1History = ({
    currentStep,
    historyFile,
    historyData,
    historyUploading,
    historyError,
    historyFileRef,
    onFileSelect,
}) => (
    <Card className={currentStep === 1 ? 'ring-2 ring-slate-900' : ''}>
        <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5" />
                Paso 1: Archivo History Orders
            </CardTitle>
        </CardHeader>
        <CardContent>
            {!historyFile ? (
                <div
                    className="drop-zone cursor-pointer"
                    onClick={() => historyFileRef.current?.click()}
                    data-testid="history-file-zone"
                >
                    <input
                        ref={historyFileRef}
                        type="file"
                        accept=".csv,.xlsx"
                        onChange={onFileSelect}
                        className="hidden"
                        data-testid="history-file-input"
                    />
                    <Upload className="w-10 h-10 text-slate-400 mx-auto mb-3" />
                    <p className="text-slate-700 font-medium">
                        Selecciona archivo history-orders
                    </p>
                    <p className="text-slate-500 text-sm mt-1">
                        Formato: history-orders-aaaa-mm-dd-aaaa-mm-dd.csv
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
                                <p className="font-medium text-slate-900">{historyFile.name}</p>
                                <p className="text-sm text-slate-500">
                                    {(historyFile.size / 1024).toFixed(1)} KB
                                </p>
                            </div>
                        </div>
                        {historyUploading ? (
                            <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                        ) : (
                            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        )}
                    </div>

                    {historyData && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-sm">
                            <div className="flex items-center gap-2 text-emerald-700 mb-2">
                                <Package className="w-5 h-5" />
                                <span className="font-medium">
                                    {historyData.total_orders} órdenes en {historyData.total_routes} rutas
                                    {historyData.ignored_rows > 0 && (
                                        <span className="text-slate-400 ml-1">({historyData.ignored_rows} filas ignoradas)</span>
                                    )}
                                </span>
                            </div>
                            <p className="text-sm text-emerald-600">
                                Columnas detectadas: order_reference_id, tracking_url, order_status
                            </p>
                        </div>
                    )}
                </div>
            )}

            {historyError && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-sm flex items-center gap-2 text-red-700">
                    <AlertCircle className="w-5 h-5" />
                    <span>{historyError}</span>
                </div>
            )}
        </CardContent>
    </Card>
);
