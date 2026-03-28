import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from 'react-leaflet';
import { getReportsHeatmap } from '../lib/api';
import { RefreshCw, Map as MapIcon } from 'lucide-react';

const ZONE_VIEWS = {
    all:    { center: [23.5, -102.5], zoom: 5 },
    cdmx:   { center: [19.42, -99.13], zoom: 11 },
    norte:  { center: [27.5, -104], zoom: 6 },
    centro: { center: [20.5, -100], zoom: 7 },
    sur:    { center: [16.5, -92], zoom: 6 },
};

function heatColor(intensity) {
    const stops = [
        [1.00, [249, 244, 195]],
        [0.75, [253, 186, 68]],
        [0.50, [249, 115, 22]],
        [0.25, [220, 38, 38]],
        [0.00, [127, 29, 29]],
    ];
    for (let i = 0; i < stops.length - 1; i++) {
        const [t1, c1] = stops[i];
        const [t2, c2] = stops[i + 1];
        if (intensity >= t2) {
            const f = (intensity - t2) / (t1 - t2);
            return c2.map((v, j) => Math.round(v + (c1[j] - v) * f));
        }
    }
    return [127, 29, 29];
}

function rgbStr(rgb) {
    return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function MapController({ center, zoom }) {
    const map = useMap();
    useEffect(() => {
        map.flyTo(center, zoom, { duration: 0.8 });
    }, [map, center, zoom]);
    return null;
}

const HeatmapSection = ({ dateFrom, dateTo, clientId, providerId }) => {
    const [heatData, setHeatData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [mapMode, setMapMode] = useState('cdmx');
    const mapRef = useRef(null);

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (dateFrom) params.date_from = dateFrom;
            if (dateTo) params.date_to = dateTo;
            if (clientId && clientId !== 'all') params.client_id = clientId;
            if (providerId && providerId !== 'all') params.provider_id = providerId;
            const res = await getReportsHeatmap(params);
            setHeatData(res.data || []);
        } catch {
            setHeatData([]);
        } finally {
            setLoading(false);
        }
    }, [dateFrom, dateTo, clientId, providerId]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const maxTotal = useMemo(() => Math.max(1, ...heatData.map(d => d.total)), [heatData]);
    const totalDeliveries = useMemo(() => heatData.reduce((s, d) => s + d.total, 0), [heatData]);
    const top10 = useMemo(() => [...heatData].sort((a, b) => b.total - a.total).slice(0, 10), [heatData]);
    const view = ZONE_VIEWS[mapMode] || ZONE_VIEWS.cdmx;

    const flyToCP = useCallback((lat, lng) => {
        if (mapRef.current) {
            mapRef.current.flyTo([lat, lng], 13, { duration: 0.8 });
        }
    }, []);

    return (
        <div className="lm-card" data-testid="heatmap-section">
            {/* Header */}
            <div className="lm-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <MapIcon style={{ width: 18, height: 18, color: 'var(--text-secondary)' }} />
                    <span className="lm-section-title">Mapa de calor — Densidad de entregas por CP</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {/* Legend */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: 'var(--text-tertiary)' }}>
                        <span>Bajo</span>
                        <div style={{ display: 'flex', gap: '2px' }}>
                            {[0, 0.25, 0.5, 0.75, 1].map(v => (
                                <div key={v} style={{ width: 16, height: 10, borderRadius: 2, background: rgbStr(heatColor(v)) }} />
                            ))}
                        </div>
                        <span>Alto</span>
                    </div>
                    <select
                        className="lm-select"
                        value={mapMode}
                        onChange={e => setMapMode(e.target.value)}
                        data-testid="heatmap-zone-select"
                    >
                        <option value="all">Todo México</option>
                        <option value="cdmx">CDMX</option>
                        <option value="norte">Norte</option>
                        <option value="centro">Centro</option>
                        <option value="sur">Sur</option>
                    </select>
                    {loading && <RefreshCw style={{ width: 14, height: 14, animation: 'spin 1s linear infinite', color: 'var(--text-tertiary)' }} />}
                </div>
            </div>

            {/* Map + Sidebar */}
            <div style={{ display: 'flex', borderTop: '1px solid var(--border)', minHeight: 520 }}>
                {/* Map */}
                <div style={{ flex: 1, position: 'relative' }}>
                    {heatData.length === 0 && !loading ? (
                        <div style={{ position: 'absolute', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(245,244,241,0.85)' }}>
                            <div style={{ textAlign: 'center' }}>
                                <MapIcon style={{ width: 40, height: 40, color: 'var(--text-tertiary)', margin: '0 auto 12px' }} />
                                <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>Sin datos para el período seleccionado</p>
                            </div>
                        </div>
                    ) : null}
                    <MapContainer
                        center={view.center}
                        zoom={view.zoom}
                        style={{ height: 520, width: '100%' }}
                        scrollWheelZoom={true}
                        ref={mapRef}
                    >
                        <TileLayer
                            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
                        />
                        <MapController center={view.center} zoom={view.zoom} />
                        {heatData.map(pt => {
                            const intensity = pt.total / maxTotal;
                            const color = heatColor(intensity);
                            return (
                                <CircleMarker
                                    key={pt.cp}
                                    center={[pt.lat, pt.lng]}
                                    radius={Math.max(10, Math.round(intensity * 40))}
                                    fillColor={rgbStr(color)}
                                    fillOpacity={0.78}
                                    stroke={false}
                                    eventHandlers={{
                                        click: () => flyToCP(pt.lat, pt.lng),
                                    }}
                                >
                                    <Tooltip>
                                        <div style={{ fontFamily: "'DM Mono', monospace", fontSize: 12, lineHeight: 1.6 }}>
                                            <strong>CP {pt.cp}</strong> — {pt.zone}<br />
                                            Entregas: <strong>{pt.delivered}</strong><br />
                                            Fallidas: <strong>{pt.failed}</strong><br />
                                            Efectividad: <strong>{(pt.rate * 100).toFixed(1)}%</strong>
                                        </div>
                                    </Tooltip>
                                </CircleMarker>
                            );
                        })}
                    </MapContainer>
                    <div style={{ position: 'absolute', bottom: 12, left: 12, zIndex: 1000, fontSize: 11, color: 'var(--text-tertiary)', background: 'rgba(255,255,255,0.8)', padding: '4px 8px', borderRadius: 4 }}>
                        Scroll para zoom · Arrastra para mover
                    </div>
                </div>

                {/* Sidebar - Top 10 */}
                <div style={{ width: 280, borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column' }}>
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>Top 10 CPs</span>
                    </div>
                    <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
                        {top10.map((pt, i) => {
                            const barW = Math.max(8, (pt.total / maxTotal) * 100);
                            const color = heatColor(pt.total / maxTotal);
                            return (
                                <div
                                    key={pt.cp}
                                    onClick={() => flyToCP(pt.lat, pt.lng)}
                                    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', cursor: 'pointer', transition: 'background 0.15s' }}
                                    className="lm-cp-row"
                                    data-testid={`cp-row-${pt.cp}`}
                                >
                                    <span style={{ width: 20, fontSize: 12, fontWeight: 500, color: 'var(--text-tertiary)', textAlign: 'right' }}>
                                        {i + 1}
                                    </span>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                                            <span style={{ fontFamily: "'DM Mono', monospace", fontWeight: 500 }}>{pt.cp}</span>
                                            <span style={{ fontFamily: "'DM Mono', monospace", color: 'var(--text-secondary)' }}>{pt.total}</span>
                                        </div>
                                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                            {pt.zone}
                                        </div>
                                        <div style={{ height: 4, borderRadius: 2, background: 'var(--surface-2, #F0EFEc)' }}>
                                            <div style={{ height: '100%', borderRadius: 2, width: `${barW}%`, background: rgbStr(color), transition: 'width 0.3s' }} />
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        {top10.length === 0 && (
                            <div style={{ padding: 20, textAlign: 'center', fontSize: 13, color: 'var(--text-tertiary)' }}>
                                Sin datos
                            </div>
                        )}
                    </div>
                    <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', textAlign: 'center' }}>
                        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Total entregas período</span>
                        <p style={{ fontSize: 22, fontWeight: 600, fontFamily: "'DM Mono', monospace", color: 'var(--text-primary)' }}>
                            {totalDeliveries.toLocaleString()}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default HeatmapSection;
