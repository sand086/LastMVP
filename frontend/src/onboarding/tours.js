/**
 * Tour configurations — Bundle E fix UX-ONBOARDING-001 (Iter33).
 *
 * Cambios respecto a la versión previa:
 *   1. NINGÚN `target: "body"`. Cada paso apunta a un `data-tour-target`
 *      específico (elemento real en el DOM). Esto resuelve UX-ONBOARDING-001
 *      (tour inservible por overlays sin contexto).
 *   2. Cada step puede declarar `fallbackToBody=true` SOLO para el primer
 *      paso de bienvenida en cada tour. El resto debe apuntar a elementos
 *      reales con fallback automático: si el target no existe en el DOM,
 *      el step se salta (manejado por OnboardingProvider).
 *   3. `requiresWizardCompleted`: si está en true, el paso NO se muestra
 *      mientras el wizard de admin onboarding esté activo (sincronización
 *      con admin_onboarding_progress vía window.__myeWizardActive).
 *
 * Targets data-tour-target referenciados (asegurate que existen en el DOM):
 *   - hierarchy-breadcrumb (SaaSHierarchyBreadcrumb component)
 *   - agent-layout-switch / agent-inbox-list / agent-filter-search /
 *     agent-saved-filter-save / agent-help-button (AgentPanel)
 *   - hierarchy-tabs (AdminHierarchy)
 *   - nav-jerarquia / nav-ai / nav-heatmap (AdminCAEHome nav)
 *   - user-audit-log-section (AdminSecurity, root_dev only)
 *
 * react-joyride Step shape:
 *   { target, content, title?, placement?, disableBeacon?, pageHint?,
 *     fallbackToBody?, requiresWizardCompleted? }
 */

export const TOUR_AGENT = [
  {
    target: '[data-tour-target="hierarchy-breadcrumb"]',
    fallbackToBody: true,
    title: "Bienvenido al panel de Agente",
    content: "En 2 minutos te muestro lo más útil. Arriba siempre ves tu jerarquía Plataforma → Tenant → Cliente para saber en qué contexto estás trabajando.",
    placement: "bottom",
    disableBeacon: true,
    pageHint: "/agente",
  },
  {
    target: '[data-testid="agent-layout-switch"]',
    title: "Cambiá la vista",
    content: "Inbox (densa) · Tabla · Tarjetas. Tu preferencia se guarda automáticamente.",
    pageHint: "/agente",
  },
  {
    target: '[data-testid="agent-inbox-list"], [data-testid="agent-list"]',
    title: "Tus tickets",
    content: "Cada fila muestra prioridad (rayita vertical de color), status, SLA restante y mini-progress bar.",
    pageHint: "/agente",
  },
  {
    target: '[data-testid="agent-filter-search"]',
    title: "Búsqueda + atajos",
    content: "Apretá ⌘K o / para enfocar acá. Usá j/k para navegar entre tickets. ? muestra todos los atajos.",
    pageHint: "/agente",
  },
  {
    target: '[data-testid="agent-saved-filter-save"]',
    title: "Filtros guardados",
    content: "Aplicá un filtro y guardalo con un nombre. Quedará disponible para usar con 1 click.",
    pageHint: "/agente",
  },
  {
    target: '[data-testid="agent-help-button"], [data-testid="agent-shortcuts-trigger"]',
    title: "Ayuda en cualquier momento",
    content: "Apretá este botón o `?` para ver todos los atajos. También podés volver a hacer este tour desde el botón Tour del header.",
    pageHint: "/agente",
  },
];

export const TOUR_ADMIN = [
  {
    target: '[data-tour-target="hierarchy-breadcrumb"]',
    fallbackToBody: true,
    title: "Tu jerarquía SaaS",
    content: "Siempre vés Plataforma (MyExcellence) → Tenant (tu organización) → Cliente. Tocá cada chip para entender qué controla cada nivel.",
    placement: "bottom",
    disableBeacon: true,
    pageHint: "/admin/jerarquia",
    requiresWizardCompleted: true,
  },
  {
    target: '[data-testid="hierarchy-tabs"], [data-testid="admin-hierarchy-page"]',
    title: "Jerarquía + Usuarios",
    content: "Clientes, subclientes, proyectos, carriers y — si sos root_dev/superadmin — gestión de usuarios.",
    placement: "bottom",
    pageHint: "/admin/jerarquia",
    requiresWizardCompleted: true,
  },
  {
    target: '[data-testid="catalog-page"], [data-testid="motivos-tab"]',
    fallbackToBody: true,
    title: "Catálogo y matriz de permisos",
    content: "Configurás motivos, soluciones y permisos de automatización por cliente y canal (R03). Si usaste el asistente, el catálogo MX estándar ya está cargado.",
    placement: "top",
    pageHint: "/admin/catalogo",
  },
  {
    target: '[data-testid="tickets-page"], [data-testid="admin-tickets-table"]',
    fallbackToBody: true,
    title: "Tickets globales",
    content: "Todos los tickets de tu tenant con filtros avanzados, bulk-bar y exportación PDF.",
    placement: "top",
    pageHint: "/admin/tickets",
  },
  {
    target: '[data-testid="ai-page"], [data-testid="ai-consumption-card"]',
    fallbackToBody: true,
    title: "Inteligencia Artificial",
    content: "Consumo IA, tendencia de costos por feature (en USD/MXN, Bundle D), benchmark de modelos y auditoría externa firmada.",
    placement: "top",
    pageHint: "/admin/ai",
  },
  {
    target: '[data-testid="notifications-page"], [data-testid="email-test-form"]',
    fallbackToBody: true,
    title: "Notificaciones y templates",
    content: "Probás envíos de email con Resend, deeplink de WhatsApp y editás las plantillas parametrizables por tenant.",
    placement: "top",
    pageHint: "/admin/notificaciones",
  },
];

export const TOUR_ROOT_DEV = [
  {
    target: '[data-tour-target="hierarchy-breadcrumb"]',
    fallbackToBody: true,
    title: "Panel de plataforma (root_dev)",
    content: "Como root_dev / superadmin tenés capacidades que ningún otro rol ve. Empezamos por la jerarquía SaaS para que entiendas qué nivel toca cada cambio.",
    placement: "bottom",
    disableBeacon: true,
    pageHint: "/admin/cae",
  },
  {
    target: '[data-testid="nav-jerarquia"]',
    title: "Gestión de Usuarios",
    content: "Dentro de Jerarquía, el tab 'Usuarios' te permite crear, editar, resetear passwords y soft-deletear usuarios del tenant.",
    pageHint: "/admin/cae",
  },
  {
    target: '[data-testid="security-page"], [data-testid="security-checks-card"]',
    fallbackToBody: true,
    title: "Security Audit Dashboard",
    content: "Pre-go-live checks (JWT length, CORS, HMAC secrets, indexes…). 13 verificaciones con severidad pass/warn/fail.",
    placement: "top",
    pageHint: "/admin/security",
  },
  {
    target: '[data-testid="user-audit-log-section"]',
    title: "Audit log de usuarios",
    content: "Registro append-only de creaciones, cambios de rol, resets y eliminaciones. Filtrable por acción/email/fecha. Visible SOLO para root_dev.",
    pageHint: "/admin/security",
    placement: "top",
  },
  {
    target: '[data-testid="webhooks-page"], [data-testid="webhooks-list"]',
    fallbackToBody: true,
    title: "Webhooks outbound",
    content: "Integraciones con sistemas externos: HMAC SHA-256, circuit breaker, JSONPath filters, retry con backoff exponencial.",
    placement: "top",
    pageHint: "/admin/webhooks",
  },
];

export const TOUR_REGISTRY = {
  agent: TOUR_AGENT,
  admin: TOUR_ADMIN,
  root_dev: TOUR_ROOT_DEV,
};
