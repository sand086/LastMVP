/**
 * AdminPlatformCarriers — /admin/platform/carriers (root_dev only).
 *
 * Configura credenciales de carriers a NIVEL PLATAFORMA. Cualquier tenant que
 * NO tenga override por-cliente y NO tenga creds propias en `carriers` heredará
 * estas credenciales (regulado por tenant_access whitelist).
 *
 * Reusa CarrierConfigDialog con apiBase="/platform/carriers".
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, KeyRound, Plus, Users, Shield, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { CARRIER_SCHEMAS } from "./hierarchy/carrierSchemas";
import CarrierConfigDialog from "./hierarchy/CarrierConfigDialog";
import TenantAccessDialog from "./platform/TenantAccessDialog";


export default function AdminPlatformCarriers() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(null); // {code}
  const [accessDialog, setAccessDialog] = useState(null); // {code, name}

  async function refresh() {
    setLoading(true);
    try {
      const r = await api.get("/platform/carriers");
      setItems(r.data?.data?.items || []);
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || "Error cargando");
    } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, []);

  const configuredCodes = new Set(items.map((c) => c.code));
  const availableCodes = Object.keys(CARRIER_SCHEMAS)
    .filter((c) => !configuredCodes.has(c));

  return (
    <div className="min-h-screen bg-mye-app text-mye-ink" data-testid="admin-platform-carriers-page">
      <header className="bg-mye-bg border-b border-mye-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate(-1)}
                  className="text-mye-ink-muted hover:text-mye-ink"
                  data-testid="back-btn">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
              PROMPT 20.X · Plataforma
            </div>
            <div className="font-semibold flex items-center gap-2">
              <Shield className="h-4 w-4 text-mye-accent" />
              Carriers de plataforma (root_dev)
            </div>
          </div>
        </div>
      </header>

      <main className="px-6 py-6 max-w-5xl mx-auto space-y-6">
        <div className="bg-white border border-mye-border rounded-lg p-5">
          <h2 className="font-semibold text-lg mb-1">Configuración general (read-only para tenants)</h2>
          <p className="text-sm text-mye-ink-muted leading-relaxed">
            Estas credenciales son <strong>propias de MyExcellence</strong> y se prestan a los tenants
            según el modelo de billing. La jerarquía de resolución es:
            <span className="font-mono text-[11px] mt-2 block bg-mye-primary-soft/40 rounded p-2">
              cliente.carriers.&lt;code&gt; → tenant.carriers (con api_creds_ref propio) → <strong className="text-mye-accent">platform_carrier_configs.&lt;code&gt;</strong>
            </span>
          </p>
        </div>

        {loading ? (
          <div className="text-sm text-mye-ink-muted flex items-center gap-2">
            <Loader2 className="h-3 w-3 animate-spin" /> Cargando…
          </div>
        ) : (
          <div className="bg-white border border-mye-border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-mye-border">
              <div>
                <div className="font-medium">Carriers configurados · {items.length}</div>
                <div className="text-[11px] text-mye-ink-muted">
                  Carriers con credenciales generales activas
                </div>
              </div>
              {availableCodes.length > 0 && (
                <select onChange={(e) => {
                          if (e.target.value) {
                            setDialog({ code: e.target.value });
                            e.target.value = "";
                          }
                        }}
                        className="rounded-md border border-mye-border bg-white px-3 py-1.5 text-xs"
                        data-testid="platform-add-carrier-select">
                  <option value="">+ Agregar carrier…</option>
                  {availableCodes.map((c) => (
                    <option key={c} value={c}>{CARRIER_SCHEMAS[c].label}</option>
                  ))}
                </select>
              )}
            </div>
            {items.length === 0 ? (
              <div className="px-5 py-10 text-center text-sm text-mye-ink-muted">
                No hay carriers configurados a nivel plataforma todavía.
                <br />
                Usá el menú "+ Agregar carrier…" para empezar.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-mye-primary-soft/40 text-[11px] uppercase tracking-[0.1em] font-mono text-mye-ink-muted">
                  <tr>
                    <th className="text-left px-5 py-2">Carrier</th>
                    <th className="text-left px-5 py-2">Estado</th>
                    <th className="text-left px-5 py-2">Billing</th>
                    <th className="text-left px-5 py-2">Tenants whitelist</th>
                    <th className="text-right px-5 py-2">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => {
                    const schema = CARRIER_SCHEMAS[c.code];
                    const accessCount = Object.keys(c.tenant_access || {}).length;
                    return (
                      <tr key={c.code} className="border-t border-mye-border"
                          data-testid={`platform-carrier-row-${c.code}`}>
                        <td className="px-5 py-3">
                          <div className="font-medium flex items-center gap-1.5">
                            <KeyRound className="h-3.5 w-3.5 text-mye-accent" />
                            {schema?.label || c.code}
                          </div>
                          <div className="text-[10px] font-mono text-mye-ink-muted">{c.code}</div>
                        </td>
                        <td className="px-5 py-3">
                          {c.api_key_set ? (
                            <span className="font-mono text-[11px] text-status-resolved">
                              ✓ cifrada · {c.enabled === false ? "DESACTIVADA" : "activa"}
                            </span>
                          ) : (
                            <span className="font-mono text-[11px] text-mye-ink-muted">sin api_key</span>
                          )}
                        </td>
                        <td className="px-5 py-3 font-mono text-[11px] text-mye-ink-muted">
                          {c.billing_mode || "platform_pays"}
                        </td>
                        <td className="px-5 py-3">
                          <button onClick={() => setAccessDialog({ code: c.code, name: schema?.label || c.code })}
                                  className="inline-flex items-center gap-1 rounded-md border border-mye-border bg-white px-2 py-1 text-[11px] hover:bg-mye-primary-soft transition"
                                  data-testid={`platform-access-btn-${c.code}`}>
                            <Users className="h-3 w-3" />
                            {accessCount === 0
                              ? "abierto a todos"
                              : `${accessCount} tenant${accessCount === 1 ? "" : "s"}`}
                          </button>
                        </td>
                        <td className="px-5 py-3 text-right">
                          <button onClick={() => setDialog({ code: c.code })}
                                  className="rounded-md border border-mye-border bg-white px-3 py-1 text-[11px] hover:bg-mye-primary-soft transition"
                                  data-testid={`platform-edit-btn-${c.code}`}>
                            Editar
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </main>

      {dialog && (
        <CarrierConfigDialog
          clientId="platform"
          clientName="MyExcellence (plataforma)"
          carrierCode={dialog.code}
          apiBase="/platform/carriers"
          onClose={() => setDialog(null)}
          onSaved={refresh}
        />
      )}

      {accessDialog && (
        <TenantAccessDialog
          code={accessDialog.code}
          carrierName={accessDialog.name}
          onClose={() => setAccessDialog(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
