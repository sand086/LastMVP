# Bundle F · Categorización por grupos

**Total a remediar:** 15 hallazgos en 5 grupos.

| Grupo | Cantidad | Hallazgos IDs | Tipo de cambio | Tiempo estimado |
|---|---|---|---|---|
| 1. Microcopy / tooltips | 4 | UX-WEBHOOKS-004, UX-LATAM-013, UX-TORRE-003, UX-LATAM-009 | inserción de texto / tooltips | 0.5 día |
| 2. Visual polish | 3 | UX-JERARQUIA-005, UX-TICKETS-004, UX-AGENTE-007 | UI tokens existentes | 0.5 día |
| 3. Terminología canónica | 2 | UX-AGENTE-003, UX-LATAM-009 | glosario UI ("caso", "rastreo") | 0.5 día |
| 4. Accesibilidad menor | 1 | UX-TICKETS-006 | `disabled` + tooltip por rol | 0.2 día |
| 6. Formatos LATAM | 5 | UX-RECLAMOS-004, UX-WEBHOOKS-005, UX-AI-003, UX-LATAM-004, UX-LATAM-008 | aplicar formatFechaMX / MxInput | 0.5 día |

**Grupo 5 (Migración CrudPanel): 0 hallazgos.** Bundle C ya migró los consumidores con hallazgo específico.

**Total: 5 grupos efectivos · ~2.2 días estimados.**

---

## Estructura de commits

1. `fix(bundle-f-terminology): glosario canónico + reemplazo en UI — UX-AGENTE-003, UX-LATAM-009`
2. `fix(bundle-f-microcopy): tooltips + tz CDMX + última actualización — UX-WEBHOOKS-004, UX-LATAM-013, UX-TORRE-003`
3. `fix(bundle-f-visual): contadores en tabs + breadcrumb en ticket detail + indicador guardado — UX-JERARQUIA-005, UX-TICKETS-004, UX-AGENTE-007`
4. `fix(bundle-f-a11y): disabled state por rol en botones RBAC — UX-TICKETS-006`
5. `fix(bundle-f-latam): fechaRelativa + fechaCompacta + MxInput RFC — UX-RECLAMOS-004, UX-WEBHOOKS-005, UX-AI-003, UX-LATAM-004, UX-LATAM-008`
