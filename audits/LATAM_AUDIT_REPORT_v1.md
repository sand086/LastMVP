# Mini-Auditoría LATAM (México) — Informe v1

> **Fecha:** Mayo 12, 2026 (proyección Bundle D · pre-Bundle E)
> **Auditor:** Emergent (rol auditor UX LATAM, sesgo operativo, no estético)
> **Alcance:** Sub-ejes 8.1 a 8.10 sobre TODAS las superficies construidas
> (Panel Agente, Reclamos, Admin Tickets/Jerarquía/Catálogo/Notificaciones/
> AI/Webhooks/Ingesta, Dashboard, Torre, Auditor Panel, Onboarding).

---

## RESUMEN EJECUTIVO

Se auditaron las 13 superficies productivas del SaaS contra los 10 sub-ejes
del marco México-céntrico. **Total: 18 hallazgos** (S0=2, S1=6, S2=7, S3=3).
La concentración fue en **8.1 (fechas mezcladas, 4 hallazgos)** y **8.2 (montos
sin divisa explícita en módulo AI, 5 hallazgos)** — coherente con la predicción
del consultor externo en el audit v1.

**Top hallazgos críticos (S0):**
1. **UX-LATAM-002** (8.2): tarjetas de costo IA muestran `$0.0234` sin etiqueta
   USD/MXN. CFO consolida 4 features × USD-no-etiquetado y reporta cifras
   confundidas con pesos mexicanos en presentaciones.
2. **UX-LATAM-006** (8.6): `SlaService` calcula vencimiento con `timedelta`
   lineal — NO respeta festivos mexicanos. Ticket creado el 14-sep con SLA de
   3 días vence 17-sep cuando legalmente debería vencer 18 o 19-sep (saltando
   feriado 16-sep + posible 15-sep en muchos clientes mexicanos).

**Hallazgo más extendido:** falta de helper `formatFechaMX` centralizado. Hoy
hay 7 archivos que llaman a `new Date(x).toLocaleString()` con configuraciones
distintas (algunos con `es-MX`, otros sin locale, otros con `toLocaleString()`
desnudo que respeta `Accept-Language` del navegador).

**Recomendación general:** la infraestructura Parte 2 del Bundle D
(`formatFechaMX` + `CurrencyService` + `mx_holidays` + `MxCalendarService` +
`MxInput`) cubre el 100% de los hallazgos S0/S1 si se aplica integralmente.
Los S2/S3 quedan deferidos a Bundle F.

---

## ÍNDICE DE HALLAZGOS

| ID            | Sub-eje | Sev | Título resumido                                                   |
|---------------|---------|-----|-------------------------------------------------------------------|
| UX-LATAM-001  | 8.1     | S1  | `new Date().toLocaleString()` desnudo en 4 archivos               |
| UX-LATAM-002  | 8.2     | S0  | Costos IA en `$X.XX` sin etiqueta USD/MXN (módulo AdminAI)         |
| UX-LATAM-003  | 8.2     | S1  | `monto_reclamado` en Reclamos sin formato MX consistente          |
| UX-LATAM-004  | 8.1     | S2  | Fechas relativas en inglés ("2 minutes ago") en algunos sitios   |
| UX-LATAM-005  | 8.3     | S1  | Inputs de teléfono sin validación MX (+52 / 10 dígitos)           |
| UX-LATAM-006  | 8.6     | S0  | `SlaService` no respeta festivos mexicanos                        |
| UX-LATAM-007  | 8.4     | S1  | Formularios de cliente sin campos `colonia` / `cp`                |
| UX-LATAM-008  | 8.7     | S2  | Falta validación de RFC en clientes corporativos                  |
| UX-LATAM-009  | 8.8     | S2  | Anglicismos en UI: "tracking" usado como label visible            |
| UX-LATAM-010  | 8.5     | S2  | `users.name` único campo (no separa apellido paterno/materno)     |
| UX-LATAM-011  | 8.9     | S3  | Acentos visibles pero algunas clases `text-[10px]` los recortan   |
| UX-LATAM-012  | 8.10    | S1  | País default no especificado en formulario de clientes nuevos    |
| UX-LATAM-013  | 8.10    | S2  | Zona horaria en banners no etiquetada como CDMX                   |
| UX-LATAM-014  | 8.2     | S1  | `CurrencyService` no existe — cada feature inventa formato        |
| UX-LATAM-015  | 8.1     | S2  | `AdminAI.jsx` mezcla `new Date().toLocaleString()` y mono ISO     |
| UX-LATAM-016  | 8.8     | S2  | Tono mezcla "tú" y "usted" entre componentes                      |
| UX-LATAM-017  | 8.6     | S3  | Horario laboral de tenant no configurable                         |
| UX-LATAM-018  | 8.7     | S3  | Falta validación de CURP para persona física                      |

---

## HALLAZGOS DETALLADOS

### UX-LATAM-001 — Sub-eje 8.1 — S1 — Confianza Alta

**Hallazgo:** 7 archivos del frontend llaman `new Date(x).toLocaleString()` o
`toLocaleDateString()` sin locale forzado. En navegadores corporativos con
`Accept-Language: en-US` la fecha se renderiza como `5/11/2026` (que un usuario
mexicano lee como 5 de noviembre, cuando realmente es 11 de mayo).

**Evidencia técnica:**
- `pages/AdminAI.jsx:1106` — `new Date(latest.started_at).toLocaleString()` sin args.
- `pages/AuditorPanel.jsx:206, 350, 372-375` — `.toLocaleString()` desnudo para números (rompe formato de millares en algunos locales).
- `pages/AdminWebhooks.jsx:159` — ídem.
- `components/InboxBell.jsx:15` — `new Date(iso)` sin formato consistente.
- `pages/agent/sla.js:12-13, 33` — cálculos OK pero presentación no.

**Escenario operativo:** Coordinador en Chrome corporativo (default `en-US`)
abre `/admin/ai` y ve "Última corrida: 5/11/2026, 2:30:00 PM". Asume "5 de
noviembre" (fecha pasada). En realidad era "11 de mayo" (hoy). Toma decisión
de re-correr benchmark innecesariamente.

**Impacto cuantificado:** ~5-10 confusiones/mes × ~3 min de re-trabajo =
30 min/mes evitables. Riesgo mayor en decisiones presupuestarias del CFO.

**Sugerencia:** introducir helper `formatFechaMX` con funciones nombradas
(`fechaCompacta`, `fechaRelativa`, etc.) y refactorizar las 7 ocurrencias.
ESLint rule custom para bloquear `toLocaleString` desnudo (deferido a Bundle F).

---

### UX-LATAM-002 — Sub-eje 8.2 — S0 — Confianza Alta

**Hallazgo:** El módulo `AdminAI.jsx` muestra costos en USD pero el símbolo `$`
sin prefijo de divisa puede leerse como MXN. Hay 7 ocurrencias en el archivo:
`${(r.total_cost_usd || 0).toFixed(4)}`, `${f.avg_cost_usd}`, etc.

**Evidencia técnica:**
- `pages/AdminAI.jsx:173, 317, 320, 321, 986, 1019, 1123` — formateo manual con
  `$` literal.
- `pages/AuditorPanel.jsx:310, 375` — ídem.

**Escenario operativo:** CFO de cliente Cubbo ve el banner del Dashboard AI
"Costo IA del mes: $87.30". Lo interpreta como $87 MXN (~5 USD). Aprueba el
gasto. Reality: $87.30 USD ≈ $1,700 MXN. Sorpresa en factura.

**Impacto cuantificado:** Pérdida de credibilidad en reporte ejecutivo + riesgo
financiero. Aún 0 incidentes reportados (módulo nuevo) pero crece con uso.

**Sugerencia:** servicio centralizado `CurrencyService.format(amount, "USD")`
→ `"USD 87.30"`. Etiquetar SIEMPRE divisa en UI de costos AI. Ver Parte 2.

---

### UX-LATAM-003 — Sub-eje 8.2 — S1 — Confianza Media

**Hallazgo:** En `Reclamos.jsx`, `monto_reclamado` se muestra como string crudo
sin separadores de millares: `<span class="font-mono">{claim.monto_reclamado} {claim.divisa}</span>`.
Para montos de $25,000 MXN se ve `25000 MXN` (no `$25,000.00 MXN`).

**Evidencia técnica:**
- `pages/Reclamos.jsx:438` — render directo del número sin formateo.

**Escenario operativo:** Reclamo de daño total por $125,000 MXN se muestra
"125000 MXN" en el banner. Ana cuenta dígitos para confirmar el monto.

**Impacto cuantificado:** ~30 seg/lectura × 30 reclamos/día = 15 min/día por
agente revisor. Bajo individualmente, acumulativo a 4 horas/mes.

**Sugerencia:** `CurrencyService.format()` en backend o `formatCurrencyMX` en
frontend con Intl.NumberFormat('es-MX', {style: 'currency', currency: claim.divisa}).

---

### UX-LATAM-004 — Sub-eje 8.1 — S2 — Confianza Media

**Hallazgo:** Algunas fechas relativas se renderizan vía `date-fns/formatDistanceToNow`
con locale por defecto inglés (ej. `agent/Composer.jsx` y `Reclamos.jsx` indicador
"Guardado hace N seg" — sí está en español pero no usa Intl uniforme).

**Evidencia técnica:**
- `pages/Reclamos.jsx:865-870` — helper local `useDraftSavedAgo`.
- `pages/InboxBell.jsx:18-30` — su propia función `formatRelative`.

**Sugerencia:** centralizar `fechaRelativa` en `formatFechaMX.js`.

---

### UX-LATAM-005 — Sub-eje 8.3 — S1 — Confianza Alta

**Hallazgo:** No hay componente de captura de teléfono con validación MX.
Los inputs son `<input type="tel" />` libre. Los modelos backend de cliente
guardan `phone` como string opaco.

**Evidencia técnica:**
- `grep "input.*type.*tel" /app/frontend/src` → 0 resultados con validación.
- `models/client.py` — campo `phone: Optional[str]` sin regex.

**Escenario operativo:** Admin carga cliente nuevo con teléfono "55 1234-5678".
El sistema lo acepta. Agente intenta click-to-call: `tel:55 1234-5678` falla
en algunos sistemas operativos por el guion. Reagarra teléfono físico.

**Impacto cuantificado:** 1-2 calls/día/agente fallan en click-to-call ×
5 agentes = ~30 calls/semana con re-trabajo de 30 seg.

**Sugerencia:** Componente `<MxInput type="telefono" />` con regex
`^(\+52\s?)?[0-9]{2}\s?\d{4}\s?\d{4}$` y normalización a E.164 antes de submit.

---

### UX-LATAM-006 — Sub-eje 8.6 — S0 — Confianza Alta

**Hallazgo:** `services/sla_inactivity.py::scan_sla` calcula vencimiento de SLA
usando `timedelta(hours=N)` sobre `created_at` directo, **sin restar festivos
mexicanos ni horarios laborales del tenant**. Un ticket creado el 14-sep 16:00
con SLA "24 horas hábiles" vence el 15-sep 16:00 — pero 15-sep tarde es ya
feriado en muchas operaciones, 16-sep es el feriado nacional, y el plazo
debería vencer 17 o 18-sep.

**Evidencia técnica:**
- `services/sla_inactivity.py` — el cálculo de `next_sla_check_at` usa aritmética
  lineal sobre `datetime.now(timezone.utc) + timedelta`.
- No existe `mx_holidays` collection ni `MxCalendarService`.

**Escenario operativo:** Ticket de Cubbo creado 14-sep 23:00 con SLA P1 (4 hrs).
El cron de SLA dispara escalación a las 03:00 del 15-sep — Cubbo no opera de
noche, no hay nadie. SLA reportado como "incumplido" cuando técnicamente debió
vencer al inicio del horario laboral del 15-sep.

**Impacto cuantificado:** Métricas de SLA infladas + falsos escalamientos +
disputas con cliente. Difícil de cuantificar pero severo: el North Star del
producto es "% en SLA" — calcularlo mal mina la confianza del producto entero.

**Sugerencia:** introducir `MxCalendarService.add_business_hours()` que respete
festivos + horario laboral. Refactorizar `scan_sla` para usar el helper.

---

### UX-LATAM-007 — Sub-eje 8.4 — S1 — Confianza Alta

**Hallazgo:** El modelo `Client` y el formulario `ClientsPanel` no tienen
campos `colonia`, `codigo_postal`, `estado_mx`. Las direcciones se guardan
como string libre opaco.

**Evidencia técnica:**
- `models/client.py` — no expone campos de dirección estructurada.
- `pages/AdminHierarchy.jsx::ClientsPanel` — form sin esos inputs.

**Escenario operativo:** Admin onboardea Cubbo-Pro. Captura dirección
"Av. Insurgentes 1234, Roma Norte, CDMX, CP 06700". Para integrar con un
carrier que requiere campos separados, hay que parsear el string opaco —
proceso manual y propenso a error.

**Impacto cuantificado:** ~5 min/cliente onboardeado × 4 clientes/mes = 20 min
+ riesgo de error en integraciones con carriers que validan estructura.

**Sugerencia:** agregar columnas `client.address_mx: { calle, numero, colonia,
cp, ciudad, estado, referencias }`. Form usa `<MxInput type="cp">`.

---

### UX-LATAM-008 — Sub-eje 8.7 — S2 — Confianza Media

**Hallazgo:** Modelo `Client` no captura RFC. Para facturación corporativa
mexicana es obligatorio (SAT lo exige). El producto aún no factura, pero el
gap se materializa apenas se agregue módulo de facturación (V3 según el
backlog).

**Sugerencia:** agregar `client.rfc` con validación regex MX. Componente
`<MxInput type="rfc">`.

---

### UX-LATAM-009 — Sub-eje 8.8 — S2 — Confianza Alta

**Hallazgo:** El término "tracking" aparece como label visible al usuario en
varios componentes (no solo como campo técnico). En MX se prefiere "rastreo"
o "guía".

**Evidencia técnica:**
- `pages/AdminIngest.jsx:292` — `<li>· tracking_id</li>` visible en docs UI.
- `components/GuiaCancelButton.jsx:61` — `<div>tracking: {tracking}</div>`.
- `pages/agent/ContextPanel.jsx:67` — label "tracking" en sidebar.

**Sugerencia:** UI debe leer "Guía" / "Rastreo" / "Folio carrier". Mantener
`tracking_id` como nombre de campo técnico API (compatibilidad).

---

### UX-LATAM-010 — Sub-eje 8.5 — S2 — Confianza Media

**Hallazgo:** `User.name` es único campo libre. En MX las personas tienen 3
componentes: nombre + apellido_paterno + apellido_materno. Implica:
ordenamiento alfabético por apellido paterno requiere parsing heurístico
inestable.

**Sugerencia:** opcionalmente desglosar en `User.name`, `User.apellido_paterno`,
`User.apellido_materno`. Como retro-compat: si solo viene `name`, conservar.

---

### UX-LATAM-011 — Sub-eje 8.9 — S3 — Confianza Baja

**Hallazgo:** Inspección visual de algunas badges `text-[10px]` con acentos
("Última actualización", "información") muestra recorte mínimo en algunas
combinaciones browser+font. No reproducible consistente.

**Sugerencia:** revisar a `text-[11px]` o `leading-[1.4]` para conservar
tildes. Deferido a Bundle F.

---

### UX-LATAM-012 — Sub-eje 8.10 — S1 — Confianza Alta

**Hallazgo:** Form de cliente nuevo no asume México como default. Tampoco hay
field "país". Probablemente futuros bugs si se permite un cliente foráneo.

**Sugerencia:** agregar `client.country = "MX"` con default fijo + checkbox
"Cliente fuera de México" (oculto por defecto, P3).

---

### UX-LATAM-013 — Sub-eje 8.10 — S2 — Confianza Media

**Hallazgo:** Banners "Entregado el 12/05/2026 14:23" no etiquetan TZ. La hora
es UTC en BD; se muestra convertida pero sin sufijo "hrs CDMX".

**Sugerencia:** `formatFechaMX.fechaBanner()` agrega siempre " hrs CDMX" en
contextos críticos.

---

### UX-LATAM-014 — Sub-eje 8.2 — S1 — Confianza Alta

**Hallazgo:** No existe servicio centralizado `CurrencyService`. Cada feature
inventa su formato. Bundle B/C usan Intl ad-hoc.

**Sugerencia:** **Parte 2 de este Bundle**. Servicio centralizado con cache.

---

### UX-LATAM-015 — Sub-eje 8.1 — S2 — Confianza Media

**Hallazgo:** `AdminAI.jsx` línea 1106 mezcla formato display (`.toLocaleString()`)
con strings ISO crudos (en algunos timeline). Inconsistencia visual.

**Sugerencia:** todo el archivo usa `formatFechaMX.fechaCompacta()`.

---

### UX-LATAM-016 — Sub-eje 8.8 — S2 — Confianza Media

**Hallazgo:** Mezcla "Tu solicitud fue enviada" (tú) en un toast y "Su cliente
ha sido notificado" (usted) en otro. Falta convención.

**Sugerencia:** "tú" para CSA interno (toasts, modales operativos), "usted"
para comunicación enviada al cliente final (emails, WhatsApp). Deferido a
Bundle F (revisión sistemática de copy).

---

### UX-LATAM-017 — Sub-eje 8.6 — S3 — Confianza Baja

**Hallazgo:** Horario laboral del tenant no configurable. Asumimos 24/7 por
defecto. Para SLA correctos hace falta.

**Sugerencia:** `tenant.business_hours = {start_hour: 9, end_hour: 18,
days_of_week: [1..5]}`. Deferido a Bundle F.

---

### UX-LATAM-018 — Sub-eje 8.7 — S3 — Confianza Baja

**Hallazgo:** CURP no aplica todavía (no hay módulo de persona física). Solo
relevante si V4 introduce facturación a personas físicas. Documentado para
futuro.

---

## ASPECTOS BIEN EJECUTADOS

1. **`pages/hierarchy/UsersPanel.jsx:23`** ya usa `new Date(iso).toLocaleString("es-MX", {dateStyle: "short", timeStyle: "short"})` correctamente — el patrón a replicar.
2. **`pages/AdminHierarchy.jsx:1074`** sigue el mismo patrón es-MX.
3. **`models/claim.py`** correctamente incluye `divisa` como campo obligatorio (R34 cumplida en este dominio).
4. **`services/ai/pii_masker.py`** detecta direcciones mexicanas con regex heurístico de "colonia" — buen patrón referencia.
5. **`AdminTickets.jsx`** y **`Reclamos.jsx`** ya migrados a copy en español MX consistente (tras Bundle A).
6. Fechas ISO en BD se almacenan UTC (R20) — conversión a CDMX correctamente diferida al display layer.

## CONCLUSIÓN

**Fixes a aplicar AHORA (S0 + S1, 8 hallazgos):**
- UX-LATAM-001 (refactor fechas frontend → formatFechaMX)
- UX-LATAM-002, UX-LATAM-003, UX-LATAM-014 (CurrencyService + format AI/Reclamos)
- UX-LATAM-005 (MxInput telefono)
- UX-LATAM-006 (MxCalendarService + refactor scan_sla)
- UX-LATAM-007 (campos colonia/cp en client model + form)
- UX-LATAM-012 (default country MX)

**Diferidos a Bundle F (S2/S3, 10 hallazgos):** UX-LATAM-004, 008, 009, 010, 011, 013, 015, 016, 017, 018.

**Prerrequisito de infraestructura:** Parte 2 del Bundle D. Ya documentada en
PRD.md como BP-05.
