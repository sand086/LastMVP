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
export const updateUserAssignments = (id, data) => api.put(`/users/${id}/assignments`, data);
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
export const resolveAllIncidents = (journeyId) => api.put(`/incidents/journey/${journeyId}/resolve-all`);

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

// Journey images (multiple files)
export const uploadJourneyImages = (files, journeyId, section, incidentId = null) => {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('journey_id', journeyId);
    formData.append('section', section);
    if (incidentId) formData.append('incident_id', incidentId);
    return api.post('/upload/journey-images', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
};

export const getJourneyImages = (journeyId, section = null, incidentId = null) => {
    const params = {};
    if (section) params.section = section;
    if (incidentId) params.incident_id = incidentId;
    return api.get(`/journey-images/${journeyId}`, { params });
};

export const deleteJourneyImage = (imageId) => api.delete(`/journey-images/${imageId}`);

export const downloadTemplate = () => api.get('/template/layout', { responseType: 'blob' });

// Retry packages
export const getRetryPackages = (providerId) => api.get(`/retry-packages/${providerId}`);

// Dashboard
export const getDashboardStats = (dateFrom, dateTo) => api.get('/dashboard/stats', { params: { date_from: dateFrom, date_to: dateTo } });
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

// Reports API (for Power BI, etc.)
export const getReportJourneys = (params) => api.get('/reports/journeys', { params });
export const getReportPackages = (params) => api.get('/reports/packages', { params });
export const getReportIncidents = (params) => api.get('/reports/incidents', { params });
export const getReportKpis = (params) => api.get('/reports/kpis', { params });
export const getReportSchema = () => api.get('/reports/schema');

// Custom Reports
export const generateReport = (data) => api.post('/reports/generate', data);
export const generateReportExcel = (data) => api.post('/reports/generate-excel', data, { responseType: 'blob' });

// Kosmo Sync
export const syncKosmoTracking = () => api.post('/sync/tracking');
export const getKosmoSyncStatus = () => api.get('/sync/status');

// Quality Reports
export const getQualityReport = (params) => api.get('/reports/quality', { params });
export const exportQualityReport = (data) => api.post('/reports/quality-export', data, { responseType: 'blob' });
export const evaluateJourneyQuality = (journeyId) => api.post(`/reports/evaluate-journey/${journeyId}`);

// AI Evidence Evaluation
export const evaluatePackageEvidence = (journeyId, guide) => api.post(`/journeys/${journeyId}/packages/${encodeURIComponent(guide)}/evaluate-evidence`);
export const evaluateAllEvidence = (journeyId) => api.post(`/journeys/${journeyId}/evaluate-evidence-all`);

// Package Search
export const searchPackages = (q) => api.get('/packages/search', { params: { q } });

// Package Review
export const reviewPackage = (packageId) => api.put(`/packages/${packageId}/review`);

// CRUD Clients & Providers
export const updateClient = (id, data) => api.put(`/clients/${id}`, data);
export const deleteClient = (id) => api.delete(`/clients/${id}`);
export const updateProvider = (id, data) => api.put(`/providers/${id}`, data);
export const deleteProvider = (id) => api.delete(`/providers/${id}`);

// Cleanup
export const cleanupRoutesPackages = () => api.post('/cleanup/routes-packages');

// Analytics / Heatmap
export const getHeatmapData = (params) => api.get('/analytics/heatmap', { params });
export const exportHeatmap = (params) => api.post('/analytics/heatmap-export', null, { params, responseType: 'blob' });

// System Sync Schedule
export const getSyncSchedule = () => api.get('/system/sync-schedule');

// Token Consumption
export const getTokenConsumption = () => api.get('/system/token-consumption');
export const updateExchangeRate = (rate) => api.put(`/system/exchange-rate?rate=${rate}`);

// Bulk package status update
export const bulkUpdatePackageStatus = (journeyId, packageIds, newStatus) =>
    api.post(`/journeys/${journeyId}/packages/bulk-status`, { package_ids: packageIds, new_status: newStatus });

// Quality Criteria
export const getQualityCriteria = () => api.get('/quality/criteria');
export const updateQualityCriteria = (data) => api.put('/quality/criteria', data);
export const resetQualityCriteria = () => api.post('/quality/criteria/reset');

// Package rescrape
export const rescrapePackage = (packageId) => api.post(`/packages/${packageId}/rescrape`);

export default api;
