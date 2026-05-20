"""Rule projection — Bundle B · R50.

Patrón sistémico introducido por Bundle B: las reglas del runtime
(R02, R03, R28, ...) se proyectan a la UI ANTES de la acción del
usuario, eliminando la fricción del descubrir-vía-403.

Arquitectura:
  services/rules/
    evaluators/        — un evaluator por regla (R02, R03, R28)
    projection_service — orquesta evaluators y produce TicketProjection / ReclamoProjection
    cache              — adapter de cache (Mongo TTL collection)

Las proyecciones se incluyen en GET /api/agent/tickets/{id} y
GET /api/reclamos/{id}. Hay un endpoint de debug solo para root_dev:
GET /api/admin/rules/explain.

NOTA importante: la proyección es OPTIMISTA. El backend siempre revalida
en el submit y devuelve 403/422 si la regla cambió en runtime; el
endpoint /api/agent/tickets/{id} se refetcha en ese caso.
"""
