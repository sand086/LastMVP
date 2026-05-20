/**
 * CarrierConfigDialog — modal genérico per-cliente para cualquier carrier.
 *
 * Reemplaza al `RoutalConfigDialog` específico. El render se construye desde
 * el schema declarativo en `carrierSchemas.js`, y la comunicación con backend
 * sigue siendo idéntica:
 *
 *   GET    /api/admin/clients/{client_id}/carriers/{code}
 *   PUT    /api/admin/clients/{client_id}/carriers/{code}
 *   DELETE /api/admin/clients/{client_id}/carriers/{code}
 *   POST   /api/admin/clients/{client_id}/carriers/{code}/test
 *
 * Para agregar un carrier nuevo SOLO se necesita extender `CARRIER_SCHEMAS`.
 * No hay branching especial por código de carrier.
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Loader2, Plus, Trash2, X, Power, KeyRound,
  CheckCircle2, XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { getCarrierSchema } from "./carrierSchemas";


export default function CarrierConfigDialog({ clientId, clientName,
                                                carrierCode, onClose, onSaved,
                                                /**
                                                 * Optional override of the REST base path.
                                                 *   - per-client:  `/admin/clients/${clientId}/carriers`
                                                 *   - platform:    `/platform/carriers`
                                                 *
                                                 * Default = per-client.
                                                 */
                                                apiBase = null,
                                              }) {
  const schema = getCarrierSchema(carrierCode);
  const baseUrl = apiBase || `/admin/clients/${clientId}/carriers`;
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [values, setValues] = useState({});      // current form state (no secrets initially)
  const [secretsSet, setSecretsSet] = useState({}); // {api_key: true, client_secret: false}
  const [chipInputs, setChipInputs] = useState({}); // {project_ids: "current typing"}

  // Build initial empty values from schema defaults.
  useEffect(() => {
    if (!schema) return;
    const init = {};
    schema.fields.forEach((f) => {
      if (f.type === "chips") init[f.name] = [];
      else if (f.type === "bool") init[f.name] = f.default ?? false;
      else init[f.name] = f.default ?? "";
      if (f.defaultField) init[f.defaultField] = "";
    });
    setValues(init);
  }, [schema?.label]);  // schema is stable per carrier code

  // Load existing config (if any).
  useEffect(() => {
    if (!schema) return;
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const r = await api.get(`${baseUrl}/${carrierCode}`);
        if (!alive) return;
        const d = r.data?.data || {};
        const next = {};
        const sec = {};
        schema.fields.forEach((f) => {
          if (f.type === "secret") {
            next[f.name] = "";  // never seed secrets back
            // Backend exposes "<name>_set" (PUT response) or generic api_key_set
            sec[f.name] = !!(d[`${f.name}_set`] || (f.name === "api_key" && d.api_key_set));
          } else if (f.type === "chips") {
            next[f.name] = d[f.name] || [];
          } else if (f.type === "bool") {
            next[f.name] = d[f.name] ?? f.default ?? false;
          } else {
            next[f.name] = d[f.name] || f.default || "";
          }
          if (f.defaultField) next[f.defaultField] = d[f.defaultField] || "";
        });
        setValues(next);
        setSecretsSet(sec);
      } catch (e) {
        toast.error(e.response?.data?.errors?.[0]?.message || "Error cargando config");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [clientId, carrierCode, schema]);

  const canSave = useMemo(() => {
    if (!schema) return false;
    for (const f of schema.fields) {
      if (!f.required) continue;
      // At platform level, "chips" fields (project_ids) are optional because
      // distribution to tenants is controlled via tenant_access whitelist.
      if (f.type === "chips" && apiBase === "/platform/carriers") continue;
      if (f.type === "secret") {
        if (!values[f.name] && !secretsSet[f.name]) return false;
      } else if (f.type === "chips") {
        if ((values[f.name] || []).length === 0) return false;
      } else if (!values[f.name]) {
        return false;
      }
    }
    return true;
  }, [schema, values, secretsSet, apiBase]);

  if (!schema) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div className="w-full max-w-md rounded-lg bg-white shadow-2xl border border-mye-border p-5">
          <div className="font-semibold text-mye-ink">Carrier no soportado</div>
          <p className="text-xs text-mye-ink-muted mt-1">
            No hay schema definido para <code className="font-mono">{carrierCode}</code>.
          </p>
          <div className="mt-3 flex justify-end">
            <button onClick={onClose} className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft">
              Cerrar
            </button>
          </div>
        </div>
      </div>
    );
  }

  function addChip(fieldName) {
    const v = (chipInputs[fieldName] || "").trim();
    if (!v) return;
    const list = values[fieldName] || [];
    if (list.includes(v)) {
      toast.message("Ya está en la lista");
      return;
    }
    const f = schema.fields.find((x) => x.name === fieldName);
    if (f?.max && list.length >= f.max) {
      toast.error(`Máximo ${f.max}`);
      return;
    }
    const next = { ...values, [fieldName]: [...list, v] };
    if (f?.defaultField && !values[f.defaultField]) next[f.defaultField] = v;
    setValues(next);
    setChipInputs({ ...chipInputs, [fieldName]: "" });
  }

  function removeChip(fieldName, v) {
    const f = schema.fields.find((x) => x.name === fieldName);
    const next = (values[fieldName] || []).filter((x) => x !== v);
    const update = { ...values, [fieldName]: next };
    if (f?.defaultField && values[f.defaultField] === v) {
      update[f.defaultField] = next[0] || "";
    }
    setValues(update);
  }

  async function save() {
    setBusy(true);
    setTestResult(null);
    try {
      const body = {};
      const isPlatform = apiBase === "/platform/carriers";
      // Platform-level endpoint ignores per-tenant fields (project_ids,
      // default_project_id, account_number) because those belong to the
      // whitelist (tenant_access) or per-client overrides, not to the
      // root credentials themselves.
      const platformBlacklist = new Set(["project_ids", "default_project_id", "account_number"]);
      schema.fields.forEach((f) => {
        if (isPlatform && platformBlacklist.has(f.name)) return;
        if (f.type === "secret") {
          if (values[f.name]) body[f.name] = values[f.name]; // only if typed
        } else if (f.type === "bool") {
          body[f.name] = !!values[f.name];
        } else {
          body[f.name] = values[f.name] || null;
        }
        if (f.defaultField && !isPlatform) {
          body[f.defaultField] = values[f.defaultField] || null;
        }
      });
      await api.put(`${baseUrl}/${carrierCode}`, body);
      toast.success(`${schema.label}: configuración guardada`);
      // Refresh secrets-set state
      const sec = { ...secretsSet };
      schema.fields.forEach((f) => {
        if (f.type === "secret" && values[f.name]) sec[f.name] = true;
      });
      setSecretsSet(sec);
      // Clear secret values
      const cleared = { ...values };
      schema.fields.forEach((f) => { if (f.type === "secret") cleared[f.name] = ""; });
      setValues(cleared);
      onSaved && onSaved();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error guardando");
    } finally { setBusy(false); }
  }

  async function runTest() {
    setTesting(true); setTestResult(null);
    try {
      const r = await api.post(`${baseUrl}/${carrierCode}/test`, {});
      setTestResult({ ok: !!r.data?.data?.pingable, raw: r.data?.data });
    } catch (e) {
      setTestResult({ ok: false, error: e.response?.data?.errors?.[0]?.message || e.message });
    } finally { setTesting(false); }
  }

  async function deleteCfg() {
    if (!window.confirm(`¿Eliminar la configuración ${schema.label} del cliente ${clientName}?`)) return;
    setBusy(true);
    try {
      await api.delete(`${baseUrl}/${carrierCode}`);
      toast.success("Configuración eliminada");
      onSaved && onSaved(); onClose && onClose();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error eliminando");
    } finally { setBusy(false); }
  }

  const anySecretSet = Object.values(secretsSet).some(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
         data-testid="carrier-cfg-dialog">
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-2xl border border-mye-border max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
              Integración por cliente
            </div>
            <div className="font-semibold text-mye-ink flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-mye-accent" />
              {schema.label} · {clientName}
            </div>
            <div className="text-[11px] text-mye-ink-muted mt-0.5">{schema.description}</div>
          </div>
          <button onClick={onClose} className="text-mye-ink-muted hover:text-mye-ink"
                  data-testid="carrier-cfg-close">
            <X className="h-4 w-4" />
          </button>
        </div>

        {loading ? (
          <div className="p-10 flex items-center justify-center text-mye-ink-muted text-sm">
            <Loader2 className="h-4 w-4 animate-spin mr-2" /> Cargando…
          </div>
        ) : (
          <div className="px-5 py-4 space-y-5">
            {schema.fields.map((f) => (
              <FieldRenderer
                key={f.name}
                field={f}
                values={values}
                setValues={setValues}
                secretsSet={secretsSet}
                chipInputs={chipInputs}
                setChipInputs={setChipInputs}
                onAddChip={() => addChip(f.name)}
                onRemoveChip={(v) => removeChip(f.name, v)}
              />
            ))}

            {testResult && (
              <div className={`rounded-md border px-3 py-2 text-sm flex items-start gap-2 ${
                testResult.ok
                  ? "border-status-resolved/30 bg-status-resolved/5"
                  : "border-status-escalated/30 bg-status-escalated/5"
              }`} data-testid="carrier-cfg-test-result">
                {testResult.ok
                  ? <CheckCircle2 className="h-4 w-4 text-status-resolved shrink-0 mt-0.5" />
                  : <XCircle className="h-4 w-4 text-status-escalated shrink-0 mt-0.5" />}
                <div>
                  <div className="font-medium">
                    {testResult.ok
                      ? `${schema.label} respondió correctamente`
                      : `${schema.label} no respondió`}
                  </div>
                  {testResult.error && (
                    <div className="text-[11px] text-mye-ink-muted">{testResult.error}</div>
                  )}
                  {testResult.raw?.project_ids && (
                    <div className="text-[11px] font-mono text-mye-ink-muted mt-0.5">
                      project_ids: {testResult.raw.project_ids.join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {!loading && (
          <div className="px-5 py-3 border-t border-mye-border flex flex-wrap items-center justify-between gap-2 bg-mye-primary-soft/30">
            <div className="flex items-center gap-2">
              <button onClick={runTest} disabled={!anySecretSet || testing}
                      className="inline-flex items-center gap-1.5 rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition disabled:opacity-50"
                      data-testid="carrier-cfg-test">
                {testing && <Loader2 className="h-3 w-3 animate-spin" />}
                Probar conexión
              </button>
              {anySecretSet && (
                <button onClick={deleteCfg} disabled={busy}
                        className="inline-flex items-center gap-1.5 rounded-md border border-status-escalated/30 bg-white px-3 py-1.5 text-xs text-status-escalated hover:bg-status-escalated/5 transition disabled:opacity-50"
                        data-testid="carrier-cfg-delete">
                  <Trash2 className="h-3 w-3" /> Eliminar
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button onClick={onClose}
                      className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs hover:bg-mye-primary-soft transition"
                      data-testid="carrier-cfg-cancel">
                Cerrar
              </button>
              <button onClick={save} disabled={busy || !canSave}
                      className="inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-50"
                      data-testid="carrier-cfg-save">
                {busy && <Loader2 className="h-3 w-3 animate-spin" />}
                Guardar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function FieldRenderer({ field: f, values, setValues, secretsSet,
                          chipInputs, setChipInputs,
                          onAddChip, onRemoveChip }) {
  const set = (val) => setValues({ ...values, [f.name]: val });
  const labelClass = "block text-[11px] uppercase tracking-[0.15em] font-mono text-mye-ink-muted mb-1";
  const helperClass = "text-[10px] text-mye-ink-muted mt-1.5 leading-relaxed";
  const inputClass = "w-full rounded-md border border-mye-border bg-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-mye-accent/40";

  if (f.type === "secret") {
    return (
      <div>
        <label className={labelClass}>
          {f.label}
          {secretsSet[f.name] && <span className="ml-1 normal-case tracking-normal text-status-resolved">· ya configurado</span>}
        </label>
        <input type="password" value={values[f.name] || ""}
               onChange={(e) => set(e.target.value)}
               placeholder={secretsSet[f.name] ? "Dejar vacío para conservar el actual" : f.placeholder}
               className={inputClass}
               data-testid={`carrier-cfg-${f.name}`} />
        {f.helper && <div className={helperClass}>{f.helper}</div>}
      </div>
    );
  }

  if (f.type === "text") {
    return (
      <div>
        <label className={labelClass}>{f.label}</label>
        <input value={values[f.name] || ""}
               onChange={(e) => set(e.target.value)}
               placeholder={f.placeholder}
               className={inputClass}
               data-testid={`carrier-cfg-${f.name}`} />
        {f.helper && <div className={helperClass}>{f.helper}</div>}
      </div>
    );
  }

  if (f.type === "select") {
    return (
      <div>
        <label className={labelClass}>{f.label}</label>
        <select value={values[f.name] || ""}
                onChange={(e) => set(e.target.value)}
                className={inputClass.replace("font-mono", "")}
                data-testid={`carrier-cfg-${f.name}`}>
          {f.options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {f.helper && <div className={helperClass}>{f.helper}</div>}
      </div>
    );
  }

  if (f.type === "bool") {
    return (
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={!!values[f.name]}
               onChange={(e) => set(e.target.checked)}
               className="rounded border-mye-border focus:ring-mye-accent/40"
               data-testid={`carrier-cfg-${f.name}`} />
        <Power className="h-3.5 w-3.5 text-mye-ink-muted" /> {f.label}
      </label>
    );
  }

  if (f.type === "chips") {
    const list = values[f.name] || [];
    const defaultVal = f.defaultField ? values[f.defaultField] : null;
    return (
      <div>
        <label className={labelClass}>
          {f.label} · {list.length} configurados
        </label>
        <div className="flex flex-wrap gap-2 mb-2 min-h-[28px]"
             data-testid={`carrier-cfg-${f.name}-list`}>
          {list.map((v) => (
            <span key={v}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-mono border ${
                    v === defaultVal
                      ? "border-mye-accent/40 bg-mye-accent/5 text-mye-ink"
                      : "border-mye-border bg-mye-primary-soft text-mye-ink"
                  }`}
                  data-testid={`carrier-cfg-${f.name}-chip-${v.slice(0, 8)}`}>
              {v === defaultVal && <span className="text-mye-accent">★</span>}
              {f.defaultField ? (
                <button onClick={() => setValues({ ...values, [f.defaultField]: v })}
                        className="hover:underline" title="Marcar como default">
                  {v}
                </button>
              ) : <span>{v}</span>}
              <button onClick={() => onRemoveChip(v)}
                      className="text-mye-ink-muted hover:text-status-escalated"
                      title="Quitar">
                <Trash2 className="h-3 w-3" />
              </button>
            </span>
          ))}
          {list.length === 0 && (
            <span className="text-[11px] text-mye-ink-muted italic">Aún no agregaste valores</span>
          )}
        </div>
        <div className="flex gap-2">
          <input value={chipInputs[f.name] || ""}
                 onChange={(e) => setChipInputs({ ...chipInputs, [f.name]: e.target.value })}
                 onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), onAddChip())}
                 placeholder={f.placeholder}
                 className={`flex-1 ${inputClass}`}
                 data-testid={`carrier-cfg-${f.name}-input`} />
          <button onClick={onAddChip}
                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-3 py-2 text-xs hover:bg-mye-primary-soft transition"
                  data-testid={`carrier-cfg-${f.name}-add`}>
            <Plus className="h-3.5 w-3.5" /> Agregar
          </button>
        </div>
        {f.helper && <div className={helperClass}>{f.helper}</div>}
      </div>
    );
  }

  return null;
}
