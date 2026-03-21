import React, { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { 
    ShieldCheck, Play, Loader2, RefreshCw, Download, AlertTriangle, 
    CheckCircle2, Info, ExternalLink
} from 'lucide-react';
import { toast } from 'sonner';
import { downloadFile } from '../lib/utils';

const SEVERITY_COLORS = {
    'Alta': 'bg-red-100 text-red-700 border-red-200',
    'Media': 'bg-amber-100 text-amber-700 border-amber-200',
    'Baja': 'bg-blue-100 text-blue-700 border-blue-200',
};

const SEVERITY_ICONS = {
    'Alta': AlertTriangle,
    'Media': Info,
    'Baja': Info,
};

const SystemIntegrity = () => {
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [exporting, setExporting] = useState(false);

    const fetchResults = useCallback(async () => {
        try {
            const res = await api.get('/system/integrity/results');
            setResults(res.data);
        } catch (error) {
            console.error('Error fetching integrity results:', error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchResults(); }, [fetchResults]);

    const handleRun = async () => {
        setRunning(true);
        try {
            const res = await api.post('/system/integrity/run');
            setResults(res.data);
            toast.success(`Validación completa: ${res.data.total_issues} problemas encontrados`);
        } catch (error) {
            toast.error('Error al ejecutar validación');
        } finally {
            setRunning(false);
        }
    };

    const handleExport = async () => {
        setExporting(true);
        try {
            const res = await api.get('/system/integrity/export', { responseType: 'blob' });
            downloadFile(res.data, `integrity_report_${new Date().toISOString().slice(0,10)}.csv`);
            toast.success('Reporte exportado');
        } catch (error) {
            toast.error('Error al exportar');
        } finally {
            setExporting(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">Data Integrity</h1>
                    <p className="text-slate-500 text-sm">Validación de integridad de datos en MongoDB</p>
                </div>
                <div className="flex gap-2">
                    {results?.issues?.length > 0 && (
                        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting} data-testid="export-integrity-btn">
                            {exporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Download className="w-4 h-4 mr-2" />}
                            Exportar
                        </Button>
                    )}
                    <Button onClick={handleRun} disabled={running} data-testid="run-integrity-btn">
                        {running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                        Ejecutar validación
                    </Button>
                </div>
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
                </div>
            ) : !results?.issues ? (
                <Card className="p-8 text-center">
                    <ShieldCheck className="w-12 h-12 mx-auto mb-3 text-slate-300" />
                    <p className="text-slate-600 font-medium">No se ha ejecutado ninguna validación</p>
                    <p className="text-sm text-slate-400 mt-1">Haz clic en "Ejecutar validación" para comenzar</p>
                </Card>
            ) : (
                <>
                    {/* Summary cards */}
                    <div className="grid grid-cols-4 gap-4">
                        <Card className="p-4 text-center">
                            <p className="text-xs text-slate-500 uppercase">Total</p>
                            <p className="font-mono font-bold text-2xl">{results.total_issues}</p>
                        </Card>
                        <Card className="p-4 text-center border-red-200">
                            <p className="text-xs text-red-500 uppercase">Alta</p>
                            <p className="font-mono font-bold text-2xl text-red-600">{results.issues_by_severity?.Alta || 0}</p>
                        </Card>
                        <Card className="p-4 text-center border-amber-200">
                            <p className="text-xs text-amber-500 uppercase">Media</p>
                            <p className="font-mono font-bold text-2xl text-amber-600">{results.issues_by_severity?.Media || 0}</p>
                        </Card>
                        <Card className="p-4 text-center border-blue-200">
                            <p className="text-xs text-blue-500 uppercase">Baja</p>
                            <p className="font-mono font-bold text-2xl text-blue-600">{results.issues_by_severity?.Baja || 0}</p>
                        </Card>
                    </div>

                    {/* Last run info */}
                    {results.timestamp && (
                        <p className="text-xs text-slate-400">
                            Última ejecución: {results.timestamp?.slice(0, 19)}
                        </p>
                    )}

                    {/* Issues */}
                    {results.total_issues === 0 ? (
                        <Card className="p-8 text-center">
                            <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-emerald-400" />
                            <p className="text-slate-600 font-medium">Sin inconsistencias</p>
                            <p className="text-sm text-slate-400 mt-1">Todos los datos están íntegros</p>
                        </Card>
                    ) : (
                        <div className="space-y-3">
                            {results.issues.map((issue, idx) => {
                                const Icon = SEVERITY_ICONS[issue.severity] || Info;
                                return (
                                    <Card key={idx} data-testid={`integrity-issue-${idx}`}>
                                        <CardContent className="p-4">
                                            <div className="flex items-start gap-3">
                                                <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${
                                                    issue.severity === 'Alta' ? 'text-red-500' :
                                                    issue.severity === 'Media' ? 'text-amber-500' : 'text-blue-500'
                                                }`} />
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className={`px-2 py-0.5 text-xs font-medium rounded border ${SEVERITY_COLORS[issue.severity]}`}>
                                                            {issue.severity}
                                                        </span>
                                                        <span className="font-medium text-sm text-slate-900">{issue.type}</span>
                                                    </div>
                                                    <p className="text-sm text-slate-600">{issue.description}</p>
                                                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                                                        <span>Entidad: {issue.entity_type}</span>
                                                        <span className="font-mono">{issue.entity_id?.slice(0, 8)}...</span>
                                                    </div>
                                                    <p className="text-xs text-blue-600 mt-1">
                                                        Acción sugerida: {issue.suggested_action}
                                                    </p>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                );
                            })}
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default SystemIntegrity;
