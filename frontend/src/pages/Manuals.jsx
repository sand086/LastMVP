import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { getManuals, seedManuals } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
    Search, BookOpen, Upload, Route, BarChart3, Settings, Code, LayoutDashboard,
    Loader2, Database, ArrowRight, Monitor, Smartphone, Globe,
} from 'lucide-react';
import { toast } from 'sonner';

const ICON_MAP = {
    'book-open': BookOpen,
    'upload': Upload,
    'route': Route,
    'bar-chart-3': BarChart3,
    'settings': Settings,
    'code': Code,
    'layout-dashboard': LayoutDashboard,
};

const SECTIONS = ['Paneles', 'Operación de Envíos', 'Configuración', 'Integraciones'];

const SECTION_COLORS = {
    'Paneles': { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', icon: 'text-blue-500' },
    'Operación de Envíos': { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', icon: 'text-emerald-500' },
    'Configuración': { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700', icon: 'text-amber-500' },
    'Integraciones': { bg: 'bg-violet-50', border: 'border-violet-200', text: 'text-violet-700', icon: 'text-violet-500' },
};

const PLATFORM_ICONS = { web: Monitor, app: Smartphone, both: Globe };

const Manuals = () => {
    const { isCoordinator } = useAuth();
    const [manuals, setManuals] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [filterSection, setFilterSection] = useState('all');
    const [filterPlatform, setFilterPlatform] = useState('all');

    useEffect(() => {
        fetchManuals();
    }, []);

    const fetchManuals = async () => {
        try {
            const res = await getManuals({});
            setManuals(res.data.data);
        } catch (err) {
            console.error('Failed to load manuals:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleSeed = async () => {
        try {
            const res = await seedManuals();
            toast.success(res.data.message);
            fetchManuals();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Error al sembrar manuales');
        }
    };

    const filtered = useMemo(() => {
        let result = manuals;
        if (filterSection !== 'all') result = result.filter(m => m.section === filterSection);
        if (filterPlatform !== 'all') result = result.filter(m => m.platform_type === filterPlatform || m.platform_type === 'both');
        if (search.trim()) {
            const q = search.toLowerCase();
            result = result.filter(m =>
                m.title.toLowerCase().includes(q) ||
                (m.subtitle || '').toLowerCase().includes(q) ||
                (m.tags || []).some(t => t.toLowerCase().includes(q))
            );
        }
        return result;
    }, [manuals, filterSection, filterPlatform, search]);

    const grouped = useMemo(() => {
        const groups = {};
        for (const sec of SECTIONS) groups[sec] = [];
        for (const m of filtered) {
            const sec = m.section || 'Paneles';
            if (!groups[sec]) groups[sec] = [];
            groups[sec].push(m);
        }
        return groups;
    }, [filtered]);

    if (loading) {
        return <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-slate-400" /></div>;
    }

    return (
        <div className="space-y-6" data-testid="manuals-page">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">Manuales de Plataforma</h1>
                    <p className="text-slate-500 text-sm">Documentacion interna para equipos de operaciones</p>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded">{filtered.length} manuales</span>
                    {isCoordinator() && manuals.length === 0 && (
                        <Button variant="outline" size="sm" onClick={handleSeed} data-testid="seed-manuals-btn">
                            <Database className="w-4 h-4 mr-1" />Inicializar manuales
                        </Button>
                    )}
                </div>
            </div>

            {/* Filters */}
            <div className="flex items-center gap-3 flex-wrap">
                <div className="relative flex-1 max-w-md">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar manual..." className="pl-9" data-testid="manuals-search" />
                </div>
                <Select value={filterSection} onValueChange={setFilterSection}>
                    <SelectTrigger className="w-[200px]" data-testid="manuals-filter-section">
                        <SelectValue placeholder="Seccion" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todas las secciones</SelectItem>
                        {SECTIONS.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                </Select>
                <Select value={filterPlatform} onValueChange={setFilterPlatform}>
                    <SelectTrigger className="w-[140px]" data-testid="manuals-filter-platform">
                        <SelectValue placeholder="Plataforma" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todas</SelectItem>
                        <SelectItem value="web">Web</SelectItem>
                        <SelectItem value="app">App</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Grouped Cards */}
            {manuals.length === 0 ? (
                <Card>
                    <CardContent className="py-16 text-center">
                        <BookOpen className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500 mb-4">No hay manuales todavia</p>
                        {isCoordinator() && (
                            <Button onClick={handleSeed} data-testid="seed-manuals-empty-btn">
                                <Database className="w-4 h-4 mr-2" />Inicializar con manuales de ejemplo
                            </Button>
                        )}
                    </CardContent>
                </Card>
            ) : filtered.length === 0 ? (
                <Card><CardContent className="py-12 text-center"><p className="text-slate-500">Sin resultados para "{search}"</p></CardContent></Card>
            ) : (
                Object.entries(grouped).map(([section, items]) => {
                    if (items.length === 0) return null;
                    const colors = SECTION_COLORS[section] || SECTION_COLORS['Paneles'];
                    return (
                        <div key={section}>
                            <div className="flex items-center gap-2 mb-3">
                                <span className={`text-xs font-semibold uppercase tracking-wider ${colors.text}`}>{section}</span>
                                <span className="text-xs text-slate-400">({items.length})</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {items.map(manual => {
                                    const IconComp = ICON_MAP[manual.icon_key] || BookOpen;
                                    const PlatIcon = PLATFORM_ICONS[manual.platform_type] || Globe;
                                    return (
                                        <Link key={manual.id} to={`/manuales/${manual.slug}`} className="block group" data-testid={`manual-card-${manual.slug}`}>
                                            <Card className={`h-full transition-all duration-200 hover:shadow-md hover:border-slate-300 ${colors.border} border`}>
                                                <CardContent className="p-5">
                                                    <div className="flex items-start gap-3">
                                                        <div className={`w-10 h-10 rounded-lg ${colors.bg} flex items-center justify-center flex-shrink-0`}>
                                                            <IconComp className={`w-5 h-5 ${colors.icon}`} />
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <h3 className="font-semibold text-sm text-slate-900 group-hover:text-blue-600 transition-colors truncate">{manual.title}</h3>
                                                            <p className="text-xs text-slate-500 mt-1 line-clamp-2">{manual.subtitle}</p>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center justify-between mt-4">
                                                        <div className="flex flex-wrap gap-1">
                                                            {(manual.tags || []).slice(0, 3).map(tag => (
                                                                <span key={tag} className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">{tag}</span>
                                                            ))}
                                                        </div>
                                                        <div className="flex items-center gap-1 text-slate-400">
                                                            <PlatIcon className="w-3.5 h-3.5" />
                                                            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                                                        </div>
                                                    </div>
                                                </CardContent>
                                            </Card>
                                        </Link>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })
            )}
        </div>
    );
};

export default Manuals;
