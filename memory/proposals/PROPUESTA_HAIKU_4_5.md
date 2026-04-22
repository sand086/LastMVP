# Propuesta: Migración Claude Sonnet 4.5 → Haiku 4.5

**Fecha**: 22/04/2026
**Autor**: Equipo LastMile OS
**Scope**: Evaluación IA de evidencias (endpoint `/api/journeys/{id}/evaluate-evidence-all` + worker `ai_eval_worker.py`)
**Decisión esperada**: Cambio de modelo ± opción de hybrid routing

---

## 1. Contexto y problema

Actualmente el motor de evaluación IA usa **`claude-sonnet-4-5-20250929`** vía Emergent LLM key. En los últimos 14 días la plataforma hit `Budget exceeded: $48.35` —bloqueando evaluaciones en producción—, y los jobs promedio tardan **~3 minutos** por ruta de 30 guías (MAX_ROUTES_CONCURRENT=3, TIMEOUT_PER_GUIA=90s).

Anthropic liberó **Claude Haiku 4.5** (Octubre 2025) como el modelo rápido/económico de la familia 4.5, con capacidades multimodales (visión) idénticas a Sonnet para casos de clasificación/detección visual.

## 2. Comparativo técnico

| Métrica                | Sonnet 4.5                | Haiku 4.5                | Diferencia |
|------------------------|---------------------------|--------------------------|------------|
| Precio input /M tokens | **$3.00**                 | **$1.00**                | **-66%**   |
| Precio output /M tokens| **$15.00**                | **$5.00**                | **-66%**   |
| Latencia (<1K prompt)  | 500–800 ms                | **< 200 ms**             | **4-5x más rápido** |
| Vision multimodal      | ✅ (6 img, 200K ctx)       | ✅ (6 img, 200K ctx)      | Paridad    |
| Context window         | 200K (1M beta)            | 200K                     | Suficiente |
| Razonamiento complejo  | Superior                  | Bueno para clasificación | **Aceptable para nuestro caso** |

**Nuestro caso es clasificación visual estructurada** (detectar si la foto cumple 5-7 criterios binarios + nota del driver). No requiere razonamiento multi-step profundo. Haiku 4.5 es el modelo objetivo correcto.

## 3. Proyección de volumen (ME)

Base de cálculo con datos reales del sistema:

- **Rutas/día**: 50 (estimación producción — hoy hay 39 en DB piloto).
- **Guías promedio/ruta**: 40.4 (medido).
- **Evaluaciones/mes**: 50 × 40 × 30 = **60,000 evaluaciones**.
- **Tokens por evaluación** (6 imágenes 1024×1024 base64 + prompt sistema + contexto training + nota driver):
  - Input: ~8,300 tokens (6 imgs × 1,300 + 500 prompt)
  - Output: ~800 tokens (JSON de resultado con observaciones)
- **Volumen mensual**: 498M input + 48M output tokens

## 4. Proyección de costo mensual

| Escenario                  | Input (M tokens)| Output (M tokens)| Costo USD/mes | Costo MXN/mes (TC 20) |
|----------------------------|-----------------|------------------|---------------|------------------------|
| **Sonnet 4.5 (actual)**    | 498             | 48               | **$2,214**    | **~$44,280**           |
| **Haiku 4.5 (propuesto)**  | 498             | 48               | **$738**      | **~$14,760**           |
| **Ahorro mensual**         |                 |                  | **-$1,476**   | **-$29,520**           |
| **Ahorro anual**           |                 |                  | **-$17,712**  | **-$354,240**          |

### Hybrid routing (opcional, recomendado Fase 2)

Rutear por confianza: 90% casos simples → Haiku, 10% casos complejos (discrepancia, foto borrosa) → Sonnet.

- Costo blended: 0.9 × $738 + 0.1 × $2,214 = **$886 USD/mes**
- Mantiene precisión alta donde importa, 60% de ahorro vs Sonnet puro.

## 5. Impacto operacional

| Aspecto                    | Ganancia esperada                                          |
|----------------------------|------------------------------------------------------------|
| **Tiempo por guía**        | 30s → **~8s** (4x más rápido)                              |
| **Jobs/ruta**              | 3 min → **~50 s** (batch de 5 concurrent × 8s + overhead)  |
| **Timeouts**               | De ~35% actual → **< 2%** (holgura amplia con 90s)         |
| **Throughput diario**      | Worker actual: ~3,000 guías/día → **~12,000 guías/día**    |
| **Concurrencia**           | Podemos bajar TIMEOUT_PER_GUIA a 30s sin riesgo            |

## 6. Riesgos y mitigaciones

| Riesgo                                    | Probabilidad | Mitigación                                                             |
|-------------------------------------------|--------------|------------------------------------------------------------------------|
| Precisión menor en casos ambiguos         | Media        | A/B test 500 guías reales (ver §7); fallback a Sonnet vía hybrid       |
| Formato JSON menos estructurado en output | Baja         | Prompt con schema explícito + `_parse_ai_response` ya tolera variantes |
| Regresiones en evidence_score             | Media        | Comparar distribución de scores pre/post 1 semana antes de switch total|

## 7. Plan de implementación

### Fase 1 — A/B Test (1 sprint, 3 días)
- Cambiar `chat.with_model("anthropic", "claude-haiku-4-5-20251001")` en `evidence_scoring._call_ai_vision` via env var.
- Nueva env var `AI_EVAL_MODEL=haiku-4-5` (con `sonnet-4-5` como fallback).
- Ejecutar 500 evaluaciones en paralelo con ambos modelos sobre las mismas guías.
- Comparar: score medio, desviación estándar, % acuerdo con revisión humana, tokens reales consumidos.
- Entregable: `/app/memory/AB_TEST_HAIKU_VS_SONNET.md`

### Fase 2 — Rollout (1 día)
- Si Fase 1 muestra acuerdo >90%: flip a Haiku en producción.
- Mantener Sonnet disponible para endpoint dedicado `/api/journeys/{id}/evaluate-evidence-all?model=sonnet` para casos escalados.

### Fase 3 — Hybrid routing (opcional, 1 sprint)
- Añadir lógica en `_evaluate_single_guia`: si `discrepancy_detected || no_photos || driver_note_length > 200` → Sonnet, else → Haiku.
- Monitorear KPI "% escalación a Sonnet" en `/api/ai-evaluation/health`.

## 8. Presupuesto de implementación

| Concepto                                       | Esfuerzo  | Responsable     |
|------------------------------------------------|-----------|-----------------|
| Cambio de modelo + env var                     | 0.5 día   | Backend         |
| A/B test script + comparativo                  | 1 día     | Backend + Data  |
| Revisión manual de 200 guías para ground truth | 1 día     | Operaciones     |
| Documento comparativo + decisión               | 0.5 día   | PM              |
| Rollout + monitoreo 1 semana                   | 0.5 día   | DevOps          |
| **TOTAL Fase 1 + 2**                           | **3.5 días** |              |

**Costo del A/B test**: 500 guías × $0.14 (Sonnet) + 500 × $0.045 (Haiku) = **~$92 USD (one-shot)**.

## 9. Recomendación

**✅ Aprobar Fase 1 + 2 inmediatamente**. Ahorro proyectado de **$17,712 USD/año** (~$354K MXN) con mismo o mejor throughput. Riesgo bajo dado que el caso de uso (clasificación visual con prompt estructurado) es el sweet-spot de Haiku.

**Fase 3 (hybrid) evaluar post-rollout** según resultados del A/B.

---

*Para aprobar, responder: "OK Haiku Fase 1"*
