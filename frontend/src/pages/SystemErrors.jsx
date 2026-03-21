import React, { useState, useEffect, useCallback } from 'react';
import api from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { 
    Bug, CheckCircle2, RefreshCw, Loader2, Eye, Filter, XCircle, AlertTriangle
} from 'lucide-react';
import { toast } from 'sonner';

const ERROR_TYPE_LABELS = {
    api_error: 'Error de API',
    parsing_error: 'Error de parsing',
    validation_error: 'Error de validación',
};

const getErrorTypeColor = (type) => {
    switch (type) {
        case 'parsing_error': return 'bg-amber-100 text-amber-700 border-amber-200';
        case 'validation_error': return 'bg-blue-100 text-blue-700 border-blue-200';
        default: return 'bg-red-100 text-red-700 border-red-200';
    }
};

const SystemErrors = () => {
    const [errors, setErrors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [reviewing, setReviewing] = useState(null);
    const [filterType, setFilterType] = useState('all');
    const [showReviewed, setShowReviewed] = useState(false);

    const fetchErrors = useCallback(async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            if (filterType !== 'all') params.append('error_type', filterType);
            if (!showReviewed) params.append('reviewed', 'false');
            
            const res = await api.get(`/system/errors?${params}`);
            setErrors(res.data.errors || []);
        } catch (error) {
            console.error('Error fetching errors:', error);
        } finally {
            setLoading(false);
        }
    }, [filterType, showReviewed]);

    useEffect(() => { fetchErrors(); }, [fetchErrors]);

    const handleReview = async (errorId) => {
        setReviewing(errorId);
        try {
            await api.post(`/system/errors/${errorId}/review`);
            toast.success('Error marcado como revisado');
            fetchErrors();
        } catch (error) {
            toast.error('Error al marcar');
        } finally {
            setReviewing(null);
        }
    };

    const handleReviewAll = async () => {
        try {
            await api.post('/system/errors/review-all');
            toast.success('Todos los errores marcados como revisados');
            fetchErrors();
        } catch (error) {
            toast.error('Error al marcar todos');
        }
    };

    const unreviewedCount = errors.filter(e => !e.reviewed).length;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">Error Tracker</h1>
                    <p className="text-slate-500 text-sm">
                        {unreviewedCount} errores sin revisar de {errors.length} totales
                    </p>
                </div>
                <div className="flex gap-2">
                    {unreviewedCount > 0 && (
                        <Button variant="outline" size="sm" onClick={handleReviewAll} data-testid="review-all-errors-btn">
                            <CheckCircle2 className="w-4 h-4 mr-2" /> Marcar todos como revisados
                        </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={fetchErrors} data-testid="refresh-errors-btn">
                        <RefreshCw className="w-4 h-4 mr-2" /> Actualizar
                    </Button>
                </div>
            </div>

            {/* Filters */}
            <div className="flex items-center gap-4">
                <Select value={filterType} onValueChange={(v) => { setFilterType(v); }}>
                    <SelectTrigger className="w-48" data-testid="error-filter-type">
                        <SelectValue placeholder="Tipo de error" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todos los tipos</SelectItem>
                        <SelectItem value="api_error">Error de API</SelectItem>
                        <SelectItem value="parsing_error">Error de parsing</SelectItem>
                        <SelectItem value="validation_error">Error de validación</SelectItem>
                    </SelectContent>
                </Select>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input 
                        type="checkbox" 
                        checked={showReviewed} 
                        onChange={(e) => setShowReviewed(e.target.checked)} 
                        className="rounded" 
                    />
                    Mostrar revisados
                </label>
            </div>

            {/* Error List */}
            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
                </div>
            ) : errors.length === 0 ? (
                <Card className="p-8 text-center">
                    <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-emerald-400" />
                    <p className="text-slate-600 font-medium">Sin errores pendientes</p>
                    <p className="text-sm text-slate-400 mt-1">El sistema funciona correctamente</p>
                </Card>
            ) : (
                <div className="space-y-3">
                    {errors.map((err) => (
                        <Card key={err.id} className={`transition-opacity ${err.reviewed ? 'opacity-60' : ''}`} data-testid={`error-card-${err.id}`}>
                            <CardContent className="p-4">
                                <div className="flex items-start justify-between">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-3 mb-2">
                                            <span className={`px-2 py-0.5 text-xs font-medium rounded border ${getErrorTypeColor(err.error_type)}`}>
                                                {ERROR_TYPE_LABELS[err.error_type] || err.error_type}
                                            </span>
                                            <span className={`px-2 py-0.5 text-xs font-mono rounded ${
                                                err.status_code >= 500 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                                            }`}>{err.status_code}</span>
                                            <span className="font-mono text-xs font-bold text-slate-900">
                                                x{err.occurrence_count}
                                            </span>
                                            {err.reviewed && (
                                                <span className="px-2 py-0.5 text-xs bg-emerald-50 text-emerald-600 rounded">Revisado</span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="px-1.5 py-0.5 text-xs font-mono bg-slate-100 rounded">{err.method}</span>
                                            <span className="font-mono text-sm text-slate-700">{err.endpoint}</span>
                                        </div>
                                        {err.last_detail && (
                                            <p className="text-xs text-slate-500 mt-2 font-mono bg-slate-50 p-2 rounded truncate">
                                                {err.last_detail}
                                            </p>
                                        )}
                                        <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                                            <span>Primera vez: {err.first_seen?.slice(0, 16)}</span>
                                            <span>Última vez: {err.last_seen?.slice(0, 16)}</span>
                                            <span>IP: {err.last_ip}</span>
                                        </div>
                                    </div>
                                    {!err.reviewed && (
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => handleReview(err.id)}
                                            disabled={reviewing === err.id}
                                            data-testid={`review-error-${err.id}`}
                                        >
                                            {reviewing === err.id ? (
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                            ) : (
                                                <Eye className="w-4 h-4 mr-1" />
                                            )}
                                            Revisado
                                        </Button>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
};

export default SystemErrors;
