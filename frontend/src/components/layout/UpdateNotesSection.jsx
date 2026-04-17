import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { FileText, Loader2 } from 'lucide-react';

export const UpdateNotesSection = ({ notesFileRef, notesUploading, notesResult, onUpload }) => (
    <Card className="border-slate-200">
        <CardHeader className="pb-3">
            <CardTitle className="font-heading text-lg flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-500" />
                Actualizar notas de entrega
            </CardTitle>
            <p className="text-xs text-slate-500">
                Sube un archivo history-orders para actualizar failure_reason_note y note_from_driver sin afectar otros campos.
            </p>
        </CardHeader>
        <CardContent className="space-y-3">
            <div className="flex items-center gap-3">
                <div className="flex-1">
                    <Input
                        ref={notesFileRef}
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        onChange={(e) => onUpload(e.target.files[0])}
                        disabled={notesUploading}
                        data-testid="notes-file-input"
                    />
                    <p className="text-xs text-slate-400 mt-1">Formato: history-orders-aaaa-mm-dd.csv (requiere columnas order_reference_id + failure_reason_note o note_from_driver)</p>
                </div>
                {notesUploading && <Loader2 className="w-5 h-5 animate-spin text-blue-500" />}
            </div>
            {notesResult && !notesResult.error && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 rounded-lg p-3" data-testid="notes-result">
                    <div className="text-center">
                        <p className="text-lg font-mono font-bold text-slate-700">{notesResult.total_rows}</p>
                        <p className="text-xs text-slate-500">Filas en archivo</p>
                    </div>
                    <div className="text-center">
                        <p className="text-lg font-mono font-bold text-emerald-600">{notesResult.updated}</p>
                        <p className="text-xs text-slate-500">Actualizados</p>
                    </div>
                    <div className="text-center">
                        <p className="text-lg font-mono font-bold text-amber-600">{notesResult.not_found}</p>
                        <p className="text-xs text-slate-500">No encontrados</p>
                    </div>
                    <div className="text-center">
                        <p className="text-lg font-mono font-bold text-red-600">{notesResult.errors}</p>
                        <p className="text-xs text-slate-500">Errores</p>
                    </div>
                </div>
            )}
            {notesResult?.error && (
                <p className="text-sm text-red-600 bg-red-50 p-2 rounded">{notesResult.error}</p>
            )}
        </CardContent>
    </Card>
);
