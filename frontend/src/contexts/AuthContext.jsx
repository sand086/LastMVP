import React, { createContext, useContext, useState, useEffect } from 'react';
import { login as apiLogin, logout as apiLogout, getMe } from '../lib/api';

const AuthContext = createContext(null);

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Verify session via httpOnly cookie (no token in localStorage)
        getMe()
            .then((res) => {
                setUser(res.data);
                localStorage.setItem('user', JSON.stringify(res.data));
            })
            .catch(() => {
                localStorage.removeItem('user');
                setUser(null);
            })
            .finally(() => setLoading(false));
    }, []);

    const login = async (email, password) => {
        try {
            setError(null);
            const response = await apiLogin(email, password);
            const { user: userData } = response.data;
            
            localStorage.setItem('user', JSON.stringify(userData));
            setUser(userData);
            
            return { success: true };
        } catch (err) {
            const message = err.response?.data?.detail || 'Error al iniciar sesión';
            setError(message);
            return { success: false, error: message };
        }
    };

    const logout = async () => {
        try {
            await apiLogout();
        } catch (err) {
            // Ignore errors on logout
        } finally {
            localStorage.removeItem('user');
            setUser(null);
        }
    };

    const hasRole = (roles) => {
        if (!user) return false;
        if (typeof roles === 'string') return user.role === roles;
        return roles.includes(user.role);
    };

    const canEdit = () => hasRole(['agent', 'coordinator', 'developer']);
    const isCoordinator = () => hasRole(['coordinator', 'developer']);
    const isExecutive = () => hasRole('executive');
    const isProvider = () => hasRole('proveedor');

    const value = {
        user,
        loading,
        error,
        login,
        logout,
        hasRole,
        canEdit,
        isCoordinator,
        isExecutive,
        isProvider,
        isAuthenticated: !!user,
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export default AuthContext;
