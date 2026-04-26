import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api';

// Create axios instance with httpOnly cookie support
const api = axios.create({
    baseURL: API_BASE,
    headers: {
        'Content-Type': 'application/json',
    },
    withCredentials: true,
});

// Handle 401 errors — auto-logout with redirect reason
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            const currentPath = window.location.pathname;
            if (currentPath !== '/login') {
                console.warn('[Auth] Sesión expirada — redirigiendo a login');
                localStorage.removeItem('user');
                window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}&reason=expired`;
                return new Promise(() => {});
            }
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
export const deleteJourney = (id) => api.delete(`/journeys/${id}`);
export const changeJourneyProvider = (id, data) => api.patch(`/journeys/${id}/provider`, data);

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
export const reviewPackageWithNote = (packageId, data) => api.patch(`/packages/${packageId}/review`, data);

// CRUD Clients & Providers
export const updateClient = (id, data) => api.put(`/clients/${id}`, data);
export const deleteClient = (id) => api.delete(`/clients/${id}`);
export const updateProvider = (id, data) => api.put(`/providers/${id}`, data);
export const deleteProvider = (id) => api.delete(`/providers/${id}`);

// Cleanup
export const cleanupRoutesPackages = (params) => api.post('/cleanup/routes-packages', params || {});
export const cleanupRoutesPackagesPreview = (params) => api.get('/cleanup/routes-packages/preview', { params });

// Analytics / Heatmap
export const getHeatmapData = (params) => api.get('/analytics/heatmap', { params });
export const exportHeatmap = (params) => api.post('/analytics/heatmap-export', null, { params, responseType: 'blob' });
export const getReportsHeatmap = (params) => api.get('/reports/heatmap', { params });

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
export const batchRescrapeJourney = (journeyId) => api.post(`/journeys/${journeyId}/batch-rescrape`);

// Reports v2
export const getReportAttempts = (params) => api.get('/reports/attempts', { params });
export const getReportSla = (params) => api.get('/reports/sla', { params });
export const updateSlaTargets = (brackets) => api.patch('/config/sla-targets', { brackets });
export const generateAiReport = (data) => api.post('/reports/generate-ai', data);

// Lumi Chat
export const sendLumiMessage = (data) => api.post('/chat/lumi', data);

// Quality Settings v2 (master endpoints)
export const getQualitySettings = () => api.get('/config/quality-settings');
export const patchQualitySettings = (section, value) => api.patch('/config/quality-settings', { section, value });

// Quality Tab v2
export const getQualitySummary = (journeyId) => api.get(`/journeys/${journeyId}/quality-summary`);
export const getPackagesQuality = (journeyId, params) => api.get(`/journeys/${journeyId}/packages-quality`, { params });
export const saveTrainingSample = (data) => api.post('/training/samples', data);
export const updatePackageReview = (journeyId, guide, data) => api.patch(`/journeys/${journeyId}/packages/${encodeURIComponent(guide)}/review`, data);

// Discrepancy Detection
export const evaluateConfidence = (journeyId) => api.post(`/journeys/${journeyId}/guides/evaluate-confidence`);
export const reviewDiscrepancy = (journeyId, guideId, data) => api.patch(`/journeys/${journeyId}/guides/${encodeURIComponent(guideId)}/review`, data);

// AI Evaluation Status Polling
export const getAiEvalStatus = (journeyId) => api.get(`/journeys/${journeyId}/ai-eval-status`);

export default api;

// Webhooks
export const getWebhookEvents = () => api.get('/webhooks/events');
export const getWebhooks = () => api.get('/webhooks');
export const createWebhook = (data) => api.post('/webhooks', data);
export const updateWebhook = (id, data) => api.put(`/webhooks/${id}`, data);
export const deleteWebhook = (id) => api.delete(`/webhooks/${id}`);
export const testWebhook = (id) => api.post(`/webhooks/${id}/test`);
export const getWebhookDeliveries = (id) => api.get(`/webhooks/${id}/deliveries`);
export const regenerateWebhookSecret = (id) => api.post(`/webhooks/${id}/regenerate-secret`);


// Drivers
export const getDrivers = (params) => api.get('/drivers', { params });
export const getDriver = (id) => api.get(`/drivers/${id}`);
export const updateDriver = (id, data) => api.patch(`/drivers/${id}`, data);
export const populateDrivers = () => api.post('/drivers/populate');
export const getVehicleTypes = () => api.get('/drivers/vehicle-types');
export const createProviderInline = (data) => api.post('/providers/inline', data);
export const updateDeliveryNotes = (file) => { const fd = new FormData(); fd.append('file', file); return api.post('/upload/update-notes', fd, { headers: { 'Content-Type': 'multipart/form-data' } }); };


// Manuals (Knowledge Hub)
export const getManuals = (params) => api.get('/manuals', { params });
export const getManualBySlug = (slug) => api.get(`/manuals/${slug}`);
export const getManualsAdmin = () => api.get('/manuals-admin');
export const getManualAdmin = (id) => api.get(`/manuals-admin/${id}`);
export const createManual = (data) => api.post('/manuals-admin', data);
export const updateManual = (id, data) => api.patch(`/manuals-admin/${id}`, data);
export const updateManualContent = (id, data) => api.put(`/manuals-admin/${id}/content`, data);
export const deleteManual = (id) => api.delete(`/manuals-admin/${id}`);
export const seedManuals = () => api.post('/manuals-admin/seed');


// AI Evaluation Jobs (Monitor de Procesos)
export const getAiEvalJobs = (params) => api.get('/ai-evaluation/jobs', { params });
export const getAiEvalJob = (jobId) => api.get(`/ai-evaluation/jobs/${jobId}`);
export const createAiEvalJobManual = (data) => api.post('/ai-evaluation/jobs/manual', data);
export const createAiEvalJobGuia = (data) => api.post('/ai-evaluation/jobs/manual/guia', data);
export const cancelAiEvalJob = (jobId) => api.delete(`/ai-evaluation/jobs/${jobId}`);
export const retryAiEvalErrors = (data) => api.post('/ai-evaluation/jobs/retry-errors', data || {});


// ── Architecture (live auto-generated documentation) ──────────────
export const getArchitectureSnapshot = () => api.get('/architecture/snapshot');
export const regenerateArchitecture = () => api.post('/architecture/regenerate');
export const getArchitectureHistory = (limit = 20) => api.get(`/architecture/history?limit=${limit}`);
export const getArchitectureSnapshotById = (id) => api.get(`/architecture/snapshot/${id}`);
export const getArchitectureDiff = (fromId, toId) => api.get(`/architecture/diff?from_id=${fromId}&to_id=${toId}`);
export const getArchitectureChangelog = (limit = 50) => api.get(`/architecture/changelog?limit=${limit}`);

// ─── R00A: Multi-tenant integrations (Routal/Kosmo/Manual) ───
export const listIntegrations = () => api.get('/integrations');
export const getIntegration = (clientId) => api.get(`/integrations/${clientId}`);
export const upsertIntegration = (clientId, payload) => api.post(`/integrations/${clientId}`, payload);
export const updateIntegrationStatus = (clientId, status) => api.patch(`/integrations/${clientId}/status`, { status });
export const testIntegration = (clientId) => api.post(`/integrations/${clientId}/test`);
export const deleteIntegration = (clientId) => api.delete(`/integrations/${clientId}`);
export const getRoutalWebhookStatus = (clientId) => api.get(`/webhooks/routal/${clientId}/status`);

// ─── R00B / SEL01: Selection module + client config ───
export const listClientConfigs = () => api.get('/client-config');
export const getClientConfig = (clientId) => api.get(`/client-config/${clientId}`);
export const patchClientConfig = (clientId, payload) => api.patch(`/client-config/${clientId}`, payload);
export const runSelection = (clientId, date) =>
    api.post(`/selection/run/${clientId}` + (date ? `?date=${date}` : ''));
export const runSelectionRange = (clientId, dateFrom, dateTo) =>
    api.post(`/selection/run-range/${clientId}?date_from=${dateFrom}&date_to=${dateTo}`);
export const backfillSelectionFromRoutal = (clientId, dateFrom, dateTo, autoRun = true) =>
    api.post(
        `/selection/backfill-from-routal/${clientId}?date_from=${dateFrom}&date_to=${dateTo}&auto_run_selection=${autoRun}`,
        null,
        { timeout: 180000 }
    );
export const reconcileJourneyDates = (clientId, daysBack = 30, dryRun = true) =>
    api.post(
        `/selection/reconcile-dates/${clientId}?days_back=${daysBack}&dry_run=${dryRun}`,
        null,
        { timeout: 180000 }
    );
export const getSelectionSummary = (clientId, date) =>
    api.get(`/selection/summary/${clientId}` + (date ? `?date=${date}` : ''));
export const getDriverAuditHistory = (driverId, clientId, days = 30) =>
    api.get(`/drivers/audit-history/${driverId}?client_id=${clientId}&days=${days}`);

