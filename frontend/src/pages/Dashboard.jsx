import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useSortableTable } from '../lib/useSortableTable';
import { KPICard } from '../components/dashboard/KPICard';
import { RoutesTable } from '../components/dashboard/RoutesTable';
import { useWebSocket } from '../lib/useWebSocket';
import ConnectionStatus from '../components/ConnectionStatus';
import './Dashboard.css';
import { 
    getDashboardStats, 
    getJourneys, 
    getIncidentsBreakdown,
    getProviderComparison,
    exportJourneys,
    getClients,
    getProviders,
    syncKosmoTracking,
    getKosmoSyncStatus,
    searchPackages
} from '../lib/api';
import { 
    formatDate, 
    getStatusColor, 
    getStatusLabel,
    getProgressColor,
    calculateDeliveryRate,
    downloadFile
} from '../lib/utils';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { Calendar } from '../components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { 
    Truck, 
    Package, 
    AlertTriangle, 
    CheckCircle2, 
    Calendar as CalendarIcon,
    Download,
    Eye,
    RefreshCw,
    Upload,
    TrendingUp,
    ShieldCheck,
    Search
} from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { es } from 'date-fns/locale';

const HeatmapSection = lazy(() => import('../components/HeatmapSection'));

/* ─── Design tokens inline ─── */
const T = {
    bg: '#F5F4F1', surface: '#FFFFFF', surface2: '#F0EFEC',
    border: '#E2E0DB', borderStrong: '#C8C6BF',
    textPri: '#1A1916', textSec: '#6B6960', textTer: '#9C9A92',
    blue: '#2563EB', blueLt: '#EFF6FF',
    amber: '#D97706', amberLt: '#FFFBEB',
    green: '#16A34A', greenLt: '#F0FDF4',
    coral: '#DC2626', coralLt: '#FEF2F2',
    purple: '#7C3AED', purpleLt: '#F5F3FF',
    radius: 10, radiusSm: 6,
};

/* ─── KPI Card ─── */
/* ─────────────── DASHBOARD ─────────────── */
const Dashboard = () => {
    const { canEdit, hasRole } = useAuth();
    const isProviderOnly = hasRole('proveedor');
    const [stats, setStats] = useState(null);
    const [journeys, setJourneys] = useState([]);
    const [pagination, setPagination] = useState({ page: 1, page_size: 25, total_count: 0, total_pages: 1 });
    const [incidentsBreakdown, setIncidentsBreakdown] = useState({});
    const [providerComparison, setProviderComparison] = useState([]);
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [loading, setLoading] = useState(true);
    const [exporting, setExporting] = useState(false);
    const [kosmoSync, setKosmoSync] = useState({ last_sync: null, total_checked: 0, updated: 0, errors: 0 });
    const [syncing, setSyncing] = useState(false);
    const [packageSearch, setPackageSearch] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [searching, setSearching] = useState(false);
    const [dateFrom, setDateFrom] = useState(new Date());
    const [dateTo, setDateTo] = useState(new Date());
    const [selectedClient, setSelectedClient] = useState('all');
    const [selectedProvider, setSelectedProvider] = useState('all');
    const [selectedStatus, setSelectedStatus] = useState('all');
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(25);

    const dateFromStr = format(dateFrom, 'yyyy-MM-dd');
    const dateToStr = format(dateTo, 'yyyy-MM-dd');

    const fetchData = useCallback(async () => {
        try {
            const results = await Promise.allSettled([
                getDashboardStats(dateFromStr, dateToStr),
                getJourneys({
                    date_from: dateFromStr, date_to: dateToStr,
                    client_id: selectedClient !== 'all' ? selectedClient : undefined,
                    provider_id: selectedProvider !== 'all' ? selectedProvider : undefined,
                    status: selectedStatus !== 'all' ? selectedStatus : undefined,
                    page: currentPage, page_size: pageSize,
                }),
                getIncidentsBreakdown(dateFromStr, dateToStr),
                getProviderComparison(dateFromStr, dateToStr),
                getClients(),
                getProviders(),
                getKosmoSyncStatus().catch(() => ({ data: { last_sync: null } })),
            ]);
            const [statsRes, journeysRes, breakdownRes, comparisonRes, clientsRes, providersRes, kosmoRes] = results;

            if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
            if (journeysRes.status === 'fulfilled') {
                const jData = journeysRes.value.data;
                setJourneys(jData.data || []);
                setPagination(jData.pagination || { page: 1, page_size: 25, total_count: 0, total_pages: 1 });
            }
            if (breakdownRes.status === 'fulfilled') setIncidentsBreakdown(breakdownRes.value.data);
            if (comparisonRes.status === 'fulfilled') setProviderComparison(comparisonRes.value.data);
            if (clientsRes.status === 'fulfilled') setClients(clientsRes.value.data);
            if (providersRes.status === 'fulfilled') setProviders(providersRes.value.data);
            if (kosmoRes.status === 'fulfilled' && kosmoRes.value.data) setKosmoSync(kosmoRes.value.data);

            const failed = results.filter(r => r.status === 'rejected');
            if (failed.length === results.length) {
                toast.error('Error al cargar datos');
            }
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
            toast.error('Error al cargar datos');
        } finally {
            setLoading(false);
        }
    }, [dateFromStr, dateToStr, selectedClient, selectedProvider, selectedStatus, currentPage, pageSize]);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 60000);
        return () => clearInterval(interval);
    }, [fetchData]);

    const handleWsEvent = useCallback((event) => {
        if (['stats_update', 'journey_update', 'incident_update', 'sync_update'].includes(event.type)) fetchData();
    }, [fetchData]);
    const { connectionMode, justRecovered } = useWebSocket(handleWsEvent);

    useEffect(() => { setCurrentPage(1); }, [dateFrom, dateTo, selectedClient, selectedProvider, selectedStatus]);

    const handleExport = async () => {
        setExporting(true);
        try {
            const response = await exportJourneys({
                date_from: dateFromStr, date_to: dateToStr,
                client_id: selectedClient !== 'all' ? selectedClient : undefined,
                provider_id: selectedProvider !== 'all' ? selectedProvider : undefined,
            });
            downloadFile(response.data, `rutas_${dateFromStr}_${dateToStr}.xlsx`);
            toast.success('Archivo exportado exitosamente');
        } catch { toast.error('Error al exportar'); }
        setExporting(false);
    };

    const handleRefresh = () => { setLoading(true); fetchData(); };

    const handleKosmoSync = async () => {
        setSyncing(true);
        try {
            await syncKosmoTracking();
            toast.success('Sincronización iniciada');
            setTimeout(async () => {
                try {
                    const statusRes = await getKosmoSyncStatus();
                    if (statusRes.data) setKosmoSync(statusRes.data);
                } catch (err) { console.error('Kosmo sync status check failed:', err); }
                fetchData();
                setSyncing(false);
            }, 5000);
        } catch (err) {
            console.error('Kosmo sync trigger failed:', err);
            toast.error('Error al sincronizar con Kosmo');
            setSyncing(false);
        }
    };

    const getTimeSince = (iso) => {
        if (!iso) return null;
        const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
        if (diff < 1) return 'ahora';
        if (diff < 60) return `hace ${diff} min`;
        if (diff < 1440) return `hace ${Math.floor(diff / 60)}h`;
        return `hace ${Math.floor(diff / 1440)}d`;
    };

    const handlePackageSearch = async (query) => {
        setPackageSearch(query);
        if (query.length < 2) { setSearchResults([]); return; }
        setSearching(true);
        try {
            const res = await searchPackages(query);
            setSearchResults(res.data || []);
        } catch (err) { console.error('Package search failed:', err); setSearchResults([]); }
        finally { setSearching(false); }
    };

    return (
        <div className="lm-dashboard">
            {/* ─── Top bar: WS + Kosmo sync ─── */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ConnectionStatus connectionMode={connectionMode} justRecovered={justRecovered} />
                    {kosmoSync.last_sync && (
                        <span style={{ fontSize: 12, color: T.textTer, marginLeft: 8, fontFamily: "'DM Mono', monospace" }}>
                            · Kosmo: {getTimeSince(kosmoSync.last_sync)}
                        </span>
                    )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button
                        className="lm-filter-btn"
                        onClick={() => {
                            if (isProviderOnly) { toast.info('Sin permisos para esta acción'); return; }
                            handleKosmoSync();
                        }}
                        disabled={syncing}
                        data-testid="kosmo-sync-btn"
                        style={{ fontSize: 12 }}
                    >
                        <RefreshCw style={{ width: 13, height: 13, ...(syncing ? { animation: 'lm-spin 1s linear infinite' } : {}) }} />
                        {syncing ? 'Sincronizando...' : 'Sincronizar ahora'}
                    </button>
                    {canEdit() && (
                        <Link to="/layout">
                            <button className="lm-filter-btn" style={{ fontSize: 12, background: T.textPri, color: '#fff', border: 'none' }} data-testid="new-journey-btn">
                                <Upload style={{ width: 13, height: 13 }} />Cargar Layout
                            </button>
                        </Link>
                    )}
                </div>
            </div>

            {/* ─── FILTERS ROW ─── */}
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }} data-testid="filters-row">
                {/* Search */}
                <div className="lm-search-box" style={{ minWidth: 260, position: 'relative' }} data-testid="package-search-container">
                    <Search style={{ width: 15, height: 15, color: T.textTer, flexShrink: 0 }} />
                    <input
                        type="text"
                        value={packageSearch}
                        onChange={(e) => handlePackageSearch(e.target.value)}
                        placeholder="Buscar paquete por guía o referencia..."
                        data-testid="package-search-input"
                    />
                    {searching && <RefreshCw style={{ width: 13, height: 13, color: T.textTer, animation: 'lm-spin 1s linear infinite' }} />}
                    {searchResults.length > 0 && packageSearch.length >= 2 && (
                        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, marginTop: 4, background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.radiusSm, boxShadow: '0 4px 16px rgba(0,0,0,0.1)', maxHeight: 260, overflowY: 'auto' }}>
                            {searchResults.map((pkg) => (
                                <a
                                    key={pkg.id}
                                    href={`/journeys/${pkg.journey_id}`}
                                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: `1px solid ${T.border}`, textDecoration: 'none', color: 'inherit', transition: 'background 0.15s' }}
                                    data-testid={`search-result-${pkg.id}`}
                                    className="lm-cp-row"
                                >
                                    <div style={{ minWidth: 0 }}>
                                        <p style={{ fontSize: 13, fontFamily: "'DM Mono', monospace", fontWeight: 500, color: T.textPri }}>{pkg.order_reference_id || pkg.tracking_number}</p>
                                        <p style={{ fontSize: 12, color: T.textSec }}>{pkg.recipient_name} — {pkg.address}</p>
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginLeft: 12 }}>
                                        <span style={{ fontSize: 11, fontWeight: 500, padding: '2px 8px', borderRadius: 4, background: pkg.status === 'delivered' ? T.greenLt : pkg.status === 'failed' ? T.coralLt : T.amberLt, color: pkg.status === 'delivered' ? T.green : pkg.status === 'failed' ? T.coral : T.amber }}>{pkg.status}</span>
                                        <span style={{ fontSize: 12, color: T.textTer }}>{pkg.journey_date}</span>
                                    </div>
                                </a>
                            ))}
                        </div>
                    )}
                </div>

                {/* Date Range */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Popover>
                        <PopoverTrigger asChild>
                            <button className="lm-filter-btn" data-testid="date-from-picker">
                                <CalendarIcon style={{ width: 14, height: 14, color: T.textTer }} />
                                {format(dateFrom, 'dd MMM yyyy', { locale: es })}
                            </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                            <Calendar mode="single" selected={dateFrom} onSelect={(d) => d && setDateFrom(d)} initialFocus />
                        </PopoverContent>
                    </Popover>
                    <span style={{ color: T.textTer }}>—</span>
                    <Popover>
                        <PopoverTrigger asChild>
                            <button className="lm-filter-btn" data-testid="date-to-picker">
                                <CalendarIcon style={{ width: 14, height: 14, color: T.textTer }} />
                                {format(dateTo, 'dd MMM yyyy', { locale: es })}
                            </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                            <Calendar mode="single" selected={dateTo} onSelect={(d) => d && setDateTo(d)} initialFocus />
                        </PopoverContent>
                    </Popover>
                </div>

                {/* Client filter */}
                <select className="lm-select" value={selectedClient} onChange={e => setSelectedClient(e.target.value)} data-testid="client-filter">
                    <option value="all">Todos los clientes</option>
                    {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>

                {/* Provider filter */}
                <select className="lm-select" value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)} data-testid="provider-filter">
                    <option value="all">Todos los proveedores</option>
                    {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>

                {/* Status filter */}
                <select className="lm-select" value={selectedStatus} onChange={e => setSelectedStatus(e.target.value)} data-testid="status-filter">
                    <option value="all">Todos</option>
                    <option value="in_progress">En progreso</option>
                    <option value="closed">Cerradas</option>
                    <option value="scheduled">Pendientes</option>
                </select>

                <div style={{ flex: 1 }} />

                {/* Refresh */}
                <button className="lm-filter-btn" onClick={handleRefresh} data-testid="refresh-btn" style={{ padding: 7 }}>
                    <RefreshCw style={{ width: 15, height: 15, ...(loading ? { animation: 'lm-spin 1s linear infinite' } : {}) }} />
                </button>

                {/* Export */}
                <button className="lm-filter-btn" onClick={() => {
                    if (isProviderOnly) { toast.info('Sin permisos para esta acción'); return; }
                    handleExport();
                }} disabled={exporting} data-testid="export-btn">
                    <Download style={{ width: 14, height: 14 }} />
                    Exportar
                </button>
            </div>

            {/* ─── KPIs ─── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16 }} data-testid="kpis-grid">
                <KPICard title="Rutas activas" value={stats?.active_journeys || 0} subtitle="en progreso hoy" icon={Truck} accentColor={T.green} accentBg={T.greenLt} loading={loading} testId="kpi-rutas-activas" />
                <KPICard title="Paquetes entregados" value={`${stats?.delivered_packages || 0}/${stats?.total_packages || 0}`} subtitle={`${stats?.delivery_rate || 0}% completado`} icon={Package} accentColor={T.blue} accentBg={T.blueLt} loading={loading} testId="kpi-paquetes-entregados" />
                <KPICard title="Incidencias abiertas" value={stats?.open_incidents || 0} subtitle="requieren atención" icon={AlertTriangle} accentColor={T.amber} accentBg={T.amberLt} loading={loading} testId="kpi-incidencias-abiertas" />
                <KPICard title="Rutas cerradas" value={stats?.closed_journeys || 0} subtitle="completadas hoy" icon={CheckCircle2} accentColor={T.blue} accentBg={T.blueLt} loading={loading} testId="kpi-rutas-cerradas" />
                <KPICard
                    title="Calidad de soporte"
                    value={`${stats?.avg_evidence_score || 0}%`}
                    subtitle={stats?.packages_incomplete_support > 0 ? `${stats.packages_incomplete_support} sin soporte completo` : 'Todos completos'}
                    icon={ShieldCheck}
                    accentColor={(stats?.avg_evidence_score || 0) >= 90 ? T.green : (stats?.avg_evidence_score || 0) >= 70 ? T.amber : T.coral}
                    accentBg={(stats?.avg_evidence_score || 0) >= 90 ? T.greenLt : (stats?.avg_evidence_score || 0) >= 70 ? T.amberLt : T.coralLt}
                    loading={loading}
                    testId="kpi-calidad-soporte"
                />
            </div>

            {/* ─── ROUTES TABLE ─── */}
            <div className="lm-card">
                <div className="lm-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="lm-section-title">Rutas</span>
                        <span style={{ fontSize: 12, fontFamily: "'DM Mono', monospace", color: T.textTer, background: T.surface2, padding: '2px 8px', borderRadius: 4 }}>
                            {pagination.total_count}
                        </span>
                    </div>
                </div>
                {journeys.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '48px 20px' }}>
                        <Truck style={{ width: 40, height: 40, color: T.textTer, margin: '0 auto 16px' }} />
                        <p style={{ color: T.textSec, marginBottom: 16, fontSize: 14 }}>No hay rutas para mostrar</p>
                        {canEdit() && (
                            <Link to="/layout">
                                <Button variant="outline" data-testid="empty-upload-btn">
                                    <Upload className="h-4 w-4 mr-2" />¿Cargar un layout?
                                </Button>
                            </Link>
                        )}
                    </div>
                ) : (
                    <RoutesTable journeys={journeys} />
                )}
                {/* Pagination */}
                {pagination.total_pages > 0 && (
                    <div className="lm-pag" data-testid="pagination-controls">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span>Filas:</span>
                            <select className="lm-select" value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setCurrentPage(1); }} data-testid="page-size-selector" style={{ width: 68 }}>
                                <option value={25}>25</option>
                                <option value={50}>50</option>
                                <option value={75}>75</option>
                                <option value={100}>100</option>
                            </select>
                            <span style={{ color: T.textTer, marginLeft: 8 }} data-testid="pagination-info">
                                Página {pagination.page} de {pagination.total_pages} ({pagination.total_count} rutas)
                            </span>
                        </div>
                        <div style={{ display: 'flex', gap: 4 }}>
                            <button className="lm-pag-btn" disabled={currentPage <= 1} onClick={() => setCurrentPage(1)} data-testid="pagination-first">{'<<'}</button>
                            <button className="lm-pag-btn" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => Math.max(1, p - 1))} data-testid="pagination-prev">Anterior</button>
                            <button className="lm-pag-btn" disabled={currentPage >= pagination.total_pages} onClick={() => setCurrentPage(p => Math.min(pagination.total_pages, p + 1))} data-testid="pagination-next">Siguiente</button>
                            <button className="lm-pag-btn" disabled={currentPage >= pagination.total_pages} onClick={() => setCurrentPage(pagination.total_pages)} data-testid="pagination-last">{'>>'}</button>
                        </div>
                    </div>
                )}
            </div>

            {/* ─── BOTTOM GRID ─── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                {/* Metrics */}
                <div className="lm-card">
                    <div className="lm-card-header" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <TrendingUp style={{ width: 16, height: 16, color: T.textSec }} />
                        <span className="lm-section-title">Métricas del día</span>
                    </div>
                    <div>
                        <div className="lm-metric-row">
                            <span style={{ fontSize: 13, color: T.textSec }}>Tasa de entrega promedio</span>
                            <span style={{ fontFamily: "'DM Mono', monospace", fontWeight: 600, fontSize: 16 }}>{stats?.delivery_rate || 0}%</span>
                        </div>
                        <div className="lm-metric-row">
                            <span style={{ fontSize: 13, color: T.textSec }}>Km totales recorridos</span>
                            <span style={{ fontFamily: "'DM Mono', monospace", fontWeight: 600, fontSize: 16 }}>{(stats?.total_km || 0).toLocaleString()} km</span>
                        </div>
                        <div className="lm-metric-row">
                            <span style={{ fontSize: 13, color: T.textSec }}>Total rutas</span>
                            <span style={{ fontFamily: "'DM Mono', monospace", fontWeight: 600, fontSize: 16 }}>{stats?.total_journeys || 0}</span>
                        </div>
                        {/* Incidents breakdown */}
                        {Object.keys(incidentsBreakdown).length > 0 && (
                            <div style={{ padding: '12px 16px' }}>
                                <p style={{ fontSize: 12, fontWeight: 500, color: T.textTer, textTransform: 'uppercase', letterSpacing: '0.03em', marginBottom: 8 }}>Incidencias por tipo</p>
                                {Object.entries(incidentsBreakdown).map(([type, count]) => (
                                    <div key={type} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0' }}>
                                        <span style={{ color: T.textSec }}>{type}</span>
                                        <span style={{ fontFamily: "'DM Mono', monospace", background: T.surface2, padding: '1px 8px', borderRadius: 4 }}>{count}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* Provider comparison */}
                <div className="lm-card">
                    <div className="lm-card-header" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Truck style={{ width: 16, height: 16, color: T.textSec }} />
                        <span className="lm-section-title">Comparativo de proveedores</span>
                    </div>
                    {providerComparison.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: '40px 20px' }}>
                            <p style={{ color: T.textTer, fontSize: 13 }}>No hay datos de proveedores</p>
                        </div>
                    ) : (
                        <>
                            <div className="lm-provider-header">
                                <span>Proveedor</span>
                                <span style={{ textAlign: 'center' }}>Rutas</span>
                                <span style={{ textAlign: 'center' }}>Entrega%</span>
                                <span style={{ textAlign: 'center' }}>Visita%</span>
                                <span style={{ textAlign: 'center' }}>Incid.</span>
                                <span style={{ textAlign: 'right' }}>Km</span>
                            </div>
                            {providerComparison.map(p => (
                                <div key={p.provider_id} className="lm-provider-row">
                                    <span style={{ fontWeight: 500 }}>{p.provider_name}</span>
                                    <span style={{ textAlign: 'center', fontFamily: "'DM Mono', monospace" }}>{p.journeys_count}</span>
                                    <span style={{ textAlign: 'center', fontFamily: "'DM Mono', monospace", color: p.avg_delivery_rate >= 70 ? T.green : p.avg_delivery_rate >= 40 ? T.amber : T.coral }}>{p.avg_delivery_rate}%</span>
                                    <span style={{ textAlign: 'center', fontFamily: "'DM Mono', monospace", color: (p.visit_rate || 0) >= 90 ? T.green : (p.visit_rate || 0) >= 70 ? T.amber : T.coral }}>{p.visit_rate || 0}%</span>
                                    <span style={{ textAlign: 'center', fontFamily: "'DM Mono', monospace" }}>{p.total_incidents}</span>
                                    <span style={{ textAlign: 'right', fontFamily: "'DM Mono', monospace" }}>{(p.total_km || 0).toLocaleString()}</span>
                                </div>
                            ))}
                        </>
                    )}
                </div>
            </div>

            {/* ─── HEATMAP ─── */}
            <Suspense fallback={
                <div className="lm-card" style={{ padding: 40, textAlign: 'center' }}>
                    <RefreshCw style={{ width: 24, height: 24, color: T.textTer, margin: '0 auto', animation: 'lm-spin 1s linear infinite' }} />
                    <p style={{ color: T.textTer, fontSize: 13, marginTop: 12 }}>Cargando mapa...</p>
                </div>
            }>
                <HeatmapSection
                    dateFrom={dateFromStr}
                    dateTo={dateToStr}
                    clientId={selectedClient}
                    providerId={selectedProvider}
                />
            </Suspense>
        </div>
    );
};

export default Dashboard;
