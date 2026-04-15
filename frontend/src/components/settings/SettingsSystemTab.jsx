import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Loader2, Server, Clock } from 'lucide-react';

export const SettingsSystemTab = ({ systemConfig, configLoading }) => (
    <div className="space-y-4">
        <Card>
            <CardHeader>
                <CardTitle className="font-heading flex items-center gap-2">
                    <Server className="w-5 h-5" />
                    Configuracion del entorno
                </CardTitle>
            </CardHeader>
            <CardContent>
                {configLoading ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                    </div>
                ) : systemConfig ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-3">
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">Backend</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.backend_version}</p>
                            </div>
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">Python</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.python_version}</p>
                            </div>
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">MongoDB Host</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.mongo_host}</p>
                            </div>
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">Base de datos</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.db_name} ({systemConfig.db_size_mb} MB, {systemConfig.collections_count} colecciones)</p>
                            </div>
                        </div>
                        <div className="space-y-3">
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">CORS</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.cors_origins}</p>
                            </div>
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">JWT Expiracion</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.jwt_expiry_hours} horas</p>
                            </div>
                            <div className="p-3 bg-slate-50 rounded-sm">
                                <p className="text-xs text-slate-500 uppercase">Ultimo deploy</p>
                                <p className="font-mono text-sm font-medium">{systemConfig.last_deploy?.slice(0, 19)}</p>
                            </div>
                            <div className="p-3 bg-slate-50 rounded-sm flex items-center gap-2">
                                <Clock className="w-4 h-4 text-slate-400" />
                                <div>
                                    <p className="text-xs text-slate-500 uppercase">Uptime</p>
                                    <p className="font-mono text-sm font-medium">{systemConfig.uptime}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : (
                    <p className="text-slate-500 text-sm">No se pudo cargar la configuracion</p>
                )}
            </CardContent>
        </Card>
    </div>
);
