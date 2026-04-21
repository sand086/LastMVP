import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { 
    LayoutDashboard, Truck, Upload, Settings, LogOut, Bell, User,
    ChevronDown, Code, FileText, Activity, ScrollText, Bug,
    ShieldCheck, ClipboardCheck, Cpu, BookOpen, Radar,
    PanelLeftClose, PanelLeftOpen, Menu, X,
} from 'lucide-react';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem,
    DropdownMenuSeparator, DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Button } from '../components/ui/button';

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard, roles: ['agent', 'coordinator', 'executive', 'developer', 'proveedor'] },
    { path: '/journeys', label: 'Rutas', icon: Truck, roles: ['agent', 'coordinator', 'executive', 'developer', 'proveedor'] },
    { path: '/layout', label: 'Layout', icon: Upload, roles: ['agent', 'coordinator', 'developer'] },
    { path: '/reports', label: 'Reportes', icon: FileText, roles: ['coordinator', 'executive', 'developer'] },
    { path: '/documentation', label: 'API & Reportes', icon: Code, roles: ['coordinator', 'executive', 'developer'] },
    { path: '/settings', label: 'Configuracion', icon: Settings, roles: ['coordinator', 'developer'] },
    { path: '/quality-criteria', label: 'Criterios Calidad', icon: ClipboardCheck, roles: ['coordinator', 'developer'] },
    { path: '/admin', label: 'Admin IA', icon: Cpu, roles: ['developer', 'executive', 'ejecutivo', 'coordinator'] },
    { path: '/monitor', label: 'Monitor IA', icon: Radar, roles: ['coordinator', 'developer'] },
    { path: '/manuales', label: 'Manuales', icon: BookOpen, roles: ['agent', 'coordinator', 'executive', 'developer', 'proveedor'] },
];

const systemNavItems = [
    { path: '/system/health', label: 'Health', icon: Activity },
    { path: '/system/logs', label: 'Logs', icon: ScrollText },
    { path: '/system/errors', label: 'Errores', icon: Bug },
    { path: '/system/integrity', label: 'Integridad', icon: ShieldCheck },
];

export const DashboardLayout = ({ children }) => {
    const { user, logout, hasRole } = useAuth();
    const location = useLocation();
    const navigate = useNavigate();
    const [errorCount, setErrorCount] = useState(0);
    const [collapsed, setCollapsed] = useState(() => {
        try { return localStorage.getItem('sidebar_collapsed') === 'true'; } catch { return false; }
    });
    const [mobileOpen, setMobileOpen] = useState(false);

    const showSystemSection = hasRole(['coordinator', 'developer']);

    // Close mobile drawer on route change
    useEffect(() => { setMobileOpen(false); }, [location.pathname]);

    const toggleSidebar = () => {
        setCollapsed(prev => {
            const next = !prev;
            try { localStorage.setItem('sidebar_collapsed', String(next)); } catch (err) { console.error('Sidebar state save error:', err); }
            return next;
        });
    };

    const fetchErrorCount = useCallback(async () => {
        if (!showSystemSection) return;
        try {
            const res = await api.get('/system/errors/count');
            setErrorCount(res.data.count || 0);
        } catch (err) { console.error("DashboardLayout fetch error:", err); }
    }, [showSystemSection]);

    useEffect(() => {
        fetchErrorCount();
        const interval = setInterval(fetchErrorCount, 60000);
        return () => clearInterval(interval);
    }, [fetchErrorCount]);

    const handleLogout = async () => { await logout(); navigate('/login'); };
    const filteredNavItems = navItems.filter(item => hasRole(item.roles));
    const getRoleLabel = (role) => ({ agent: 'Agente', coordinator: 'Coordinador', executive: 'Ejecutivo', developer: 'Developer', proveedor: 'Proveedor' }[role] || role);
    const isActive = (path) => location.pathname === path || (path !== '/' && location.pathname.startsWith(path));

    const currentLabel = (() => {
        const sysItem = systemNavItems.find(i => isActive(i.path));
        if (sysItem) return `Sistema / ${sysItem.label}`;
        return filteredNavItems.find(i => isActive(i.path))?.label || 'Dashboard';
    })();

    // Shared sidebar content
    const SidebarContent = ({ isMobile }) => {
        const showLabels = isMobile || !collapsed;
        return (
            <div className="flex flex-col h-full">
                {/* Logo */}
                <div className="h-14 sm:h-16 flex items-center justify-between px-3 sm:px-4 border-b border-slate-200">
                    <Link to="/" className="flex items-center gap-2 overflow-hidden">
                        <div className="w-8 h-8 bg-slate-900 rounded-sm flex items-center justify-center flex-shrink-0">
                            <Truck className="w-5 h-5 text-white" strokeWidth={1.5} />
                        </div>
                        {showLabels && (
                            <div className="whitespace-nowrap">
                                <span className="font-heading font-bold text-lg text-slate-900 tracking-tight">LASTMILE</span>
                                <span className="font-heading text-xs text-slate-500 block -mt-1">OS</span>
                            </div>
                        )}
                    </Link>
                    {isMobile ? (
                        <button onClick={() => setMobileOpen(false)} className="w-8 h-8 flex items-center justify-center rounded hover:bg-slate-100 text-slate-500" data-testid="close-mobile-sidebar"><X className="w-5 h-5" /></button>
                    ) : (
                        <button onClick={toggleSidebar} className="w-7 h-7 hidden sm:flex items-center justify-center rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors flex-shrink-0" data-testid="toggle-sidebar-btn" title={collapsed ? 'Expandir menu' : 'Contraer menu'}>
                            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
                        </button>
                    )}
                </div>

                {/* Nav */}
                <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
                    {filteredNavItems.map((item) => {
                        const Icon = item.icon;
                        const active = isActive(item.path);
                        return (
                            <Link key={item.path} to={item.path} data-testid={`nav-${item.path.replace('/', '') || 'dashboard'}`} title={!showLabels ? item.label : undefined}
                                className={`flex items-center gap-3 rounded-md transition-colors ${!showLabels ? 'justify-center px-2 py-2.5' : 'px-3 py-2'} ${active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
                                <Icon className="w-5 h-5 flex-shrink-0" strokeWidth={1.5} />
                                {showLabels && <span className="text-sm whitespace-nowrap">{item.label}</span>}
                            </Link>
                        );
                    })}

                    {showSystemSection && (
                        <>
                            <div className={`pt-4 pb-1 ${!showLabels ? 'text-center' : ''}`}>
                                {showLabels ? <p className="px-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Sistema</p> : <div className="w-6 h-px bg-slate-200 mx-auto" />}
                            </div>
                            {systemNavItems.map((item) => {
                                const Icon = item.icon;
                                const active = isActive(item.path);
                                const showBadge = item.path === '/system/errors' && errorCount > 0;
                                return (
                                    <Link key={item.path} to={item.path} data-testid={`nav-system-${item.label.toLowerCase()}`} title={!showLabels ? item.label : undefined}
                                        className={`flex items-center gap-3 rounded-md transition-colors relative ${!showLabels ? 'justify-center px-2 py-2.5' : 'px-3 py-2'} ${active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
                                        <Icon className="w-5 h-5 flex-shrink-0" strokeWidth={1.5} />
                                        {showLabels && <span className="text-sm whitespace-nowrap">{item.label}</span>}
                                        {showBadge && <span className={`px-1.5 py-0.5 text-[10px] font-bold bg-red-500 text-white rounded-full ${!showLabels ? 'absolute -top-0.5 -right-0.5 min-w-[18px] text-center' : 'ml-auto'}`} data-testid="error-badge-count">{errorCount}</span>}
                                    </Link>
                                );
                            })}
                        </>
                    )}
                </nav>

                {/* User */}
                <div className="p-3 border-t border-slate-200">
                    <div className={`flex items-center gap-3 ${!showLabels ? 'justify-center px-0 py-1' : 'px-2 py-2'}`}>
                        <div className="w-9 h-9 bg-slate-200 rounded-full flex items-center justify-center flex-shrink-0">
                            <User className="w-5 h-5 text-slate-600" strokeWidth={1.5} />
                        </div>
                        {showLabels && (
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-slate-900 truncate">{user?.name}</p>
                                <p className="text-xs text-slate-500">{getRoleLabel(user?.role)}</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    const sidebarW = collapsed ? 'w-[68px]' : 'w-64';
    const mainMl = collapsed ? 'sm:ml-[68px]' : 'sm:ml-64';

    return (
        <div className="min-h-screen bg-[#F8FAFC] flex">
            {/* Desktop sidebar */}
            <aside className={`fixed left-0 top-0 h-full ${sidebarW} bg-white border-r border-slate-200 z-30 transition-all duration-200 ease-in-out hidden sm:block`} data-testid="sidebar">
                <SidebarContent isMobile={false} />
            </aside>

            {/* Mobile overlay + drawer */}
            {mobileOpen && (
                <div className="fixed inset-0 z-40 sm:hidden" data-testid="mobile-sidebar-overlay">
                    <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
                    <aside className="absolute left-0 top-0 h-full w-72 bg-white shadow-xl animate-slide-in-left z-50">
                        <SidebarContent isMobile={true} />
                    </aside>
                </div>
            )}

            {/* Main content */}
            <div className={`flex-1 ${mainMl} transition-all duration-200 ease-in-out`}>
                {/* Top header */}
                <header className="h-14 sm:h-16 bg-white border-b border-slate-200 flex items-center justify-between px-4 sm:px-6 sticky top-0 z-20">
                    <div className="flex items-center gap-3">
                        {/* Hamburger for mobile */}
                        <button className="sm:hidden w-9 h-9 flex items-center justify-center rounded-md hover:bg-slate-100" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-btn">
                            <Menu className="w-5 h-5 text-slate-700" />
                        </button>
                        <h1 className="font-heading font-semibold text-lg sm:text-xl text-slate-800 truncate">{currentLabel}</h1>
                    </div>
                    <div className="flex items-center gap-2 sm:gap-3">
                        <Button variant="ghost" size="icon" className="relative" data-testid="notifications-btn">
                            <Bell className="w-5 h-5 text-slate-600" strokeWidth={1.5} />
                        </Button>
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="ghost" className="flex items-center gap-1 sm:gap-2 px-2" data-testid="user-menu-btn">
                                    <div className="w-8 h-8 bg-slate-900 rounded-full flex items-center justify-center">
                                        <span className="text-white text-sm font-medium">{user?.name?.charAt(0).toUpperCase()}</span>
                                    </div>
                                    <ChevronDown className="w-4 h-4 text-slate-500 hidden sm:block" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48">
                                <div className="px-2 py-1.5">
                                    <p className="text-sm font-medium">{user?.name}</p>
                                    <p className="text-xs text-slate-500">{user?.email}</p>
                                </div>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={handleLogout} className="text-red-600 cursor-pointer" data-testid="logout-btn">
                                    <LogOut className="w-4 h-4 mr-2" />Cerrar sesion
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                </header>

                {/* Page content */}
                <main className="p-4 sm:p-6">
                    <div className="max-w-7xl mx-auto animate-fade-in">{children}</div>
                </main>
            </div>

            {/* Mobile slide-in animation */}
            <style>{`
                @keyframes slideInLeft { from { transform: translateX(-100%); } to { transform: translateX(0); } }
                .animate-slide-in-left { animation: slideInLeft 0.2s ease-out; }
            `}</style>
        </div>
    );
};

export default DashboardLayout;
