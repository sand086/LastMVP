import React from 'react';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Calendar } from '../ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Link as LinkIcon, Calendar as CalendarIcon, AlertCircle, Loader2, Package } from 'lucide-react';

export const LayoutStep3Config = ({
    selectedDate,
    setSelectedDate,
    selectedClient,
    setSelectedClient,
    clients,
    providers,
    routeData,
    driverProviderMap,
    onDriverProviderChange,
    allDriversAssigned,
    creating,
    onOpenConfirm,
}) => (
    <Card className="ring-2 ring-slate-900">
        <CardHeader>
            <CardTitle className="font-heading text-lg flex items-center gap-2">
                <LinkIcon className="w-5 h-5" />
                Paso 3: Configuración y Asignación de Proveedores
            </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                    <Label>Fecha de las rutas (respaldo)</Label>
                    <Popover>
                        <PopoverTrigger asChild>
                            <Button
                                variant="outline"
                                className="w-full justify-start text-left font-normal"
                                data-testid="journey-date-picker"
                            >
                                <CalendarIcon className="mr-2 h-4 w-4" />
                                {format(selectedDate, 'dd MMM yyyy', { locale: es })}
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                            <Calendar
                                mode="single"
                                selected={selectedDate}
                                onSelect={(date) => date && setSelectedDate(date)}
                                initialFocus
                            />
                        </PopoverContent>
                    </Popover>
                    <p className="text-xs text-slate-400">Se usa "Creation Date" del route-summary por ruta. Esta fecha es respaldo si no existe.</p>
                </div>
                <div className="space-y-2">
                    <Label>Cliente</Label>
                    <Select value={selectedClient} onValueChange={setSelectedClient}>
                        <SelectTrigger data-testid="select-client">
                            <SelectValue placeholder="Seleccionar cliente" />
                        </SelectTrigger>
                        <SelectContent>
                            {clients.map((client) => (
                                <SelectItem key={client.id} value={client.id}>
                                    {client.name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </div>

            <div className="border border-slate-200 rounded-sm">
                <div className="p-3 bg-slate-50 border-b border-slate-200">
                    <p className="font-medium text-slate-900">Asignar Proveedor a cada Mensajero</p>
                    <p className="text-sm text-slate-500">
                        Los mensajeros detectados necesitan un proveedor asignado
                    </p>
                </div>
                <div className="max-h-80 overflow-y-auto">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Mensajero (Driver)</TableHead>
                                <TableHead>Proveedor Asignado</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {routeData?.drivers.map((driver) => (
                                <TableRow key={driver}>
                                    <TableCell className="font-medium">{driver}</TableCell>
                                    <TableCell>
                                        <Select
                                            value={driverProviderMap[driver] || ''}
                                            onValueChange={(v) => onDriverProviderChange(driver, v)}
                                        >
                                            <SelectTrigger
                                                className={`w-full ${!driverProviderMap[driver] ? 'border-amber-400' : ''}`}
                                                data-testid={`provider-select-${driver}`}
                                            >
                                                <SelectValue placeholder="Sin asignar" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {providers.map((provider) => (
                                                    <SelectItem key={provider.id} value={provider.id}>
                                                        {provider.name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            </div>

            {!allDriversAssigned && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-sm flex items-center gap-2 text-amber-700">
                    <AlertCircle className="w-5 h-5" />
                    <span>Asigna un proveedor a todos los mensajeros para continuar</span>
                </div>
            )}

            <div className="flex justify-end">
                <Button
                    onClick={onOpenConfirm}
                    disabled={!selectedClient || !allDriversAssigned || creating}
                    data-testid="create-journeys-btn"
                >
                    {creating ? (
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                        <Package className="w-4 h-4 mr-2" />
                    )}
                    Crear Rutas
                </Button>
            </div>
        </CardContent>
    </Card>
);
