import React from 'react';
import { Button } from '../ui/button';
import { AlertTriangle } from 'lucide-react';
import { KpiCard, SEGMENT_FILTERS } from './GuiasHelpers';

/** Fila de KPI cards + banners (Discrepancia y alertas IA). */
export const GuiasKpisRow = ({ kpis, aiErrorSummary, driverName, onViewDiscrepancies }) => (
    <>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <KpiCard
                label="Score promedio"
                value={`${kpis.avgScore}%`}
                color={kpis.avgScore >= 90 ? 'emerald' : kpis.avgScore >= 60 ? 'amber' : 'red'}
                testId="kpi-avg-score"
            />
            <KpiCard label="Completos" value={`${kpis.complete}/${kpis.totalScored}`} color="emerald" testId="kpi-complete" />
            <KpiCard label="Evaluados IA" value={`${kpis.aiEvaluated}/${kpis.totalPkgs}`} color="blue" testId="kpi-ai-evaluated" />
            <KpiCard label="Revisión manual" value={`${kpis.manualReviewed}/${kpis.totalPkgs}`} color="violet" testId="kpi-manual-reviewed" />
            <KpiCard
                label="Discrepancias"
                value={kpis.discrepancies}
                color={kpis.discrepancies > 0 ? 'red' : 'emerald'}
                accent={kpis.discrepancies > 0 ? 'red' : undefined}
                testId="kpi-discrepancies"
            />
            <KpiCard
                label="Confianza prom."
                value={kpis.avgConfidence != null ? `${kpis.avgConfidence}%` : '—'}
                color={kpis.avgConfidence >= 70 ? 'emerald' : kpis.avgConfidence >= 30 ? 'amber' : 'red'}
                testId="kpi-avg-confidence"
            />
        </div>

        {kpis.discrepancies > 0 && (
            <div
                className="rounded-xl border border-amber-300 bg-amber-50 p-4 flex items-start gap-3"
                data-testid="discrepancy-alert-banner"
            >
                <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center shrink-0 mt-0.5">
                    <AlertTriangle className="w-4 h-4 text-amber-600" />
                </div>
                <div className="flex-1">
                    <p className="text-sm font-semibold text-amber-800">
                        {kpis.discrepancies} guía{kpis.discrepancies !== 1 ? 's' : ''} con discrepancia de estatus detectada
                    </p>
                    <p className="text-xs text-amber-700 mt-0.5">
                        El tracking público de Kosmo reporta "Entregado" pero no se encontraron evidencias fotográficas ni motivo de excepción.
                    </p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    className="border-amber-400 text-amber-700 hover:bg-amber-100 shrink-0"
                    onClick={onViewDiscrepancies}
                    data-testid="view-discrepancies-btn"
                >
                    Ver discrepancias
                </Button>
            </div>
        )}

        {aiErrorSummary.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-3" data-testid="ai-alert-banner">
                <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                <div className="text-sm">
                    <p className="font-medium text-amber-800">Alertas IA detectadas — Driver: {driverName || 'N/A'}</p>
                    <div className="flex flex-wrap gap-2 mt-1">
                        {aiErrorSummary.slice(0, 5).map(([error, count]) => (
                            <span key={error} className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">
                                {error} ({count})
                            </span>
                        ))}
                    </div>
                </div>
            </div>
        )}
    </>
);

/** Pills de filtros por segmento. */
export const GuiasSegmentFilters = ({ segment, segmentCounts, onSegmentChange }) => (
    <div className="flex gap-2 flex-wrap" data-testid="segment-filters">
        {SEGMENT_FILTERS.map((f) => {
            const count = segmentCounts[f.key];
            const isDiscrepancy = f.key === 'discrepancy' && count > 0;
            return (
                <button
                    key={f.key}
                    className={`px-3 py-1.5 text-xs font-medium rounded-full border transition-colors ${
                        segment === f.key
                            ? isDiscrepancy
                                ? 'bg-amber-600 text-white border-amber-600'
                                : 'bg-slate-900 text-white border-slate-900'
                            : isDiscrepancy
                              ? 'bg-amber-50 text-amber-700 border-amber-300 hover:bg-amber-100'
                              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                    }`}
                    onClick={() => onSegmentChange(f.key)}
                    data-testid={`segment-${f.key}`}
                >
                    {f.label} <span className="ml-1 opacity-70">({count})</span>
                </button>
            );
        })}
    </div>
);

export default GuiasKpisRow;
