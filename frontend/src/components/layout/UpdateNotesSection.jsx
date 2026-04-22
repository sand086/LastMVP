import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { FileText, Loader2, Upload, CheckCircle2, X, AlertCircle } from 'lucide-react';

const MAX_SIZE_MB = 10;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;
const ALLOWED_EXT = ['.csv', '.xlsx', '.xls'];

export const UpdateNotesSection = ({ notesFileRef, notesUploading, notesResult, onUpload }) => {
    const [dragActive, setDragActive] = useState(false);
    const [selected, setSelected] = useState(null);
    const [localError, setLocalError] = useState(null);

    const validate = (file) => {
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (!ALLOWED_EXT.includes(ext)) {
            return `Formato inválido. Usa ${ALLOWED_EXT.join(', ')}.`;
        }
        if (file.size > MAX_SIZE_BYTES) {
            return `El archivo pesa ${(file.size / 1024 / 1024).toFixed(1)}MB. Máximo permitido: ${MAX_SIZE_MB}MB.`;
        }
        if (file.size < 50) {
            return 'Archivo muy pequeño o vacío.';
        }
        return null;
    };

    const handleFile = (file) => {
        if (!file) return;
        const err = validate(file);
        if (err) {
            setLocalError(err);
            setSelected(null);
            return;
        }
        setLocalError(null);
        setSelected(file);
        onUpload(file);
    };

    const handleInputChange = (e) => handleFile(e.target.files[0]);

    const handleDrop = (e) => {
        e.preventDefault();
        setDragActive(false);
        handleFile(e.dataTransfer.files?.[0]);
    };

    const handleReset = () => {
        setSelected(null);
        setLocalError(null);
        if (notesFileRef.current) notesFileRef.current.value = '';
    };

    return (
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
                {!selected && !notesUploading && (
                    <div
                        className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
                            dragActive ? 'border-blue-500 bg-blue-50' : 'border-slate-300 hover:border-blue-400 hover:bg-slate-50'
                        }`}
                        onClick={() => notesFileRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                        onDragLeave={() => setDragActive(false)}
                        onDrop={handleDrop}
                        data-testid="notes-drop-zone"
                    >
                        <input
                            ref={notesFileRef}
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            onChange={handleInputChange}
                            disabled={notesUploading}
                            className="hidden"
                            data-testid="notes-file-input"
                        />
                        <Upload className="w-7 h-7 text-slate-400 mx-auto mb-1.5" />
                        <p className="text-sm font-medium text-slate-700">Arrastra o haz clic</p>
                        <p className="text-xs text-slate-400 mt-0.5">CSV / XLSX · Máx {MAX_SIZE_MB}MB</p>
                    </div>
                )}

                {selected && (
                    <div className="flex items-center justify-between p-2.5 bg-slate-50 rounded border border-slate-200" data-testid="notes-file-chip">
                        <div className="flex items-center gap-2 min-w-0">
                            <FileText className="w-4 h-4 text-blue-600 shrink-0" />
                            <div className="min-w-0">
                                <p className="text-sm font-medium text-slate-900 truncate" title={selected.name}>{selected.name}</p>
                                <p className="text-xs text-slate-500">{(selected.size / 1024).toFixed(1)} KB</p>
                            </div>
                        </div>
                        {notesUploading ? (
                            <Loader2 className="w-4 h-4 animate-spin text-blue-500 shrink-0" />
                        ) : (
                            <div className="flex items-center gap-1 shrink-0">
                                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleReset} data-testid="notes-reset-btn">
                                    <X className="w-3.5 h-3.5" />
                                </Button>
                            </div>
                        )}
                    </div>
                )}

                <p className="text-xs text-slate-400">Formato: history-orders-aaaa-mm-dd.csv (requiere columnas order_reference_id + failure_reason_note o note_from_driver)</p>

                {localError && (
                    <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700" data-testid="notes-client-error">
                        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>{localError}</span>
                    </div>
                )}

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
                    <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700" data-testid="notes-server-error">
                        <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>{notesResult.error}</span>
                    </div>
                )}
            </CardContent>
        </Card>
    );
};
