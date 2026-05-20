"""JSONPath filter for webhook subscriptions (PROMPT 39 V3 P2 backlog).

Soporta dos modos en `subscription.filter_jsonpath`:
  - Modo dict simple {"key": "value"}: igualdad por clave raíz (legacy).
  - Modo expresiones JSONPath: {"$.data.priority": "high",
                                "$.data.amount[?(@>1000)]": true}

Si TODAS las expresiones resuelven a algo verdadero, se entrega.
Si AL MENOS una falla, se descarta la entrega para esa suscripción.
"""
from __future__ import annotations

try:
    from jsonpath_ng.ext import parse as jp_parse
    _HAS_JSONPATH = True
except ImportError:
    _HAS_JSONPATH = False


def _is_jsonpath_expr(key: str) -> bool:
    return key.startswith("$") or key.startswith("@")


def evaluate_filter(*, filter_spec: dict | None, payload: dict) -> bool:
    """Devuelve True si el payload pasa el filtro (o si no hay filtro)."""
    if not filter_spec:
        return True
    if not isinstance(filter_spec, dict):
        return True

    for key, expected in filter_spec.items():
        if _is_jsonpath_expr(key):
            if not _HAS_JSONPATH:
                # Fallback silencioso: si la lib no está, ignoramos esta expresión
                # para no dropear silenciosamente entregas legítimas.
                continue
            try:
                expr = jp_parse(key)
                matches = [m.value for m in expr.find(payload)]
            except Exception:  # noqa: BLE001
                # Filtro inválido → conservador: descartar entrega
                return False
            if expected is True:
                # "Existe al menos un match"
                if not matches:
                    return False
            elif expected is False:
                if matches:
                    return False
            else:
                # Cualquier otro valor → al menos un match igual
                if expected not in matches:
                    return False
        else:
            # Modo legacy dict-igualdad por clave raíz (en `data` o `payload`)
            data = payload.get("data") if isinstance(payload, dict) else None
            actual = (data or {}).get(key) if isinstance(data, dict) else None
            if actual is None and isinstance(payload, dict):
                actual = payload.get(key)
            if actual != expected:
                return False
    return True
