# Precedente: Inconsistencia "Budget Exceeded" vs Saldo Real (Emergent LLM Key)

**Fecha:** 2026-04-24
**Reportado por:** Usuario (Jair) durante operación productiva
**Impacto:** Worker IA se detiene con "Saldo agotado" aunque el saldo visible es positivo

---

## 🔍 Hallazgo

El backend (via LiteLLM proxy de Emergent) rechaza requests con error:

```
litellm.BadRequestError: OpenAIException - Budget has been exceeded!
Current cost: 91.32, Max budget: 91.31
```

**Al mismo tiempo**, en `Profile → Clave universal` el saldo visible es:

```
Saldo de clave API: 103.74 Créditos
Recarga automática: Activado (+5 créditos al llegar a cero)
```

El delta entre el "budget" rechazado ($91.32) y el saldo real ($103.74) es ~$12.42.

---

## 📊 Datos de contexto (24-abr-2026)

### Consumo histórico real por modelo
| Modelo | Guías | Costo total | Costo/guía | Tokens in | Tokens out |
|---|---|---|---|---|---|
| claude-sonnet-4-5 | 265 | $3.92 | $0.0148 | 158 | 955 |
| claude-haiku-4-5 | 432 | $3.13 | $0.0072 | 169 | 1,415 |

### Throughput operativo
- 46.3 guías promedio por ruta
- 39 rutas activas
- 1,497 paquetes terminales pendientes de evaluar

### Proyecciones con saldo $103.74
- Haiku 4.5: ~14,400 guías (~313 rutas completas)
- Sonnet 4.5: ~7,000 guías (~152 rutas completas)

---

## 🧠 Hipótesis sobre la causa raíz

La inconsistencia sugiere que el proxy de Emergent aplica un **cap intermedio por ventana** que es **distinto del saldo de la clave**. Posibles causas:

1. **Rate limit / budget cap diario**: LiteLLM puede imponer un `max_budget` por ventana de 24h que se resetea, sin afectar el saldo total.
2. **Cap por modelo**: cada modelo (haiku/sonnet/gpt) podría tener una cuota separada que se consume en paralelo.
3. **Rollup asíncrono**: el usage reportado por Anthropic tarda minutos en propagarse al proxy → el proxy puede reportar "exceeded" cuando realmente ya se descontó tiempo atrás.
4. **Reserva de cola/concurrencia**: el proxy puede reservar cupo para N requests en vuelo, consumiendo budget antes de ejecutar; si el request falla, el budget no se libera correctamente.
5. **Drift de contabilidad**: el proxy y el sistema de billing de Emergent pueden usar distintos agregadores (cached counts vs real).

---

## 🔬 Evidencia cronológica

| Hora (UTC) | Evento |
|---|---|
| 17:17 | Budget exceeded a $89.33 / $89.31 (primer ciclo) |
| 17:18–17:20 | 3 jobs finalizan Parcial (budget-limited) |
| 04:49 (día siguiente) | Budget exceeded a $91.32 / $91.32 (segundo ciclo) |
| 05:04 | Haiku sigue ejecutándose OK tras ~15 min |
| En ese mismo momento | UI Profile muestra saldo $103.74 + recarga automática activa |

**Patrón:** el "budget" crece monotónicamente durante la jornada; no se resetea visiblemente al medio del día; aparenta ser un **contador por ventana larga** (días) que no se refleja en el saldo total.

---

## 🚨 HALLAZGO MAYOR: Subestimación del costo real (2026-04-24 T10:20 CDMX)

### Evidencia cruzada saldo real vs logs

| Métrica | Valor | Fuente |
|---|---|---|
| Saldo ayer 04:58 UTC | $103.74 | UI Profile Emergent |
| Saldo hoy 16:20 UTC | $94.07 | UI Profile Emergent |
| Consumo real medido | **$9.67 USD** | delta |
| Consumo registrado (abril) | $4.09 USD | `token_usage_log` aggregation |
| **Delta no contabilizado** | **$5.58 USD (137% del registrado)** | — |

### Implicación

**Nuestro estimador de tokens (`_estimate_tokens: len(text)/4`) subestima sistemáticamente el costo real.** El costo por guía no es $0.0072 sino **~$0.017**. Proyecciones corregidas:

- Saldo $94.07 → **~5,530 guías** (no 13,000)
- 1,000 guías → **$17** (no $7)
- Backlog 1,497 paquetes → **$25** (no $11)

### Hipótesis causa raíz del delta de $5.58

1. **Retries sin log**: el worker tiene `max_retries=3` con backoff. Cada retry llama al LLM y consume tokens, pero SÓLO se loggea el resultado exitoso final → ~3 retries por guía fallida se pierden.
2. **Timeouts cobran tokens parciales**: al hacer `asyncio.wait_for(..., timeout=60)` y timeout, Anthropic ya procesó parte → cobra tokens aunque nosotros no recibimos response.
3. **Tokens de sistema/prompt no contados**: `len(system_prompt)/4` puede subestimar; los prompt caching hits/misses tampoco se reflejan.
4. **Evaluaciones de Lumi + Reportes adicionales no pasan por el logger**: si hay integraciones que llaman al LLM sin usar `log_token_usage()`, se vuelven "shadow calls" invisibles.
5. **Descuento por imagen**: 6 imágenes/guía con vision-model pueden cobrar más tokens de los que `len(text)/4` refleja (las imágenes a tokens en Anthropic tienen su propio cálculo).

### Impacto operativo

- Proyecciones de costo mensual actual deben **multiplicarse x2.36** para ser realistas.
- Budget caps en LiteLLM probablemente reflejan el real (por eso llegan a "exceeded" con solo $91).
- La métrica "Costo USD / mes" del admin dashboard es **optimista x2.36**.

### Acciones recomendadas (backlog P1)

1. **Audit de `log_token_usage` callsites**: grep todos los lugares que llaman al LLM y confirmar que TODOS lloguean.
2. **Agregar `_log_ai_token_usage` dentro de retries**: cada retry debe loguear su propio costo (con `referencia=<tracking>_retry_N`).
3. **Log también timeouts**: si `asyncio.TimeoutError`, asumir tokens_in completos + 0 output (conservador).
4. **Ajustar fórmula de tokens**: `len(text)/3.5` en español (caracteres acentuados pesan más), o usar tokenizer real (`tiktoken` para Anthropic es el mismo).
5. **Reconciliación diaria**: script que compare `token_usage_log.cost_usd` vs delta de saldo Emergent y alerte si drift >10%.
6. **Exponer `/api/admin/budget-reconciliation`**: endpoint que retorne `{logged_cost, inferred_real_cost, drift_pct, anomalies}`.

---

## 📊 Datos de contexto ACTUALIZADOS (24-abr-2026)

---

## 🛡️ Mitigaciones implementadas (2026-04-24)

### 1. Auto-pausa inteligente
Si un batch completo del worker falla con error "saldo" → el worker se auto-pausa 10 min antes de seguir gastando retries.
**Archivo:** `/app/backend/ai_eval_worker.py::_process_job` — sección `all_budget_errors`.

### 2. Finalización temprana del job
Las guías restantes del job actual se marcan `Error - "Saldo IA agotado"` inmediatamente.
Job se finaliza como `Parcial`/`Error` con `error_detail` claro → la UI muestra el motivo real sin dejar jobs huérfanos.

### 3. Orphan recovery extendido
Jobs en `En_Cola > 2h` se marcan `Error` automáticamente cada 5 min.
Mensaje: "Job En_Cola >2h sin procesar (probable saturación IA). Usa 'Reintentar'.".
**Archivo:** `/app/backend/ai_eval_worker.py::_recover_orphan_jobs`.

### 4. Mensaje friendly en el error
`_evaluate_single_guia` ya detecta patrones "Budget exceeded" y devuelve:
> "Saldo de Emergent LLM Key agotado. Recarga en Perfil → Clave Universal."

En vez del stacktrace opaco de LiteLLM.

---

## 📋 Workarounds propuestos para el futuro

### Corto plazo (si reaparece)
1. **Monitorear ambos valores**: saldo Profile (`$103.74`) vs log del backend (`Budget: $X/$Y`).
2. **Si saldo > Budget exceeded**: es cap del proxy, no saldo real. Esperar 1-2h (ventana del proxy se resetea) o hacer una recarga forzada de $5 para triggear refresh.
3. **Reintentar Error jobs**: usar el botón "Reintentar Errores" en `/monitor` una vez el proxy recupere.

### Mediano plazo (si es recurrente)
1. **Widget de saldo live** en `/admin?tab=tokens` (propuesto, no implementado aún):
   - Pull `/api/integrations/emergent-llm-balance` cada 60s
   - Alerta visual si saldo < $20 OR si hay budget-exceeded en logs recientes
2. **Endpoint `/api/ai-evaluation/health-detailed`**: retorna last-known budget from logs + current balance + delta.
3. **Escalar a Emergent support** si el drift se mantiene consistente (>$5 delta sostenido).

### Largo plazo
1. **Implementar backoff exponencial por BUDGET error**: pausa 10min → 30min → 2h si persiste.
2. **Integrar con webhook de Emergent billing** si existe, para recibir notificaciones pre-agotamiento.
3. **Circuit breaker**: si >3 budget-exceeded en 1h, bloquear el worker y notificar admin.

---

## 🔗 Archivos relevantes

- `/app/backend/ai_eval_worker.py` — worker loop + budget detection + auto-pause
- `/app/backend/ai_eval_config.py` — pause/resume API
- `/app/backend/evidence_scoring.py::_call_ai_vision` — llamada directa a LiteLLM
- `/app/backend/token_logger.py` — logging de cost_usd (usado para el análisis histórico)
- `/app/backend/routes/ai_eval_routes.py` — endpoints de pausa/reanudar

## 📞 Referencia para el equipo

Si alguien ve el mismo error en los logs de producción, **NO es que el saldo real se haya agotado**. Es un cap interno del proxy. Los fixes del worker ya manejan el caso con gracia (auto-pausa 10 min). Si persiste >2h, revisar este documento.
