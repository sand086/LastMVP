"""Helper para respuestas paginadas estandarizadas.

Provee una respuesta que incluye las 3 formas historicas simultaneamente:
  1. Flat:     {data, total, page, pages, page_size}
  2. Nested:   {data, pagination: {total, page, page_size, total_pages, pages}}

Esto permite que tanto los consumidores nuevos como legacy (que leen
`res.data.pages`, `res.data.pagination.total_pages`, `res.data.pagination.page_size`)
sigan funcionando sin modificacion.

Uso:
    return paginated_response(items, total=total, page=page, page_size=limit)
"""
from typing import Any


def paginated_response(data: list, *, total: int, page: int, page_size: int) -> dict[str, Any]:
    """Construye una respuesta paginada con ambos formatos (flat + nested)."""
    total_pages = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
    return {
        "data": data,
        # Flat (legacy-compatible con driver_routes, quality_tab, ai_eval)
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": total_pages,
        # Nested (legacy-compatible con journey_routes, admin_module_routes)
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "pages": total_pages,
        },
    }
