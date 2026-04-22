import React from 'react';
import { TabsContent } from '../../components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { FileJson, Code, Copy, Check } from 'lucide-react';

const INTEGRATION_TIPS = [
    { title: 'Power BI', color: 'blue', items: ['Usa "Obtener datos" → "Web"', 'Configura headers de autenticación', 'Programa actualización cada hora'] },
    { title: 'Tableau', color: 'emerald', items: ['Conector Web Data', 'JSON parsing automático', 'Incremental refresh disponible'] },
    { title: 'Excel', color: 'amber', items: ['Power Query → Desde Web', 'Exporta JSON y convierte a tabla', 'Usa el sandbox para descargar datos'] },
    { title: 'Google Sheets', color: 'purple', items: ['Apps Script con UrlFetchApp', 'Trigger programado', 'Parsea JSON con JSON.parse()'] },
];

const tipBg = {
    blue: 'bg-blue-50 border-blue-200', emerald: 'bg-emerald-50 border-emerald-200',
    amber: 'bg-amber-50 border-amber-200', purple: 'bg-purple-50 border-purple-200',
};
const tipText = {
    blue: 'text-blue-900', emerald: 'text-emerald-900',
    amber: 'text-amber-900', purple: 'text-purple-900',
};
const tipItemText = {
    blue: 'text-blue-700', emerald: 'text-emerald-700',
    amber: 'text-amber-700', purple: 'text-purple-700',
};

export const ExamplesTab = ({ powerBiCode, pythonCode, copied, onCopy }) => (
    <TabsContent value="examples" className="space-y-6">
        {/* Power BI */}
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <FileJson className="w-5 h-5" />
                    Power BI - Power Query M
                </CardTitle>
                <CardDescription>Copia este código en el editor avanzado de Power Query</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="relative">
                    <pre className="bg-slate-900 text-slate-100 p-4 rounded-sm text-xs overflow-x-auto max-h-96">
                        {powerBiCode}
                    </pre>
                    <Button variant="ghost" size="sm" className="absolute top-2 right-2" onClick={() => onCopy(powerBiCode, 'powerbi')}>
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
                <CardDescription>Ejemplo para análisis de datos con Python</CardDescription>
            </CardHeader>
            <CardContent>
                <div className="relative">
                    <pre className="bg-slate-900 text-slate-100 p-4 rounded-sm text-xs overflow-x-auto max-h-96">
                        {pythonCode}
                    </pre>
                    <Button variant="ghost" size="sm" className="absolute top-2 right-2" onClick={() => onCopy(pythonCode, 'python')}>
                        {copied === 'python' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                    </Button>
                </div>
            </CardContent>
        </Card>

        {/* Integration Tips */}
        <Card>
            <CardHeader>
                <CardTitle className="font-heading text-lg">Consejos de Integración</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {INTEGRATION_TIPS.map((t) => (
                        <div key={t.title} className={`p-4 border rounded-sm ${tipBg[t.color]}`}>
                            <h4 className={`font-medium mb-2 ${tipText[t.color]}`}>{t.title}</h4>
                            <ul className={`text-sm space-y-1 ${tipItemText[t.color]}`}>
                                {t.items.map((it) => <li key={it}>• {it}</li>)}
                            </ul>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    </TabsContent>
);

export default ExamplesTab;
