import React, { useState, useEffect } from 'react';
import { getReportSchema, getReportJourneys, getReportPackages, getReportIncidents, getReportKpis } from '../lib/api';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs';
import { BookOpen, Zap, Code, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { DocsTab } from '../components/api-docs/DocsTab';
import { SandboxTab } from '../components/api-docs/SandboxTab';
import { ExamplesTab } from '../components/api-docs/ExamplesTab';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ApiDocumentation = () => {
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

    // Visible token for Power BI / docs
    const [visibleToken, setVisibleToken] = useState('');

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

    useEffect(() => {
        const fetchToken = async () => {
            try {
                const { default: api } = await import('../lib/api');
                const res = await api.post('/auth/api-token');
                setVisibleToken(res.data.access_token || '');
            } catch (err) {
                console.error('Failed to fetch API token:', err);
            }
        };
        fetchToken();
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

            const fetchers = {
                journeys: getReportJourneys,
                packages: getReportPackages,
                incidents: getReportIncidents,
                kpis: getReportKpis,
            };
            const fetcher = fetchers[selectedEndpoint] || getReportJourneys;
            const res = await fetcher(params);

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

    const getDisplayToken = () => visibleToken || '(token no disponible - inicia sesion)';

    const generateCurlCommand = (endpoint) => {
        const params = [];
        if (dateFrom) params.push(`date_from=${format(dateFrom, 'yyyy-MM-dd')}`);
        if (dateTo) params.push(`date_to=${format(dateTo, 'yyyy-MM-dd')}`);
        if (endpoint === 'kpis') params.push(`group_by=${groupBy}`);
        const queryString = params.length > 0 ? `?${params.join('&')}` : '';
        return `curl -X GET "${API_URL}/api/reports/${endpoint}${queryString}" \\
  -H "Authorization: Bearer ${getDisplayToken().substring(0, 20)}..." \\
  -H "Content-Type: application/json"`;
    };

    const generatePowerBiCode = () => `// Power BI - Power Query M Code (con Refresh Token)
let
    // ─── Configuración ───
    ApiUrl = "${API_URL}/api",
    RefreshToken = "TU_REFRESH_TOKEN_AQUI",  // Generar desde Integraciones

    // ─── Paso 1: Obtener access token usando refresh token ───
    TokenResponse = Json.Document(
        Web.Contents(
            ApiUrl & "/auth/exchange-token",
            [
                Headers = [
                    #"Authorization" = "Bearer " & RefreshToken,
                    #"Content-Type" = "application/json"
                ],
                Content = Text.ToBinary("{}")
            ]
        )
    ),
    AccessToken = TokenResponse[access_token],

    // ─── Paso 2: Consultar datos ───
    DateFrom = "${dateFrom ? format(dateFrom, 'yyyy-MM-dd') : ''}",
    DateTo = "${dateTo ? format(dateTo, 'yyyy-MM-dd') : ''}",
    ${selectedEndpoint === 'kpis' ? `GroupBy = "${groupBy}",` : ''}
    QueryParams = [date_from = DateFrom, date_to = DateTo${selectedEndpoint === 'kpis' ? ', group_by = GroupBy' : ''}],

    Source = Json.Document(
        Web.Contents(
            ApiUrl & "/reports/${selectedEndpoint}",
            [
                Headers = [
                    #"Authorization" = "Bearer " & AccessToken,
                    #"Content-Type" = "application/json"
                ],
                Query = QueryParams
            ]
        )
    ),

    Data = Source[data],
    #"Converted to Table" = Table.FromList(Data, Splitter.SplitByNothing(), null, null, ExtraValues.Error),
    #"Expanded Column1" = Table.ExpandRecordColumn(#"Converted to Table", "Column1", Record.FieldNames(Data{0}))
in
    #"Expanded Column1"`;

    const generatePythonCode = () => `import requests
import pandas as pd

# Configuración
API_URL = "${API_URL}/api"
REFRESH_TOKEN = "TU_REFRESH_TOKEN_AQUI"  # Generar desde Integraciones

# Paso 1: Obtener access token usando refresh token
auth_response = requests.post(
    f"{API_URL}/auth/exchange-token",
    headers={"Authorization": f"Bearer {REFRESH_TOKEN}"}
)
access_token = auth_response.json()["access_token"]

# Paso 2: Consultar datos
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

params = {
    "date_from": "${dateFrom ? format(dateFrom, 'yyyy-MM-dd') : ''}",
    "date_to": "${dateTo ? format(dateTo, 'yyyy-MM-dd') : ''}"${selectedEndpoint === 'kpis' ? `,
    "group_by": "${groupBy}"` : ''}
}

response = requests.get(
    f"{API_URL}/reports/${selectedEndpoint}",
    headers=headers,
    params={k: v for k, v in params.items() if v}
)

data = response.json()
df = pd.DataFrame(data["data"])
print(f"Total registros: {data['total']}")
print(df.head())`;

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
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

                <DocsTab
                    schema={schema}
                    visibleToken={visibleToken}
                    copied={copied}
                    onCopy={handleCopy}
                />

                <SandboxTab
                    selectedEndpoint={selectedEndpoint}
                    setSelectedEndpoint={setSelectedEndpoint}
                    dateFrom={dateFrom}
                    setDateFrom={setDateFrom}
                    dateTo={dateTo}
                    setDateTo={setDateTo}
                    groupBy={groupBy}
                    setGroupBy={setGroupBy}
                    sandboxResult={sandboxResult}
                    sandboxLoading={sandboxLoading}
                    onRunSandbox={handleRunSandbox}
                    onDownloadJson={downloadJson}
                    generateCurlCommand={generateCurlCommand}
                    copied={copied}
                    onCopy={handleCopy}
                />

                <ExamplesTab
                    powerBiCode={generatePowerBiCode()}
                    pythonCode={generatePythonCode()}
                    copied={copied}
                    onCopy={handleCopy}
                />
            </Tabs>
        </div>
    );
};

export default ApiDocumentation;
