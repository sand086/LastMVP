import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api, getToken, API } from "@/lib/api";
import {
  MapPin, Upload, Image as ImageIcon, FileText, Trash2, X,
  Loader2, AlertTriangle, Camera, CheckCircle2, UploadCloud,
} from "lucide-react";

// Default marker icon fix (Leaflet bundles assets via webpack which Vite/CRA mangle).
const _icon = new L.Icon({
  iconUrl:
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23C2410C' width='32' height='32'>
        <path d='M12 2C8 2 5 5 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-4-3-7-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z'/>
      </svg>`
    ),
  iconSize: [32, 32], iconAnchor: [16, 32], popupAnchor: [0, -28],
});

const MEX_CITY = [19.4326, -99.1332];

// Imperative Leaflet wrapper — survives React 18 StrictMode double-mount.
function MapPicker({ marker, onPick }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const m = L.map(containerRef.current).setView(MEX_CITY, 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(m);
    m.on("click", (e) => onPick({ lat: e.latlng.lat, lng: e.latlng.lng }));
    mapRef.current = m;
    return () => {
      try { m.remove(); } catch (_e) { /* ignore */ }
      mapRef.current = null;
      markerRef.current = null;
    };
     
  }, []);

  // Keep marker layer in sync with prop.
  useEffect(() => {
    const m = mapRef.current;
    if (!m) return;
    if (markerRef.current) {
      try { m.removeLayer(markerRef.current); } catch (_e) { /* ignore */ }
      markerRef.current = null;
    }
    if (marker) {
      markerRef.current = L.marker([marker.lat, marker.lng], { icon: _icon }).addTo(m);
      m.flyTo([marker.lat, marker.lng], Math.max(m.getZoom(), 14), { animate: true, duration: 0.6 });
    }
  }, [marker?.lat, marker?.lng]);

  return <div ref={containerRef} className="h-full w-full" data-testid="evidence-map" />;
}

export default function EvidenceCard({ ownerKind, ownerId, onChanged, disabled = false }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [bulk, setBulk] = useState({ active: false, total: 0, done: 0, errors: [] });

  async function refresh() {
    setLoading(true);
    try {
      const param = ownerKind === "ticket" ? `ticket_id=${ownerId}` : `claim_id=${ownerId}`;
      const r = await api.get(`/evidencias?${param}`);
      setItems(r.data?.data?.items || []);
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh();   }, [ownerKind, ownerId]);

  async function remove(id) {
    if (!window.confirm("¿Borrar esta evidencia?")) return;
    try {
      await api.delete(`/evidencias/${id}`);
      await refresh();
      onChanged && onChanged();
    } catch (e) {
      alert(e.response?.data?.errors?.[0]?.message || e.message);
    }
  }

  async function uploadBatch(files) {
    if (disabled || !files || files.length === 0) return;
    const accepted = Array.from(files).filter((f) =>
      /^(image\/(jpeg|png|webp|heic|heif)|application\/pdf)$/.test(f.type)
      || /\.(jpe?g|png|webp|heic|heif|pdf)$/i.test(f.name));
    if (accepted.length === 0) {
      alert("Ningún archivo válido — sólo JPG/PNG/WebP/HEIC/PDF.");
      return;
    }
    setBulk({ active: true, total: accepted.length, done: 0, errors: [] });
    const errs = [];
    for (let i = 0; i < accepted.length; i++) {
      const f = accepted[i];
      try {
        const fd = new FormData();
        fd.append("file", f);
        if (ownerKind === "ticket") fd.append("ticket_id", ownerId);
        else fd.append("claim_id", ownerId);
        await api.post("/evidencias/upload", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } catch (e) {
        errs.push(`${f.name}: ${e.response?.data?.errors?.[0]?.message || e.message}`);
      }
      setBulk((b) => ({ ...b, done: i + 1, errors: errs }));
    }
    await refresh();
    onChanged && onChanged();
    // Mantener mensaje 4s y limpiar
    setTimeout(() => setBulk({ active: false, total: 0, done: 0, errors: [] }), 4000);
  }

  function onDrop(e) {
    e.preventDefault(); e.stopPropagation();
    setDragOver(false);
    if (disabled) return;
    const files = e.dataTransfer?.files;
    if (files && files.length > 0) uploadBatch(files);
  }

  return (
    <div className="bg-white border border-mye-border rounded-lg p-5 space-y-4" data-testid="evidence-card">
      <div className="flex items-center gap-2 font-medium text-sm">
        <Camera className="h-4 w-4 text-mye-accent" /> Evidencias
        <span className="ml-auto text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
          {items.length} adjunto{items.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Drop zone bulk */}
      {!disabled && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={"rounded-lg border-2 border-dashed transition px-4 py-5 text-center "
            + (dragOver
              ? "border-mye-accent bg-mye-accent/5"
              : "border-mye-border bg-mye-app/40 hover:border-mye-accent/40")}
          data-testid="evidence-dropzone">
          <UploadCloud className={"h-6 w-6 mx-auto mb-1 " + (dragOver ? "text-mye-accent" : "text-mye-ink-muted")} />
          <div className="text-xs text-mye-ink-muted">
            Arrastra <strong>varios archivos</strong> aquí o
            <label className="ml-1 underline text-mye-accent cursor-pointer">
              selecciona desde tu equipo
              <input type="file" multiple
                     accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
                     onChange={(e) => uploadBatch(e.target.files)}
                     className="hidden"
                     data-testid="evidence-bulk-file-input" />
            </label>
          </div>
          <div className="text-[10px] font-mono text-mye-ink-muted mt-1">
            JPG · PNG · WebP · HEIC · PDF · máx 10 MB cada uno
          </div>
        </div>
      )}

      {/* Bulk progress */}
      {bulk.active && (
        <div className="rounded-md border border-mye-accent/30 bg-mye-accent/5 px-3 py-2 space-y-1"
             data-testid="evidence-bulk-progress">
          <div className="flex items-center gap-2 text-xs">
            {bulk.done < bulk.total ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-mye-accent" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5 text-status-resolved" />
            )}
            <span className="font-mono">{bulk.done}/{bulk.total}</span>
            <span className="text-mye-ink-muted">
              {bulk.done < bulk.total ? "Subiendo evidencias…" : "Subida completada"}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-mye-border overflow-hidden">
            <div className="h-full bg-mye-accent transition-all"
                 style={{ width: `${(bulk.done / bulk.total) * 100}%` }} />
          </div>
          {bulk.errors.length > 0 && (
            <ul className="text-[11px] text-status-escalated pt-1 list-disc pl-4">
              {bulk.errors.slice(0, 5).map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          )}
        </div>
      )}

      {loading ? (
        <div className="text-xs text-mye-ink-muted font-mono">Cargando…</div>
      ) : items.length === 0 ? (
        <div className="text-xs text-mye-ink-muted">
          Sin evidencias. Agrega al menos 2 fotos antes de enviar el reclamo al carrier (R35).
        </div>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="evidence-list">
          {items.map((ev) => (
            <EvidenceItem key={ev.id} ev={ev} disabled={disabled} onDelete={() => remove(ev.id)} />
          ))}
        </ul>
      )}

      {!disabled && (
        <button onClick={() => setShowAdd(true)}
                data-testid="evidence-add-btn"
                className="inline-flex items-center gap-1.5 rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition">
          <Upload className="h-3.5 w-3.5" /> Agregar evidencia con geolocalización
        </button>
      )}

      {showAdd && (
        <UploadModal
          ownerKind={ownerKind} ownerId={ownerId}
          onClose={() => setShowAdd(false)}
          onUploaded={async () => {
            setShowAdd(false);
            await refresh();
            onChanged && onChanged();
          }}
        />
      )}
    </div>
  );
}

function EvidenceItem({ ev, onDelete, disabled }) {
  const isImage = ev.kind === "photo";
  const fileUrl = `${API}/evidencias/${ev.id}/file`;
  const [src, setSrc] = useState(null);
  const srcRef = useRef(null);
  // Authenticated fetch for inline preview (since the file endpoint is bearer-protected)
  useEffect(() => {
    if (!isImage) return;
    let cancelled = false;
    fetch(fileUrl, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((b) => {
        if (cancelled) return;
        const url = URL.createObjectURL(b);
        srcRef.current = url;
        setSrc(url);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (srcRef.current) URL.revokeObjectURL(srcRef.current);
      srcRef.current = null;
    };
     
  }, [ev.id]);

  async function downloadFull() {
    try {
      const r = await fetch(fileUrl, { headers: { Authorization: `Bearer ${getToken()}` } });
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = ev.filename || `evidence-${ev.id}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { /* ignore */ }
  }

  return (
    <li className="rounded-md border border-mye-border bg-mye-app/40 overflow-hidden" data-testid={`evidence-item-${ev.id}`}>
      <div className="aspect-square bg-mye-ink/5 grid place-items-center cursor-pointer"
           onClick={downloadFull}>
        {isImage && src ? (
          <img src={src} alt={ev.filename}
               className="w-full h-full object-cover" data-testid={`evidence-img-${ev.id}`} />
        ) : isImage ? (
          <Loader2 className="h-6 w-6 animate-spin text-mye-ink-muted" />
        ) : (
          <FileText className="h-10 w-10 text-mye-ink-muted" />
        )}
      </div>
      <div className="p-2 space-y-1 text-[11px]">
        <div className="font-mono truncate" title={ev.filename}>{ev.filename}</div>
        <div className="font-mono text-mye-ink-muted">
          {Math.round((ev.size_bytes || 0) / 1024)} KB
          {ev.lat && ev.lng && (
            <span className="ml-2 inline-flex items-center gap-1 text-mye-accent">
              <MapPin className="h-3 w-3" />
              {ev.lat.toFixed(3)}, {ev.lng.toFixed(3)}
            </span>
          )}
        </div>
        {ev.location_label && (
          <div className="text-mye-ink-muted truncate" title={ev.location_label}>
            {ev.location_label}
          </div>
        )}
        {ev.note && (
          <div className="text-mye-ink-muted italic line-clamp-2">{ev.note}</div>
        )}
        {!disabled && (
          <button onClick={(e) => { e.stopPropagation(); onDelete(); }}
                  data-testid={`evidence-delete-${ev.id}`}
                  className="inline-flex items-center gap-1 text-status-escalated text-[11px] hover:underline">
            <Trash2 className="h-3 w-3" /> Borrar
          </button>
        )}
      </div>
    </li>
  );
}

function UploadModal({ ownerKind, ownerId, onClose, onUploaded }) {
  const fileInputRef = useRef();
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [marker, setMarker] = useState(null);
  const [locationLabel, setLocationLabel] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  function pickFile(f) {
    if (!f) return;
    setFile(f);
    if (f.type.startsWith("image/")) {
      const url = URL.createObjectURL(f);
      setPreview(url);
    } else {
      setPreview(null);
    }
  }

  function useGeolocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const m = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setMarker(m);
      },
      () => alert("No se pudo obtener la ubicación del navegador.")
    );
  }

  async function submit(e) {
    e.preventDefault();
    setErr(null);
    if (!file) { setErr("Selecciona un archivo."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (ownerKind === "ticket") fd.append("ticket_id", ownerId);
      else fd.append("claim_id", ownerId);
      if (marker) {
        fd.append("lat", String(marker.lat));
        fd.append("lng", String(marker.lng));
      }
      if (locationLabel) fd.append("location_label", locationLabel);
      if (note) fd.append("note", note);
      await api.post("/evidencias/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onUploaded();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 overflow-y-auto"
         onClick={onClose} data-testid="evidence-upload-modal">
      <div className="bg-white border border-mye-border rounded-lg w-full max-w-2xl p-6 space-y-4 shadow-xl my-auto"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <Upload className="h-4 w-4 text-mye-accent" />
          <h2 className="text-lg font-semibold">Agregar evidencia</h2>
          <button onClick={onClose} className="ml-auto text-mye-ink-muted hover:text-mye-ink"
                  data-testid="evidence-modal-close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={submit} className="space-y-3" data-testid="evidence-upload-form">
          <div>
            <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              Archivo (JPG / PNG / WebP / HEIC / PDF — máx 10 MB)
            </label>
            <div className="flex items-center gap-3">
              <input ref={fileInputRef} type="file"
                     accept="image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf"
                     onChange={(e) => pickFile(e.target.files?.[0])}
                     data-testid="evidence-file-input"
                     className="text-xs flex-1" />
              {preview && (
                <img src={preview} alt="preview"
                     className="h-16 w-16 object-cover rounded-md border border-mye-border"
                     data-testid="evidence-preview" />
              )}
              {file && !preview && (
                <span className="inline-flex items-center gap-1 text-xs text-mye-ink-muted">
                  <FileText className="h-3.5 w-3.5" /> {file.name}
                </span>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
                Ubicación (opcional)
              </label>
              <button type="button" onClick={useGeolocation}
                      data-testid="evidence-use-geo"
                      className="ml-auto inline-flex items-center gap-1 text-[11px] text-mye-accent hover:underline">
                <MapPin className="h-3.5 w-3.5" /> Usar mi ubicación
              </button>
            </div>
            <div className="rounded-md overflow-hidden border border-mye-border" style={{ height: 240 }}>
              <MapPicker marker={marker} onPick={(m) => { setMarker(m); }} />
            </div>
            <div className="text-[11px] font-mono text-mye-ink-muted">
              {marker
                ? `📍 ${marker.lat.toFixed(5)}, ${marker.lng.toFixed(5)}`
                : "Haz click en el mapa para marcar el punto del incidente."}
            </div>
            <input type="text" value={locationLabel} onChange={(e) => setLocationLabel(e.target.value)}
                   placeholder="Etiqueta (ej. 'Frente al CEDIS')"
                   data-testid="evidence-location-label"
                   className="w-full rounded-md border border-mye-border px-3 py-2 text-sm" />
          </div>

          <div>
            <label className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              Nota (opcional)
            </label>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
                      placeholder="Detalles del daño, número de bultos, etc."
                      data-testid="evidence-note"
                      className="w-full rounded-md border border-mye-border px-3 py-2 text-sm" />
          </div>

          {err && (
            <div className="rounded-md border border-status-escalated/40 bg-status-escalated/5 px-3 py-2 text-xs text-status-escalated"
                 data-testid="evidence-upload-error">
              <AlertTriangle className="h-3.5 w-3.5 inline mr-1" /> {err}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
                    className="rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition">
              Cancelar
            </button>
            <button type="submit" disabled={busy || !file}
                    data-testid="evidence-upload-submit"
                    className="rounded-md bg-mye-accent text-white px-3 py-2 text-xs hover:opacity-90 transition disabled:opacity-50">
              {busy ? "Subiendo…" : "Subir evidencia"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
