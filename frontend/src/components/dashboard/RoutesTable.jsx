import React from 'react';
import { Link } from 'react-router-dom';
import { useSortableTable } from '../../lib/useSortableTable';
import { formatDate } from '../../lib/utils';
import { Progress } from '../ui/progress';
import { Eye, AlertTriangle, ExternalLink } from 'lucide-react';

const T = {
    textPri: '#1A1916', textTer: '#9C9A92', amber: '#D97706',
};

const calculateDeliveryRate = (d, t) => t > 0 ? Math.round((d / t) * 100) : 0;
const getProgressColor = (r) => r >= 90 ? 'bg-emerald-500' : r >= 70 ? 'bg-amber-500' : 'bg-red-500';
const getStatusColor = (s) => ({ scheduled: 'bg-blue-100 text-blue-700', in_progress: 'bg-emerald-100 text-emerald-700', closed: 'bg-slate-200 text-slate-700' }[s] || 'bg-slate-100 text-slate-600');
const getStatusLabel = (s) => ({ scheduled: 'Programada', in_progress: 'En Progreso', closed: 'Cerrada' }[s] || s);

export const RoutesTable = ({ journeys }) => {
    const { sortedData, SortHeader } = useSortableTable(journeys);
    return (
        <div className="overflow-x-auto">
            <table className="lm-table" style={{ width: '100%' }}>
                <thead>
                    <tr>
                        <SortHeader field="order_id">Origen / ID</SortHeader>
                        <SortHeader field="date">Fecha</SortHeader>
                        <SortHeader field="client_name">Cliente</SortHeader>
                        <SortHeader field="provider_name">Proveedor</SortHeader>
                        <SortHeader field="driver_name">Driver</SortHeader>
                        <SortHeader field="packages_total">Paquetes</SortHeader>
                        <SortHeader field="packages_delivered">Progreso</SortHeader>
                        <SortHeader field="open_incidents_count">Incid.</SortHeader>
                        <SortHeader field="status">Estado</SortHeader>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    {sortedData.map((j) => {
                        const rate = calculateDeliveryRate(j.packages_delivered, j.packages_total);
                        const pc = getProgressColor(rate);
                        return (
                            <tr key={j.id} data-testid={`journey-row-${j.id}`}>
                                <td style={{ maxWidth: 180 }} data-testid={`row-source-${j.id}`}>
                                    {j.source === 'routal' && j.routal_plan_id ? (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <span style={{ padding: '2px 6px', backgroundColor: '#ECFDF5', color: '#047857', borderRadius: 4, border: '1px solid #A7F3D0', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', flexShrink: 0 }}>Routal</span>
                                            <span
                                                style={{ fontFamily: "'DM Mono', monospace", fontSize: 11, color: '#475569', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                                                title={j.routal_plan_id}
                                            >
                                                {j.routal_plan_label || (j.routal_plan_id.slice(0, 10) + '…')}
                                            </span>
                                            {j.routal_project_id && (
                                                <a
                                                    href={`https://planner.routal.com/h/${j.routal_project_id}/planner/plan/${j.routal_plan_id}/stops`}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    onClick={(e) => e.stopPropagation()}
                                                    title="Abrir en Routal Planner"
                                                    style={{ color: '#10B981', flexShrink: 0, display: 'inline-flex' }}
                                                    data-testid={`row-routal-link-${j.id}`}
                                                >
                                                    <ExternalLink style={{ width: 13, height: 13 }} />
                                                </a>
                                            )}
                                        </div>
                                    ) : j.order_id ? (
                                        <span style={{ fontFamily: "'DM Mono', monospace", fontSize: 12, color: '#1D4ED8', display: 'inline-block', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={j.order_id}>
                                            {j.order_id}
                                        </span>
                                    ) : (
                                        <span style={{ color: T.textTer }}>-</span>
                                    )}
                                </td>
                                <td style={{ fontFamily: "'DM Mono', monospace", fontSize: 13 }}>{formatDate(j.date)}</td>
                                <td>{j.client_name}</td>
                                <td>{j.provider_name}</td>
                                <td style={{ fontSize: 13 }}>
                                    {j.driver_name
                                        ? <span>{j.driver_name.length > 20 ? j.driver_name.split(' ').slice(0, 1).join(' ') + ' ' + (j.driver_name.split(' ')[1]?.[0] || '') + '.' : j.driver_name}</span>
                                        : <span style={{ color: T.textTer, fontStyle: 'italic' }}>Sin asignar</span>}
                                </td>
                                <td style={{ fontFamily: "'DM Mono', monospace" }}>{j.packages_delivered}/{j.packages_total}</td>
                                <td style={{ width: 130 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <Progress value={rate} className="h-2 flex-1" indicatorClassName={pc} />
                                        <span style={{ fontSize: 12, fontFamily: "'DM Mono', monospace", width: 36, textAlign: 'right' }}>{rate}%</span>
                                    </div>
                                </td>
                                <td>
                                    {j.open_incidents_count > 0
                                        ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: T.amber }}><AlertTriangle style={{ width: 15, height: 15 }} />{j.open_incidents_count}</span>
                                        : <span style={{ color: T.textTer }}>0</span>}
                                </td>
                                <td>
                                    <span className={`status-badge ${getStatusColor(j.status)}`}>{getStatusLabel(j.status)}</span>
                                </td>
                                <td>
                                    <Link to={`/journeys/${j.id}`}>
                                        <button className="lm-btn-ghost" data-testid={`view-journey-${j.id}`}>
                                            <Eye style={{ width: 15, height: 15, marginRight: 4 }} />Ver detalle
                                        </button>
                                    </Link>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};
