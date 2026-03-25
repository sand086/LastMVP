import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Toaster } from './components/ui/sonner';
import DashboardLayout from './components/DashboardLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Journeys from './pages/Journeys';
import JourneyDetail from './pages/JourneyDetail';
import Layout from './pages/Layout';
import Settings from './pages/Settings';
import ApiDocumentation from './pages/ApiDocumentation';
import Reports from './pages/Reports';
import SystemHealth from './pages/SystemHealth';
import SystemLogs from './pages/SystemLogs';
import SystemErrors from './pages/SystemErrors';
import SystemIntegrity from './pages/SystemIntegrity';
import './App.css';

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
        return <Navigate to="/" replace />;
    }

    return <DashboardLayout>{children}</DashboardLayout>;
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
                    <ProtectedRoute allowedRoles={['agent', 'coordinator']}>
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
                path="/api-docs" 
                element={
                    <ProtectedRoute allowedRoles={['coordinator', 'executive']}>
                        <ApiDocumentation />
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

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <AppRoutes />
                <Toaster 
                    position="top-right"
                    richColors
                    closeButton
                />
            </AuthProvider>
        </BrowserRouter>
    );
}

export default App;
