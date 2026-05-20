/**
 * Catálogo de eventos del bus admin — Bundle C (Mayo 2026).
 *
 * Single source of truth para los nombres de eventos. Convención:
 *     admin.<entidad>.<accion>
 *
 * Los componentes consumen estas constantes en lugar de strings literales
 * para evitar typos y facilitar refactors. Agregar nuevos eventos en futuros
 * Bundles ampliando este catálogo (no inventando strings ad-hoc).
 *
 * Payload por evento:
 *
 *   ADMIN_EVENTS.CARRIER_UPDATED   { client_id: string, carrier_code: string }
 *   ADMIN_EVENTS.CARRIER_DELETED   { client_id: string, carrier_code: string }
 *
 *   ADMIN_EVENTS.CLIENT_CREATED    { client_id: string }
 *   ADMIN_EVENTS.CLIENT_UPDATED    { client_id: string }
 *   ADMIN_EVENTS.CLIENT_DELETED    { client_id: string }
 *
 *   ADMIN_EVENTS.SUBCLIENT_CREATED { subclient_id: string, client_id: string }
 *   ADMIN_EVENTS.SUBCLIENT_UPDATED { subclient_id: string }
 *   ADMIN_EVENTS.SUBCLIENT_DELETED { subclient_id: string }
 *
 *   ADMIN_EVENTS.PROJECT_CREATED   { project_id: string }
 *   ADMIN_EVENTS.USER_CREATED      { user_id: string }
 */
export const ADMIN_EVENTS = Object.freeze({
  // Carriers (per-cliente)
  CARRIER_UPDATED:   "admin.carrier.updated",
  CARRIER_DELETED:   "admin.carrier.deleted",

  // Clientes
  CLIENT_CREATED:    "admin.client.created",
  CLIENT_UPDATED:    "admin.client.updated",
  CLIENT_DELETED:    "admin.client.deleted",

  // Subclientes
  SUBCLIENT_CREATED: "admin.subclient.created",
  SUBCLIENT_UPDATED: "admin.subclient.updated",
  SUBCLIENT_DELETED: "admin.subclient.deleted",

  // Proyectos
  PROJECT_CREATED:   "admin.project.created",
  PROJECT_UPDATED:   "admin.project.updated",
  PROJECT_DELETED:   "admin.project.deleted",

  // Usuarios
  USER_CREATED:      "admin.user.created",
  USER_UPDATED:      "admin.user.updated",
  USER_DELETED:      "admin.user.deleted",

  // Motivos / soluciones (futuros bundles, incluidos por completitud)
  MOTIVO_CREATED:    "admin.motivo.created",
  MOTIVO_UPDATED:    "admin.motivo.updated",
  MOTIVO_DELETED:    "admin.motivo.deleted",
  MOTIVO_IMPORTED:   "admin.motivo.imported",

  SOLUCION_CREATED:  "admin.solucion.created",
  SOLUCION_UPDATED:  "admin.solucion.updated",
  SOLUCION_DELETED:  "admin.solucion.deleted",

  // Onboarding wizard (Bundle E · Iter33)
  ONBOARDING_STEP_COMPLETED: "admin.onboarding.step_completed",
  ONBOARDING_STEP_SKIPPED:   "admin.onboarding.step_skipped",
  ONBOARDING_COMPLETED:      "admin.onboarding.completed",
  TENANT_CONFIGURED:         "admin.tenant.configured",
  AUTOMATION_MATRIX_CONFIGURED: "admin.automation_matrix.configured",
});
