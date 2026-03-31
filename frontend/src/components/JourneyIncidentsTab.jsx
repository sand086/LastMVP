import React from 'react';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { 
    Plus, Pencil, Trash2, Download, Loader2, CheckCircle2, CheckCheck, Camera,
} from 'lucide-react';
import { formatTime, getStatusColor, getStatusLabel, getSeverityColor, getImputabilityColor } from '../lib/utils';

export const JourneyIncidentsTab = ({
    journey,
    canEdit,
    isCoordinator,
    sortedIncidents,
    IncSortHeader,
    incidentImages,
    openIncidents,
    resolvingAll,
    handleOpenIncidentModal,
    handleResolveIncident,
    handleDeleteIncident,
    handleExportIncidents,
    setShowResolveAllConfirm,
}) => {
    return (
        <>
            <div className="flex items-center justify-between">
                <h3 className="font-heading text-lg font-semibold">Incidencias registradas</h3>
                <div className="flex gap-2">
                    {journey.incidents?.length > 0 && (
                        <Button variant="outline" onClick={handleExportIncidents} data-testid="export-incidents-btn">
                            <Download className="w-4 h-4 mr-2" />
                            Exportar CSV
                        </Button>
                    )}
                    {canEdit() && openIncidents.length > 0 && (
                        <Button
                            variant="outline"
                            onClick={() => setShowResolveAllConfirm(true)}
                            disabled={resolvingAll}
                            data-testid="resolve-all-incidents-btn"
                        >
                            {resolvingAll ? (
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                            ) : (
                                <CheckCheck className="w-4 h-4 mr-2" />
                            )}
                            Resolver todas
                        </Button>
                    )}
                    {canEdit() && journey.status !== 'closed' && (
                        <Button onClick={() => handleOpenIncidentModal()} data-testid="add-incident-btn">
                            <Plus className="w-4 h-4 mr-2" />
                            Nueva incidencia
                        </Button>
                    )}
                </div>
            </div>

            {journey.incidents?.length === 0 ? (
                <Card>
                    <CardContent className="py-12 text-center">
                        <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
                        <p className="text-slate-600 font-medium">Sin incidencias</p>
                        <p className="text-slate-500 text-sm">No se han registrado incidencias en esta ruta</p>
                    </CardContent>
                </Card>
            ) : (
                <Card>
                    <CardContent className="p-0">
                        <table className="data-table w-full">
                            <thead>
                                <tr>
                                    <IncSortHeader field="occurred_at">Hora</IncSortHeader>
                                    <IncSortHeader field="incident_type">Tipo</IncSortHeader>
                                    <IncSortHeader field="severity">Severidad</IncSortHeader>
                                    <IncSortHeader field="imputability">Imputabilidad</IncSortHeader>
                                    <th>Descripcion</th>
                                    <th>Fotos</th>
                                    <IncSortHeader field="status">Estado</IncSortHeader>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {sortedIncidents.map((incident) => (
                                    <tr key={incident.id} data-testid={`incident-row-${incident.id}`}>
                                        <td className="font-mono text-sm">
                                            {formatTime(incident.occurred_at)}
                                        </td>
                                        <td>{incident.incident_type}</td>
                                        <td>
                                            <span className={`status-badge ${getSeverityColor(incident.severity)}`}>
                                                {incident.severity}
                                            </span>
                                        </td>
                                        <td>
                                            <span className={`px-2 py-0.5 text-xs font-medium rounded border ${getImputabilityColor(incident.imputability)}`} data-testid={`imputability-badge-${incident.id}`}>
                                                {incident.imputability || 'Por definir'}
                                            </span>
                                        </td>
                                        <td className="max-w-xs truncate">{incident.description}</td>
                                        <td>
                                            {incidentImages[incident.id]?.length > 0 ? (
                                                <span className="flex items-center gap-1 text-slate-600">
                                                    <Camera className="w-4 h-4" />
                                                    {incidentImages[incident.id].length}
                                                </span>
                                            ) : (
                                                <span className="text-slate-400">-</span>
                                            )}
                                        </td>
                                        <td>
                                            <span className={`status-badge ${getStatusColor(incident.status)}`}>
                                                {getStatusLabel(incident.status)}
                                            </span>
                                        </td>
                                        <td>
                                            <div className="flex items-center gap-1">
                                                {canEdit() && incident.status === 'open' && (
                                                    <>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={() => handleOpenIncidentModal(incident)}
                                                            data-testid={`edit-incident-${incident.id}`}
                                                        >
                                                            <Pencil className="w-4 h-4" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={() => handleResolveIncident(incident)}
                                                            className="text-emerald-600"
                                                            data-testid={`resolve-incident-${incident.id}`}
                                                        >
                                                            <CheckCircle2 className="w-4 h-4" />
                                                        </Button>
                                                    </>
                                                )}
                                                {(isCoordinator() || canEdit()) && (
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={() => handleDeleteIncident(incident.id)}
                                                        className="text-red-600"
                                                        data-testid={`delete-incident-${incident.id}`}
                                                    >
                                                        <Trash2 className="w-4 h-4" />
                                                    </Button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </CardContent>
                </Card>
            )}
        </>
    );
};
