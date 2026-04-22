import React, { useCallback, useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import {
    RefreshCw, Loader2, Layers, Database, GitBranch, AlertTriangle, CheckCircle2, Clock,
    Server, Globe,
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';
import {
    getArchitectureSnapshot,
    regenerateArchitecture,
    getArchitectureChangelog,
} from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { MermaidDiagram } from '../components/architecture/MermaidDiagram';
import {
    buildSystemDiagram,
    buildDataModelDiagram,
    buildAIEvalFlowDiagram,
} from '../components/architecture/diagramBuilders';

const Architecture = () => {
    const { user } = useAuth();
    const [snapshot, setSnapshot] = useState(null);
    const [changelog, setChangelog] = useState([]);
    const [loading, setLoading] = useState(true);
    const [regenerating, setRegenerating] = useState(false);
    const canRegenerate = user?.role === 'developer' || user?.role === 'executive';

    const fetchAll = useCallback(async () => {
        setLoading(true);
        try {
            const [snapRes, logRes] = await Promise.all([
                getArchitectureSnapshot(),
                getArchitectureChangelog(10),
            ]);
            setSnapshot(snapRes.data);
            setChangelog(logRes.data.data || []);
        } catch (e) {
            toast.error('Error cargando arquitectura');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchAll(); }, [fetchAll]);

    const handleRegenerate = async () => {
        setRegenerating(true);
        try {
            const res = await regenerateArchitecture();
            if (res.data.status === 'unchanged') {
                toast.info('Sin cambios estructurales detectados');
            } else {
                const n = res.data.diff?.total_changes || 0;
                toast.success(`Snapshot regenerado (${n} cambios detectados)`);
            }
            await fetchAll();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Error regenerando snapshot');
        } finally {
            setRegenerating(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-24" data-testid="architecture-loading">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        );
    }

    if (!snapshot) {
        return <div className="p-6 text-slate-500">Sin datos de arquitectura</div>;
    }

    return (
        <div className="space-y-6" data-testid="architecture-page">
            {/* Header */}
            <div className="flex items-start justify-between flex-wrap gap-3">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
                        <Layers className="w-6 h-6" /> Arquitectura Viva
                    </h1>
                    <p className="text-slate-500 text-sm">
                        Diagrama técnico autogenerado desde el codebase actual · Para DevOps & Arquitectos de Soluciones
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="text-xs text-slate-500 flex items-center gap-1" data-testid="snapshot-meta">
                        <Clock className="w-3 h-3" />
                        {format(new Date(snapshot.generated_at), "d MMM yyyy HH:mm", { locale: es })}
                        <span className="mx-1 opacity-50">·</span>
                        <span className="font-mono">{snapshot.content_hash}</span>
                    </div>
                    {canRegenerate && (
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={handleRegenerate}
                            disabled={regenerating}
                            data-testid="regenerate-snapshot-btn"
                        >
                            {regenerating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                            Regenerar
                        </Button>
                    )}
                </div>
            </div>

            {/* Executive summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                <StatCard icon={Database} label="Colecciones" value={snapshot.stats.collections} />
                <StatCard icon={Server} label="Endpoints" value={snapshot.stats.endpoints} />
                <StatCard icon={Globe} label="Rutas FE" value={snapshot.stats.frontend_routes} />
                <StatCard icon={Layers} label="Páginas" value={snapshot.stats.pages} />
                <StatCard icon={GitBranch} label="Integraciones" value={snapshot.stats.integrations} />
                <StatCard
                    icon={AlertTriangle}
                    label="Antipatrones"
                    value={snapshot.stats.antipatterns}
                    accent={snapshot.stats.antipatterns > 0 ? 'amber' : 'emerald'}
                />
            </div>

            {/* Tabs */}
            <Tabs defaultValue="overview">
                <TabsList className="grid grid-cols-5 w-full">
                    <TabsTrigger value="overview" data-testid="tab-arch-overview">Sistema</TabsTrigger>
                    <TabsTrigger value="data" data-testid="tab-arch-data">Datos</TabsTrigger>
                    <TabsTrigger value="flows" data-testid="tab-arch-flows">Flujos</TabsTrigger>
                    <TabsTrigger value="modules" data-testid="tab-arch-modules">Módulos</TabsTrigger>
                    <TabsTrigger value="changelog" data-testid="tab-arch-changelog">Changelog</TabsTrigger>
                </TabsList>

                {/* Capa 1: Sistema */}
                <TabsContent value="overview" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg">Vista sistémica</CardTitle>
                            <CardDescription>Frontend → Ingress → Backend → Datos → Integraciones</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <MermaidDiagram chart={buildSystemDiagram(snapshot)} testId="system-diagram" />
                        </CardContent>
                    </Card>
                    <IntegrationsList integrations={snapshot.integrations} />
                </TabsContent>

                {/* Capa 2: Datos */}
                <TabsContent value="data" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg">Modelo de datos (top 15 colecciones)</CardTitle>
                            <CardDescription>Entidades con ownership de escritura y operaciones</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <MermaidDiagram chart={buildDataModelDiagram(snapshot)} testId="data-diagram" />
                        </CardContent>
                    </Card>
                    <CollectionsTable collections={snapshot.collections} />
                    <AntipatternsList items={snapshot.antipatterns} />
                </TabsContent>

                {/* Capa 3: Flujos */}
                <TabsContent value="flows">
                    <Card>
                        <CardHeader>
                            <CardTitle className="font-heading text-lg">Flujo: Evaluación IA end-to-end</CardTitle>
                            <CardDescription>
                                Desde el click en GuiasTab hasta la persistencia del score con cron de recuperación
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <MermaidDiagram chart={buildAIEvalFlowDiagram(snapshot)} testId="flow-diagram" />
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Módulos */}
                <TabsContent value="modules">
                    <ModulesTable modules={snapshot.modules} />
                </TabsContent>

                {/* Changelog */}
                <TabsContent value="changelog">
                    <ChangelogList entries={changelog} />
                </TabsContent>
            </Tabs>
        </div>
    );
};

const StatCard = ({ icon: Icon, label, value, accent = 'slate' }) => {
    const colors = {
        slate: 'bg-slate-50 text-slate-700',
        emerald: 'bg-emerald-50 text-emerald-700',
        amber: 'bg-amber-50 text-amber-700',
        red: 'bg-red-50 text-red-700',
    };
    return (
        <Card>
            <CardContent className="p-4 flex items-center gap-3">
                <div className={`p-2 rounded-md ${colors[accent]}`}>
                    <Icon className="w-4 h-4" />
                </div>
                <div>
                    <p className="text-xs text-slate-500 uppercase tracking-wide">{label}</p>
                    <p className="text-2xl font-bold font-heading">{value}</p>
                </div>
            </CardContent>
        </Card>
    );
};

const IntegrationsList = ({ integrations }) => (
    <Card>
        <CardHeader>
            <CardTitle className="font-heading text-lg">Integraciones externas detectadas</CardTitle>
        </CardHeader>
        <CardContent>
            <div className="space-y-2">
                {(integrations || []).map((i) => (
                    <div key={i.package} className="flex items-start gap-3 p-3 bg-slate-50 rounded-md">
                        <Badge variant="outline" className="font-mono">{i.package}</Badge>
                        <div className="flex-1">
                            <p className="text-sm text-slate-900">{i.description}</p>
                            <p className="text-xs text-slate-500 mt-0.5">
                                Usado en: {i.used_in.slice(0, 4).join(', ')}
                                {i.used_in.length > 4 && ` +${i.used_in.length - 4} más`}
                            </p>
                        </div>
                    </div>
                ))}
            </div>
        </CardContent>
    </Card>
);

const CollectionsTable = ({ collections }) => (
    <Card>
        <CardHeader>
            <CardTitle className="font-heading text-lg">Colecciones MongoDB</CardTitle>
            <CardDescription>Ownership de escritura y operaciones detectadas</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="collections-table">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                        <th className="text-left p-2">Colección</th>
                        <th className="text-left p-2">Ownership</th>
                        <th className="text-left p-2">Writers</th>
                        <th className="text-left p-2">Operaciones</th>
                    </tr>
                </thead>
                <tbody>
                    {Object.entries(collections).map(([name, meta]) => (
                        <tr key={name} className="border-t border-slate-100">
                            <td className="p-2 font-mono text-xs">{name}</td>
                            <td className="p-2">
                                <OwnershipBadge status={meta.write_ownership.status} />
                            </td>
                            <td className="p-2 text-xs text-slate-600 max-w-xs truncate" title={meta.writers.join(', ')}>
                                {meta.writers.length === 0 ? '—' : meta.writers.length + ' mod'}
                            </td>
                            <td className="p-2 text-xs font-mono text-slate-500">
                                {meta.operations.join(', ')}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </CardContent>
    </Card>
);

const OwnershipBadge = ({ status }) => {
    const cfg = {
        single: { color: 'bg-emerald-100 text-emerald-700', label: 'Single' },
        multi_route: { color: 'bg-blue-100 text-blue-700', label: 'Multi-route' },
        violation: { color: 'bg-amber-100 text-amber-700', label: 'Multi-layer' },
        read_only: { color: 'bg-slate-100 text-slate-700', label: 'Read-only' },
    }[status] || { color: 'bg-slate-100', label: status };
    return <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${cfg.color}`}>{cfg.label}</span>;
};

const AntipatternsList = ({ items }) => {
    if (!items || items.length === 0) {
        return (
            <Card>
                <CardContent className="p-4 flex items-center gap-2 text-sm text-emerald-700">
                    <CheckCircle2 className="w-4 h-4" /> No se detectaron antipatrones arquitectónicos.
                </CardContent>
            </Card>
        );
    }
    return (
        <Card data-testid="antipatterns-list">
            <CardHeader>
                <CardTitle className="font-heading text-lg flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-600" /> Antipatrones detectados ({items.length})
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
                {items.map((a, i) => (
                    <div key={i} className="p-3 bg-amber-50 border border-amber-200 rounded-md text-sm">
                        <div className="flex items-center gap-2 mb-1">
                            <Badge variant="outline" className="text-xs">{a.severity}</Badge>
                            <span className="font-mono text-xs">{a.type}</span>
                        </div>
                        <p className="text-slate-700 text-xs">{a.description}</p>
                    </div>
                ))}
            </CardContent>
        </Card>
    );
};

const ModulesTable = ({ modules }) => (
    <Card>
        <CardHeader>
            <CardTitle className="font-heading text-lg">Módulos funcionales</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="modules-table">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                        <th className="text-left p-2">Módulo</th>
                        <th className="text-left p-2">Descripción</th>
                        <th className="text-right p-2">Endpoints</th>
                        <th className="text-right p-2">Líneas</th>
                    </tr>
                </thead>
                <tbody>
                    {modules.map((m) => (
                        <tr key={m.module} className="border-t border-slate-100">
                            <td className="p-2 font-mono text-xs">{m.module}</td>
                            <td className="p-2 text-sm">{m.label}</td>
                            <td className="p-2 text-right tabular-nums">{m.endpoint_count}</td>
                            <td className="p-2 text-right tabular-nums text-slate-500">{m.lines}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </CardContent>
    </Card>
);

const ChangelogList = ({ entries }) => {
    if (!entries || entries.length === 0) {
        return (
            <Card>
                <CardContent className="p-8 text-center text-slate-500 text-sm">
                    Sin cambios registrados aún. Los cambios se registran automáticamente al regenerar.
                </CardContent>
            </Card>
        );
    }
    return (
        <Card data-testid="changelog-list">
            <CardHeader>
                <CardTitle className="font-heading text-lg">Historial de cambios estructurales</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-slate-100">
                {entries.map((e) => (
                    <div key={e.id} className="py-3">
                        <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
                            <span>{format(new Date(e.timestamp), "d MMM yyyy HH:mm", { locale: es })}</span>
                            <Badge variant="outline">{e.total_changes} cambios</Badge>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                            {Object.entries(e.changes || {}).map(([k, v]) => (
                                <div key={k} className="bg-slate-50 rounded p-2">
                                    <p className="font-mono text-[10px] uppercase text-slate-500 mb-0.5">{k.replace(/_/g, ' ')}</p>
                                    <p className="text-slate-700">
                                        {Array.isArray(v) ? v.slice(0, 5).join(', ') : String(v)}
                                        {Array.isArray(v) && v.length > 5 && ` +${v.length - 5} más`}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </CardContent>
        </Card>
    );
};

export default Architecture;
