import React, { useState, useMemo } from 'react';
import { generateReport, generateReportExcel, getQualityReport, exportQualityReport } from '../lib/api';
import { downloadFile } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Checkbox } from '../components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
    FileText, 
    Download, 
    Loader2, 
    BarChart3, 
    Truck, 
    Users, 
    AlertTriangle,
    Sparkles,
    Calendar,
    FileSpreadsheet,
    ShieldCheck,
    ExternalLink,
} from 'lucide-react';
import { toast } from 'sonner';

const PERIOD_PRESETS = [
    { label: 'Últimos 7 días', value: '7d' },
    { label: 'Últimos 15 días', value: '15d' },
    { label: 'Mes actual', value: 'current_month' },
    { label: 'Mes anterior', value: 'prev_month' },
    { label: 'Personalizado', value: 'custom' },
];

const REPORT_SECTIONS = [
    { id: 'provider_metrics', label: 'Métricas por proveedor', icon: Truck, description: 'Días operados, rutas, paquetes, tasa de entrega, km' },
    { id: 'driver_metrics', label: 'Métricas por driver', icon: Users, description: 'Desempeño individual por mensajero' },
    { id: 'incidents_breakdown', label: 'Desglose de incidencias', icon: AlertTriangle, description: 'Conteo por tipo e imputabilidad' },
];

const getDateRange = (preset) => {
    const now = new Date();
    const fmt = (d) => d.toISOString().split('T')[0];
    
    switch (preset) {
        case '7d': {
            const from = new Date(now);
            from.setDate(from.getDate() - 6);
            return { from: fmt(from), to: fmt(now) };
        }
        case '15d': {
            const from = new Date(now);
            from.setDate(from.getDate() - 14);
            return { from: fmt(from), to: fmt(now) };
        }
        case 'current_month': {
            const from = new Date(now.getFullYear(), now.getMonth(), 1);
            return { from: fmt(from), to: fmt(now) };
        }
        case 'prev_month': {
            const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
            const to = new Date(now.getFullYear(), now.getMonth(), 0);
            return { from: fmt(from), to: fmt(to) };
        }
        default:
            return { from: fmt(now), to: fmt(now) };
    }
};

const Reports = () => {
    const [periodPreset, setPeriodPreset] = useState('7d');
    const [dateFrom, setDateFrom] = useState(() => getDateRange('7d').from);
    const [dateTo, setDateTo] = useState(() => getDateRange('7d').to);
    const [selectedSections, setSelectedSections] = useState(['provider_metrics', 'driver_metrics', 'incidents_breakdown']);
    const [loading, setLoading] = useState(false);
    const [excelLoading, setExcelLoading] = useState(false);
    const [reportData, setReportData] = useState(null);
    const [qualityData, setQualityData] = useState(null);
    const [qualityLoading, setQualityLoading] = useState(false);
    const [cubboExporting, setCubboExporting] = useState(false);

    const handlePeriodChange = (preset) => {
        setPeriodPreset(preset);
        if (preset !== 'custom') {
            const range = getDateRange(preset);
            setDateFrom(range.from);
            setDateTo(range.to);
        }
    };

    const toggleSection = (sectionId) => {
        setSelectedSections(prev => 
            prev.includes(sectionId) 
                ? prev.filter(s => s !== sectionId) 
                : [...prev, sectionId]
        );
    };

    const handleGenerateReport = async () => {
        if (selectedSections.length === 0) {
            toast.error('Selecciona al menos una sección');
            return;
        }
        setLoading(true);
        try {
            const res = await generateReport({
                date_from: dateFrom,
                date_to: dateTo,
                sections: selectedSections,
            });
            if (res.data.error) {
                toast.error(res.data.error);
            } else {
                setReportData(res.data);
                toast.success('Reporte generado');
            }
        } catch (error) {
            toast.error('Error al generar reporte');
        } finally {
            setLoading(false);
        }
    };

    const handleDownloadExcel = async () => {
        setExcelLoading(true);
        try {
            const res = await generateReportExcel({
                date_from: dateFrom,
                date_to: dateTo,
                sections: selectedSections,
            });
            downloadFile(res.data, `reporte_${dateFrom}_${dateTo}.xlsx`);
            toast.success('Excel descargado');
        } catch (error) {
            toast.error('Error al descargar Excel');
        } finally {
            setExcelLoading(false);
        }
    };

    const handleLoadQuality = async () => {
        setQualityLoading(true);
        try {
            const res = await getQualityReport({ date_from: dateFrom, date_to: dateTo });
            setQualityData(res.data);
            toast.success('Reporte de calidad cargado');
        } catch (error) {
            toast.error('Error al cargar reporte de calidad');
        } finally {
            setQualityLoading(false);
        }
    };

    const handleExportCubbo = async () => {
        setCubboExporting(true);
        try {
            const formData = new FormData();
            formData.append('date_from', dateFrom);
            formData.append('date_to', dateTo);
            const res = await exportQualityReport(formData);
            downloadFile(res.data, `calidad_cubbo_${dateFrom}_${dateTo}.xlsx`);
            toast.success('Excel para Cubbo descargado');
        } catch (error) {
            toast.error('Error al exportar');
        } finally {
            setCubboExporting(false);
        }
    };

    const MetricTable = ({ data, title }) => {
        if (!data || Object.keys(data).length === 0) return null;
        const entries = Object.entries(data);
        return (
            <div className="border border-slate-200 rounded-sm overflow-hidden">
                <div className="p-3 bg-slate-50 border-b border-slate-200">
                    <p className="font-medium text-slate-900 text-sm">{title}</p>
                </div>
                <div className="overflow-x-auto">
                    <table className="data-table w-full text-sm">
                        <thead>
                            <tr>
                                <th>Nombre</th>
                                <th className="text-center">Días</th>
                                <th className="text-center">Rutas</th>
                                <th className="text-center">Cargados</th>
                                <th className="text-center">Entregados</th>
                                <th className="text-center">Fallidos</th>
                                <th className="text-center">Reintentos</th>
                                <th className="text-center">Tasa %</th>
                                <th className="text-center">Km</th>
                            </tr>
                        </thead>
                        <tbody>
                            {entries.map(([name, m]) => (
                                <tr key={name}>
                                    <td className="font-medium">{name}</td>
                                    <td className="text-center font-mono">{m.days_operated}</td>
                                    <td className="text-center font-mono">{m.routes}</td>
                                    <td className="text-center font-mono">{m.packages_loaded}</td>
                                    <td className="text-center font-mono text-emerald-700">{m.delivered}</td>
                                    <td className="text-center font-mono text-red-700">{m.failed}</td>
                                    <td className="text-center font-mono text-amber-700">{m.retry}</td>
                                    <td className="text-center font-mono font-bold">
                                        <span className={
                                            m.delivery_rate >= 70 ? 'text-emerald-600' :
                                            m.delivery_rate >= 40 ? 'text-amber-600' : 'text-red-600'
                                        }>
                                            {m.delivery_rate}%
                                        </span>
                                    </td>
                                    <td className="text-center font-mono">{m.km_total?.toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                    Reportes
                </h1>
                <p className="text-slate-500 text-sm">
                    Genera reportes personalizados con insights de IA
                </p>
            </div>

            {/* Configuration */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Period Selection */}
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="font-heading text-base flex items-center gap-2">
                            <Calendar className="w-4 h-4" />
                            Período
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="grid grid-cols-2 gap-2">
                            {PERIOD_PRESETS.map((p) => (
                                <Button
                                    key={p.value}
                                    variant={periodPreset === p.value ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => handlePeriodChange(p.value)}
                                    className="text-xs"
                                    data-testid={`period-${p.value}`}
                                >
                                    {p.label}
                                </Button>
                            ))}
                        </div>
                        {periodPreset === 'custom' && (
                            <div className="grid grid-cols-2 gap-2 pt-2">
                                <div className="space-y-1">
                                    <Label className="text-xs">Desde</Label>
                                    <Input
                                        type="date"
                                        value={dateFrom}
                                        onChange={(e) => setDateFrom(e.target.value)}
                                        data-testid="report-date-from"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label className="text-xs">Hasta</Label>
                                    <Input
                                        type="date"
                                        value={dateTo}
                                        onChange={(e) => setDateTo(e.target.value)}
                                        data-testid="report-date-to"
                                    />
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Section Selection (Lego blocks) */}
                <Card className="lg:col-span-2">
                    <CardHeader className="pb-3">
                        <CardTitle className="font-heading text-base flex items-center gap-2">
                            <BarChart3 className="w-4 h-4" />
                            Secciones del reporte
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {REPORT_SECTIONS.map((section) => {
                                const isSelected = selectedSections.includes(section.id);
                                const Icon = section.icon;
                                return (
                                    <div
                                        key={section.id}
                                        onClick={() => toggleSection(section.id)}
                                        className={`p-3 rounded-sm border-2 cursor-pointer transition-colors ${
                                            isSelected 
                                                ? 'border-slate-900 bg-slate-50' 
                                                : 'border-slate-200 hover:border-slate-300'
                                        }`}
                                        data-testid={`section-toggle-${section.id}`}
                                    >
                                        <div className="flex items-start gap-3">
                                            <Checkbox checked={isSelected} className="mt-0.5" />
                                            <div>
                                                <div className="flex items-center gap-2">
                                                    <Icon className="w-4 h-4 text-slate-600" />
                                                    <p className="font-medium text-sm">{section.label}</p>
                                                </div>
                                                <p className="text-xs text-slate-500 mt-1">{section.description}</p>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                        <div className="flex gap-3 mt-4">
                            <Button 
                                onClick={handleGenerateReport} 
                                disabled={loading}
                                data-testid="generate-report-btn"
                            >
                                {loading ? (
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                ) : (
                                    <Sparkles className="w-4 h-4 mr-2" />
                                )}
                                Generar reporte con IA
                            </Button>
                            <Button 
                                variant="outline" 
                                onClick={handleDownloadExcel} 
                                disabled={excelLoading}
                                data-testid="download-excel-btn"
                            >
                                {excelLoading ? (
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                ) : (
                                    <FileSpreadsheet className="w-4 h-4 mr-2" />
                                )}
                                Descargar Excel
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Report Results */}
            {reportData && (
                <div className="space-y-6" data-testid="report-results">
                    {/* Summary KPIs */}
                    <Card>
                        <CardHeader className="pb-3">
                            <CardTitle className="font-heading text-base">Resumen general</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
                                <div className="p-3 bg-slate-50 rounded-sm text-center">
                                    <p className="text-xs text-slate-500 uppercase">Rutas</p>
                                    <p className="font-mono font-bold text-lg">{reportData.total_journeys}</p>
                                </div>
                                <div className="p-3 bg-slate-50 rounded-sm text-center">
                                    <p className="text-xs text-slate-500 uppercase">Paquetes</p>
                                    <p className="font-mono font-bold text-lg">{reportData.total_packages}</p>
                                </div>
                                <div className="p-3 bg-emerald-50 rounded-sm text-center">
                                    <p className="text-xs text-emerald-600 uppercase">Entregados</p>
                                    <p className="font-mono font-bold text-lg text-emerald-700">{reportData.total_delivered}</p>
                                </div>
                                <div className="p-3 bg-red-50 rounded-sm text-center">
                                    <p className="text-xs text-red-600 uppercase">Fallidos</p>
                                    <p className="font-mono font-bold text-lg text-red-700">{reportData.total_failed}</p>
                                </div>
                                <div className="p-3 bg-amber-50 rounded-sm text-center">
                                    <p className="text-xs text-amber-600 uppercase">Reintentos</p>
                                    <p className="font-mono font-bold text-lg text-amber-700">{reportData.total_retry}</p>
                                </div>
                                <div className="p-3 bg-slate-50 rounded-sm text-center">
                                    <p className="text-xs text-slate-500 uppercase">Tasa %</p>
                                    <p className={`font-mono font-bold text-lg ${
                                        reportData.delivery_rate >= 70 ? 'text-emerald-600' :
                                        reportData.delivery_rate >= 40 ? 'text-amber-600' : 'text-red-600'
                                    }`}>{reportData.delivery_rate}%</p>
                                </div>
                                <div className="p-3 bg-slate-50 rounded-sm text-center">
                                    <p className="text-xs text-slate-500 uppercase">Km</p>
                                    <p className="font-mono font-bold text-lg">{reportData.total_km?.toLocaleString()}</p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Provider Metrics */}
                    {selectedSections.includes('provider_metrics') && reportData.provider_metrics && (
                        <MetricTable data={reportData.provider_metrics} title="Métricas por proveedor" />
                    )}

                    {/* Driver Metrics */}
                    {selectedSections.includes('driver_metrics') && reportData.driver_metrics && (
                        <MetricTable data={reportData.driver_metrics} title="Métricas por driver" />
                    )}

                    {/* Incidents Breakdown */}
                    {selectedSections.includes('incidents_breakdown') && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {reportData.incidents_by_type && Object.keys(reportData.incidents_by_type).length > 0 && (
                                <Card>
                                    <CardHeader className="pb-3">
                                        <CardTitle className="font-heading text-base">Incidencias por tipo</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-2">
                                            {Object.entries(reportData.incidents_by_type).map(([type, count]) => (
                                                <div key={type} className="flex items-center justify-between p-2 bg-slate-50 rounded-sm">
                                                    <span className="text-sm">{type}</span>
                                                    <span className="font-mono font-bold">{count}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </CardContent>
                                </Card>
                            )}
                            {reportData.incidents_by_imputability && (
                                <Card>
                                    <CardHeader className="pb-3">
                                        <CardTitle className="font-heading text-base">Incidencias por imputabilidad</CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-2">
                                            <div className="flex items-center justify-between p-2 bg-red-50 rounded-sm">
                                                <span className="text-sm text-red-700">ME / Mensajero</span>
                                                <span className="font-mono font-bold text-red-700">{reportData.incidents_by_imputability['ME / Mensajero'] || 0}</span>
                                            </div>
                                            <div className="flex items-center justify-between p-2 bg-amber-50 rounded-sm">
                                                <span className="text-sm text-amber-700">Cliente (destinatario)</span>
                                                <span className="font-mono font-bold text-amber-700">{reportData.incidents_by_imputability['Cliente (destinatario)'] || 0}</span>
                                            </div>
                                            <div className="flex items-center justify-between p-2 bg-slate-50 rounded-sm">
                                                <span className="text-sm text-slate-600">Por definir</span>
                                                <span className="font-mono font-bold text-slate-600">{reportData.incidents_by_imputability['Por definir'] || 0}</span>
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            )}
                        </div>
                    )}

                    {/* AI Insights */}
                    {reportData.ai_insights && (
                        <Card className="border-2 border-slate-900">
                            <CardHeader className="pb-3">
                                <CardTitle className="font-heading text-base flex items-center gap-2">
                                    <Sparkles className="w-4 h-4" />
                                    Insights generados por IA
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="prose prose-sm max-w-none text-slate-700 whitespace-pre-wrap" data-testid="ai-insights-text">
                                    {reportData.ai_insights}
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>
            )}

            {/* Quality Report Section */}
            <Card className="mt-6">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle className="font-heading flex items-center gap-2">
                            <ShieldCheck className="w-5 h-5" />
                            Calidad de soporte
                        </CardTitle>
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleLoadQuality}
                                disabled={qualityLoading}
                                data-testid="load-quality-report-btn"
                            >
                                {qualityLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <BarChart3 className="w-4 h-4 mr-2" />}
                                Cargar datos
                            </Button>
                            {qualityData && (
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleExportCubbo}
                                    disabled={cubboExporting}
                                    data-testid="export-cubbo-btn"
                                >
                                    {cubboExporting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Download className="w-4 h-4 mr-2" />}
                                    Exportar para Cubbo
                                </Button>
                            )}
                        </div>
                    </div>
                    <p className="text-xs text-slate-500">
                        Usa las mismas fechas seleccionadas arriba. Basado en el estándar de evidencias de Cubbo (3 fotos por entrega).
                    </p>
                </CardHeader>
                {qualityData && (
                    <CardContent className="space-y-6">
                        {/* Summary */}
                        <div className="grid grid-cols-4 gap-4">
                            <div className="p-3 bg-slate-50 rounded-sm text-center">
                                <p className="text-xs text-slate-500 uppercase">Score promedio</p>
                                <p className={`text-2xl font-mono font-bold ${
                                    qualityData.summary.avg_score >= 90 ? 'text-emerald-600' :
                                    qualityData.summary.avg_score >= 70 ? 'text-amber-600' : 'text-red-600'
                                }`} data-testid="quality-report-avg">{qualityData.summary.avg_score}%</p>
                            </div>
                            <div className="p-3 bg-emerald-50 rounded-sm text-center">
                                <p className="text-xs text-emerald-600 uppercase">Completos</p>
                                <p className="text-2xl font-mono font-bold text-emerald-700">{qualityData.summary.complete}</p>
                            </div>
                            <div className="p-3 bg-amber-50 rounded-sm text-center">
                                <p className="text-xs text-amber-600 uppercase">Parciales</p>
                                <p className="text-2xl font-mono font-bold text-amber-700">{qualityData.summary.partial}</p>
                            </div>
                            <div className="p-3 bg-red-50 rounded-sm text-center">
                                <p className="text-xs text-red-600 uppercase">Incompletos</p>
                                <p className="text-2xl font-mono font-bold text-red-700">{qualityData.summary.incomplete}</p>
                            </div>
                        </div>

                        {/* By Provider */}
                        {qualityData.by_provider.length > 0 && (
                            <div className="border border-slate-200 rounded-sm overflow-hidden">
                                <div className="p-3 bg-slate-50 border-b border-slate-200">
                                    <p className="font-medium text-slate-900 text-sm">Métricas por proveedor</p>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="data-table w-full text-sm">
                                        <thead>
                                            <tr>
                                                <th>Proveedor</th>
                                                <th className="text-center">Rutas</th>
                                                <th className="text-center">Entregados</th>
                                                <th className="text-center">% Completo</th>
                                                <th className="text-center">% Parcial</th>
                                                <th className="text-center">% Sin soporte</th>
                                                <th className="text-center">Score</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {qualityData.by_provider.map((p, i) => (
                                                <tr key={i}>
                                                    <td className="font-medium">{p.provider_name}</td>
                                                    <td className="text-center">{p.routes}</td>
                                                    <td className="text-center">{p.delivered}</td>
                                                    <td className="text-center text-emerald-600">{p.complete_pct}%</td>
                                                    <td className="text-center text-amber-600">{p.partial_pct}%</td>
                                                    <td className="text-center text-red-600">{p.incomplete_pct}%</td>
                                                    <td className="text-center font-mono font-bold">{p.avg_score}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* By Type */}
                        {qualityData.by_type.length > 0 && (
                            <div className="border border-slate-200 rounded-sm overflow-hidden">
                                <div className="p-3 bg-slate-50 border-b border-slate-200">
                                    <p className="font-medium text-slate-900 text-sm">Métricas por tipo de entrega</p>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="data-table w-full text-sm">
                                        <thead>
                                            <tr>
                                                <th>Tipo</th>
                                                <th className="text-center">Cantidad</th>
                                                <th className="text-center">% Score 100</th>
                                                <th className="text-center">Score promedio</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {qualityData.by_type.map((t, i) => (
                                                <tr key={i}>
                                                    <td className="font-medium capitalize">{t.type}</td>
                                                    <td className="text-center">{t.count}</td>
                                                    <td className="text-center text-emerald-600">{t.perfect_pct}%</td>
                                                    <td className="text-center font-mono font-bold">{t.avg_score}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* Worst Packages */}
                        {qualityData.worst_packages.length > 0 && (
                            <div className="border border-slate-200 rounded-sm overflow-hidden">
                                <div className="p-3 bg-red-50 border-b border-red-200">
                                    <p className="font-medium text-red-900 text-sm">TOP 5 paquetes con peor soporte</p>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="data-table w-full text-sm">
                                        <thead>
                                            <tr>
                                                <th>Guía</th>
                                                <th>Proveedor</th>
                                                <th className="text-center">Score</th>
                                                <th>Faltante</th>
                                                <th>Link</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {qualityData.worst_packages.map((p, i) => (
                                                <tr key={i}>
                                                    <td className="font-mono text-xs">{p.tracking_number}</td>
                                                    <td>{p.provider_name}</td>
                                                    <td className="text-center text-red-600 font-mono font-bold">{p.score}</td>
                                                    <td className="text-xs text-slate-500">{p.missing.join(', ')}</td>
                                                    <td>
                                                        {p.tracking_url && (
                                                            <a href={p.tracking_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-700">
                                                                <ExternalLink className="w-3.5 h-3.5" />
                                                            </a>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </CardContent>
                )}
            </Card>
        </div>
    );
};

export default Reports;
