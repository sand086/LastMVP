# 🛡️ Estructura de Roles y Jerarquía – MyExcellence SaaS

> **Generado**: Feb 2026 · **Fuente**: `middleware/rbac.py`, `middleware/stack.py`, `routes/admin_users.py`, `models/admin.py`
> **Objetivo**: Visualizar la jerarquía multi-tenant + multi-client y detectar gaps de visibilidad/auditoría.

---

## 1. Pirámide de Roles (rango → privilegio)

```
                            ┌─────────────────────┐
                            │   root_dev   (7)    │  ◄── Plataforma
                            │  Cross-tenant ops   │      (Emergent)
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  superadmin  (6)    │  ◄── Owner del Tenant
                            │ Config global tenant│
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │    admin     (5)    │  ◄── Administrador
                            │ Config + tickets    │      operativo
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  coordinator (4)    │  ◄── Líder operación
                            │ Workflows + KPIs    │
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  supervisor  (3)    │  ◄── Torre de control
                            │ /torre              │
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │    agent     (2)    │  ◄── Operador de piso
                            │ /agente             │      (CX, tickets)
                            └──────────┬──────────┘
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
   ┌──────────▼──────────┐                          ┌───────────▼─────────┐
   │ client_viewer  (1)  │                          │ client_auditor (1)  │
   │  Read-only          │                          │  Read-only + AI     │
   │  Cliente externo    │                          │  audit + CSV export │
   └─────────────────────┘                          └─────────────────────┘
```

**Fuente**: `middleware/rbac.py::ROLE_RANK`

---

## 2. Doble Eje de Aislamiento

El SaaS tiene **dos dimensiones de scope** que deben combinarse en CADA query:

```
                ┌──────────────────────────────────────────────┐
                │              EJE 1: TENANT                   │
                │  (separa empresas/instancias del SaaS)       │
                │                                              │
                │   tenant_id  ──►  obligatorio en todas las   │
                │                   queries de Mongo           │
                │                                              │
                │   Enforced por: AuthTenantMiddleware         │
                │   (middleware/stack.py L133)                 │
                └──────────────────────┬───────────────────────┘
                                       │
                ┌──────────────────────▼───────────────────────┐
                │              EJE 2: CLIENT                   │
                │  (separa clientes finales dentro del tenant) │
                │                                              │
                │   client_id  ──►  OPCIONAL para internos,    │
                │                   OBLIGATORIO para externos  │
                │                                              │
                │   Enforced por: ⚠️ Manual en cada route     │
                │                 (NO hay middleware)          │
                └──────────────────────────────────────────────┘
```

---

## 3. Flujo de Login → Landing → Permisos

```
┌──────────────┐
│  POST /api/  │
│  auth/login  │
└──────┬───────┘
       │
       ├──► Validar email + password (bcrypt)
       ├──► Rate-limit (LOGIN_MAX_ATTEMPTS)
       ├──► Tenant status check (active/maintenance/suspended)
       │
       ▼
┌──────────────────────────────────────────────────┐
│  JWT firmado con:                                │
│    sub        = user.id                          │
│    tenant_id  = user.tenant_id                   │
│    role       = user.role                        │
│    email      = user.email                       │
│                                                  │
│  ⚠️  client_id NO viaja en el JWT                │
└──────┬───────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│  default_landing_for(role)  ── rbac.py L67       │
│                                                  │
│  root_dev      → /dashboard                      │
│  superadmin    → /dashboard                      │
│  admin         → /dashboard                      │
│  coordinator   → /dashboard                      │
│  supervisor    → /torre                          │
│  agent         → /agente                         │
│  client_viewer → /dashboard   ⚠️ (revisar)       │
│  client_auditor→ /auditor                        │
└──────────────────────────────────────────────────┘
```

---

## 4. Matriz Rol × Capacidad

| Capacidad                                | root | super | admin | coord | super² | agent | viewer | auditor |
|------------------------------------------|:----:|:-----:|:-----:|:-----:|:------:|:-----:|:------:|:-------:|
| Cross-tenant (ver TODOS los tenants)     |  ✅  |   ❌   |   ❌  |   ❌  |   ❌    |  ❌   |   ❌   |    ❌   |
| Gestionar usuarios del tenant            |  ✅  |   ✅   |   ❌  |   ❌  |   ❌    |  ❌   |   ❌   |    ❌   |
| Config tenant (catálogos, carriers, IA)  |  ✅  |   ✅   |   ✅  |   ❌  |   ❌    |  ❌   |   ❌   |    ❌   |
| Aprobar webhooks / cron / seed           |  ✅  |   ✅   |   ✅  |   ⚠️  |   ❌    |  ❌   |   ❌   |    ❌   |
| Crear / editar tickets                   |  ✅  |   ✅   |   ✅  |   ✅  |   ✅    |  ✅   |   ❌   |    ❌   |
| Torre de control (`/torre`)              |  ✅  |   ✅   |   ✅  |   ✅  |   ✅    |  ❌   |   ❌   |    ❌   |
| Panel operativo (`/agente`)              |  ✅  |   ✅   |   ✅  |   ✅  |   ✅    |  ✅   |   ❌   |    ❌   |
| Ver dashboard / KPIs                     |  ✅  |   ✅   |   ✅  |   ✅  |   ✅    |  ✅   |   ✅   |    ✅   |
| Auditar IA (logs + CSV export)           |  ✅  |   ✅   |   ✅* |   ❌  |   ❌    |  ❌   |   ❌   |    ✅   |
| Ingesta / Layout V2                      |  ✅  |   ✅   |   ✅  |   ✅  |   ❌    |  ❌   |   ❌   |    ❌   |

> super² = supervisor · `*` solo lectura · ⚠️ = requiere validación manual

---

## 5. Aislamiento de Datos por Cliente (¿qué ve cada quién?)

```
                            ┌──────────────────────┐
                            │   TENANT "ACME SA"   │
                            └──────────┬───────────┘
                                       │
                  ┌────────────────────┼────────────────────┐
                  │                    │                    │
            ┌─────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
            │ Client A   │      │ Client B    │      │ Client C    │
            │ (Mercado   │      │ (Liverpool) │      │ (Walmart)   │
            │  Libre)    │      │             │      │             │
            └─────┬──────┘      └──────┬──────┘      └──────┬──────┘
                  │                    │                    │
            ┌─────┴──────┐       ┌─────┴──────┐       ┌─────┴──────┐
            │ Shipments  │       │ Shipments  │       │ Shipments  │
            │ Tickets    │       │ Tickets    │       │ Tickets    │
            │ Claims     │       │ Claims     │       │ Claims     │
            └────────────┘       └────────────┘       └────────────┘

  🟢 root_dev / superadmin / admin / coordinator / supervisor / agent
     → ven TODOS los clientes del tenant

  🟡 client_viewer (Client A)
     → DEBERÍA ver solo Client A
     → user.client_id = "uuid-client-A"

  🟡 client_auditor (Client B)
     → DEBERÍA ver IA-logs solo de Client B
     → user.client_id = "uuid-client-B"
```

---

## 6. ⚠️ GAPS DETECTADOS (CRÍTICOS)

### 🔴 G-01 · `client_id` no se enforza automáticamente

**Síntoma**: Un `client_viewer` o `client_auditor` con `client_id="A"` puede llamar a
`/api/admin/ai/consumption` y pasar `?client_id=B` para ver datos de OTRO cliente
del mismo tenant.

**Causa raíz**:
- `CurrentUser` (en `middleware/context.py`) **NO incluye** el campo `client_id`.
- El JWT (`core/security.create_access_token`) **NO incluye** `client_id`.
- Los routes filtran por **query param `client_id`** sin validar contra `user.client_id`.

**Evidencia**:
```python
# routes/ai.py L426-433  — consumption_dashboard
@router_admin.get("/consumption")
async def consumption_dashboard(
    request: Request,
    client_id: str | None = Query(default=None),   # ◄── viene del CLIENTE
    ...
):
    q = {}
    if client_id:
        q["client_id"] = client_id                  # ◄── sin clamp a user.client_id
```

**Fix recomendado**:
1. Añadir `client_id: Optional[str] = None` a `CurrentUser`.
2. Incluir `client_id` en el JWT (`create_access_token`).
3. Cargar `client_id` desde la BD en `AuthTenantMiddleware`.
4. Crear dependencia `enforce_client_scope()` que sobreescriba `client_id` con el del usuario si éste es `client_viewer`/`client_auditor`.

---

### 🟠 G-02 · `client_viewer` aterriza en `/dashboard` (global)

**Síntoma**: `default_landing_for("client_viewer")` retorna `/dashboard`, que muestra
KPIs globales del tenant — un cliente externo NO debería ver eso.

**Fix recomendado**:
- Cambiar a `/portal/client/{client_id}` o `/auditor` con vista de **solo su client_id**.

---

### 🟡 G-03 · No hay validación de `client_id` en escritura

**Síntoma**: `admin_users.py` valida que `client_viewer`/`client_auditor` tengan
`client_id` al crearlos, pero **no valida** que ese `client_id` exista en el tenant.

**Fix recomendado**:
- Verificar `db.clients.find_one({"id": client_id, "tenant_id": actor.tenant_id})` antes de guardar.

---

### 🟡 G-04 · El campo `client_id` no se respeta en logout/sesión

**Síntoma**: Si un admin cambia el `client_id` de un usuario externo activo, la sesión
sigue viva con el `client_id` anterior (porque no está en BD-read tiempo real).

**Fix recomendado**:
- Leer `client_id` fresco de la BD en cada request (ya se hace para `role`/`status`, agregar a la proyección).

---

### 🟢 G-05 · `coordinator` no figura en `_RBAC` de muchos paneles

**Estado**: ✅ Resuelto en iter41 (Bundle G+). Ahora `coordinator+` puede
gestionar usuarios externos. Adicionalmente, `ASSIGNMENT_RULES` define
formalmente quién puede invitar/asignar a quién, sin tabla DB.

**Implementación**:
- `middleware/rbac.py` · `ASSIGNMENT_RULES`, `can_assign_role()`, `assignable_roles_for()`.
- `routes/admin_users.py` · guardrails en POST/PATCH/RESET-PASSWORD/DELETE.
- 19 tests E2E en `tests/test_iter41_bundle_g_plus_assignment_rules.py`.

---

## 7. Recomendación de Diseño (target state)

```
┌───────────────────────────────────────────────────────────────────┐
│                AuthTenantMiddleware (existing)                    │
│                                                                   │
│  1. Decode JWT  → sub, tenant_id, role, [client_id]               │
│  2. DB read     → user (status=active, client_id, must_reset_pwd) │
│  3. Tenant gate → maintenance / suspended                         │
│  4. Build CurrentUser(id, tenant_id, role, email, client_id) ◄── NEW │
└──────────────────────────────┬────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
   ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
   │ require_role()   │ │ require_min_ │ │ enforce_client_  │  ◄── NEW
   │ allow-list       │ │ role()       │ │ scope()          │
   │                  │ │ rank-based   │ │ inject client_id │
   └──────────────────┘ └──────────────┘ └──────────────────┘
                                                 │
                                                 ▼
                          ┌──────────────────────────────────────┐
                          │ Route handler                        │
                          │                                      │
                          │ q = {"tenant_id": user.tenant_id}    │
                          │ if user.client_id:                   │
                          │     q["client_id"] = user.client_id  │
                          │     # (clamp wins over query param)  │
                          └──────────────────────────────────────┘
```

---

## 8. Resumen ejecutivo

| Ítem                                                              | Estado |
|-------------------------------------------------------------------|:------:|
| Jerarquía de 8 roles definida y documentada                       |   ✅   |
| Aislamiento por `tenant_id` (middleware)                          |   ✅   |
| Aislamiento por `client_id` para externos (clamp en routes AI)    |   ✅   |
| `client_id` en `CurrentUser` / JWT / `/me`                        |   ✅   |
| Validación de `client_id` existente en tenant al crear/editar     |   ✅   |
| Landing dedicado para `client_viewer` (→ `/auditor` read-only)    |   ✅   |
| Tests E2E que validen aislamiento entre clients del mismo tenant  |   ✅   |
| **Multi-cliente para externos** (UserScopeAssignment 1:N)         |   ✅   |
| **Delegación de invitación** (ASSIGNMENT_RULES)                   |   ✅   |

> **Bundle G COMPLETO** (iter40 · 2026-02) — clamp 1:1.
> **Bundle G+ COMPLETO** (iter41) — ASSIGNMENT_RULES (coordinators invitan externos).
> **Bundle H COMPLETO** (iter42) — UserScopeAssignment (multi-cliente, lazy migration).
> 610 tests totales pasando, 0 regresiones.
