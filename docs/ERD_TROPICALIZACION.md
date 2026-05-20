# 🔍 ERD Enterprise vs MyExcellence — Análisis de Tropicalización

> **Input**: ERD SaaS Enterprise (Roles, Jerarquías y Privilegios) — propuesto.
> **Objetivo**: Validar el encaje del modelo enterprise sobre la arquitectura
> actual de MyExcellence y proponer un plan de tropicalización **incremental**.

---

## 0. TL;DR — Resumen ejecutivo

| Aspecto                                      | ERD propuesto                  | MyExcellence actual                | Veredicto |
|----------------------------------------------|--------------------------------|------------------------------------|:---------:|
| Multi-tenant                                 | Tenant raíz                    | ✅ Mismo                            |     ✅    |
| Catálogo de roles (8)                        | Tabla `Role` DB-driven         | Constantes hardcoded `ROLE_RANK`   |     🟡    |
| Asignación user → rol                        | M2M (`UserRole`) + audit       | 1:1 (`users.role` string)          |     🟡    |
| Asignación user → scope                      | M2M (`UserScopeAssignment`)    | 1:1 (`users.client_id`)            |     🔴    |
| Permisos por acción                          | `PermissionConcept/Action` ACL | Rank-based en código (`require_*`) |     🟡    |
| Quién puede asignar qué rol                  | `RoleHierarchyRule` (tabla)    | Hardcoded en `admin_users.py`      |     🟡    |
| **Orden jerárquico de entidades**            | **Tenant→Client→Subclient→Project** | **Tenant→Project→Client→Subclient** |  🔴 INVERTIDO |

**Conclusión**: El ERD está bien pensado para un SaaS enterprise genérico, pero
**no se puede aplicar tal cual** sobre MyE. Hay UNA discrepancia bloqueante
(orden de jerarquía) y varias decisiones de diseño que no convienen forzar a
MyE en su madurez actual (8 roles fijos, RBAC funcional, 576 tests).

---

## 1. Mapeo entidad por entidad

### 1.1 `Tenant` · ✅ Match perfecto

| Campo ERD       | Campo MyE        | Notas |
|-----------------|------------------|-------|
| tenant_id PK    | `id` (UUID str)  | MyE usa UUIDs string, no ints |
| name            | `name`           | OK |
| status          | `status`         | OK (active/maintenance/suspended) |
| created_at      | `created_at`     | OK |

> ⚠️ **Diferencia menor**: el ERD usa `int` autoincrement, MyE usa UUID v4.
> Es preferible mantener UUIDs (multi-region safe, no exposición de cardinalidad).

---

### 1.2 `User` · 🟡 Encaje parcial

| Campo ERD       | Campo MyE                  | Diferencia |
|-----------------|----------------------------|------------|
| user_id         | `id`                       | UUID vs int |
| tenant_id FK    | `tenant_id`                | OK |
| email (unique)  | `email` (unique por tenant)| MyE permite mismo email en distintos tenants |
| full_name       | `name`                     | OK |
| status          | `status`                   | OK |
| —               | `role` ⚠️                   | MyE tiene el rol DENTRO de User (no en UserRole) |
| —               | `client_id`                | MyE ancla a UN client |
| —               | `password_hash`            | falta en ERD (asume identity provider externo?) |
| —               | `must_reset_password`      | flujo onboarding |
| —               | `last_login_at`            | auditoría |

> 🔍 **Hallazgo**: El ERD asume autenticación externa (SSO/OAuth) — no incluye
> `password_hash`. Si MyE adopta el modelo, hay que decidir entre:
> (a) mantener auth interna con bcrypt + agregar `password_hash` al ERD
> (b) migrar a OAuth/SSO (cambio mayor).

---

### 1.3 `Role` · 🟡 Filosofía diferente

**ERD** propone una **tabla** con los 8 roles enumerados como filas:
```
Root Dev, Superadmin, Admin, Coordinator, Supervisor, Agente, Client Auditor, Client Viewer
```

**MyE** los tiene como **constantes** en código:
```python
# middleware/rbac.py
ROLE_RANK = {
    "client_viewer": 1, "client_auditor": 1,
    "agent": 2, "supervisor": 3, "coordinator": 4,
    "admin": 5, "superadmin": 6, "root_dev": 7,
}
```

| Pro tabla DB                          | Contra tabla DB                       |
|---------------------------------------|---------------------------------------|
| Admin puede crear "Supervisor Senior" | Migración + cache invalidation        |
| i18n centralizado                     | Roles "custom" rompen tests E2E       |
| Audit log más expresivo               | Complejidad innecesaria si solo hay 8 |

> 🟡 **Recomendación**: **NO migrar** roles a DB en esta etapa. Los 8 roles
> actuales cubren todos los casos de uso de MyE y están blindados con tests.
> El día que el PO pida "roles custom por cliente", se evalúa.

---

### 1.4 `UserRole` · 🟡 Multi-rol

**ERD**: un user puede tener N roles (M2M con `assigned_by_user_id`).
**MyE**: 1 rol por user.

| Caso de uso              | ¿Necesita multi-rol?  |
|--------------------------|:---------------------:|
| Admin que también monitorea como Supervisor | 🟢 Sí, pero hoy se resuelve con rank=admin (admin > supervisor) |
| Coordinator que audita IA en su tiempo libre | 🟡 Sí, requeriría 2 roles |
| Cliente externo viewer + auditor             | 🟢 Resuelto: client_auditor ya incluye permisos de client_viewer (rank 1=1) |

> 🟡 **Recomendación**: **NO adoptar multi-rol**. El sistema de **rank** ya cubre
> el caso "admin puede hacer todo lo de supervisor". Multi-rol introduce
> ambigüedad ("¿qué rol uso para este endpoint?") y complejidad en RBAC.

---

### 1.5 `UserScopeAssignment` · 🔴 ESTE SÍ es crítico

**ERD**: tabla M2M que asigna user → (tenant | client | subclient | project) con
`required: boolean`. **Un usuario puede tener N asignaciones**.

**MyE**: `users.client_id` es **un único valor** (string).

#### Casos de uso reales que MyE NO puede modelar hoy:

1. **Cuenta auditor multi-cliente**: PwC audita a 3 clientes del mismo tenant.
   → Hoy hay que crearle 3 cuentas separadas.
2. **Cuenta viewer multi-subclient**: Un dueño de marca quiere ver 2 subclients.
   → Hoy hay que duplicar.
3. **Cuenta interno con scope reducido**: Agente especializado en 2 clients,
   no en los 20 del tenant.
   → Hoy: imposible (interno = ve todo el tenant).

> 🔴 **Recomendación**: **SÍ adoptar `UserScopeAssignment`** en Bundle H.
> Es la única pieza del ERD que aporta capacidad nueva y reusa lo construido en
> Bundle G. **Es la evolución natural de G-01**.

---

### 1.6 `PermissionConcept` + `PermissionAction` + `RolePermission` · 🟡 Sobre-engineering

**ERD** propone un sistema ACL completo:
- `PermissionConcept` agrupa acciones (ej: "Administración de roles")
- `PermissionAction` es la acción atómica (ej: "Configurar Admin")
- `RolePermission` es la matriz role × action → allowed

**MyE** lo resuelve hoy con:
```python
_RBAC = require_role("root_dev", "superadmin")
_AUDIT_READ_RBAC = require_role("root_dev", "superadmin", "admin", "client_auditor", "client_viewer")
```

#### ¿Cuándo conviene migrar a ACL?

| Hoy MyE                                      | Cuándo migrar a ACL |
|----------------------------------------------|---------------------|
| Tiene ~40 endpoints con `require_*`           | Cuando lleguemos a ~200 |
| Cambios de RBAC son cambios de código (lentos) | Cuando el PO quiera tocar permisos sin deploy |
| Todos los roles tienen permisos coherentes    | Cuando "Admin del Tenant X" deba ver menos que "Admin del Tenant Y" |

> 🟡 **Recomendación**: **NO adoptar ACL completo aún**. En su lugar, adoptar
> un **subconjunto**: una tabla `tenant_feature_flags` que permita activar/
> desactivar features por tenant (ej: "este tenant tiene WhatsApp", "este
> tenant tiene IA"). Es ~10% del trabajo del ACL y resuelve el 80% del valor.

---

### 1.7 `RoleHierarchyRule` · 🟡 Útil pero sobredimensionado

**ERD**: tabla que define "rol X puede asignar rol Y en scope Z".

**MyE**: `admin_users.py` hardcoded — solo `root_dev | superadmin` administran usuarios.

#### Caso de uso real:
- "Coordinator de cliente A puede invitar viewers a SU client A" — hoy no se puede.
- "Admin del tenant puede crear Supervisores pero NO otros Admins" — hoy sí (admin guardrail solo previene self-degradation).

> 🟡 **Recomendación**: **NO adoptar como tabla**, sí formalizar como
> **YAML/dict config** en `middleware/rbac.py`. Más simple, igual de potente.

```python
# Propuesta concreta — añadir a rbac.py
ASSIGNMENT_RULES = {
    "root_dev":   {"can_assign": ["*"],                          "scope": "tenant"},
    "superadmin": {"can_assign": ["admin","coordinator","supervisor","agent","client_viewer","client_auditor"], "scope": "tenant"},
    "admin":      {"can_assign": ["coordinator","supervisor","agent"], "scope": "tenant"},
    "coordinator": {"can_assign": ["client_viewer","client_auditor"],   "scope": "client"},  # NUEVO
    # ...
}
```

---

### 1.8 Jerarquía de entidades · 🔴 INVERTIDA

Este es el **gap bloqueante**.

```
ERD propuesto:                      MyExcellence actual:
┌─────────┐                         ┌─────────┐
│ Tenant  │                         │ Tenant  │
└────┬────┘                         └────┬────┘
     │                                   │
     ▼                                   ▼
┌─────────┐                         ┌─────────┐
│ Client  │  ◄──┐                   │ Project │  ◄──┐
└────┬────┘     │                   └────┬────┘     │
     │          │ "carteras"             │          │
     ▼          │                        ▼          │
┌──────────┐    │                   ┌─────────┐     │
│ Subclient│    │                   │ Client  │     │
└────┬─────┘    │                   └────┬────┘     │
     │          │                        │          │
     ▼          │                        ▼          │
┌─────────┐  ◄──┘ "iniciativas"     ┌──────────┐ ◄──┘
│ Project │                         │ Subclient│
└─────────┘                         └──────────┘
```

#### ¿Cuál es "correcta" semánticamente?

| Semántica | ERD (Project leaf)                       | MyE (Client mid)                      |
|-----------|------------------------------------------|---------------------------------------|
| Tenant    | Empresa que paga el SaaS                 | = mismo                               |
| Project   | "Iniciativa interna del cliente"         | "Vertical de negocio del tenant"     |
| Client    | Marca/cuenta del tenant                  | "Marca" dentro de la vertical         |
| Subclient | Sub-marca / categoría                    | = mismo                               |

#### Veredicto

- El ERD asume que **Project es la unidad operativa más fina** (típico en consultoría: "Cliente Liverpool > Proyecto Black Friday 2026").
- MyE asume que **Subclient es la unidad operativa más fina** y **Project es una agrupación administrativa de alto nivel** (típico en logística: "Vertical e-commerce > Cliente Liverpool > Subclient Liverpool Express").

**Ambos modelos son válidos**. Migrar el orden sería un cambio MAYOR:
- 21 colecciones referencian la estructura actual.
- Routal multi-project (1 ApiKey → N project_ids) ya está integrado bajo el modelo actual.
- 576 tests asumen el orden actual.

> 🔴 **Recomendación inmediata**: **Adaptar el ERD al orden de MyE**, no al revés.
> Comunicar al autor del ERD que la jerarquía debe ser:
>
> ```
> Tenant → Project → Client → Subclient
> ```
>
> Y que `Project` agrupa una **vertical/línea de negocio** (no una iniciativa puntual).
> Si más adelante se necesita "Iniciativa" como concepto de 5° nivel, se modela
> como `Initiative` colgando de `Subclient`.

---

## 2. Plan de Tropicalización · Bundle H sugerido

### 2.1 Adoptar (alto ROI, bajo riesgo)
- ✅ **`UserScopeAssignment`** (sección 1.5) — habilita multi-scope para externos.
  - Migrar `users.client_id` → colección `user_scope_assignments`.
  - Backwards-compat: si existe `users.client_id`, autogenerar 1 row en la nueva colección al primer login.
  - Adaptar `resolve_client_scope()` para devolver `list[str]` cuando aplique.
  - Adaptar las queries Mongo a `{client_id: {"$in": user.allowed_clients}}`.

### 2.2 Formalizar (sin tabla)
- 🟡 **`ASSIGNMENT_RULES`** (sección 1.7) — config dict en `rbac.py`.
  - 1h de trabajo, evita la tabla `RoleHierarchyRule`.
  - Permite reglas "Coordinator puede invitar Viewers a SU client".

### 2.3 Posponer (cuando el negocio lo pida)
- 🟡 Roles en DB (`Role`) — sólo si hay demanda de "roles custom por tenant".
- 🟡 Multi-rol (`UserRole`) — sólo si hay caso de uso real.
- 🟡 ACL completo (`PermissionAction`) — sólo cuando los endpoints superen ~150.

### 2.4 Rechazar
- ❌ Cambio del orden Tenant→Client→Subclient→Project. Se mantiene el actual.

---

## 3. Próximos pasos sugeridos

| Prioridad | Tarea                                                  | Esfuerzo |
|:---------:|--------------------------------------------------------|:--------:|
| 🔴 P0     | Validar con el autor del ERD el orden de la jerarquía  | 30 min   |
| 🟢 P1     | Bundle H · `UserScopeAssignment` (multi-cliente)        | 1 día    |
| 🟢 P1     | `ASSIGNMENT_RULES` config + endpoint de invitación      | 0.5 día  |
| 🔵 P3     | `tenant_feature_flags` (mini-ACL)                       | 1 día    |
| 🔵 P3     | Migración a OAuth/SSO (cuando el cliente lo pida)       | 1 sprint |

---

## 4. Anexo · Compatibilidad con Bundle G

El cambio recomendado (`UserScopeAssignment`) es **100% compatible** con
Bundle G. Sólo cambia el **payload** de `resolve_client_scope`:

```python
# Bundle G (hoy)
def resolve_client_scope(user, requested) -> str | None:
    if user.is_external() and user.client_id:
        return user.client_id  # un solo client_id
    return requested

# Bundle H (propuesto)
def resolve_client_scope(user, requested) -> str | list[str] | None:
    if user.is_external():
        allowed = user.allowed_client_ids  # list[str] desde user_scope_assignments
        if not allowed:
            raise RbacDeniedException(...)
        if requested and requested in allowed:
            return requested  # honor request si está dentro de scope
        return allowed  # → query Mongo: {"client_id": {"$in": allowed}}
    return requested
```

Los 18 tests de Bundle G **siguen pasando sin modificación** porque
`allowed_client_ids = [user.client_id]` en backwards-compat.

---

> **Generado**: Feb 2026 · iter40+
> **Autor sugerido para revisar**: PO + autor del ERD enterprise
