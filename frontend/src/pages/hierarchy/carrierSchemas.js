/**
 * carrierSchemas — declarative config schema per carrier.
 *
 * Each schema describes which fields the per-client carrier config dialog
 * should render. The generic <CarrierConfigDialog/> consumes this to build
 * the form without duplicating UI per adapter.
 *
 * Field types:
 *   - secret:  password input (write-only; backend returns api_key_set:bool)
 *   - text:    single-line text
 *   - chips:   multi-value list (used by Routal's project_ids)
 *   - select:  one-of (used for env: sandbox/production)
 *   - bool:    checkbox
 *
 * Mapping to backend `clients.carriers.<code>` schema:
 *   - secret name → encrypted as `<name>_ref` (`api_key` → `api_key_ref`)
 *   - everything else stored as-is.
 *
 * The first chip in a `chips` field is rendered with a "default" star icon;
 * clicking another chip promotes it to default (used as fallback for 1:1
 * outbound calls). The schema must declare `defaultField` to know where to
 * persist the default value.
 */

export const CARRIER_SCHEMAS = {
  routal: {
    label: "Routal",
    description: "Plataforma de ruteo de última milla. 1 ApiKey por cliente, N proyectos.",
    fields: [
      { name: "api_key", type: "secret", label: "API Key",
        placeholder: "Pega tu private_key de Routal",
        helper: "Tu private_key desde Routal · Settings · API",
        required: true },
      { name: "project_ids", type: "chips", label: "project_ids",
        placeholder: "ej. 636aaed54235630d2258fa6d",
        helper: "1:N para ingesta · 1:1 para updates (★ default usado por send_instruction cuando la guía aún no trae project_id)",
        defaultField: "default_project_id",
        max: 50, required: true },
      { name: "base_url", type: "text", label: "Base URL",
        placeholder: "https://api.routal.com",
        helper: "Opcional · default api.routal.com" },
      { name: "enabled", type: "bool", label: "Integración activa",
        default: true },
    ],
  },

  dhl: {
    label: "DHL",
    description: "DHL Shipment Tracking - Unified. 1 ApiKey por aplicación.",
    fields: [
      { name: "api_key", type: "secret", label: "API Key (DHL-API-Key)",
        placeholder: "Pega tu Consumer Key de DHL Developer Portal",
        helper: "Consumer Key desde developer.dhl.com/user/apps",
        required: true },
      { name: "base_url", type: "select", label: "Entorno",
        options: [
          { value: "https://api-eu.dhl.com/track", label: "Producción (api-eu.dhl.com)" },
          { value: "https://api-test.dhl.com/track", label: "Sandbox (api-test.dhl.com)" },
        ],
        default: "https://api-eu.dhl.com/track" },
      { name: "enabled", type: "bool", label: "Integración activa",
        default: true },
    ],
  },

  fedex: {
    label: "FedEx",
    description: "FedEx Track API. OAuth2 client_credentials.",
    fields: [
      { name: "api_key", type: "secret", label: "Client ID",
        placeholder: "El client_id de tu API project FedEx",
        helper: "Desde developer.fedex.com → My Projects → API Key",
        required: true },
      { name: "client_secret", type: "secret", label: "Client Secret",
        placeholder: "El secret correspondiente",
        helper: "Se cifra junto al client_id con Fernet" },
      { name: "account_number", type: "text", label: "Account Number",
        placeholder: "ej. 510087860",
        helper: "Opcional · sólo necesario para algunos endpoints" },
      { name: "base_url", type: "select", label: "Entorno",
        options: [
          { value: "https://apis.fedex.com", label: "Producción (apis.fedex.com)" },
          { value: "https://apis-sandbox.fedex.com", label: "Sandbox (apis-sandbox.fedex.com)" },
        ],
        default: "https://apis-sandbox.fedex.com" },
      { name: "enabled", type: "bool", label: "Integración activa",
        default: true },
    ],
  },
};


export function getCarrierSchema(code) {
  return CARRIER_SCHEMAS[(code || "").toLowerCase()] || null;
}
