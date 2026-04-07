import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Checkbox } from '../components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Button } from '../components/ui/button';
import { Play, Loader2, CheckCircle2, Clock } from 'lucide-react';
import ImageUploader from '../components/ImageUploader';
import { formatDateTime, FUEL_LEVELS, VEHICLE_CONDITIONS } from '../lib/utils';

export const JourneyStartTab = ({
    journey,
    canEdit,
    startForm,
    setStartForm,
    startChecklist,
    setStartChecklist,
    startSubmitting,
    startImages,
    handleUploadImages,
    handleDeleteImage,
    uploadingImages,
    handleStartJourney,
}) => {
    if (journey.status === 'scheduled' && canEdit()) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="font-heading">Iniciar ruta</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <Label>Hora de salida</Label>
                            <Input
                                type="datetime-local"
                                value={startForm.departure_time}
                                onChange={(e) => setStartForm({ ...startForm, departure_time: e.target.value })}
                                data-testid="departure-time-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Odometro inicial (km)</Label>
                            <Input
                                type="number"
                                value={startForm.odometer_start}
                                onChange={(e) => setStartForm({ ...startForm, odometer_start: e.target.value })}
                                placeholder="45230"
                                data-testid="odometer-start-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Nivel de combustible</Label>
                            <Select
                                value={startForm.fuel_level}
                                onValueChange={(v) => setStartForm({ ...startForm, fuel_level: v })}
                            >
                                <SelectTrigger data-testid="fuel-level-select">
                                    <SelectValue placeholder="Seleccionar" />
                                </SelectTrigger>
                                <SelectContent>
                                    {FUEL_LEVELS.map((level) => (
                                        <SelectItem key={level} value={level}>{level}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Condicion del vehiculo</Label>
                            <Select
                                value={startForm.vehicle_condition}
                                onValueChange={(v) => setStartForm({ ...startForm, vehicle_condition: v })}
                            >
                                <SelectTrigger data-testid="vehicle-condition-select">
                                    <SelectValue placeholder="Seleccionar" />
                                </SelectTrigger>
                                <SelectContent>
                                    {VEHICLE_CONDITIONS.map((cond) => (
                                        <SelectItem key={cond} value={cond}>{cond}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        {startForm.vehicle_condition === 'Con observación' && (
                            <div className="space-y-2 md:col-span-2">
                                <Label>Observaciones del vehiculo</Label>
                                <Input
                                    value={startForm.vehicle_notes}
                                    onChange={(e) => setStartForm({ ...startForm, vehicle_notes: e.target.value })}
                                    placeholder="Describe las observaciones"
                                    data-testid="vehicle-notes-input"
                                />
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label>Paquetes cargados</Label>
                            <Input
                                type="number"
                                value={startForm.packages_loaded}
                                onChange={(e) => setStartForm({ ...startForm, packages_loaded: parseInt(e.target.value) })}
                                data-testid="packages-loaded-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Hora de llegada a CEDIS</Label>
                            <Input
                                type="time"
                                value={startForm.arrival_time_cedis}
                                onChange={(e) => setStartForm({ ...startForm, arrival_time_cedis: e.target.value })}
                                data-testid="arrival-time-cedis-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Traslado a 1er punto (min)</Label>
                            <Input
                                type="number"
                                min={1}
                                max={240}
                                value={startForm.traslado_primer_punto}
                                onChange={(e) => setStartForm({ ...startForm, traslado_primer_punto: parseInt(e.target.value) || 40 })}
                                placeholder="40"
                                data-testid="traslado-primer-punto-input"
                            />
                            <p className="text-xs text-slate-400">Tiempo estimado de traslado al primer punto de entrega. Se usa en Pulse.</p>
                        </div>
                    </div>

                    {/* Backup driver fields */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <Label>Mensajero de respaldo (opcional)</Label>
                            <Input
                                value={startForm.backup_driver_name}
                                onChange={(e) => setStartForm({ ...startForm, backup_driver_name: e.target.value })}
                                placeholder="Nombre del mensajero de respaldo"
                                data-testid="backup-driver-name-input"
                            />
                        </div>
                        {startForm.backup_driver_name && (
                            <>
                                <div className="space-y-2">
                                    <Label>Hora de solicitud del backup</Label>
                                    <Input
                                        type="time"
                                        value={startForm.backup_request_time}
                                        onChange={(e) => setStartForm({ ...startForm, backup_request_time: e.target.value })}
                                        data-testid="backup-request-time-input"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Hora de incorporacion del backup</Label>
                                    <Input
                                        type="time"
                                        value={startForm.backup_arrival_time}
                                        onChange={(e) => setStartForm({ ...startForm, backup_arrival_time: e.target.value })}
                                        data-testid="backup-arrival-time-input"
                                    />
                                </div>
                            </>
                        )}
                    </div>

                    {/* Route Type Selection */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <Label>Tipo de ruta</Label>
                            <Select value={startForm.route_type} onValueChange={(v) => setStartForm({ ...startForm, route_type: v })}>
                                <SelectTrigger data-testid="select-route-type">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="CDMX / Zona Metro">CDMX / Zona Metro</SelectItem>
                                    <SelectItem value="Foranea">Foranea</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {startForm.route_type === 'Foranea' && (
                            <>
                                <div className="space-y-2">
                                    <Label>Ciudad</Label>
                                    <Input
                                        value={startForm.city}
                                        onChange={(e) => setStartForm({ ...startForm, city: e.target.value })}
                                        placeholder="Ej: Pachuca, Guadalajara"
                                        data-testid="route-city-input"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Max. paquetes</Label>
                                    <Input
                                        type="number"
                                        value={startForm.max_packages}
                                        onChange={(e) => setStartForm({ ...startForm, max_packages: parseInt(e.target.value) || 50 })}
                                        data-testid="route-max-packages-input"
                                    />
                                </div>
                            </>
                        )}
                    </div>

                    <div className="space-y-2">
                        <Label>Notas adicionales</Label>
                        <Textarea
                            value={startForm.notes}
                            onChange={(e) => setStartForm({ ...startForm, notes: e.target.value })}
                            placeholder="Observaciones generales..."
                            rows={3}
                            data-testid="start-notes-textarea"
                        />
                    </div>

                    {/* Image upload for start */}
                    <div className="space-y-1">
                        <Label>Evidencia fotografica <span className="text-slate-400 font-normal">(opcional)</span></Label>
                        <ImageUploader
                            images={startImages}
                            onUpload={(files) => handleUploadImages(files, 'start')}
                            onDelete={handleDeleteImage}
                            uploading={uploadingImages}
                            label="Agregar fotos de inicio"
                        />
                        <p className="text-xs text-slate-400">Solo si genera valor adicional.</p>
                    </div>

                    {/* Checklist */}
                    <div className="border border-slate-200 rounded-sm p-4 space-y-3">
                        <p className="font-medium text-slate-900 mb-3">Checklist de salida</p>
                        {[
                            { key: 'cedis_arrival', label: 'Llegada a CEDIS registrada con hora' },
                            { key: 'cedis_pass', label: 'Confirmacion de pase a CEDIS' },
                            { key: 'cosmo_route', label: 'Confirmacion de ruta en Cosmo / plataforma' },
                            { key: 'packages_scanned', label: 'Paquetes escaneados y asignados en la plataforma del cliente' },
                            { key: 'retry_registered', label: 'Paquetes de reintento del dia anterior registrados' },
                            { key: 'whatsapp', label: 'Driver / mensajero notifico salida del almacen' },
                            { key: 'odometer_photo', label: 'Evidencia fotografica del odometro tomada', optional: true },
                            { key: 'cedis_screenshot', label: 'Pantallazo CEDIS - 1a entrega tomado', optional: true },
                            { key: 'zone_confirmed', label: 'Zona de entrega confirmada' },
                        ].map((item) => (
                            <div key={item.key} className="flex items-center space-x-3">
                                <Checkbox
                                    id={item.key}
                                    checked={startChecklist[item.key]}
                                    onCheckedChange={(checked) =>
                                        setStartChecklist({ ...startChecklist, [item.key]: checked })
                                    }
                                    data-testid={`checklist-${item.key}`}
                                />
                                <label htmlFor={item.key} className="text-sm text-slate-700 cursor-pointer">
                                    {item.label}
                                    {item.optional && <span className="text-slate-400 ml-1">(opcional)</span>}
                                </label>
                            </div>
                        ))}
                    </div>

                    <div className="flex justify-end">
                        <Button
                            onClick={handleStartJourney}
                            disabled={startSubmitting}
                            className="bg-status-success hover:bg-status-success/90"
                            data-testid="start-journey-btn"
                        >
                            {startSubmitting ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <Play className="w-4 h-4 mr-2" />
                            )}
                            Iniciar ruta
                        </Button>
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (journey.start_data) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="font-heading flex items-center gap-2">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        Ruta iniciada
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Hora de salida</p>
                            <p className="font-mono font-medium">{formatDateTime(journey.start_data.departure_time)}</p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Odometro inicial</p>
                            <p className="font-mono font-medium">{journey.start_data.odometer_start?.toLocaleString()} km</p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Combustible</p>
                            <p className="font-medium">{journey.start_data.fuel_level}</p>
                        </div>
                        <div className="p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase">Paquetes cargados</p>
                            <p className="font-mono font-medium">{journey.start_data.packages_loaded}</p>
                        </div>
                        {journey.start_data.traslado_primer_punto && (
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">Traslado a 1er punto</p>
                                <p className="font-mono font-medium">{journey.start_data.traslado_primer_punto} min</p>
                            </div>
                        )}
                    </div>
                    {journey.start_data.notes && (
                        <div className="mt-4 p-3 bg-slate-50 rounded-sm">
                            <p className="text-xs text-slate-500 uppercase mb-1">Notas</p>
                            <p className="text-sm">{journey.start_data.notes}</p>
                        </div>
                    )}
                    {startImages.length > 0 && (
                        <div className="mt-4">
                            <p className="text-xs text-slate-500 uppercase mb-2">Evidencia fotografica</p>
                            <ImageUploader
                                images={startImages}
                                onDelete={canEdit() ? handleDeleteImage : null}
                                disabled={!canEdit()}
                            />
                        </div>
                    )}
                    {journey.status === 'in_progress' && canEdit() && (
                        <div className="mt-4">
                            <ImageUploader
                                images={[]}
                                onUpload={(files) => handleUploadImages(files, 'start')}
                                uploading={uploadingImages}
                                label="Agregar mas fotos"
                            />
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
                <p className="text-slate-500">Ruta pendiente de inicio</p>
            </CardContent>
        </Card>
    );
};
