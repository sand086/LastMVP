import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getReportSchema, getReportJourneys, getReportPackages, getReportIncidents, getReportKpis } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { 
    Code, 
    Database, 
    Play, 
    Copy, 
    Check,
    Calendar as CalendarIcon,
    FileJson,
    Download,
    ExternalLink,
    Loader2,
    BookOpen,
    Zap
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ApiDocumentation = () => {
    const { user } = useAuth();
    const [schema, setSchema] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('docs');
    const [copied, setCopied] = useState(null);

    // Sandbox state
    const [selectedEndpoint, setSelectedEndpoint] = useState('journeys');
    const [dateFrom, setDateFrom] = useState(null);
    const [dateTo, setDateTo] = useState(null);
    const [groupBy, setGroupBy] = useState('day');
    const [sandboxResult, setSandboxResult] = useState(null);
    const [sandboxLoading, setSandboxLoading] = useState(false);

    useEffect(() => {
        const fetchSchema = async () => {
            try {
                const res = await getReportSchema();
                setSchema(res.data);
            } catch (error) {
                toast.error('Error al cargar documentación');
            } finally {
                setLoading(false);
            }
        };
        fetchSchema();
    }, []);

    const handleCopy = (text, id) => {
        navigator.clipboard.writeText(text);
        setCopied(id);
        toast.success('Copiado al portapapeles');
        setTimeout(() => setCopied(null), 2000);
    };

    const handleRunSandbox = async () => {
        setSandboxLoading(true);
        setSandboxResult(null);

        try {
            const params = {};
            if (dateFrom) params.date_from = format(dateFrom, 'yyyy-MM-dd');
            if (dateTo) params.date_to = format(dateTo, 'yyyy-MM-dd');
            if (selectedEndpoint === 'kpis') params.group_by = groupBy;

            let res;
            switch (selectedEndpoint) {
                case 'journeys':
                    res = await getReportJourneys(params);
                    break;
                case 'packages':
                    res = await getReportPackages(params);
                    break;
                case 'incidents':
                    res = await getReportIncidents(params);
                    break;
                case 'kpis':
                    res = await getReportKpis(params);
                    break;
                default:
                    res = await getReportJourneys(params);
            }

            setSandboxResult(res.data);
            toast.success(`${res.data.total} registros obtenidos`);
        } catch (error) {
            toast.error('Error al ejecutar consulta');
            setSandboxResult({ error: error.message });
        } finally {
            setSandboxLoading(false);
        }
    };

    const downloadJson = () => {
        if (!sandboxResult) return;
        const blob = new Blob([JSON.stringify(sandboxResult, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `lastmile_${selectedEndpoint}_${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const getToken = () => localStorage.getItem('token') || '';

    const generateCurlCommand = (endpoint) => {
        const params = [];
        if (dateFrom) params.push(`date_from=${format(dateFrom, 'yyyy-MM-dd')}`);
        if (dateTo) params.push(`date_to=${format(dateTo, 'yyyy-MM-dd')}`);
        if (endpoint === 'kpis') params.push(`group_by=${groupBy}`);
        
        const queryString = params.length > 0 ? `?${params.join('&')}` : '';
        
        return `curl -X GET "${API_URL}/api/reports/${endpoint}${queryString}" \\
  -H "Authorization: Bearer ${getToken().substring(0, 20)}..." \\
  -H "Content-Type: application/json"`;
    };

    const generatePowerBiCode = () => {
        return `// Power BI - Power Query M Code
let
    // Configuración
    ApiUrl = "${API_URL}/api/reports/${selectedEndpoint}",
    Token = "YOUR_TOKEN_HERE",  // Reemplazar con tu token
    
    // Parámetros opcionales
    DateFrom = "${dateFrom ? format(dateFrom, 'yyyy-MM-dd') : ''}",
    DateTo = "${dateTo ? format(dateTo, 'yyyy-MM-dd') : ''}",
    ${selectedEndpoint === 'kpis' ? `GroupBy = "${groupBy}",` : ''}
    
    // Construir URL con parámetros
    QueryParams = [date_from = DateFrom, date_to = DateTo${selectedEndpoint === 'kpis' ? ', group_by = GroupBy' : ''}],
    
    // Llamada a la API
    Source = Json.Document(
        Web.Contents(
            ApiUrl,
            [
                Headers = [
                    #"Authorization" = "Bearer " & Token,
                    #"Content-Type" = "application/json"
                ],
                Query = QueryParams
            ]
        )
    ),
    
    // Extraer datos
    Data = Source[data],
    #"Converted to Table" = Table.FromList(Data, Splitter.SplitByNothing(), null, null, ExtraValues.Error),
    #"Expanded Column1" = Table.ExpandRecordColumn(#"Converted to Table", "Column1", Record.FieldNames(Data{0}))
in
    #"Expanded Column1"`;
    };

    const generatePythonCode = () => {
        return `import requests
import pandas as pd

# Configuración
API_URL = "${API_URL}/api"
TOKEN = "YOUR_TOKEN_HERE"  # Reemplazar con tu token

# Headers
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Parámetros
params = {
    "date_from": "${dateFrom ? format(dateFrom, 'yyyy-MM-dd') : ''}",
    "date_to": "${dateTo ? format(dateTo, 'yyyy-MM-dd') : ''}"${selectedEndpoint === 'kpis' ? `,
    "group_by": "${groupBy}"` : ''}
}

# Obtener datos
response = requests.get(
    f"{API_URL}/reports/${selectedEndpoint}",
    headers=headers,
    params={k: v for k, v in params.items() if v}  # Solo params no vacíos
)

# Convertir a DataFrame
data = response.json()
df = pd.DataFrame(data["data"])
print(f"Total registros: {data['total']}")
print(df.head())`;
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                    API & Integraciones
                </h1>
                <p className="text-slate-500 text-sm">
                    Documentación y sandbox para integración con Power BI, Tableau, Python y más
                </p>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="docs" data-testid="tab-docs">
                        <BookOpen className="w-4 h-4 mr-2" />
                        Documentación
                    </TabsTrigger>
                    <TabsTrigger value="sandbox" data-testid="tab-sandbox">
                        <Zap className="w-4 h-4 mr-2" />
                        Sandbox
                    </TabsTrigger>
                    <TabsTrigger value="examples" data-testid="tab-examples">
                        <Code className="w-4 h-4 mr-2" />
                        Ejemplos de Código
                    </TabsTrigger>
                </TabsList>

                {/* Documentation Tab */}
                <TabsContent value="docs" className="space-y-6">
                    {/* Auth Info */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <Database className="w-5 h-5" />
                                Autenticación
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <p className="text-sm text-slate-600">
                                Todas las peticiones requieren un token JWT en el header Authorization.
                            </p>
                            <div className="bg-slate-900 rounded-sm p-4 overflow-x-auto">
                                <code className="text-sm text-emerald-400">
                                    Authorization: Bearer {getToken().substring(0, 40)}...
                                </code>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleCopy(getToken(), 'token')}
                                >
                                    {copied === 'token' ? <Check className="w-4 h-4 mr-1" /> : <Copy className="w-4 h-4 mr-1" />}
                                    Copiar Token
                                </Button>
                                <span className="text-xs text-slate-500">
                                    El token expira en 8 horas
                                </span>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Endpoints */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg">
                                Endpoints Disponibles
                            </CardTitle>
                            <CardDescription>
                                URL Base: <code className="bg-slate-100 px-2 py-1 rounded">{API_URL}/api</code>
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {schema?.endpoints?.map((endpoint, idx) => (
                                <div key={idx} className="border border-slate-200 rounded-sm overflow-hidden">
                                    <div className="bg-slate-50 p-4 border-b border-slate-200">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <h4 className="font-medium text-slate-900">{endpoint.name}</h4>
                                                <p className="text-sm text-slate-500">{endpoint.description}</p>
                                            </div>
                                            <span className="px-3 py-1 bg-emerald-100 text-emerald-700 text-xs font-mono rounded">
                                                {endpoint.method}
                                            </span>
                                        </div>
                                        <code className="text-sm text-blue-600 mt-2 block">
                                            {endpoint.endpoint}
                                        </code>
                                    </div>
                                    <div className="p-4 space-y-4">
                                        {/* Parameters */}
                                        <div>
                                            <h5 className="text-sm font-medium text-slate-700 mb-2">Parámetros</h5>
                                            <div className="overflow-x-auto">
                                                <table className="w-full text-sm">
                                                    <thead>
                                                        <tr className="border-b border-slate-100">
                                                            <th className="text-left py-2 pr-4 font-medium text-slate-600">Nombre</th>
                                                            <th className="text-left py-2 pr-4 font-medium text-slate-600">Tipo</th>
                                                            <th className="text-left py-2 font-medium text-slate-600">Descripción</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {endpoint.parameters?.map((param, pidx) => (
                                                            <tr key={pidx} className="border-b border-slate-50">
                                                                <td className="py-2 pr-4">
                                                                    <code className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">
                                                                        {param.name}
                                                                    </code>
                                                                </td>
                                                                <td className="py-2 pr-4 text-slate-600 text-xs">
                                                                    {param.type}
                                                                    {param.format && <span className="text-slate-400"> ({param.format})</span>}
                                                                </td>
                                                                <td className="py-2 text-slate-600 text-xs">
                                                                    {param.enum && `Valores: ${param.enum.join(', ')}`}
                                                                    {param.default && ` (default: ${param.default})`}
                                                                    {!param.required && <span className="text-slate-400"> (opcional)</span>}
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                        {/* Fields */}
                                        <div>
                                            <h5 className="text-sm font-medium text-slate-700 mb-2">Campos de Respuesta</h5>
                                            <div className="flex flex-wrap gap-1">
                                                {endpoint.fields?.map((field, fidx) => (
                                                    <span key={fidx} className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">
                                                        {field}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Sandbox Tab */}
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
                                            <SelectItem value="journeys">Jornadas</SelectItem>
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
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
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
                                <Button onClick={handleRunSandbox} disabled={sandboxLoading} data-testid="run-sandbox-btn">
                                    {sandboxLoading ? (
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    ) : (
                                        <Play className="w-4 h-4 mr-2" />
                                    )}
                                    Ejecutar Consulta
                                </Button>
                                {sandboxResult && !sandboxResult.error && (
                                    <Button variant="outline" onClick={downloadJson}>
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
                                        onClick={() => handleCopy(generateCurlCommand(selectedEndpoint), 'curl')}
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
                                            <span className="text-sm text-slate-500">
                                                {sandboxResult.total} registros
                                            </span>
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

                {/* Code Examples Tab */}
                <TabsContent value="examples" className="space-y-6">
                    {/* Power BI */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <FileJson className="w-5 h-5" />
                                Power BI - Power Query M
                            </CardTitle>
                            <CardDescription>
                                Copia este código en el editor avanzado de Power Query
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="relative">
                                <pre className="bg-slate-900 text-slate-100 p-4 rounded-sm text-xs overflow-x-auto max-h-96">
                                    {generatePowerBiCode()}
                                </pre>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="absolute top-2 right-2"
                                    onClick={() => handleCopy(generatePowerBiCode(), 'powerbi')}
                                >
                                    {copied === 'powerbi' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Python */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg flex items-center gap-2">
                                <Code className="w-5 h-5" />
                                Python + Pandas
                            </CardTitle>
                            <CardDescription>
                                Ejemplo para análisis de datos con Python
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="relative">
                                <pre className="bg-slate-900 text-slate-100 p-4 rounded-sm text-xs overflow-x-auto max-h-96">
                                    {generatePythonCode()}
                                </pre>
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="absolute top-2 right-2"
                                    onClick={() => handleCopy(generatePythonCode(), 'python')}
                                >
                                    {copied === 'python' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Integration Tips */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg">
                                Consejos de Integración
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="p-4 bg-blue-50 border border-blue-200 rounded-sm">
                                    <h4 className="font-medium text-blue-900 mb-2">Power BI</h4>
                                    <ul className="text-sm text-blue-700 space-y-1">
                                        <li>• Usa "Obtener datos" → "Web"</li>
                                        <li>• Configura headers de autenticación</li>
                                        <li>• Programa actualización cada hora</li>
                                    </ul>
                                </div>
                                <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-sm">
                                    <h4 className="font-medium text-emerald-900 mb-2">Tableau</h4>
                                    <ul className="text-sm text-emerald-700 space-y-1">
                                        <li>• Conector Web Data</li>
                                        <li>• JSON parsing automático</li>
                                        <li>• Incremental refresh disponible</li>
                                    </ul>
                                </div>
                                <div className="p-4 bg-amber-50 border border-amber-200 rounded-sm">
                                    <h4 className="font-medium text-amber-900 mb-2">Excel</h4>
                                    <ul className="text-sm text-amber-700 space-y-1">
                                        <li>• Power Query → Desde Web</li>
                                        <li>• Exporta JSON y convierte a tabla</li>
                                        <li>• Usa el sandbox para descargar datos</li>
                                    </ul>
                                </div>
                                <div className="p-4 bg-purple-50 border border-purple-200 rounded-sm">
                                    <h4 className="font-medium text-purple-900 mb-2">Google Sheets</h4>
                                    <ul className="text-sm text-purple-700 space-y-1">
                                        <li>• Apps Script con UrlFetchApp</li>
                                        <li>• Trigger programado</li>
                                        <li>• Parsea JSON con JSON.parse()</li>
                                    </ul>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
};

export default ApiDocumentation;
