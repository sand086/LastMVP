import React, { useEffect, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Toaster } from './components/ui/sonner';
import { toast } from 'sonner';
import DashboardLayout from './components/DashboardLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Journeys from './pages/Journeys';
// Lazy-loaded routes (code-split for faster initial bundle)
const JourneyDetail = lazy(() => import('./pages/JourneyDetail'));
const Layout = lazy(() => import('./pages/Layout'));
const Settings = lazy(() => import('./pages/Settings'));
const ApiDocumentation = lazy(() => import('./pages/ApiDocumentation'));
const Reports = lazy(() => import('./pages/Reports'));
const SystemHealth = lazy(() => import('./pages/SystemHealth'));
const SystemLogs = lazy(() => import('./pages/SystemLogs'));
const SystemErrors = lazy(() => import('./pages/SystemErrors'));
const SystemIntegrity = lazy(() => import('./pages/SystemIntegrity'));
const QualityCriteria = lazy(() => import('./pages/QualityCriteria'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const Manuals = lazy(() => import('./pages/Manuals'));
const ManualViewer = lazy(() => import('./pages/ManualViewer'));
const MonitorProcesos = lazy(() => import('./pages/MonitorProcesos'));
import LumiChat from './components/LumiChat';
import './App.css';

// Fallback UI while lazy chunks load
const PageLoader = () => (
    <div className="flex items-center justify-center py-24" data-testid="page-loader">
        <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-900 rounded-full animate-spin" />
    </div>
);

// Protected route wrapper
const ProtectedRoute = ({ children, allowedRoles }) => {
    const { isAuthenticated, loading, hasRole } = useAuth();

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC]">
                <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-900 rounded-full animate-spin" />
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    if (allowedRoles && !hasRole(allowedRoles)) {
        return <NoPermissionRedirect />;
    }

    return <DashboardLayout>{children}</DashboardLayout>;
};

// Separate component to show toast on redirect
const NoPermissionRedirect = () => {
    useEffect(() => {
        toast.info('Sin permisos — No tienes acceso a esta sección');
    }, []);
    return <Navigate to="/" replace />;
};

// Public route - redirect to dashboard if authenticated
const PublicRoute = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC]">
                <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-900 rounded-full animate-spin" />
            </div>
        );
    }

    if (isAuthenticated) {
        return <Navigate to="/" replace />;
    }

    return children;
};

function AppRoutes() {
    return (
        <Suspense fallback={<PageLoader />}>
            <Routes>
            {/* Public routes */}
            <Route 
                path="/login" 
                element={
                    <PublicRoute>
                        <Login />
                    </PublicRoute>
                } 
            />

            {/* Protected routes */}
            <Route 
                path="/" 
                element={
                    <ProtectedRoute>
                        <Dashboard />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/journeys" 
                element={
                    <ProtectedRoute>
                        <Journeys />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/journeys/:id" 
                element={
                    <ProtectedRoute>
                        <JourneyDetail />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/layout" 
                element={
                    <ProtectedRoute allowedRoles={['agent', 'coordinator', 'developer']}>
                        <Layout />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/settings" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <Settings />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/documentation" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'executive', 'developer']}>
                        <ApiDocumentation />
                    </ProtectedRoute>
                } 
            />
            <Route path="/api-docs" element={<Navigate to="/documentation" replace />} />

            <Route 
                path="/admin" 
                element={
                    <ProtectedRoute allowedRoles={['developer', 'executive', 'ejecutivo', 'coordinator']}>
                        <AdminPage />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/reports" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'executive', 'developer']}>
                        <Reports />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/system/health" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <SystemHealth />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/system/logs" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <SystemLogs />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/system/errors" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <SystemErrors />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/system/integrity" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <SystemIntegrity />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/quality-criteria" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <QualityCriteria />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/manuales" 
                element={
                    <ProtectedRoute>
                        <Manuals />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/manuales/:slug" 
                element={
                    <ProtectedRoute>
                        <ManualViewer />
                    </ProtectedRoute>
                } 
            />

            <Route 
                path="/monitor" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'developer']}>
                        <MonitorProcesos />
                    </ProtectedRoute>
                } 
            />

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </Suspense>
    );
}

function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <AppRoutes />
                <LumiChatWrapper />
                <Toaster 
                    position="top-right"
                    richColors
                    closeButton
                />
            </AuthProvider>
        </BrowserRouter>
    );
}

function LumiChatWrapper() {
    const { isAuthenticated } = useAuth();
    const location = useLocation();
    if (!isAuthenticated) return null;
    // Detect journeyId from URL pattern /journeys/:id
    const match = location.pathname.match(/^\/journeys\/([a-f0-9-]{36})$/);
    const journeyId = match ? match[1] : null;
    return <LumiChat journeyId={journeyId} />;
}

export default App;
