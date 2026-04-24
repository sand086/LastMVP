# Diccionario técnico — Página `/reports` (Reporteria Operativa)

**Producto:** LastMile OS — módulo ME (Mensajería y Estrategias)
**Versión:** 2026-04-24
**Audiencia:** Coordinación operativa, finanzas, Dirección, equipo IT
**Propósito:** Documentar cada tablero, gráfica e indicador visible en `/reports` con su definición, metodología de cálculo, fuente de datos y lectura operativa recomendada.

---

## 1. Arquitectura general de la página

La página `/reports` se compone de **cinco bloques** y **siete pestañas (tabs)**:

| Bloque | Ubicación | Fuente de datos (endpoint) |
|---|---|---|
| 1. Barra de filtros | Superior | — |
| 2. KPI Strip (4 tarjetas) | Debajo de filtros | `POST /api/reports/generate` + `GET /api/reports/sla` + `GET /api/reports/quality` |
| 3. Charts Section (combo + dona) | Bajo KPI Strip | `POST /api/reports/generate` |
| 4. Bloque IA (tarjetas dinámicas + narrativa) | Bajo Charts | `POST /api/reports/generate-ai` |
| 5. Tablero de tabs (7) | Inferior | Varía por tab |

Los filtros comunes son: **Periodo** (Hoy, 7d, 15d, Mes actual, Mes anterior, Semana anterior, Personalizado), **Cliente**, **Proveedor**, **Fechas personalizadas** (si Periodo=Personalizado).

---

## 2. KPI Strip — 4 tarjetas superiores

**Archivo:** `frontend/src/pages/Reports.jsx` (componente `KPIStrip`).
**Data-testid:** `kpi-strip`.
**Regla de color (health):** verde si valor ≥ 90, ámbar si 70–89, coral si < 70.

### 2.1 Tasa de entrega
- **Definición:** Porcentaje de paquetes cargados que fueron entregados exitosamente al destinatario en el periodo seleccionado.
- **Fuente:** `reportData.delivery_rate` (endpoint `POST /api/reports/generate`).
- **Fórmula backend:**
  ```
  delivery_rate = (total_delivered / total_packages) × 100
  ```
  Donde `total_delivered = Σ j.packages_delivered` y `total_packages = Σ j.packages_total` sobre todos los `journeys` del periodo.
- **Delta (pp):** comparación vs el mismo rango de tiempo anterior (p. ej. "7d" vs los 7 días previos). Se calcula como `delivery_rate_actual − delivery_rate_prev`.
- **Lectura:** mide efectividad operativa integral (depende de direcciones correctas, gestión del driver, disponibilidad del cliente y del proveedor).

### 2.2 Tasa de visita
- **Definición:** Porcentaje de paquetes efectivamente atendidos (entregados o marcados como fallido) sobre el total cargado. Mide cobertura geográfica, no éxito.
- **Fórmula frontend:**
  ```
  visit_rate = (total_delivered + total_failed) / total_packages × 100
  ```
- **Lectura:** una tasa de visita baja indica paquetes pendientes sin intento (problema de capacidad/ruta, no de gestión de entrega).

### 2.3 Calidad evidencias
- **Definición:** Score promedio (0–100) de las evidencias fotográficas cargadas al cerrar ruta, evaluadas por IA y/o reglas. Mide qué tan completa y legible está la documentación probatoria.
- **Fuente:** `qualityData.summary.avg_score` (endpoint `GET /api/reports/quality`).
- **Fórmula backend:**
  ```
  avg_score = mean( ai_score ?? evidence_score )  para cada paquete con alguno de los dos valores
  ```
  Solo se consideran paquetes con `evidence_type ∈ {exitosa, terceros, devolucion, falla}` y `ai_score ≠ null` ó `evidence_score ≠ null`.
- **Target:** 90%. Meta Cubbo estándar para evidencias defensibles en reclamo.

### 2.4 SLA vs Target
- **Definición:** Comparación del SLA consolidado (entregas/paquetes) contra el target activo definido en brackets.
- **Fuente:** `slaData.consolidated` (endpoint `GET /api/reports/sla`).
- **Fórmula backend:**
  ```
  consolidated.actual = (Σ packages_delivered / Σ packages_total) × 100
  consolidated.target = bracket[status="active"].target
  delta = actual − target      (expresado en pp)
  ```
- **Brackets predeterminados:** Mes 1-2 = 65% (superado), Mes 3-4 = 75% (activo), Mes 5+ = 90% (pendiente). Configurables vía `PATCH /api/config/sla-targets` (sólo coordinador/developer).

---

## 3. Charts Section — Combo chart + dona

**Data-testid:** `charts-section`. Dos columnas: 3fr (combo) + 2fr (dona).

### 3.1 Órdenes asignadas vs Tiempo promedio de entrega (combo chart)
- **Tipo:** `ComposedChart` de Recharts (barra + línea con doble eje Y).
- **Series:**
  - **Barras (eje Y izquierdo):** `ordenes` — número de órdenes cargadas por día.
  - **Línea (eje Y derecho):** `tiempo_min` — tiempo promedio de entrega por paquete en minutos.
- **Fuente:** `journeyChartData[]`. Se construye desde los journeys del rango, agregando por fecha.
- **Cálculo de `tiempo_min`:**
  ```
  tiempo_min = Σ (close_data.end_time − start_data.departure_time) / Σ packages_delivered
  ```
  *En minutos, por día.*
- **Lectura:** ayuda a detectar días con sobrecarga (muchas órdenes) que no impactan el tiempo (buena planeación) y viceversa.

### 3.2 Desglose de incidencias (donut)
- **Tipo:** `PieChart` de Recharts con `innerRadius=42`, `outerRadius=70` (dona).
- **Segmentos:** un segmento por tipo de incidencia, coloreado del arreglo `DONUT_COLORS` (coral, ámbar, teal, azul, púrpura, verde).
- **Centro:** total absoluto de incidencias del periodo.
- **Leyenda:** lista de tipos con conteo absoluto y % relativo.
- **Fuente:** `reportData.incidents_by_type` (objeto `{tipo: count}`).
- **Fórmula backend:**
  ```
  incidents_by_type[i.incident_type] += 1  ∀ i ∈ incidents del periodo
  ```
- **Catálogo de tipos (enum):** Evidencia incorrecta, Dirección incorrecta/Cliente ausente, Paquete dañado, Demora del driver, Zona sin acceso, Otro.
- **Nota operativa:** Incidencias de **"Zona sin acceso"** NO penalizan el SLA del driver.

---

## 4. Bloque IA (opcional, generado bajo demanda)

**Componente:** `AiInsightsBar`. **Endpoint:** `POST /api/reports/generate-ai`. **Modelo:** Claude Sonnet 4.5 vía Emergent LLM Key.

### 4.1 Tarjetas dinámicas (alerta / tendencia / logro)
- **Hasta 3 tarjetas** por generación, cada una con:
  - `tipo` ∈ {alerta (coral), tendencia (azul), logro (verde)}
  - `titulo` (≤ 60 chars)
  - `cuerpo` (≤ 280 chars)
  - `metrica` (valor numérico destacado, opcional)
  - `variacion` (delta vs periodo anterior, opcional)
- **Fuente:** la IA recibe un JSON estructurado con los KPIs del periodo + periodo previo y devuelve estas tarjetas en JSON strict.

### 4.2 Reporte ejecutivo IA (narrativa Markdown)
- **Formato:** Markdown renderizado con DOMPurify (solo tags `h3, br, strong, p, em, ul, li, ol`).
- **Longitud:** 400–800 palabras.
- **Estructura esperada (system prompt):** Resumen ejecutivo → Fortalezas → Áreas críticas → Recomendaciones accionables.
- **Costo aprox:** $0.02–$0.05 USD por generación (modelo Sonnet 4.5, input ~3K tokens, output ~1K tokens).
- **Stale:** si cambian los filtros sin regenerar, aparece banner ámbar "Los filtros cambiaron desde la última generación" con botón "Regenerar IA".

---

## 5. Tabs inferiores — 7 pestañas

**Componente orquestador:** líneas 940–970 de `Reports.jsx`. Las tabs solo se renderizan si `hasData === true`.

### 5.1 Tab **Proveedores** (`ProvidersTab`)
- **Fuente:** `reportData.provider_metrics` + `slaData.by_provider`.
- **Columnas y fórmulas:**
  | Columna | Fórmula | Notas |
  |---|---|---|
  | Proveedor | `provider.name` | precedido de dot verde (activo) o gris (sin actividad el día) |
  | Días op. | `len({j.date ∀ j ∈ journeys del proveedor})` | cuántos días distintos operó en el periodo |
  | Rutas | `Σ 1` por journey del proveedor | total de journeys asignados |
  | Paquetes | `Σ packages_total` | paquetes cargados |
  | Entregados | `Σ packages_delivered` | |
  | Entrega% | `delivered / packages_loaded × 100` | Rate cell con barra horizontal, coloreada |
  | Visita% | `(delivered + failed) / packages_loaded × 100` | |
  | Km totales | `Σ close_data.km_traveled` | |
  | SLA | `SlaBadge(actual=sla_actual, target=75)` | 3 estados: On target (≥ target), At risk (target−5 a target), Breach (< target−5) |
- **Ordenamiento:** click en cualquier header (hook `useSortableTable`). Default: `delivery_rate desc`.

### 5.2 Tab **Drivers** (`DriversTab`)
- **Fuente:** `reportData.driver_metrics`.
- **Columnas:** Driver, Días op., Rutas, Paquetes, Entregados, **SLA individual** (= `delivery_rate` del driver), Km.
- **Resaltado:** filas con `delivery_rate < 60%` en fondo ámbar.
- **Política de strikes** (nota al pie): 1er aviso → 2do descanso operativo → 3ro baja.

### 5.3 Tab **Incidencias** (`IncidentsTab`)
- **Fuente:** `reportData.incidents_by_type`.
- **Columnas:** Tipo de incidencia, Total.
- **Nota al pie:** "Incidencias de zona (accesibilidad) NO penalizan el SLA del driver".

### 5.4 Tab **Intentos** (`AttemptsTab`) — NUEVO
- **Fuente:** `GET /api/reports/attempts`.
- **Sección A: Distribución de intentos**
  | Barra | Fórmula |
  |---|---|
  | 1er intento | `packages.attempt_number == 1` |
  | 2do intento | `packages.attempt_number == 2` |
  | 3er+ intento | `packages.attempt_number >= 3` |
  - Si no hay `attempt_number` en BD, se infiere: `first=delivered`, `second=failed`, `third=pending`.
  - El `pct` se calcula `count / total_packages × 100` con redondeo entero.
- **Sección B: Causa de reintento (2do+)** — clasificación heurística desde `incident_type`:
  | Clave | Patrón (lowercase) en `incident_type` |
  |---|---|
  | `driver_management` | contiene "driver", "mensajero" o "tardanza" |
  | `client_absent` | contiene "ausente", "destinatario" o "cliente" |
  | `wrong_address` | contiene "dirección", "address" o "direccion" |
  | `zone_no_access` | contiene "zona" o "acceso" |
  - El pct se calcula sobre `Σ cause_map.values()`, NO sobre total de paquetes.
- **Nota al pie:** "Reintentos impactan directamente el costo operativo".

### 5.5 Tab **Evidencias** (`QualityTab`)
- **Fuente:** `GET /api/reports/quality`.
- **Layout:** 240px fijo (panel score) + 1fr (tablas).
- **Panel izquierdo (Score global):**
  - **Dígito grande:** `summary.avg_score` con color por umbral (≥90 verde, 70–89 ámbar, <70 coral).
  - **Completas:** `summary.complete` = paquetes con `score == 100`.
  - **Incompletas:** `summary.incomplete` = paquetes con `score < 60`.
  - (Parciales, 60≤s<100, no se muestran en UI pero sí en API.)
  - **Barra de progreso:** `min(avg/90 × 100, 100)%`. Target 90%.
- **Panel derecho:**
  - **Por tipo de evidencia** (chips): `{type}: {count} ({avg_score}%)`. Tipos comunes: `exitosa`, `terceros`, `devolucion`, `falla`.
  - **Por proveedor** (barras horizontales): `avg_score` por proveedor, coloreadas por umbral (≥85 verde, 70–84 ámbar, <70 coral).

### 5.6 Tab **SLA** (`SLATab`)
- **Fuente:** `GET /api/reports/sla`.
- **Layout:** dos columnas 1fr/1fr.
- **Columna izquierda — SLA Consolidado:**
  - **Dígito grande:** `consolidated.actual` (%).
  - **Fórmula:** `(Σ packages_delivered / Σ packages_total) × 100` sobre todos los journeys del periodo con filtros.
  - **Barra:** `min(actual/target × 100, 100)%`. Coloreada verde si actual≥target, ámbar si menor.
  - **Brackets de escalamiento** (editables por coordinador/developer):
    | Bracket | Target típico | Estado |
    |---|---|---|
    | Mes 1-2 | 65% | exceeded (superado) |
    | Mes 3-4 | 75% | active (en curso) — determina el target consolidado |
    | Mes 5+ | 90% | pending (pendiente) |
    - **Edición inline:** `<input type="number">` con `onBlur` → `PATCH /api/config/sla-targets` (persistido en `config.sla_targets`).
- **Columna derecha:**
  - **Tabla "Por proveedor":** Proveedor, SLA actual (rate cell), Target, Brecha (`gap_pp = sla_actual − target`, coloreado), icono (✓ si above, ⚠ si below). Filas en below resaltadas coral.
  - **Tabla "Top drivers"** (top 8): Driver, SLA, vs Target, icono. Mismo tratamiento visual.

### 5.7 Tab **Tendencias** (`TrendsTab`) — NUEVO (2026-04-24)
- **Fuente:** `GET /api/reports/kpis?date_from=X&date_to=Y&group_by={day,week,month}`.
- **Control superior:** toggle Día/Semana/Mes (data-testid `trends-groupby-{day|week|month}`).
- **Fila superior — 4 MiniKPIs:**
  | KPI | Fuente | Trend chip |
  |---|---|---|
  | Rutas totales | `summary.total_journeys` | — |
  | Paquetes totales | `summary.total_packages` | — |
  | Entregados | `summary.total_delivered` | — |
  | Delivery rate promedio | `summary.delivery_rate` | Δ vs primer punto del periodo |
- **Gráfico A — "Tasa de entrega a lo largo del tiempo":**
  - `LineChart` Recharts, eje Y 0–100% fijo.
  - `delivered_rate = (packages_delivered / packages_total) × 100` por bucket temporal.
- **Gráfico B — "Volumen de paquetes por período":**
  - `ComposedChart` Recharts con doble eje Y.
  - Barras apiladas (eje izq.): Entregados (verde), Fallidos (coral), Pendientes (ámbar).
  - Línea (eje der.): Delivery rate % (púrpura).
- **Buckets:**
  | `group_by` | Clave |
  |---|---|
  | `day` | `YYYY-MM-DD` |
  | `week` | `YYYY-WNN` (ISO week) |
  | `month` | `YYYY-MM` |

---

## 6. Acciones exportables

### 6.1 Exportar Excel
- **Endpoint:** `POST /api/reports/generate-excel`.
- **Formato:** XLSX multi-pestaña (Resumen, Proveedores, Drivers, Incidencias, Paquetes crudos).
- **Usado para:** análisis ad-hoc y archivo histórico en Google Drive.

### 6.2 Exportar PDF
- **Endpoint:** frontend `generateMultiPagePDF` (`lib/pdfReportGenerator.js`), jsPDF + autoTable.
- **Páginas:** Portada (KPI cards + stat boxes + dona paquetes), Proveedores, Drivers, Incidencias (con dona nativa), Intentos, Evidencias, SLA, Herramientas tecnológicas (IA).
- **Usado para:** entrega a clientes (Belgos/SOP/Cubbo), juntas ejecutivas semanales.

---

## 7. Endpoints del backend consumidos

| Endpoint | Método | Parámetros principales | Respuesta clave |
|---|---|---|---|
| `/api/reports/generate` | POST | `{date_from, date_to, client_id?, provider_id?}` | `{total_journeys, total_packages, total_delivered, total_failed, total_retry, delivery_rate, provider_metrics, driver_metrics, incidents_by_type, incidents_by_imputability}` |
| `/api/reports/quality` | GET | `date_from, date_to, provider_id?` | `{summary{avg_score, total_evaluated, complete, partial, incomplete}, by_provider[], by_type[], worst_packages[]}` |
| `/api/reports/attempts` | GET | `date_from, date_to, client_id?, provider_id?` | `{first_attempt{count,pct}, second_attempt, third_attempt, retry_causes, total_packages}` |
| `/api/reports/sla` | GET | `date_from, date_to, client_id?, provider_id?` | `{consolidated{actual,target}, by_provider[], by_driver[], brackets[]}` |
| `/api/reports/kpis` | GET | `date_from, date_to, group_by∈{day,week,month}` | `{data[], summary, total, has_data, date_from, date_to}` |
| `/api/reports/generate-ai` | POST | `{date_from, date_to, client_id?, provider_id?}` | `{cards[], narrative}` |
| `/api/reports/generate-excel` | POST | igual que `/generate` | Binary XLSX stream |
| `/api/config/sla-targets` | PATCH | `{brackets[]}` | `{success, message}` |

---

## 8. Modelos de datos (colecciones MongoDB relevantes)

### 8.1 `journeys`
Campos usados en reporting:
- `id`, `date` (YYYY-MM-DD), `status` (pending/in_progress/closed/cancelled)
- `client_id`, `provider_id`, `driver_name`
- `packages_total`, `packages_delivered`, `packages_failed`, `packages_retry`
- `start_data` → `{departure_time, odometer_start, fuel_level}`
- `close_data` → `{closed_at, end_time, km_traveled, odometer_end, delivery_rate}`

### 8.2 `packages`
- `journey_id`, `tracking_number`, `status` (delivered/failed/pending)
- `attempt_number` (1/2/3+), `retry_cause`
- `evidence_type` (exitosa/terceros/devolucion/falla)
- `evidence_score` (0–100 por reglas), `ai_score` (0–100 por Claude Sonnet), `evidence_detail`

### 8.3 `incidents`
- `journey_id`, `occurred_at`, `incident_type`, `severity` (alta/media/baja)
- `imputability` (ME/Mensajero, Cliente/destinatario, Por definir)
- `status` (open/resolved)

### 8.4 `config` (documentos con `key`)
- `sla_targets` → `{brackets: [{label, target, status}]}`
- `ia_cost_config` → precios por modelo (para Admin/Token Usage)
- `ai_eval_config` → configuración dinámica del worker IA

---

## 9. Reglas operativas clave (lectura del reporte)

1. **SLA consolidado ≥ target activo** = cumplimiento. Si aparece coral, el proveedor principal (Cubbo) debe recibir alerta vía webhook.
2. **Driver con `delivery_rate < 60%`** → fondo ámbar en tabla; entra al protocolo de strikes.
3. **Calidad evidencias < 90%** (target) durante 7 días consecutivos → revisión por equipo de calidad.
4. **Tasa de visita − Tasa de entrega** alta (>10pp) indica problemas de gestión (direcciones erróneas, cliente ausente), no de capacidad.
5. **Incidencias de "Zona sin acceso"** no suman a strikes del driver.
6. **Pendientes = Total − Entregados − Fallidos**: paquetes sin intento exitoso ni fallo registrado; suelen ser devoluciones a bodega o entregas en curso (corte antes del cierre de ruta).
7. **Delta pp en KPI Strip:** siempre `actual − previo` (NO previo − actual). `+` implica mejora.

---

## 10. Control de acceso (RBAC)

| Rol | Ver reportes | Editar brackets SLA | Generar IA | Exportar Excel/PDF |
|---|---|---|---|---|
| Developer | ✓ | ✓ | ✓ | ✓ |
| Coordinator | ✓ | ✓ | ✓ | ✓ |
| Executive | ✓ | — | ✓ | ✓ |
| Agent | — | — | — | — |
| Proveedor | Solo sus propios journeys | — | — | — |

Los filtros de asignación (`apply_assignment_filter`) restringen automáticamente la query Mongo por `provider_id` cuando el usuario es `proveedor`.

---

## 11. Glosario

- **Journey:** Ruta operativa de un driver en un día con un conjunto de paquetes asignados.
- **Package:** Paquete individual asociado a un journey con tracking, destinatario, status y evidencia.
- **Incident:** Evento excepcional durante la operación (dirección incorrecta, ausente, zona sin acceso, etc.).
- **pp (puntos porcentuales):** Diferencia aritmética entre dos porcentajes. 82% − 75% = 7pp (NO "7%").
- **Bracket SLA:** Umbral objetivo por fase del contrato (cada cliente define sus brackets).
- **Imputabilidad:** Responsabilidad atribuida (ME/Mensajero, Cliente/destinatario, Por definir). Sólo ME/Mensajero penaliza strikes.
- **Score evidencia:** Puntaje 0–100 asignado a la documentación fotográfica del paquete al cierre. 100 = completa y legible, 0 = ausente o ilegible.

---

## 12. Versionado

| Fecha | Cambio | Autor |
|---|---|---|
| 2026-04-10 | Módulo original con 6 tabs | Ingeniería LastMile |
| 2026-04-15 | Nueva tab Intentos + SLA | Ingeniería LastMile |
| 2026-04-22 | AI Report v2 (cards + narrativa) | Ingeniería LastMile |
| 2026-04-24 | Nueva tab **Tendencias** con `/api/reports/kpis` | Ingeniería LastMile |
| 2026-04-24 | PDF reporte: 13 fixes visuales (cards, donuts nativos, tablas sin días op., "Herramientas tecnológicas") | Ingeniería LastMile |

---

*Documento generado automáticamente a partir del código fuente `frontend/src/pages/Reports.jsx` y `backend/routes/analytics_routes.py`. Para reportar imprecisiones: escribir a equipo IT con el ID de commit vigente.*
