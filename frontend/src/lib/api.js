import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api';

// Create axios instance
const api = axios.create({
    baseURL: API_BASE,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle 401 errors
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

// Auth
export const login = (email, password) => api.post('/auth/login', { email, password });
export const logout = () => api.post('/auth/logout');
export const getMe = () => api.get('/auth/me');
export const requestPasswordReset = (email) => api.post('/auth/request-password-reset', { email });

// Users
export const getUsers = () => api.get('/users');
export const createUser = (data) => api.post('/users', data);
export const updateUser = (id, data) => api.put(`/users/${id}`, data);
export const deleteUser = (id) => api.delete(`/users/${id}`);
export const changePasswordByAdmin = (userId, newPassword) => api.post('/users/change-password', { user_id: userId, new_password: newPassword });

// Password Reset Requests
export const getPasswordResetRequests = () => api.get('/password-reset-requests');
export const dismissPasswordResetRequest = (id) => api.delete(`/password-reset-requests/${id}`);

// Clients
export const getClients = () => api.get('/clients');
export const createClient = (data) => api.post('/clients', data);

// Providers
export const getProviders = () => api.get('/providers');
export const createProvider = (data) => api.post('/providers', data);

// Journeys
export const getJourneys = (params) => api.get('/journeys', { params });
export const getJourney = (id) => api.get(`/journeys/${id}`);
export const createJourney = (data) => api.post('/journeys', data);
export const startJourney = (id, data) => api.put(`/journeys/${id}/start`, data);
export const closeJourney = (id, data) => api.put(`/journeys/${id}/close`, data);

// Incidents
export const getIncidents = (params) => api.get('/incidents', { params });
export const createIncident = (data) => api.post('/incidents', data);
export const updateIncident = (id, data) => api.put(`/incidents/${id}`, data);
export const deleteIncident = (id) => api.delete(`/incidents/${id}`);

// File uploads
export const uploadLayout = (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/upload/layout', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
};

export const uploadHistoryOrders = (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/upload/history-orders', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
};

export const uploadRouteSummary = (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/upload/route-summary', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
};

export const createJourneysFromCosmo = (data) => api.post('/journeys/from-cosmo', data);

// Messenger-Provider mappings
export const getMessengerMappings = () => api.get('/messenger-mappings');
export const saveMessengerMappings = (mappings) => api.post('/messenger-mappings', mappings);
export const deleteMessengerMapping = (messengerName) => api.delete(`/messenger-mappings/${encodeURIComponent(messengerName)}`);

export const uploadPhoto = (file, journeyId, photoType) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('journey_id', journeyId);
    formData.append('photo_type', photoType);
    return api.post('/upload/photo', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
};

export const downloadTemplate = () => api.get('/template/layout', { responseType: 'blob' });

// Retry packages
export const getRetryPackages = (providerId) => api.get(`/retry-packages/${providerId}`);

// Dashboard
export const getDashboardStats = (date) => api.get('/dashboard/stats', { params: { date } });
export const getIncidentsBreakdown = (dateFrom, dateTo) => api.get('/dashboard/incidents-breakdown', { params: { date_from: dateFrom, date_to: dateTo } });
export const getProviderComparison = (dateFrom, dateTo) => api.get('/dashboard/provider-comparison', { params: { date_from: dateFrom, date_to: dateTo } });

// Upload history
export const getUploadHistory = () => api.get('/upload-history');
export const createUploadHistory = (data) => api.post('/upload-history', data);

// Export
export const exportJourneys = (params) => api.get('/export/journeys', { params, responseType: 'blob' });
export const exportIncidents = (params) => api.get('/export/incidents', { params, responseType: 'blob' });

// Seed
export const seedDatabase = () => api.post('/seed');

export default api;
