# Shadow Cost Audit — 2026-04-24

## Síntoma reportado por usuario
- Habilitó worker IA en `/admin` ~10 min antes
- Saldo Universal Key bajó de manera "considerable"
- Detalle por evento (`/admin` Token Usage) NO mostraba actualizaciones que justifiquen el consumo
- Monitor IA mostraba jobs en `Error` con `0/N` y `0 tokens`

## Root cause (post-mortem)
La función `_call_ai_vision` en `evidence_scoring.py` ejecutaba:
```python
response_text = await chat.send_message(user_msg)   # ← Anthropic factura aquí
await _log_ai_token_usage(...)                       # ← Solo si NO hay excepción
```

Si `chat.send_message()` lanzaba excepción (timeout, rate-limit 429/529, network error), Anthropic **YA HABÍA RECIBIDO** el request — esto incluye el system prompt completo (~500 tokens) + user context (~300 tokens) + 1-3 imágenes base64 (~1500 tok cada una, ~5K-6K en total). Sin embargo, `_log_ai_token_usage` **nunca se ejecutaba** porque la excepción saltaba directamente al caller.

El shadow log compensatorio en `ai_eval_worker.py` (timeout/error branches) loguaba sólo `tracking_number[:100]` (≈30 chars = ~7 tokens estimados), subestimando el cargo real en 600-1000×.

Con N intentos fallidos (rate limit cascade típico ~50-100 evals), eso produce **$0.30-$1.00 USD invisibles** por ráfaga.

## Tipos de eventos donde ocurría
| Tipo | Causa | Costo invisible típico |
|---|---|---|
| `error_before_response` | Timeout asyncio.wait_for + cancelación de send_message | ~$0.005-0.010 / eval |
| `error_before_response` | Anthropic 529 Overloaded / 429 rate limit | ~$0.005-0.010 / eval |
| `error_before_response` | Network drop o DNS issue intermitente | ~$0.005-0.010 / eval |

## Fix aplicado (2026-04-24, iter51)
1. **`token_logger.py`**:
   - Agregado parámetro `image_count` → `tokens_images = image_count * 1500` sumado a `tokens_input`
   - Agregados flags `is_shadow_cost`, `shadow_kind` para auditoría
   - Persiste `image_count` y `tokens_images` en cada doc

2. **`evidence_scoring.py::_call_ai_vision`**:
   - Wrap `chat.send_message` en try/except
   - Si lanza excepción → log shadow event con contexto REAL (system + user prompt + image count) + `is_shadow_cost=True` + `shadow_kind="error_before_response"`, luego re-raise
   - Si exitoso → log normal con `is_shadow_cost=False` + propaga `_tokens_used_estimate` y `_image_count` al resultado

3. **`ai_eval_worker.py`**:
   - Eliminados shadow logs duplicados (ahora `_call_ai_vision` ya cubre 100% de los casos donde Anthropic facturó). Esto evita doble conteo
   - El worker stat `tokens_consumidos` ahora refleja consumo real porque `tokens_used` se propaga desde `_build_ai_result`

4. **`admin_module_routes.py`**:
   - `/admin/token-usage` ahora incluye `summary.shadow.{by_kind, total_count, total_cost_usd}` y `summary.totals.shadow_cost_usd / shadow_cost_pct`

5. **`TokenUsageTab.jsx`**:
   - Banner ámbar superior cuando `shadow.total_count > 0` con desglose por tipo
   - Nueva columna "Tipo" en la tabla (badge `Shadow` o `OK`)
   - Iconito `📷×N` junto a la referencia cuando hay imágenes adjuntas
   - Filas shadow con fondo ámbar para escaneo rápido

## Cómo validar el fix
1. Habilitar worker IA → encolar evaluación → `/admin/token-usage` debe mostrar:
   - Si todo OK: filas verdes "OK" con `image_count > 0` y `tokens_images > 0`
   - Si Anthropic falla (429/529/timeout): filas ámbar "Shadow" + banner superior
2. Pytest: `pytest tests/test_iter51_shadow_costs.py -v` → 4/4 PASSED
3. Reconciliación: comparar `summary.totals.cost_usd` (mes actual) vs `Saldo de clave API` en Profile → diferencias > 5% antes del fix; después del fix deben coincidir ±1% (tolerancia de imágenes con dimensiones distintas)

## Tickets futuros relacionados
- [ ] Migrar eventos históricos: agregar `is_shadow_cost: false` y `image_count: 0` a documentos antiguos para evitar `null` en UI (P3, cosmético)
- [ ] Captcha de imágenes: implementar `image_token_estimate(width, height)` con escala 1.5K→5K basada en dimensiones reales (actual: estático en 1500). Las fotos comprimidas a 1920px (post-fix de iter49) caen en el rango 1.5K-2K, así que la estimación está bien por defecto
- [ ] Alerta proactiva: si `shadow_cost_pct > 5%` en una hora, enviar webhook a Slack/email del coordinador
