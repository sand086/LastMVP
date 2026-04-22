"""
Platform Manuals routes — Knowledge Hub for operations teams.
CRUD for manuals + public reader endpoints.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import db, get_current_user, require_role
from pagination_utils import paginated_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Manuals"])

VALID_SECTIONS = ["Paneles", "Operación de Envíos", "Configuración", "Integraciones"]
VALID_PLATFORMS = ["web", "app", "both"]


class ManualCreate(BaseModel):
    title: str
    subtitle: Optional[str] = ""
    section: str
    tags: list[str] = []
    icon_key: Optional[str] = "book-open"
    platform_type: Optional[str] = "both"
    sort_order: Optional[int] = 0
    is_published: Optional[bool] = True


class ManualUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    section: Optional[str] = None
    tags: Optional[list[str]] = None
    icon_key: Optional[str] = None
    platform_type: Optional[str] = None
    sort_order: Optional[int] = None
    is_published: Optional[bool] = None


class ManualPageUpdate(BaseModel):
    content: list[dict]


# ── PUBLIC: List manuals ────────────────────────────────────────
@router.get("/manuals")
async def list_manuals(
    section: Optional[str] = None,
    platform: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    query = {"is_published": True}
    if section and section != "all":
        query["section"] = section
    if platform and platform != "all":
        query["platform_type"] = {"$in": [platform, "both"]}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"subtitle": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    manuals = await db.manuals.find(query, {"_id": 0}).sort("sort_order", 1).to_list(200)
    # Standardized envelope (page=1, page_size=200 = no pagination in practice)
    return paginated_response(manuals, total=len(manuals), page=1, page_size=max(len(manuals), 1))


# ── PUBLIC: Get manual by slug ──────────────────────────────────
@router.get("/manuals/{slug}")
async def get_manual(slug: str, user: dict = Depends(get_current_user)):
    manual = await db.manuals.find_one({"slug": slug, "is_published": True}, {"_id": 0})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")

    page = await db.manual_pages.find_one({"manual_id": manual["id"]}, {"_id": 0})
    manual["content"] = page["content"] if page else []
    return manual


# ── ADMIN: List all (including drafts) ──────────────────────────
@router.get("/manuals-admin")
async def list_manuals_admin(user: dict = Depends(require_role(["coordinator", "developer"]))):
    manuals = await db.manuals.find({}, {"_id": 0}).sort("sort_order", 1).to_list(200)
    return paginated_response(manuals, total=len(manuals), page=1, page_size=max(len(manuals), 1))


# ── ADMIN: Create manual ────────────────────────────────────────
@router.post("/manuals-admin")
async def create_manual(data: ManualCreate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    if data.section not in VALID_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Seccion invalida. Opciones: {VALID_SECTIONS}")

    slug = data.title.lower().strip().replace(" ", "-").replace("/", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:60]

    existing = await db.manuals.find_one({"slug": slug}, {"_id": 0, "id": 1})
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    now = datetime.now(timezone.utc).isoformat()
    manual_id = str(uuid.uuid4())
    doc = {
        "id": manual_id,
        "slug": slug,
        "title": data.title.strip(),
        "subtitle": data.subtitle or "",
        "section": data.section,
        "tags": data.tags,
        "icon_key": data.icon_key or "book-open",
        "platform_type": data.platform_type or "both",
        "sort_order": data.sort_order or 0,
        "is_published": data.is_published if data.is_published is not None else True,
        "created_at": now,
        "created_by": user["id"],
    }
    await db.manuals.insert_one(doc)

    page_doc = {
        "id": str(uuid.uuid4()),
        "manual_id": manual_id,
        "content": [],
        "version": 1,
        "updated_at": now,
    }
    await db.manual_pages.insert_one(page_doc)

    return {"id": manual_id, "slug": slug, "message": "Manual creado"}


# ── ADMIN: Update manual metadata ──────────────────────────────
@router.patch("/manuals-admin/{manual_id}")
async def update_manual(manual_id: str, data: ManualUpdate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    manual = await db.manuals.find_one({"id": manual_id}, {"_id": 0, "id": 1})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.title is not None:
        update["title"] = data.title.strip()
    if data.subtitle is not None:
        update["subtitle"] = data.subtitle
    if data.section is not None:
        if data.section not in VALID_SECTIONS:
            raise HTTPException(status_code=400, detail="Seccion invalida")
        update["section"] = data.section
    if data.tags is not None:
        update["tags"] = data.tags
    if data.icon_key is not None:
        update["icon_key"] = data.icon_key
    if data.platform_type is not None:
        update["platform_type"] = data.platform_type
    if data.sort_order is not None:
        update["sort_order"] = data.sort_order
    if data.is_published is not None:
        update["is_published"] = data.is_published

    await db.manuals.update_one({"id": manual_id}, {"$set": update})
    return {"message": "Manual actualizado"}


# ── ADMIN: Update manual content (blocks) ──────────────────────
@router.put("/manuals-admin/{manual_id}/content")
async def update_manual_content(manual_id: str, data: ManualPageUpdate, user: dict = Depends(require_role(["coordinator", "developer"]))):
    manual = await db.manuals.find_one({"id": manual_id}, {"_id": 0, "id": 1})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")

    now = datetime.now(timezone.utc).isoformat()
    result = await db.manual_pages.update_one(
        {"manual_id": manual_id},
        {"$set": {"content": data.content, "updated_at": now}, "$inc": {"version": 1}},
    )
    if result.matched_count == 0:
        await db.manual_pages.insert_one({
            "id": str(uuid.uuid4()),
            "manual_id": manual_id,
            "content": data.content,
            "version": 1,
            "updated_at": now,
        })
    return {"message": "Contenido actualizado"}


# ── ADMIN: Delete manual ────────────────────────────────────────
@router.delete("/manuals-admin/{manual_id}")
async def delete_manual(manual_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    result = await db.manuals.delete_one({"id": manual_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    await db.manual_pages.delete_many({"manual_id": manual_id})
    return {"message": "Manual eliminado"}


# ── ADMIN: Get manual with content for editing ─────────────────
@router.get("/manuals-admin/{manual_id}")
async def get_manual_admin(manual_id: str, user: dict = Depends(require_role(["coordinator", "developer"]))):
    manual = await db.manuals.find_one({"id": manual_id}, {"_id": 0})
    if not manual:
        raise HTTPException(status_code=404, detail="Manual no encontrado")
    page = await db.manual_pages.find_one({"manual_id": manual_id}, {"_id": 0})
    manual["content"] = page["content"] if page else []
    return manual


# ── SEED: Populate example manuals ──────────────────────────────
@router.post("/manuals-admin/seed")
async def seed_manuals(user: dict = Depends(require_role(["coordinator", "developer"]))):
    existing = await db.manuals.count_documents({})
    if existing > 0:
        return {"message": f"Ya existen {existing} manuales. Seed omitido.", "seeded": 0}

    now = datetime.now(timezone.utc).isoformat()
    manuals_seed = [
        {
            "title": "Dashboard Principal",
            "subtitle": "Panel de control con metricas en tiempo real de entregas, SLA y operaciones",
            "section": "Paneles",
            "tags": ["dashboard", "metricas", "kpi", "tiempo-real"],
            "icon_key": "layout-dashboard",
            "slug": "dashboard-principal",
            "sort_order": 1,
            "content": [
                {"type": "callout", "text": "El Dashboard es la vista principal de LastMile OS. Muestra el estado actual de todas las operaciones de entrega en tiempo real."},
                {"type": "section", "title": "Acceso", "items": ["Disponible para todos los roles", "Se actualiza automaticamente via WebSocket"]},
                {"type": "section", "title": "Indicadores KPI", "items": ["Rutas activas del dia", "Paquetes entregados / pendientes / fallidos", "Tasa de entrega en tiempo real", "Ultima sincronizacion Kosmo"]},
                {"type": "table", "headers": ["KPI", "Descripcion", "Actualizacion"], "rows": [["Rutas activas", "Numero de rutas en progreso hoy", "Tiempo real"], ["Tasa entrega", "% paquetes entregados vs total", "Cada sync"], ["Incidencias abiertas", "Incidencias sin resolver", "Tiempo real"]]},
                {"type": "section", "title": "Tabla de rutas", "items": ["Order ID clickeable lleva al detalle", "Barra de progreso visual", "Filtro por estado: Programada / En Progreso / Cerrada", "Busqueda por driver, proveedor u Order ID"]},
                {"type": "tip", "text": "Usa el boton de sincronizacion manual para forzar una actualizacion de estados desde Kosmo cuando necesites datos inmediatos."},
                {"type": "warning", "text": "El dashboard filtra por la fecha del dia actual. Si no ves rutas, verifica que existan rutas para la fecha seleccionada."},
            ],
        },
        {
            "title": "Carga de Layouts (Cosmo)",
            "subtitle": "Proceso de 3 pasos para importar rutas desde archivos CSV y XLSX de Kosmo",
            "section": "Operación de Envíos",
            "tags": ["layout", "upload", "cosmo", "csv", "xlsx", "importar"],
            "icon_key": "upload",
            "slug": "carga-layouts",
            "sort_order": 2,
            "content": [
                {"type": "callout", "text": "El modulo de Layout permite importar rutas de entrega desde los archivos que exporta Kosmo. El proceso tiene 3 pasos secuenciales."},
                {"type": "section", "title": "Paso 1: History Orders (CSV)", "items": ["Descarga el archivo history-orders.csv desde Kosmo", "Columnas requeridas: order_id, order_reference_id, tracking_url", "El sistema detecta automaticamente paquetes ya existentes"]},
                {"type": "section", "title": "Paso 2: Route Summary (XLSX)", "items": ["Descarga el archivo route-summary.xlsx desde Kosmo", "Contiene informacion de drivers, equipos y distancias", "Si se detectan proveedores nuevos, aparecera un modal para crearlos"]},
                {"type": "warning", "text": "Si aparece el modal de 'Proveedor no registrado', debes crear el proveedor antes de continuar. No cierres el modal."},
                {"type": "section", "title": "Paso 3: Confirmar y crear rutas", "items": ["Selecciona cliente y fecha de operacion", "Asigna proveedores a cada driver", "Confirma la creacion de rutas y paquetes"]},
                {"type": "tip", "text": "Puedes cargar multiples rutas del mismo dia en una sola operacion. El sistema agrupa automaticamente por driver."},
            ],
        },
        {
            "title": "Detalle de Ruta y Guias",
            "subtitle": "Flujo de ejecucion de ruta: inicio, seguimiento de guias, incidencias y cierre",
            "section": "Operación de Envíos",
            "tags": ["ruta", "guias", "paquetes", "detalle", "incidencias", "evidencia"],
            "icon_key": "route",
            "slug": "detalle-ruta-guias",
            "sort_order": 3,
            "content": [
                {"type": "callout", "text": "Cada ruta tiene un ciclo de vida: Programada, En Progreso, Cerrada. Esta vista permite gestionar todo el flujo."},
                {"type": "section", "title": "Pestanas disponibles", "items": ["Guias: Lista de todos los paquetes con estado, score IA y evidencias", "Inicio: Datos de arranque de ruta (hora, km, vehiculo)", "Incidencias: Registro y gestion de problemas", "Cierre: Datos finales de la ruta (km final, observaciones)"]},
                {"type": "section", "title": "Tab Guias - Funciones principales", "items": ["Ver estado de cada paquete (Pendiente / Entregado / Fallido)", "Score de confianza y evaluacion IA", "Expandir paquete para ver evidencias Kosmo, evaluacion IA y revision manual", "Registrar incidencias inline desde cada paquete"]},
                {"type": "section", "title": "Evaluacion IA", "items": ["Boton 'Evaluar IA' ejecuta analisis de evidencias con Claude Sonnet", "Analiza fotos, nota del driver y estado de tracking", "Genera score de 0-100, observaciones y alertas", "Los resultados se preservan incluso despues de re-sincronizaciones Kosmo"]},
                {"type": "section", "title": "Modal 'Nueva incidencia' - Catalogo estandarizado", "items": ["No se comparte evidencia de incidencia correctamente", "No se comparte autorizacion de entrega a tercero correctamente", "No se comparte evidencia de entrega correcta", "La informacion en notas es incorrecta / incompleta", "Otro (requiere campo 'Comentario del asesor' obligatorio)"]},
                {"type": "tip", "text": "Cuando seleccionas 'Otro' como tipo de incidencia, aparece un campo adicional 'Comentario del asesor' (max 500 caracteres) que describe brevemente de que se trata. Es obligatorio y se guarda como campo independiente en el backend."},
                {"type": "tip", "text": "Puedes cambiar el proveedor de una ruta especifica usando el icono de edicion junto al nombre del proveedor en el header."},
            ],
        },
        {
            "title": "Reportes y Analitica",
            "subtitle": "6 tabs de reportes con KPIs, graficos y exportacion PDF",
            "section": "Paneles",
            "tags": ["reportes", "analitica", "kpi", "pdf", "sla", "calidad"],
            "icon_key": "bar-chart-3",
            "slug": "reportes-analitica",
            "sort_order": 4,
            "content": [
                {"type": "callout", "text": "El modulo de Reportes consolida todas las metricas operativas con filtros por periodo, cliente y proveedor."},
                {"type": "section", "title": "Tabs disponibles", "items": ["Proveedores: Metricas por proveedor (entrega, visita, SLA)", "Drivers: Rendimiento individual por mensajero", "Incidencias: Desglose por tipo y severidad", "Intentos: Analisis de primer y segundo intento", "Calidad: Scores de evidencia por tipo de entrega", "SLA: Cumplimiento vs target por proveedor"]},
                {"type": "table", "headers": ["Filtro", "Tipo", "Descripcion"], "rows": [["Periodo", "Selector", "7d, 15d, mes actual, mes anterior, custom"], ["Cliente", "Dropdown", "Filtra por cliente asignado"], ["Proveedor", "Dropdown", "Filtra por proveedor logistico"]]},
                {"type": "section", "title": "Exportacion PDF", "items": ["Boton 'Exportar PDF' genera documento multi-pagina", "Incluye portada, KPIs, todas las tabs activas y analisis IA", "Formato nativo con tablas legibles (jsPDF + autotable)"]},
                {"type": "tip", "text": "Genera el reporte IA antes de exportar PDF para incluir el analisis narrativo en el documento."},
            ],
        },
        {
            "title": "Configuracion de Usuarios y Proveedores",
            "subtitle": "Gestion de usuarios, roles, drivers, clientes y proveedores del sistema",
            "section": "Configuración",
            "tags": ["configuracion", "usuarios", "roles", "proveedores", "drivers", "clientes"],
            "icon_key": "settings",
            "slug": "configuracion-usuarios",
            "sort_order": 5,
            "content": [
                {"type": "callout", "text": "El modulo de Configuracion permite administrar todos los actores del sistema. Solo accesible para Coordinadores y Developers."},
                {"type": "section", "title": "Tabs disponibles", "items": ["Usuarios: CRUD de usuarios con roles y asignaciones", "Drivers: Catalogo de mensajeros con proveedor y vehiculo", "Clientes: Empresas que contratan el servicio", "Proveedores: Empresas logisticas que operan las rutas", "Sistema: Informacion tecnica del entorno", "Webhooks: Integraciones de notificacion"]},
                {"type": "table", "headers": ["Rol", "Permisos", "Ejemplo"], "rows": [["Agent", "Solo lectura de rutas asignadas", "Agente de campo"], ["Coordinator", "CRUD completo, reportes, configuracion", "Yael Coordinador"], ["Executive", "Lectura de reportes y dashboards", "Directivo"], ["Developer", "Acceso total + sistema", "Admin tecnico"], ["Proveedor", "Solo lectura restringida", "Empresa logistica"]]},
                {"type": "warning", "text": "Al cambiar el rol de un usuario, sus permisos se actualizan inmediatamente. Verifica antes de hacer cambios."},
            ],
        },
        {
            "title": "API & Integraciones (Power BI)",
            "subtitle": "Documentacion de API REST, sandbox interactivo y ejemplos de codigo",
            "section": "Integraciones",
            "tags": ["api", "powerbi", "integracion", "rest", "token", "refresh"],
            "icon_key": "code",
            "slug": "api-integraciones",
            "sort_order": 6,
            "content": [
                {"type": "callout", "text": "LastMile OS expone una API REST completa para integracion con herramientas externas como Power BI, Tableau o scripts Python."},
                {"type": "section", "title": "Autenticacion", "items": ["Todas las peticiones requieren un token JWT", "El token se obtiene desde la pagina API & Reportes (boton Copiar Token)", "Para integraciones automaticas, usar Refresh Tokens (90 dias de vigencia)"]},
                {"type": "section", "title": "Endpoints principales", "items": ["/api/reports/journeys — Datos de rutas con metricas", "/api/reports/packages — Detalle de paquetes", "/api/reports/incidents — Incidencias registradas", "/api/reports/kpis — KPIs agregados por periodo"]},
                {"type": "section", "title": "Refresh Tokens para Power BI", "items": ["Genera un refresh token desde Configuracion > Integraciones", "El refresh token dura 90 dias", "Usa el endpoint /api/auth/exchange-token para obtener un access token fresco", "El access token dura 8 horas"]},
                {"type": "section", "title": "Monitoreo de workers", "items": ["GET /api/ai-evaluation/health — Estado del worker de evaluacion IA (healthy/saturated/stuck), slots libres, jobs en cola, edad del job mas antiguo", "Integrable con Grafana o herramientas de uptime para alertas proactivas"]},
                {"type": "tip", "text": "En la pagina API & Reportes encontraras un sandbox interactivo para probar los endpoints directamente y descargar los resultados en JSON."},
            ],
        },
        {
            "title": "Monitor de Procesos (Evaluacion IA)",
            "subtitle": "Seguimiento en tiempo real de jobs de evaluacion IA por ruta",
            "section": "Operación de Envíos",
            "tags": ["monitor", "evaluacion", "ia", "worker", "jobs", "queue"],
            "icon_key": "radar",
            "slug": "monitor-procesos",
            "sort_order": 7,
            "content": [
                {"type": "callout", "text": "El Monitor de Procesos permite supervisar jobs de evaluacion IA encolados y en ejecucion. Acceso: coordinadores y developers."},
                {"type": "section", "title": "Estados de un job", "items": ["En_Cola: Pendiente de procesamiento", "Evaluando: En ejecucion por el worker", "Evaluada: Completada exitosamente (todas las guias OK)", "Parcial: Completada con algunos errores en guias individuales", "Error: Fallo general del job"]},
                {"type": "section", "title": "Filtros disponibles", "items": ["Estado (En_Cola, Evaluando, Evaluada, Parcial, Error)", "Origen (user_manual, scheduler, cron)", "Order ID o nombre de ruta", "Rango de fechas"]},
                {"type": "section", "title": "Acciones por job", "items": ["Ver detalle con guias individuales y tokens consumidos", "Cancelar (solo En_Cola)", "Re-evaluar ruta completa (forzar nueva evaluacion)", "SSE stream en tiempo real del progreso"]},
                {"type": "section", "title": "Arquitectura del worker", "items": ["Worker asincrono con hasta 3 rutas concurrentes (MAX_ROUTES_CONCURRENT)", "Batch de 5 guias paralelas por ruta (BATCH_SIZE_PER_ROUTE)", "Reintento automatico con backoff exponencial en errores", "Cron sweep cada 30 minutos para recuperar jobs pendientes", "Recuperacion automatica de jobs huerfanos >30min al arranque"]},
                {"type": "tip", "text": "Si el estado es 'saturated' en /api/ai-evaluation/health, aumenta MAX_ROUTES_CONCURRENT o revisa si hay jobs atascados."},
            ],
        },
    ]

    for m in manuals_seed:
        manual_id = str(uuid.uuid4())
        content = m.pop("content")
        m["id"] = manual_id
        m["platform_type"] = "both"
        m["is_published"] = True
        m["created_at"] = now
        m["created_by"] = user["id"]
        await db.manuals.insert_one(m)
        await db.manual_pages.insert_one({
            "id": str(uuid.uuid4()),
            "manual_id": manual_id,
            "content": content,
            "version": 1,
            "updated_at": now,
        })

    return {"message": f"{len(manuals_seed)} manuales creados", "seeded": len(manuals_seed)}
