import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Checkbox } from '../components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Button } from '../components/ui/button';
import { Square, Loader2, CheckCircle2, Clock, Search, XCircle } from 'lucide-react';
import ImageUploader from '../components/ImageUploader';
import { formatDateTime, FAILURE_REASONS } from '../lib/utils';

export const JourneyCloseTab = ({
    journey,
    canEdit,
    closeForm,
    setCloseForm,
    closeChecklist,
    setCloseChecklist,
    closeSubmitting,
    closeImages,
    returnEvidenceImages,
    failedPackages,
    setFailedPackages,
    returnCandidates,
    metrics,
    packageSearchTerm,
    setPackageSearchTerm,
    handleUploadImages,
    handleDeleteImage,
    uploadingImages,
    handlePreCloseJourney,
    toggleFailedPackage,
}) => {
    // Memoizar el filtro de candidatos para no recalcular en cada render
    const filteredReturnCandidates = React.useMemo(() => {
        if (!packageSearchTerm) return returnCandidates;
        const search = packageSearchTerm.toLowerCase();
        return returnCandidates.filter(pkg => (
            (pkg.tracking_number || '').toLowerCase().includes(search) ||
            (pkg.order_reference_id || '').toLowerCase().includes(search) ||
            (pkg.recipient_name || '').toLowerCase().includes(search)
        ));
    }, [returnCandidates, packageSearchTerm]);

    // Memoizar contadores de imputabilidad (se usan en 2 secciones)
    const imputabilityCounts = React.useMemo(() => {
        const incs = journey.incidents || [];
        return {
            me: incs.filter(i => i.imputability === 'ME / Mensajero').length,
            client: incs.filter(i => i.imputability === 'Cliente (destinatario)').length,
            pending: incs.filter(i => !i.imputability || i.imputability === 'Por definir').length,
        };
    }, [journey.incidents]);

    if (journey.status === 'in_progress' && canEdit()) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="font-heading">Cerrar ruta</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Hora de cierre</Label>
                            <Input
                                type="datetime-local"
                                value={closeForm.closed_at}
                                onChange={(e) => setCloseForm({ ...closeForm, closed_at: e.target.value })}
                                data-testid="closed-at-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Odometro final (km)</Label>
                            <Input
                                type="number"
                                value={closeForm.odometer_end}
                                onChange={(e) => setCloseForm({ ...closeForm, odometer_end: e.target.value })}
                                placeholder="45380"
                                data-testid="odometer-end-input"
                            />
                        </div>
                    </div>

                    {/* Auto-calculated metrics */}
                    <div className="grid grid-cols-3 gap-4">
                        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-sm text-center">
                            <p className="text-xs text-emerald-600 uppercase font-medium">Entregados</p>
                            <p className="font-mono font-bold text-2xl text-emerald-700" data-testid="auto-delivered-count">
                                {metrics.delivered}
                            </p>
                            <p className="text-xs text-emerald-500 mt-1">calculado automaticamente</p>
                        </div>
                        <div className="p-4 bg-red-50 border border-red-200 rounded-sm text-center">
                            <p className="text-xs text-red-600 uppercase font-medium">Fallidos</p>
                            <p className="font-mono font-bold text-2xl text-red-700" data-testid="auto-failed-count">
                                {metrics.failed}
                            </p>
                            <p className="text-xs text-red-500 mt-1">calculado automaticamente</p>
                        </div>
                        <div className="p-4 bg-slate-100 border border-slate-300 rounded-sm text-center">
                            <p className="text-xs text-slate-600 uppercase font-medium">Devoluciones</p>
                            <p className="font-mono font-bold text-2xl text-slate-700" data-testid="auto-return-count">
                                {metrics.toReturn}
                            </p>
                            <p className="text-xs text-slate-500 mt-1">seleccionados abajo</p>
                        </div>
                    </div>

                    {/* Operational metrics */}
                    <div className="grid grid-cols-2 gap-4 p-4 bg-slate-50 rounded-sm">
                        <div>
                            <p className="text-xs text-slate-500 uppercase">Km recorridos</p>
                            <p className="font-mono font-bold text-lg">{metrics.kmTraveled.toLocaleString()}</p>
                        </div>
                        <div>
                            <p className="text-xs text-slate-500 uppercase">Tasa de entrega</p>
                            <p className={`font-mono font-bold text-lg ${
                                parseFloat(metrics.deliveryRate) >= 70 ? 'text-emerald-600' :
                                parseFloat(metrics.deliveryRate) >= 40 ? 'text-amber-600' : 'text-red-600'
                            }`}>
                                {metrics.deliveryRate}%
                            </p>
                        </div>
                    </div>

                    {/* Imputability summary */}
                    {journey.incidents?.length > 0 && (
                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase mb-2">Resumen de imputabilidad de incidencias</p>
                            <div className="flex gap-4 text-sm">
                                <span className="text-red-700 font-medium">
                                    Imputables a ME: {imputabilityCounts.me}
                                </span>
                                <span className="text-amber-700 font-medium">
                                    Imputables al cliente: {imputabilityCounts.client}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Packages for return */}
                    {returnCandidates.length > 0 && (
                        <div className="border border-slate-200 rounded-sm">
                            <div className="p-3 bg-slate-50 border-b border-slate-200">
                                <div className="flex items-center justify-between mb-2">
                                    <div>
                                        <p className="font-medium text-slate-900">Paquetes para devolucion</p>
                                        <p className="text-sm text-slate-500">Pre-seleccionados de Kosmo. Desmarca los que no aplican.</p>
                                    </div>
                                    <span className="text-sm text-slate-500">
                                        {returnCandidates.length} candidatos
                                    </span>
                                </div>
                                <div className="relative">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                    <Input
                                        type="text"
                                        placeholder="Buscar por No. Guia o destinatario..."
                                        value={packageSearchTerm}
                                        onChange={(e) => setPackageSearchTerm(e.target.value)}
                                        className="pl-10 h-9"
                                        data-testid="package-search-input"
                                    />
                                    {packageSearchTerm && (
                                        <button
                                            type="button"
                                            onClick={() => setPackageSearchTerm('')}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                        >
                                            <XCircle className="w-4 h-4" />
                                        </button>
                                    )}
                                </div>
                            </div>
                            <div className="max-h-64 overflow-y-auto">
                                <table className="data-table w-full text-sm">
                                    <thead>
                                        <tr>
                                            <th className="w-10"></th>
                                            <th>No. Guia</th>
                                            <th>Destinatario</th>
                                            <th>Motivo</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {filteredReturnCandidates.map((pkg) => {
                                                const isFailed = failedPackages.find(f => f.id === pkg.id);
                                                return (
                                                    <tr key={pkg.id} className={isFailed ? 'bg-red-50' : ''}>
                                                        <td>
                                                            <Checkbox
                                                                checked={!!isFailed}
                                                                onCheckedChange={() => toggleFailedPackage(pkg)}
                                                            />
                                                        </td>
                                                        <td className="font-mono">{pkg.tracking_number || pkg.order_reference_id}</td>
                                                        <td>{pkg.recipient_name}</td>
                                                        <td>
                                                            {isFailed && (
                                                                <Select
                                                                    value={isFailed.failure_reason}
                                                                    onValueChange={(v) => toggleFailedPackage(pkg, v)}
                                                                >
                                                                    <SelectTrigger className="h-8">
                                                                        <SelectValue />
                                                                    </SelectTrigger>
                                                                    <SelectContent>
                                                                        {FAILURE_REASONS.map((r) => (
                                                                            <SelectItem key={r} value={r}>{r}</SelectItem>
                                                                        ))}
                                                                    </SelectContent>
                                                                </Select>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                    </tbody>
                                </table>
                                {packageSearchTerm && filteredReturnCandidates.length === 0 && (
                                    <div className="text-center py-6 text-slate-500">
                                        <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                        <p className="text-sm">No se encontraron paquetes con "{packageSearchTerm}"</p>
                                    </div>
                                )}
                            </div>
                            {failedPackages.length > 0 && (
                                <div className="p-3 bg-slate-100 border-t border-slate-300 flex items-center justify-between">
                                    <span className="text-sm text-slate-700">
                                        <strong>{failedPackages.length}</strong> paquete(s) Fallido(s) marcado(s) para devolucion
                                    </span>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => setFailedPackages([])}
                                        className="text-slate-600 hover:text-slate-700"
                                    >
                                        Limpiar seleccion
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}

                    <div className="space-y-2">
                        <Label>Notas de cierre</Label>
                        <Textarea
                            value={closeForm.notes}
                            onChange={(e) => setCloseForm({ ...closeForm, notes: e.target.value })}
                            placeholder="Observaciones finales..."
                            rows={3}
                            data-testid="close-notes-textarea"
                        />
                    </div>

                    {/* Image upload for close */}
                    <div className="space-y-1">
                        <Label>Evidencia fotografica de cierre <span className="text-slate-400 font-normal">(opcional)</span></Label>
                        <ImageUploader
                            images={closeImages}
                            onUpload={(files) => handleUploadImages(files, 'close')}
                            onDelete={handleDeleteImage}
                            uploading={uploadingImages}
                            label="Agregar fotos de cierre"
                        />
                        <p className="text-xs text-slate-400">Solo si genera valor adicional.</p>
                    </div>

                    {/* Checklist */}
                    <div className="border border-slate-200 rounded-sm p-4 space-y-3">
                        <p className="font-medium text-slate-900 mb-3">Checklist de cierre</p>
                        {[
                            { key: 'cosmo_screenshot', label: 'Pantallazo de cierre de Cosmo adjuntado' },
                            { key: 'odometer_final', label: 'Kilometraje final registrado' },
                            { key: 'failed_list', label: 'Lista de paquetes no entregados completa' },
                            { key: 'incidents_reviewed', label: 'Incidencias del dia revisadas y cerradas' },
                        ].map((item) => (
                            <div key={item.key} className="flex items-center space-x-3">
                                <Checkbox
                                    id={`close-${item.key}`}
                                    checked={closeChecklist[item.key]}
                                    onCheckedChange={(checked) =>
                                        setCloseChecklist({ ...closeChecklist, [item.key]: checked })
                                    }
                                    data-testid={`close-checklist-${item.key}`}
                                />
                                <label htmlFor={`close-${item.key}`} className="text-sm text-slate-700 cursor-pointer">
                                    {item.label}
                                </label>
                            </div>
                        ))}

                        {failedPackages.length > 0 && (
                            <div className="mt-4 pt-4 border-t border-slate-200 space-y-3">
                                <div className="flex items-center space-x-3">
                                    <Checkbox
                                        id="close-return_evidence"
                                        checked={closeChecklist.return_evidence}
                                        onCheckedChange={(checked) =>
                                            setCloseChecklist({ ...closeChecklist, return_evidence: checked })
                                        }
                                        data-testid="close-checklist-return_evidence"
                                    />
                                    <label htmlFor="close-return_evidence" className="text-sm text-slate-700 cursor-pointer font-medium">
                                        Evidencia fotografica de devolucion de paquetes
                                    </label>
                                </div>
                                <div className="ml-7">
                                    <ImageUploader
                                        images={returnEvidenceImages}
                                        onUpload={(files) => handleUploadImages(files, 'return_evidence')}
                                        onDelete={handleDeleteImage}
                                        uploading={uploadingImages}
                                        label="Agregar fotos de devolucion"
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="flex justify-end">
                        <Button
                            onClick={handlePreCloseJourney}
                            disabled={closeSubmitting}
                            variant="destructive"
                            data-testid="close-journey-btn"
                        >
                            {closeSubmitting ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <Square className="w-4 h-4 mr-2" />
                            )}
                            Cerrar ruta
                        </Button>
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (journey.close_data) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="font-heading flex items-center gap-2">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        Ruta cerrada
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Hora de cierre</p>
                            <p className="font-mono font-medium">{formatDateTime(journey.close_data.closed_at)}</p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Odometro final</p>
                            <p className="font-mono font-medium">{journey.close_data.odometer_end?.toLocaleString()} km</p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Km recorridos</p>
                            <p className="font-mono font-medium">{journey.close_data.km_traveled?.toLocaleString()}</p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Tasa de entrega</p>
                            <p className={`font-mono font-bold ${
                                journey.close_data.delivery_rate >= 70 ? 'text-emerald-600' :
                                journey.close_data.delivery_rate >= 40 ? 'text-amber-600' : 'text-red-600'
                            }`}>
                                {journey.close_data.delivery_rate}%
                            </p>
                        </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-sm text-center">
                            <p className="text-xs text-emerald-600 uppercase">Entregados</p>
                            <p className="font-mono font-bold text-2xl text-emerald-700">{journey.close_data.packages_delivered}</p>
                        </div>
                        <div className="p-3 bg-red-50 border border-red-200 rounded-sm text-center">
                            <p className="text-xs text-red-600 uppercase">Fallidos</p>
                            <p className="font-mono font-bold text-2xl text-red-700">{journey.close_data.packages_failed}</p>
                        </div>
                        <div className="p-3 bg-amber-50 border border-amber-200 rounded-sm text-center">
                            <p className="text-xs text-amber-600 uppercase">Devoluciones</p>
                            <p className="font-mono font-bold text-2xl text-amber-700">{journey.close_data.packages_to_retry}</p>
                        </div>
                    </div>
                    {closeImages.length > 0 && (
                        <div className="mt-4">
                            <p className="text-xs text-slate-500 uppercase mb-2">Evidencia fotografica de cierre</p>
                            <ImageUploader images={closeImages} disabled={true} />
                        </div>
                    )}
                    {journey.incidents?.length > 0 && (
                        <div className="mt-4 p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase mb-2">Resumen de imputabilidad</p>
                            <div className="flex gap-4 text-sm">
                                <span className="text-red-700 font-medium">
                                    Imputables a ME: {imputabilityCounts.me}
                                </span>
                                <span className="text-amber-700 font-medium">
                                    Imputables al cliente: {imputabilityCounts.client}
                                </span>
                                <span className="text-slate-600">
                                    Por definir: {imputabilityCounts.pending}
                                </span>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardContent className="py-12 text-center">
                <Clock className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-500">
                    {journey.status === 'scheduled'
                        ? 'Primero debes iniciar la ruta'
                        : 'La ruta aun no ha sido cerrada'}
                </p>
            </CardContent>
        </Card>
    );
};
