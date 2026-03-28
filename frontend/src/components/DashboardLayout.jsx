import React, { useState, useEffect, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { 
    LayoutDashboard, 
    Truck, 
    Upload, 
    Settings, 
    LogOut,
    Bell,
    User,
    ChevronDown,
    Code,
    FileText,
    Activity,
    ScrollText,
    Bug,
    ShieldCheck,
    ClipboardCheck,
    Cpu,
} from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Button } from '../components/ui/button';

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard, roles: ['agent', 'coordinator', 'executive', 'developer'] },
    { path: '/journeys', label: 'Rutas', icon: Truck, roles: ['agent', 'coordinator', 'executive', 'developer'] },
    { path: '/layout', label: 'Layout', icon: Upload, roles: ['agent', 'coordinator', 'developer'] },
    { path: '/reports', label: 'Reportes', icon: FileText, roles: ['coordinator', 'executive', 'developer'] },
    { path: '/documentation', label: 'API & Reportes', icon: Code, roles: ['coordinator', 'executive', 'developer'] },
    { path: '/settings', label: 'Configuración', icon: Settings, roles: ['coordinator', 'developer'] },
    { path: '/quality-criteria', label: 'Criterios Calidad', icon: ClipboardCheck, roles: ['coordinator', 'developer'] },
    { path: '/admin', label: 'Admin IA', icon: Cpu, roles: ['developer', 'executive', 'ejecutivo', 'coordinator'] },
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

    const showSystemSection = hasRole(['coordinator', 'developer']);

    const fetchErrorCount = useCallback(async () => {
        if (!showSystemSection) return;
        try {
            const res = await api.get('/system/errors/count');
            setErrorCount(res.data.count || 0);
        } catch {
            // Silently fail
        }
    }, [showSystemSection]);

    useEffect(() => {
        fetchErrorCount();
        const interval = setInterval(fetchErrorCount, 60000);
        return () => clearInterval(interval);
    }, [fetchErrorCount]);

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    const filteredNavItems = navItems.filter(item => hasRole(item.roles));

    const getRoleLabel = (role) => {
        const labels = {
            agent: 'Agente',
            coordinator: 'Coordinador',
            executive: 'Ejecutivo',
            developer: 'Developer',
        };
        return labels[role] || role;
    };

    const isActive = (path) => location.pathname === path || 
        (path !== '/' && location.pathname.startsWith(path));

    const currentLabel = (() => {
        const sysItem = systemNavItems.find(i => isActive(i.path));
        if (sysItem) return `Sistema / ${sysItem.label}`;
        return filteredNavItems.find(i => isActive(i.path))?.label || 'Dashboard';
    })();

    return (
        <div className="min-h-screen bg-[#F8FAFC] flex">
            {/* Sidebar */}
            <aside className="fixed left-0 top-0 h-full w-64 bg-white border-r border-slate-200 z-30">
                <div className="flex flex-col h-full">
                    {/* Logo */}
                    <div className="h-16 flex items-center px-6 border-b border-slate-200">
                        <Link to="/" className="flex items-center gap-2">
                            <div className="w-8 h-8 bg-slate-900 rounded-sm flex items-center justify-center">
                                <Truck className="w-5 h-5 text-white" strokeWidth={1.5} />
                            </div>
                            <div>
                                <span className="font-heading font-bold text-lg text-slate-900 tracking-tight">
                                    LASTMILE
                                </span>
                                <span className="font-heading text-xs text-slate-500 block -mt-1">OS</span>
                            </div>
                        </Link>
                    </div>

                    {/* Navigation */}
                    <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
                        {filteredNavItems.map((item) => {
                            const Icon = item.icon;
                            const active = isActive(item.path);
                            
                            return (
                                <Link
                                    key={item.path}
                                    to={item.path}
                                    data-testid={`nav-${item.path.replace('/', '') || 'dashboard'}`}
                                    className={`sidebar-link ${active ? 'active' : 'text-slate-600'}`}
                                >
                                    <Icon className="w-5 h-5" strokeWidth={1.5} />
                                    <span>{item.label}</span>
                                </Link>
                            );
                        })}

                        {/* System Section */}
                        {showSystemSection && (
                            <>
                                <div className="pt-4 pb-2">
                                    <p className="px-3 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                                        Sistema
                                    </p>
                                </div>
                                {systemNavItems.map((item) => {
                                    const Icon = item.icon;
                                    const active = isActive(item.path);
                                    const showBadge = item.path === '/system/errors' && errorCount > 0;
                                    
                                    return (
                                        <Link
                                            key={item.path}
                                            to={item.path}
                                            data-testid={`nav-system-${item.label.toLowerCase()}`}
                                            className={`sidebar-link ${active ? 'active' : 'text-slate-600'}`}
                                        >
                                            <Icon className="w-5 h-5" strokeWidth={1.5} />
                                            <span>{item.label}</span>
                                            {showBadge && (
                                                <span className="ml-auto px-1.5 py-0.5 text-[10px] font-bold bg-red-500 text-white rounded-full" data-testid="error-badge-count">
                                                    {errorCount}
                                                </span>
                                            )}
                                        </Link>
                                    );
                                })}
                            </>
                        )}
                    </nav>

                    {/* User section */}
                    <div className="p-4 border-t border-slate-200">
                        <div className="flex items-center gap-3 px-2 py-2">
                            <div className="w-9 h-9 bg-slate-200 rounded-full flex items-center justify-center">
                                <User className="w-5 h-5 text-slate-600" strokeWidth={1.5} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-slate-900 truncate">
                                    {user?.name}
                                </p>
                                <p className="text-xs text-slate-500">
                                    {getRoleLabel(user?.role)}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </aside>

            {/* Main content */}
            <div className="flex-1 ml-64">
                {/* Top header */}
                <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-6 sticky top-0 z-20">
                    <div className="flex items-center gap-4">
                        <h1 className="font-heading font-semibold text-xl text-slate-800">
                            {currentLabel}
                        </h1>
                    </div>

                    <div className="flex items-center gap-3">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="relative"
                            data-testid="notifications-btn"
                        >
                            <Bell className="w-5 h-5 text-slate-600" strokeWidth={1.5} />
                        </Button>

                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button 
                                    variant="ghost" 
                                    className="flex items-center gap-2"
                                    data-testid="user-menu-btn"
                                >
                                    <div className="w-8 h-8 bg-slate-900 rounded-full flex items-center justify-center">
                                        <span className="text-white text-sm font-medium">
                                            {user?.name?.charAt(0).toUpperCase()}
                                        </span>
                                    </div>
                                    <ChevronDown className="w-4 h-4 text-slate-500" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-48">
                                <div className="px-2 py-1.5">
                                    <p className="text-sm font-medium">{user?.name}</p>
                                    <p className="text-xs text-slate-500">{user?.email}</p>
                                </div>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem 
                                    onClick={handleLogout}
                                    className="text-red-600 cursor-pointer"
                                    data-testid="logout-btn"
                                >
                                    <LogOut className="w-4 h-4 mr-2" />
                                    Cerrar sesión
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    </div>
                </header>

                {/* Page content */}
                <main className="p-6">
                    <div className="max-w-7xl mx-auto animate-fade-in">
                        {children}
                    </div>
                </main>
            </div>
        </div>
    );
};

export default DashboardLayout;
