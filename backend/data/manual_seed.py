"""
Manual seed catalog — single source of truth for the platform Knowledge Hub.

Each manual entry has metadata + a `content` list of structured blocks:
  - {type: "callout", text}
  - {type: "section", title, items: [str]}
  - {type: "table", headers: [str], rows: [[str]]}
  - {type: "tip", text}
  - {type: "warning", text}

`seed_manuals` (in manual_routes.py) calls `get_manuals_seed()` and upserts by slug,
so we can extend or rewrite content without losing existing IDs.
"""

VALID_SECTIONS_EXTENDED = [
    "Paneles", "Operación de Envíos", "Configuración",
    "Integraciones", "Inteligencia Artificial", "Documentación Técnica",
]


def get_manuals_seed() -> list[dict]:
    return [
        # ─────────────── PANELES ───────────────
        {
            "title": "Dashboard Principal",
            "subtitle": "Panel de control con métricas en tiempo real de entregas, SLA y operaciones",
            "section": "Paneles",
            "tags": ["dashboard", "metricas", "kpi", "tiempo-real", "websocket"],
            "icon_key": "layout-dashboard",
            "slug": "dashboard-principal",
            "sort_order": 1,
            "content": [
                {"type": "callout", "text": "El Dashboard es la vista principal de LastMile OS. Muestra el estado actual de todas las operaciones de entrega en tiempo real con WebSocket auto-reconectable y polling adaptativo."},
                {"type": "section", "title": "Acceso", "items": ["Disponible para todos los roles", "Se actualiza automáticamente vía WebSocket", "ErrorBoundary global protege contra fallos transitorios", "Hook useApi maneja retry + circuit breaker en cada fetch"]},
                {"type": "section", "title": "Indicadores KPI", "items": ["Rutas activas del día", "Paquetes entregados / pendientes / fallidos", "Tasa de entrega en tiempo real", "Última sincronización Kosmo", "Estado de salud (degraded warnings)"]},
                {"type": "section", "title": "Pulse Banner", "items": ["Aparece SOLO en rutas in_progress", "Muestra factibilidad operativa: % progreso vs tiempo transcurrido", "Verde/ámbar/rojo según desviación de SLA dinámico", "Configurable por proveedor en Settings → Sistema"]},
                {"type": "table", "headers": ["KPI", "Descripción", "Actualización"], "rows": [["Rutas activas", "Número de rutas en progreso hoy", "Tiempo real"], ["Tasa entrega", "% paquetes entregados vs total", "Cada sync"], ["Incidencias abiertas", "Incidencias sin resolver", "Tiempo real"], ["Pulse rojo", "Rutas con desviación crítica de SLA", "Cada 30s"]]},
                {"type": "section", "title": "Tabla de rutas", "items": ["Order ID clickeable lleva al detalle", "Barra de progreso visual (verde ≥70%, ámbar ≥40%, rojo <40%)", "Filtro por estado: Programada / En Progreso / Cerrada", "Búsqueda por driver, proveedor u Order ID"]},
                {"type": "tip", "text": "Usa el botón de sincronización manual para forzar una actualización de estados desde Kosmo cuando necesites datos inmediatos."},
                {"type": "warning", "text": "El dashboard filtra por la fecha del día actual. Si no ves rutas, verifica que existan rutas para la fecha seleccionada."},
            ],
        },
        {
            "title": "Reportes y Analítica",
            "subtitle": "7 tabs de reportes con KPIs, gráficos, tendencias históricas y exportación PDF",
            "section": "Paneles",
            "tags": ["reportes", "analitica", "kpi", "pdf", "sla", "calidad", "tendencias"],
            "icon_key": "bar-chart-3",
            "slug": "reportes-analitica",
            "sort_order": 2,
            "content": [
                {"type": "callout", "text": "El módulo de Reportes consolida todas las métricas operativas con filtros por periodo, cliente y proveedor. Incluye 7 tabs y exportación PDF nativa."},
                {"type": "section", "title": "Tabs disponibles", "items": ["Proveedores: métricas por proveedor (entrega, visita, SLA)", "Drivers: rendimiento individual por mensajero", "Incidencias: desglose por tipo y severidad", "Intentos: análisis de primer y segundo intento", "Calidad: scores de evidencia por tipo de entrega", "SLA: cumplimiento vs target por proveedor", "Tendencias: líneas históricas de delivery_rate y entregados/fallidos/pendientes"]},
                {"type": "table", "headers": ["Filtro", "Tipo", "Descripción"], "rows": [["Periodo", "Selector", "7d, 15d, mes actual, mes anterior, custom"], ["Cliente", "Dropdown", "Filtra por cliente asignado"], ["Proveedor", "Dropdown", "Filtra por proveedor logístico"], ["Agrupación (Tendencias)", "Toggle", "Día / Semana / Mes"]]},
                {"type": "section", "title": "Exportación PDF (jsPDF + autotable)", "items": ["Botón 'Exportar PDF' genera documento multi-página", "Portada con donut nativo de universos (Entregados/Fallidos/Pendientes) + 5 stat boxes", "Donut de incidencias con % del total", "Tablas Proveedores y Drivers (sin columna 'Días op.' en reportes diarios)", "Sección 'Herramientas tecnológicas' con narrativa IA paginada", "Footer con paginado, target SLA dinámico vs tasa real"]},
                {"type": "section", "title": "Generador IA del informe", "items": ["Genera narrativa ejecutiva con Claude Sonnet (no Haiku) antes de exportar", "Costo por reporte ~$0.04 USD (logged en token_usage_log)", "Incluye observaciones críticas y recomendaciones contextuales"]},
                {"type": "tip", "text": "Genera el reporte IA antes de exportar PDF para incluir el análisis narrativo en el documento."},
                {"type": "tip", "text": "Para Power BI usa /api/reports/operational-detail?date_from=&date_to= con refresh token (90d). Las measures DAX están documentadas en el manual 'Diccionario técnico'."},
            ],
        },

        # ─────────────── OPERACIÓN ───────────────
        {
            "title": "Carga de Layouts (Cosmo)",
            "subtitle": "Proceso de 3 pasos para importar rutas desde archivos CSV y XLSX de Kosmo",
            "section": "Operación de Envíos",
            "tags": ["layout", "upload", "cosmo", "csv", "xlsx", "importar"],
            "icon_key": "upload",
            "slug": "carga-layouts",
            "sort_order": 10,
            "content": [
                {"type": "callout", "text": "El módulo de Layout permite importar rutas de entrega desde los archivos que exporta Kosmo. El proceso tiene 3 pasos secuenciales con validación previa."},
                {"type": "section", "title": "Paso 1: History Orders (CSV)", "items": ["Descarga el archivo history-orders.csv desde Kosmo", "Columnas requeridas: order_id, order_reference_id, tracking_url", "El sistema detecta automáticamente paquetes ya existentes y los actualiza"]},
                {"type": "section", "title": "Paso 2: Route Summary (XLSX)", "items": ["Descarga el archivo route-summary.xlsx desde Kosmo", "Contiene información de drivers, equipos y distancias", "Si se detectan proveedores nuevos, aparecerá un modal para crearlos"]},
                {"type": "warning", "text": "Si aparece el modal de 'Proveedor no registrado', debes crear el proveedor antes de continuar. No cierres el modal."},
                {"type": "section", "title": "Paso 3: Confirmar y crear rutas", "items": ["Selecciona cliente y fecha de operación", "Asigna proveedores a cada driver", "Confirma la creación de rutas y paquetes"]},
                {"type": "tip", "text": "Las imágenes subidas como evidencia se comprimen automáticamente (max 1920px, JPEG 85%) si exceden 1MB para reducir uso de disco."},
            ],
        },
        {
            "title": "Detalle de Ruta y Guías",
            "subtitle": "Flujo de ejecución de ruta: inicio, seguimiento de guías, incidencias y cierre",
            "section": "Operación de Envíos",
            "tags": ["ruta", "guias", "paquetes", "detalle", "incidencias", "evidencia"],
            "icon_key": "route",
            "slug": "detalle-ruta-guias",
            "sort_order": 11,
            "content": [
                {"type": "callout", "text": "Cada ruta tiene un ciclo de vida: Programada → En Progreso → Cerrada. Esta vista permite gestionar todo el flujo + exportar el detalle a PDF."},
                {"type": "section", "title": "Pestañas disponibles", "items": ["Inicio: datos de arranque (hora, km, vehículo, fotos)", "Incidencias: registro y gestión de problemas", "Fin: datos de cierre (km final, observaciones, evidencias) — al cerrar se calcula km_traveled y delivery_rate", "Guías: lista de paquetes con estado, score IA y evidencias"]},
                {"type": "section", "title": "Tarjetas KPI superiores", "items": ["Paquetes (entregados/total)", "Progreso (% redondeado a entero)", "Incidencias abiertas", "Visitas (paquetes con estado terminal: delivered/failed/returned)"]},
                {"type": "section", "title": "Tarjetas de cierre (sub-doc close_data)", "items": ["Hora de cierre (UTC, mostrada en CDMX)", "Odómetro final (capturado al cerrar)", "Km recorridos = max(0, odometer_end - odometer_start)", "Tasa de entrega = packages_delivered / start_data.packages_loaded × 100 (2 decimales)", "Entregados / Fallidos (incluye cancelled) / Devoluciones (residual)"]},
                {"type": "section", "title": "Tab Guías - Funciones principales", "items": ["Ver estado de cada paquete (Pendiente/Entregado/Fallido)", "Score de confianza y evaluación IA", "Expandir paquete para ver evidencias Kosmo, evaluación IA y revisión manual", "Registrar incidencias inline desde cada paquete"]},
                {"type": "section", "title": "Evaluación IA", "items": ["Botón 'Evaluar IA' ejecuta análisis con Claude Haiku 4.5 (worker async)", "Analiza fotos, nota del driver y estado de tracking", "Genera score 0-100, observaciones y alertas", "Resultados se preservan en re-sincronizaciones Kosmo", "Smart Autopause: pausa automática si hay budget exceeded"]},
                {"type": "section", "title": "Modal 'Nueva incidencia' - Catálogo estandarizado", "items": ["No se comparte evidencia de incidencia", "No se comparte autorización de entrega a tercero", "No se comparte evidencia de entrega correcta", "Información en notas incorrecta/incompleta", "Otro (campo 'Comentario del asesor' obligatorio, max 500 chars)"]},
                {"type": "tip", "text": "Cuando seleccionas 'Otro' como tipo de incidencia, aparece un campo adicional 'Comentario del asesor' (max 500 caracteres) que describe brevemente de que se trata. Es obligatorio y se guarda como campo independiente en el backend."},
                {"type": "tip", "text": "Botón 'Exportar PDF' genera un documento de hasta 7 páginas con cover+resumen, KPIs, datos de inicio, tabla de paquetes (hasta 400), incidencias y cierre."},
            ],
        },
        {
            "title": "Monitor de Procesos (Evaluación IA)",
            "subtitle": "Seguimiento en tiempo real de jobs de evaluación IA por ruta",
            "section": "Operación de Envíos",
            "tags": ["monitor", "evaluacion", "ia", "worker", "jobs", "queue"],
            "icon_key": "radar",
            "slug": "monitor-procesos",
            "sort_order": 12,
            "content": [
                {"type": "callout", "text": "El Monitor de Procesos permite supervisar jobs de evaluación IA encolados y en ejecución. Acceso: coordinadores y developers."},
                {"type": "section", "title": "Estados de un job", "items": ["En_Cola: pendiente de procesamiento", "Evaluando: en ejecución por el worker", "Evaluada: completada exitosamente (todas las guías OK)", "Parcial: completada con algunos errores en guías individuales", "Error: fallo general del job"]},
                {"type": "section", "title": "Filtros disponibles", "items": ["Estado (En_Cola, Evaluando, Evaluada, Parcial, Error)", "Origen (user_manual, scheduler, cron)", "Order ID o nombre de ruta", "Rango de fechas"]},
                {"type": "section", "title": "Acciones por job", "items": ["Ver detalle con guías individuales y tokens consumidos", "Cancelar (solo En_Cola)", "Re-evaluar ruta completa (forzar nueva evaluación)", "SSE stream en tiempo real del progreso"]},
                {"type": "section", "title": "Banner global de pausa", "items": ["Aparece amarillo en /monitor cuando worker pausado manualmente o por auto-pause", "Muestra countdown live al resume time", "Si auto-pause: la razón es 'Budget exceeded' (proteja contra shadow costs)"]},
                {"type": "tip", "text": "Si el estado de salud es 'saturated' en /api/ai-evaluation/health, ajusta MAX_ROUTES_CONCURRENT en Admin IA → Motor IA o revisa si hay jobs atascados."},
            ],
        },

        # ─────────────── INTELIGENCIA ARTIFICIAL ───────────────
        {
            "title": "Admin IA — Motor IA y Costos",
            "subtitle": "Configuración del worker IA: modelo, concurrencia, pausa, ventanas programadas y costos",
            "section": "Inteligencia Artificial",
            "tags": ["admin", "ia", "motor", "pausa", "haiku", "sonnet", "costos", "budget"],
            "icon_key": "cpu",
            "slug": "admin-ia-motor",
            "sort_order": 20,
            "content": [
                {"type": "callout", "text": "El módulo Admin IA centraliza la operación del Motor IA: cambiar modelo entre Haiku 4.5 y Sonnet 4.5, ajustar concurrencia, pausar el worker, programar ventanas y monitorear costos en tiempo real."},
                {"type": "section", "title": "Tabs Admin IA", "items": ["Token Consumption: histórico de tokens por entregable, modelo y cliente", "Routes Report: jobs IA por ruta con estado y duración", "Cost Config: precios por modelo (input/output) en USD/M tokens", "Motor IA: configuración del worker en vivo"]},
                {"type": "section", "title": "Motor IA — Selector de modelo", "items": ["Claude Haiku 4.5 (default): $1/M input, $5/M output, ~29s por guía", "Claude Sonnet 4.5: $3/M input, $15/M output, mayor calidad pero 3x más caro", "Cambio en caliente: el worker lee el config dinámico en cada batch"]},
                {"type": "section", "title": "Sliders configurables", "items": ["Timeout (30-180s): tiempo máximo por llamada al LLM", "Concurrent rutas (1-5): paralelismo del worker", "Batch size por ruta (1-10): guías paralelas dentro de una ruta", "Retries (0-5): reintentos automáticos en errores transitorios"]},
                {"type": "section", "title": "Pausa y kill-switch", "items": ["Botón Pausar con presets 1h/4h/24h/personalizado", "Countdown live al resume", "Smart Autopause: 10 min automáticos si batch completo retorna budget exceeded", "Resume manual disponible en cualquier momento"]},
                {"type": "section", "title": "Ventanas programadas (Schedule)", "items": ["Toggle enable + editor visual", "Ventanas con nombre, días L-D, time picker from→to", "Soporta overnight (ej. 22:00 → 06:00 día siguiente)", "Timezone fijo: America/Mexico_City"]},
                {"type": "warning", "text": "Cambiar a Sonnet 4.5 multiplica el costo por ~3x. Estima costo mensual con la calculadora del tab antes de aplicar."},
                {"type": "tip", "text": "El indicador LIVE en 'Detalle por evento' muestra puntito verde pulsante + 'hace Ns' confirmando que la data se refresca cada 30s sin clic manual."},
            ],
        },
        {
            "title": "Lumi — Asistente Conversacional IA",
            "subtitle": "Chatbot en español con contexto activo de rutas, paquetes y métricas",
            "section": "Inteligencia Artificial",
            "tags": ["lumi", "chatbot", "ia", "conversacional", "espanol"],
            "icon_key": "message-circle",
            "slug": "lumi-asistente",
            "sort_order": 21,
            "content": [
                {"type": "callout", "text": "Lumi es el asistente conversacional de LastMile OS. Responde preguntas en español sobre operación, métricas y datos, con contexto de la página actual del usuario."},
                {"type": "section", "title": "Casos de uso", "items": ["¿Cuántas rutas activas tengo hoy?", "¿Cuál es la tasa de entrega del último mes?", "Resumen de incidencias críticas pendientes", "Análisis de un driver específico por nombre"]},
                {"type": "section", "title": "Modelo y costo", "items": ["Claude Sonnet 4.5 (no Haiku, prioriza calidad de respuesta)", "Cada query loggea tokens en /api/admin/token-usage con entregable=lumi", "Sesión persistente: usa session_id para multi-turn conversation"]},
                {"type": "section", "title": "Contexto activo", "items": ["Lumi conoce la ruta o reporte que estás viendo (active_context)", "Puede preguntarle 'explica esta ruta' sin pegar datos", "El contexto se limpia al cambiar de página"]},
                {"type": "tip", "text": "Para queries de Power BI o pull masivo de datos, no uses Lumi: usa los endpoints /api/reports/* directamente. Lumi es para análisis puntual y conversación."},
            ],
        },

        # ─────────────── INTEGRACIONES ───────────────
        {
            "title": "Integraciones SaaS multi-fuente (Routal/Kosmo/Manual)",
            "subtitle": "Configuración por cliente con cifrado AES, webhooks HMAC y test de conexión",
            "section": "Integraciones",
            "tags": ["integraciones", "routal", "kosmo", "manual", "fernet", "hmac", "webhook"],
            "icon_key": "plug",
            "slug": "integraciones-saas",
            "sort_order": 30,
            "content": [
                {"type": "callout", "text": "Cada cliente puede operar con una de tres fuentes: Routal (API SaaS), Kosmo (scraper interno) o Manual (cargas CSV/XLSX). La configuración se hace en Settings → Integraciones (solo developer)."},
                {"type": "section", "title": "Tipos disponibles", "items": ["Manual: cliente sube layouts vía /upload, sin sync automático", "Kosmo: scraper interno opera en background, no requiere credenciales", "Routal: API SaaS con API key, project_id y webhook secret cifrados con Fernet"]},
                {"type": "section", "title": "Credenciales Routal (cifradas)", "items": ["API Key: nunca se devuelve en GET — solo flag has_api_key", "Project ID: público (mostrado en UI)", "Webhook Secret: nunca se devuelve — solo flag has_webhook_secret", "Cifrado AES-128 (Fernet) con key auto-generada en config.encryption_key si no hay ENCRYPTION_KEY env"]},
                {"type": "section", "title": "Webhook Routal", "items": ["URL: /api/webhooks/routal/{client_id}", "Validación HMAC-SHA256 con compare_digest (constant-time)", "Idempotencia por event_id (rechaza duplicados)", "Eventos: plan.created, plan.started, stop.completed, stop.failed, plan.completed, plan.cancelled"]},
                {"type": "section", "title": "Test de conexión", "items": ["Routal: GET /plans contra api.routal.com con la API key", "Kosmo: health check del scraper (last_sync_at, journeys activos hoy, pending_sync)", "Manual: estadísticas (total journeys, recent_30d, latest_journey_date) — status ok/dormant/empty"]},
                {"type": "section", "title": "Switches por integración", "items": ["auto_create_journeys: crea journeys automáticamente al recibir plan.created", "auto_close_journeys: cierra journey al completar el plan", "sync_drivers: sincroniza catálogo de drivers"]},
                {"type": "warning", "text": "Cambiar el tipo de un cliente entre Routal/Kosmo/Manual NO migra datos históricos. Las journeys existentes mantienen su 'source' original."},
                {"type": "tip", "text": "El campo source en journeys ('routal', 'kosmo' o ausente=legacy) determina qué worker procesa los eventos. Los webhooks Routal solo afectan journeys con source='routal'."},
            ],
        },
        {
            "title": "Auditorías SEL01 — Selección de drivers",
            "subtitle": "Algoritmo 2-fase con scheduler configurable para auditar máximo N drivers/día por cliente",
            "section": "Integraciones",
            "tags": ["sel01", "auditoria", "seleccion", "scheduler", "rotacion", "fairness"],
            "icon_key": "clipboard-check",
            "slug": "auditorias-sel01",
            "sort_order": 31,
            "content": [
                {"type": "callout", "text": "El módulo de Auditorías permite configurar un límite diario de drivers a auditar por cliente. Cuando selection_enabled=true, los planes Routal NO crean journeys directamente; pasan por staging y un algoritmo 2-fase decide cuáles auditar."},
                {"type": "section", "title": "Configuración por cliente (Settings → Auditorías)", "items": ["max_daily_audits (1-500): límite diario de drivers", "scheduler_time: hora HH:MM (tz CDMX) en que corre el algoritmo", "selection_enabled: si false, comportamiento legacy (crear journey directo)", "active: si false, el scheduler omite el cliente"]},
                {"type": "section", "title": "Algoritmo 2-fase", "items": ["Fase 1 (priority): drivers que NO fueron auditados ayer", "Fase 2 (rotation): drivers auditados ayer, ordenados por audit_count_30d ascendente", "Tie-breaker determinista: shuffle seed=YYYYMMDD + sort estable", "Si fleet ≤ max_daily: todos seleccionados (mixed phase)", "Si fleet > max_daily*3: warning de cobertura lenta"]},
                {"type": "section", "title": "Colecciones MongoDB", "items": ["client_config: configuración por cliente (1 doc por client_id)", "routal_daily_plans: staging buffer (planes recibidos pendientes de procesar)", "driver_audit_log: source-of-truth con selection_status (selected/unselected), selection_phase (phase_1/phase_2)"]},
                {"type": "section", "title": "Endpoints", "items": ["POST /api/selection/run/{client_id}?date=YYYY-MM-DD — ejecutar manual", "GET /api/selection/summary/{client_id}?date= — resumen del día", "GET /api/drivers/audit-history/{driver_id}?client_id=&days=30", "GET/PATCH /api/client-config/{client_id}", "GET /api/client-config — listar todas las configs"]},
                {"type": "section", "title": "Idempotencia", "items": ["Re-ejecutar /selection/run mismo día NO crea journeys duplicados", "Drivers ya marcados 'selected' se preservan", "Drivers 'unselected' se borran y recalculan", "Staged plans se marcan processed=true al final del run"]},
                {"type": "warning", "text": "Cuando flota actual > 3× max_daily_audits, el sistema avisa que la rotación cubrirá la flota lentamente. Considera aumentar el límite o explicar al cliente que algunos drivers no serán auditados en ciclos cortos."},
                {"type": "tip", "text": "Para pruebas: POST /selection/run/{client_id}?date=2026-12-31 ejecuta sobre fecha futura sin afectar el scheduler diario. Útil para validar el algoritmo con data sintética."},
            ],
        },
        {
            "title": "Webhooks Plug & Play",
            "subtitle": "CRUD de webhooks salientes con HMAC-SHA256 y delivery log",
            "section": "Integraciones",
            "tags": ["webhooks", "plug-play", "hmac", "delivery", "notificaciones"],
            "icon_key": "globe",
            "slug": "webhooks-plug-play",
            "sort_order": 32,
            "content": [
                {"type": "callout", "text": "El módulo de Webhooks permite que sistemas externos reciban notificaciones en tiempo real cuando ocurren eventos en LastMile OS (rutas creadas, paquetes entregados, incidencias)."},
                {"type": "section", "title": "Configuración (Settings → Webhooks)", "items": ["URL destino HTTPS", "Secret para firma HMAC-SHA256 (header X-LMOS-Signature)", "Eventos suscritos (multi-select)", "Activar/desactivar sin borrar"]},
                {"type": "section", "title": "Eventos disponibles", "items": ["journey.created, journey.started, journey.closed", "package.delivered, package.failed", "incident.created, incident.resolved", "kosmo.sync.completed"]},
                {"type": "section", "title": "Test endpoint", "items": ["Botón 'Probar' envía un payload sintético al webhook", "Muestra status_code, latencia y body de respuesta", "No afecta el delivery log productivo"]},
                {"type": "section", "title": "Delivery log", "items": ["Tabla con últimos 100 envíos por webhook", "Columnas: timestamp, evento, status_code, latencia, error", "Reintento automático con backoff exponencial en 5xx (max 5 intentos)"]},
                {"type": "tip", "text": "Verifica la firma con el secret del webhook: hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() y compara con el header X-LMOS-Signature."},
            ],
        },

        # ─────────────── CONFIGURACIÓN ───────────────
        {
            "title": "Configuración de Usuarios y Catálogos",
            "subtitle": "Gestión de usuarios, roles, drivers, clientes y proveedores del sistema",
            "section": "Configuración",
            "tags": ["configuracion", "usuarios", "roles", "proveedores", "drivers", "clientes"],
            "icon_key": "settings",
            "slug": "configuracion-usuarios",
            "sort_order": 40,
            "content": [
                {"type": "callout", "text": "El módulo de Configuración permite administrar todos los actores del sistema. Solo accesible para Coordinadores y Developers."},
                {"type": "section", "title": "Tabs disponibles", "items": ["Usuarios: CRUD con roles + asignaciones (clientes/proveedores)", "Drivers: catálogo de mensajeros con proveedor y vehículo", "Clientes: empresas que contratan el servicio", "Proveedores: empresas logísticas que operan las rutas", "Sistema: SLA dinámico por proveedor + IA cost config", "Webhooks: integraciones de notificación", "Integraciones: Routal/Kosmo/Manual (solo developer)", "Auditorías: SEL01 selección de drivers (solo developer)"]},
                {"type": "table", "headers": ["Rol", "Permisos", "Ejemplo"], "rows": [["Agent", "Solo lectura de rutas asignadas", "Agente de campo"], ["Coordinator", "CRUD completo, reportes, configuración", "Yael Coordinador"], ["Executive", "Lectura de reportes y dashboards", "Directivo"], ["Developer", "Acceso total + Sistema/Integraciones/Auditorías", "Admin técnico"], ["Proveedor", "Solo lectura restringida", "Empresa logística"]]},
                {"type": "section", "title": "Operaciones críticas (solo coordinator/developer)", "items": ["Inicializar datos: crea catálogos básicos si están vacíos", "Limpiar rutas y pedidos: elimina journeys/packages/incidents/AI jobs por rango de fechas o todo", "Cambio de contraseña por admin (sin requerir current password)"]},
                {"type": "section", "title": "Seguridad", "items": ["JWT en httpOnly cookie (Path=/api, Secure, SameSite=lax)", "Bearer header backward-compat para API consumers", "Refresh tokens 90 días (Power BI / Tableau)", "Rate limiting global + middleware por endpoint", "Audit log de todas las acciones admin"]},
                {"type": "warning", "text": "Al cambiar el rol de un usuario, sus permisos se actualizan inmediatamente. Verifica antes de hacer cambios."},
                {"type": "warning", "text": "La acción 'Limpiar rutas y pedidos' es IRREVERSIBLE. Usa el preview de conteos antes de confirmar."},
            ],
        },
        {
            "title": "Quality Criteria V2 — Configuración de evaluación IA",
            "subtitle": "5 tabs para definir tipos de entrega, evidencias requeridas y pesos del scoring",
            "section": "Configuración",
            "tags": ["quality", "criterios", "scoring", "ia", "evidencia", "weights"],
            "icon_key": "shield-check",
            "slug": "quality-criteria-v2",
            "sort_order": 41,
            "content": [
                {"type": "callout", "text": "Quality Criteria V2 controla cómo la IA evalúa cada entrega. Define qué evidencias son obligatorias por tipo de entrega y cómo se pondera cada criterio en el score 0-100."},
                {"type": "section", "title": "5 tabs configurables", "items": ["Tipos de entrega: domicilio, oficina, lockerbox, third_party, retornos…", "Evidencias requeridas por tipo: foto del paquete, foto del recipiente, firma, etc.", "Pesos del scoring: cuánto pesa cada criterio en el score final", "Reglas de imputabilidad: ME / cliente / pendiente / por definir", "Severidad: critical / warning / info por categoría"]},
                {"type": "section", "title": "Cómo influye en la IA", "items": ["El prompt de Claude se construye dinámicamente con la config activa", "Cambiar pesos NO re-evalúa retroactivamente (necesitas 'Re-evaluar ruta')", "Tipos de entrega nuevos requieren guías ya etiquetadas para entrenamiento supervisado"]},
                {"type": "section", "title": "Tab Calidad V2 en Journey Detail", "items": ["Vista por paquete con score breakdown", "Botones 'Correcto' / 'Incorrecto' + nota natural language", "Override de score manual (registrado en training_samples)", "Confidence Engine: detecta discrepancias entre IA y humano"]},
                {"type": "tip", "text": "Antes de cambiar pesos, exporta la config actual con GET /api/quality-criteria. Si el cambio empeora resultados, puedes hacer rollback con PUT del backup."},
            ],
        },

        # ─────────────── DOCUMENTACIÓN TÉCNICA ───────────────
        {
            "title": "API & Integraciones (Power BI / Tableau)",
            "subtitle": "Documentación de API REST, sandbox interactivo, refresh tokens y ejemplos",
            "section": "Documentación Técnica",
            "tags": ["api", "powerbi", "tableau", "rest", "token", "refresh", "sandbox"],
            "icon_key": "code",
            "slug": "api-integraciones",
            "sort_order": 50,
            "content": [
                {"type": "callout", "text": "LastMile OS expone una API REST completa para integración con Power BI, Tableau, Looker Studio o scripts Python. Incluye sandbox interactivo en /api-reportes."},
                {"type": "section", "title": "Autenticación", "items": ["Todas las peticiones requieren JWT Bearer token o cookie httpOnly", "Token corto: 8h vigencia (uso interactivo)", "Refresh token: 90 días (integraciones automáticas tipo Power BI)", "Rotación: usa /api/auth/exchange-token para canjear refresh→access"]},
                {"type": "section", "title": "Endpoints principales", "items": ["/api/reports/journeys — datos de rutas con métricas", "/api/reports/packages — detalle de paquetes", "/api/reports/incidents — incidencias registradas", "/api/reports/kpis — KPIs agregados por periodo", "/api/reports/operational-detail — dataset plano por journey listo para Power BI"]},
                {"type": "section", "title": "Refresh Tokens (Power BI)", "items": ["Genera refresh token desde Configuración → Integraciones", "El refresh token dura 90 días", "Usa /api/auth/exchange-token para obtener access token fresco", "El access token dura 8 horas"]},
                {"type": "section", "title": "Monitoreo de workers", "items": ["GET /api/ai-evaluation/health — estado del worker IA (healthy/saturated/stuck/paused)", "GET /api/health — DB + workers + storage + circuit breakers (consumido por load balancer)", "Integrable con Grafana, Datadog o uptime tools"]},
                {"type": "section", "title": "Sandbox interactivo", "items": ["Página API & Reportes muestra ejemplos curl, Python, JS", "Botón 'Copiar Token' en clipboard", "Resultados JSON descargables", "Diccionario técnico con shape de cada endpoint"]},
                {"type": "tip", "text": "Para Power BI: usa Web → Conector → URL con header Authorization: Bearer {token}. Configura un parámetro 'token' editable en el dataset para no hardcoder credenciales."},
            ],
        },
        {
            "title": "Diccionario técnico (modelo de datos)",
            "subtitle": "Schema completo de journeys, packages, drivers, integrations y selection module",
            "section": "Documentación Técnica",
            "tags": ["diccionario", "schema", "modelo", "powerbi", "dax", "data"],
            "icon_key": "database",
            "slug": "diccionario-tecnico",
            "sort_order": 51,
            "content": [
                {"type": "callout", "text": "Schema oficial de las colecciones MongoDB para que el equipo de Data pueda construir measures DAX o consultas SQL/Power Query. Todas las fechas son ISO-8601 UTC; convertir a CDMX en el cliente."},
                {"type": "section", "title": "Colección: journeys", "items": ["id (uuid str): clave primaria", "client_id, provider_id, driver_id, driver_name", "date (str YYYY-MM-DD): fecha operativa", "status: planificada / in_progress / completada / cerrada / cancelada", "packages_total, packages_delivered, packages_failed", "source: routal / kosmo / null(legacy)", "routal_plan_id (sparse, solo si source=routal)", "start_data: {odometer_start, packages_loaded, started_at, vehicle_condition, fuel_level, photos[]}", "close_data: {closed_at, odometer_end, packages_delivered, packages_failed, packages_to_retry, km_traveled, delivery_rate, notes}", "incidents[]: {id, type, severity, imputability, status, comments}", "last_kosmo_sync_at, next_sync_at (ISO timestamps)"]},
                {"type": "section", "title": "Cálculos de cierre (close_data)", "items": ["km_traveled = MAX(0, odometer_end - odometer_start)", "delivery_rate = ROUND(packages_delivered / start_data.packages_loaded × 100, 2)", "packages_to_retry = MAX(0, packages_loaded - delivered - failed)", "Visitas = COUNT(packages WHERE status IN ('delivered','failed','returned'))", "Progreso (UI) = ROUND(delivered / packages_total × 100, 0) — entero, distinto a delivery_rate"]},
                {"type": "section", "title": "Colección: packages", "items": ["id (uuid str), journey_id (FK), client_id", "tracking_number, tracking_url, order_reference_id", "address, address_cp, recipient_name, zone", "status: pending / delivered / failed / returned / cancelled", "evidence_score (0-100), evidence_evaluation (json IA)", "delivery_type, recipient_relationship", "kosmo_status_raw (estado raw del scraper)", "routal_service_id (sparse, solo si source=routal)"]},
                {"type": "section", "title": "Colección: client_integrations (R00A)", "items": ["client_id (unique), integration_type: routal/kosmo/manual", "credentials_encrypted (Fernet AES — NO leer directo)", "credentials_summary (público): {has_api_key, has_webhook_secret, routal_project_id}", "config: {auto_create_journeys, auto_close_journeys, sync_drivers}", "status: active / inactive / testing", "last_sync_at, last_error"]},
                {"type": "section", "title": "Colecciones SEL01 (R00B)", "items": ["client_config: {client_id, max_daily_audits, selection_enabled, scheduler_time, active, last_scheduled_run_date}", "routal_daily_plans: staging buffer (client_id, driver_id, date, plan_id_routal, route_metadata, processed)", "driver_audit_log: source-of-truth (client_id, driver_id, date, selection_status, selection_phase, audit_count_30d_at_selection, journey_id)"]},
                {"type": "section", "title": "Identidad de cierre (validación QA)", "items": ["packages_loaded = packages_delivered + packages_failed + packages_to_retry", "Si no cumple → hay paquetes en estado intermedio (pending/returned no contado)", "Si delivery_rate ≠ Progreso% → packages_loaded ≠ packages_total (faltaron en bodega — esperado)"]},
                {"type": "section", "title": "Endpoint para Power BI", "items": ["GET /api/reports/operational-detail?date_from=&date_to= devuelve dataset plano por journey", "Campos: packages_delivered, packages_total, delivery_rate, km_traveled, odometer_end, closed_at, provider, client, driver_name", "Auth: Authorization: Bearer <refresh_token_canjeado>"]},
                {"type": "tip", "text": "Para measures DAX: 'Tasa de Entrega %' = ROUND(DIVIDE(SUM(packages_delivered), SUM(packages_loaded)) × 100, 2). Para 'Progreso %' usa packages_total como denominador y redondea a entero."},
                {"type": "warning", "text": "El campo source puede ser null en journeys legacy (auto-migrado a 'kosmo'). Si construyes filtros DAX, usa COALESCE(source, 'kosmo')."},
            ],
        },
    ]
