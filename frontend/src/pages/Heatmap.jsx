/**
 * Heatmap — PROMPT 22.
 * Visualización geográfica de incidencias agrupadas por celda.
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import InboxBell from "@/components/InboxBell";
import { ArrowLeft, LogOut, RefreshCw, MapPin } from "lucide-react";

export default function Heatmap() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const layerRef = useRef(null);
  const [points, setPoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    date_from: "", date_to: "", motivo_codigo: "", carrier_code: "",
    grid_decimals: 2,
  });
  const [carriers, setCarriers] = useState([]);
  const [motivos, setMotivos] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get("/admin/carriers").catch(() => ({})),
      api.get("/admin/motivos").catch(() => ({})),
    ]).then(([c, m]) => {
      setCarriers(c.data?.data?.items || []);
      setMotivos(m.data?.data?.items || []);
    });
  }, []);

  // Init Leaflet
  useEffect(() => {
    let timer;
    timer = setTimeout(() => {
      if (mapInstance.current || !mapRef.current) return;
      const L = window.L;
      if (!L) {
        // load Leaflet dynamically
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        document.head.appendChild(css);
        const script = document.createElement("script");
        script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
        script.onload = () => initMap();
        document.head.appendChild(script);
      } else { initMap(); }
    }, 100);
    return () => { clearTimeout(timer); if (mapInstance.current) { mapInstance.current.remove(); mapInstance.current = null; } };
     
  }, []);

  function initMap() {
    const L = window.L;
    if (!L || !mapRef.current || mapInstance.current) return;
    mapInstance.current = L.map(mapRef.current, { zoomControl: true })
      .setView([19.43, -99.13], 5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    }).addTo(mapInstance.current);
    layerRef.current = L.layerGroup().addTo(mapInstance.current);
    refresh();
  }

  function paintPoints(items) {
    const L = window.L;
    if (!L || !layerRef.current) return;
    layerRef.current.clearLayers();
    if (items.length === 0) return;
    items.forEach((p) => {
      const radius = 8 + p.severity * 22;
      const opacity = 0.35 + p.severity * 0.5;
      const color = p.severity > 0.7 ? "#C2410C"
                  : p.severity > 0.35 ? "#f59e0b"
                                       : "#1F3A5F";
      L.circleMarker([p.lat, p.lng], {
        radius, color, fillColor: color, fillOpacity: opacity, weight: 1,
      }).bindTooltip(`${p.count} incidencias · severidad ${(p.severity * 100).toFixed(0)}%`, { permanent: false }).addTo(layerRef.current);
    });
    // Auto-fit
    const bounds = L.latLngBounds(items.map((p) => [p.lat, p.lng]));
    if (bounds.isValid()) mapInstance.current.fitBounds(bounds, { padding: [40, 40] });
  }

  async function refresh() {
    setLoading(true);
    try {
      const params = {};
      Object.entries(filters).forEach(([k, v]) => { if (v !== "" && v !== null) params[k] = v; });
      const r = await api.get("/dashboard/heatmap", { params });
      const items = r.data?.data?.items || [];
      setPoints(items);
      paintPoints(items);
    } finally { setLoading(false); }
  }

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="heatmap-page">
      <header className="sticky top-0 z-10 bg-white/85 backdrop-blur border-b border-mye-border">
        <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center gap-4">
          <button onClick={() => navigate(-1)}
                  className="inline-flex items-center gap-1.5 text-xs text-mye-ink-muted hover:text-mye-ink">
            <ArrowLeft className="h-3.5 w-3.5" /> Volver
          </button>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm">M</div>
            <div className="leading-tight">
              <div className="font-semibold tracking-tight text-sm">MyExcellence</div>
              <div className="font-mono text-[10px] text-mye-ink-muted">Heatmap · PROMPT 22</div>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <InboxBell />
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-8 space-y-4">
        <section className="space-y-1">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
            <MapPin className="h-3.5 w-3.5 text-mye-accent" /> PROMPT 22 · Mapa de calor
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Concentración geográfica de incidencias</h1>
          <p className="text-mye-ink-muted text-sm">
            Coordenadas de evidencias (pickup) priorizan; fallback a geocoding Nominatim.
            Severidad = count normalizado dentro del rango.
          </p>
        </section>

        <div className="grid md:grid-cols-5 gap-2 bg-white border border-mye-border rounded-md p-3">
          <Field label="Desde">
            <input type="date" value={filters.date_from}
                   onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                   className={inputCls} data-testid="heatmap-date-from" />
          </Field>
          <Field label="Hasta">
            <input type="date" value={filters.date_to}
                   onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                   className={inputCls} data-testid="heatmap-date-to" />
          </Field>
          <Field label="Motivo">
            <select value={filters.motivo_codigo}
                    onChange={(e) => setFilters({ ...filters, motivo_codigo: e.target.value })}
                    className={inputCls} data-testid="heatmap-motivo">
              <option value="">Todos</option>
              {motivos.map((m) => <option key={m.id} value={m.codigo}>{m.codigo}</option>)}
            </select>
          </Field>
          <Field label="Carrier">
            <select value={filters.carrier_code}
                    onChange={(e) => setFilters({ ...filters, carrier_code: e.target.value })}
                    className={inputCls} data-testid="heatmap-carrier">
              <option value="">Todos</option>
              {carriers.map((c) => <option key={c.id} value={c.code}>{c.name || c.code}</option>)}
            </select>
          </Field>
          <Field label="Grid (decimales)">
            <select value={filters.grid_decimals}
                    onChange={(e) => setFilters({ ...filters, grid_decimals: +e.target.value })}
                    className={inputCls} data-testid="heatmap-grid-decimals">
              <option value={1}>0.1° (~11km)</option>
              <option value={2}>0.01° (~1.1km)</option>
              <option value={3}>0.001° (~110m)</option>
            </select>
          </Field>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={refresh} disabled={loading}
                  className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                  data-testid="heatmap-apply">
            <RefreshCw className={"h-3.5 w-3.5 " + (loading ? "animate-spin" : "")} /> Aplicar filtros
          </button>
          <div className="text-xs font-mono text-mye-ink-muted">
            {points.length} celdas · {points.reduce((a, b) => a + b.count, 0)} incidencias agrupadas
          </div>
        </div>

        <div className="bg-white border border-mye-border rounded-md overflow-hidden" style={{ height: 560 }}>
          <div ref={mapRef} className="h-full w-full" data-testid="heatmap-map" />
        </div>

        {points.length > 0 && (
          <div className="bg-white border border-mye-border rounded-md p-3" data-testid="heatmap-legend">
            <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-2">
              Top 10 zonas
            </div>
            <ul className="text-xs space-y-1 font-mono">
              {points.slice(0, 10).map((p, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="inline-block w-3 h-3 rounded-full"
                        style={{ background: p.severity > 0.7 ? "#C2410C" : p.severity > 0.35 ? "#f59e0b" : "#1F3A5F" }} />
                  <span className="font-mono">{p.lat.toFixed(2)}, {p.lng.toFixed(2)}</span>
                  <span className="text-mye-ink-muted">· {p.count} incidencias · severidad {(p.severity * 100).toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs outline-none focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20";

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-[10px] font-mono uppercase tracking-wider text-mye-ink-muted mb-1">{label}</span>
      {children}
    </label>
  );
}
