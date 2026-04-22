import React from 'react';
import { TabsContent } from '../../components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Calendar } from '../../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../../components/ui/popover';
import { Zap, Calendar as CalendarIcon, Loader2, Play, Download, Copy, Check } from 'lucide-react';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

export const SandboxTab = ({
    selectedEndpoint, setSelectedEndpoint,
    dateFrom, setDateFrom, dateTo, setDateTo,
    groupBy, setGroupBy,
    sandboxResult, sandboxLoading,
    onRunSandbox, onDownloadJson,
    generateCurlCommand,
    copied, onCopy,
}) => (
    <TabsContent value="sandbox" className="space-y-6">
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <Zap className="w-5 h-5" />
                    Probar API en Vivo
                </CardTitle>
                <CardDescription>
                    Ejecuta consultas directamente y visualiza los resultados
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
                {/* Endpoint selector */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="space-y-2">
                        <Label>Endpoint</Label>
                        <Select value={selectedEndpoint} onValueChange={setSelectedEndpoint}>
                            <SelectTrigger data-testid="endpoint-select">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="journeys">Rutas</SelectItem>
                                <SelectItem value="packages">Paquetes</SelectItem>
                                <SelectItem value="incidents">Incidencias</SelectItem>
                                <SelectItem value="kpis">KPIs</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label>Fecha Desde</Label>
                        <Popover>
                            <PopoverTrigger asChild>
                                <Button variant="outline" className="w-full justify-start">
                                    <CalendarIcon className="mr-2 h-4 w-4" />
                                    {dateFrom ? format(dateFrom, 'dd MMM', { locale: es }) : 'Seleccionar'}
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-auto p-0">
                                <Calendar mode="single" selected={dateFrom} onSelect={setDateFrom} />
                            </PopoverContent>
                        </Popover>
                    </div>
                    <div className="space-y-2">
                        <Label>Fecha Hasta</Label>
                        <Popover>
                            <PopoverTrigger asChild>
                                <Button variant="outline" className="w-full justify-start">
                                    <CalendarIcon className="mr-2 h-4 w-4" />
                                    {dateTo ? format(dateTo, 'dd MMM', { locale: es }) : 'Seleccionar'}
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-auto p-0">
                                <Calendar mode="single" selected={dateTo} onSelect={setDateTo} />
                            </PopoverContent>
                        </Popover>
                    </div>
                    {selectedEndpoint === 'kpis' && (
                        <div className="space-y-2">
                            <Label>Agrupar por</Label>
                            <Select value={groupBy} onValueChange={setGroupBy}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="day">Día</SelectItem>
                                    <SelectItem value="week">Semana</SelectItem>
                                    <SelectItem value="month">Mes</SelectItem>
                                    <SelectItem value="provider">Proveedor</SelectItem>
                                    <SelectItem value="client">Cliente</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    )}
                </div>

                {/* Run button */}
                <div className="flex items-center gap-3">
                    <Button onClick={onRunSandbox} disabled={sandboxLoading} data-testid="run-sandbox-btn">
                        {sandboxLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                        Ejecutar Consulta
                    </Button>
                    {sandboxResult && !sandboxResult.error && (
                        <Button variant="outline" onClick={onDownloadJson}>
                            <Download className="w-4 h-4 mr-2" />
                            Descargar JSON
                        </Button>
                    )}
                </div>

                {/* cURL command */}
                <div className="space-y-2">
                    <Label className="text-xs text-slate-500">Comando cURL equivalente:</Label>
                    <div className="relative">
                        <pre className="bg-slate-900 text-slate-100 p-4 rounded-sm text-xs overflow-x-auto">
                            {generateCurlCommand(selectedEndpoint)}
                        </pre>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="absolute top-2 right-2"
                            onClick={() => onCopy(generateCurlCommand(selectedEndpoint), 'curl')}
                        >
                            {copied === 'curl' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                        </Button>
                    </div>
                </div>

                {/* Results */}
                {sandboxResult && (
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <Label>Resultado:</Label>
                            {sandboxResult.total !== undefined && (
                                <span className="text-sm text-slate-500">{sandboxResult.total} registros</span>
                            )}
                        </div>
                        <pre className="bg-slate-50 border border-slate-200 p-4 rounded-sm text-xs overflow-auto max-h-96">
                            {JSON.stringify(sandboxResult, null, 2)}
                        </pre>
                    </div>
                )}
            </CardContent>
        </Card>
    </TabsContent>
);

export default SandboxTab;
