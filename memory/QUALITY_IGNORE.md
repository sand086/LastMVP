# Code Quality — Ignore List (false positives)

Este documento describe patrones del repositorio que linters externos pueden marcar
erróneamente. Revísalo antes de aplicar "correcciones" sugeridas por herramientas
automáticas de análisis estático.

---

## 1. `dangerouslySetInnerHTML` — Ya sanitizado con DOMPurify

**Archivos afectados**
- `src/pages/Reports.jsx:242` — `renderMarkdown(narrative)`
- `src/components/LumiChat.jsx:179` — `formatAIText(msg.content)`

**Por qué es seguro**: Ambos helpers pasan el HTML por `DOMPurify.sanitize()`
con `ALLOWED_TAGS` muy restrictivo (solo `h3, br, strong, p, em, ul, li, ol`).
No hay vector de XSS.

Ejemplo:
```js
import DOMPurify from 'dompurify';

const renderMarkdown = (text) => {
    const html = /* ... */;
    return DOMPurify.sanitize(html, {
        ALLOWED_TAGS: ['h3', 'br', 'strong', 'p', 'em', 'ul', 'li', 'ol'],
        ALLOWED_ATTR: ['style'],
    });
};
```

Regla linter: ignorar `react/no-danger` cuando la expresión pasada
al prop `__html` proviene de una función cuyo nombre empieza por
`render*` / `format*` y que retorna `DOMPurify.sanitize(...)`.

---

## 2. React Hook `exhaustive-deps` — Imports estables no son dependencias

Los módulos importados (funciones de `api`, constantes, setters de `useState`)
son referencialmente estables para toda la vida del componente. Agregarlos al
array de dependencias de `useCallback`/`useEffect` no tiene efecto real y
introduce ruido.

**Ejemplo**:
```jsx
const fetchData = useCallback(async () => {
    const r = await api.get('/system/health');  // api es un import, estable
    setHealth(r.data);                          // setHealth es de useState, estable
}, []);   // ← lista vacía es correcto
```

Regla: ignorar `react-hooks/exhaustive-deps` cuando las dependencias faltantes
son (a) imports top-level, (b) setters de `useState`, (c) refs de `useRef`, o
(d) constantes declaradas fuera del componente.

---

## 3. Hardcoded passwords en tests — Usamos env-fallback pattern

Los tests usan el patrón:

```python
password = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
```

El literal `"LastMile2026"` es solo el **fallback** para desarrollo local; en
CI/producción la env var `TEST_*_PASSWORD` sobrescribe este valor. Scanners que
solo buscan la string literal lo marcan como "secreto embebido" sin considerar
el contexto.

Regla: no alertar sobre literales dentro de `os.environ.get(_, "literal")`.

---

## 4. Complejidad ciclomática en workers / scrapers

Archivos con alta complejidad pero **revisados manualmente** y considerados
aceptables por su naturaleza secuencial (orquestación de pipelines):

- `backend/kosmo_sync.py:scrape_kosmo_page` — parser HTML con múltiples
  fallbacks por campos (firma, nota del driver, fotos) que no se extraen a
  helpers porque ya comparten estado mutable local.
- `backend/liquidacion_export.py:_build_incidencias_sheet` — llena una fila de
  Excel con ~12 columnas; extraer helpers alargaría el código sin reducir la
  lógica real.

`backend/ai_eval_worker.py:_process_job` **sí fue refactorizado** (2026-04-22) a
helpers: `_evaluate_batch_with_retry`, `_update_job_progress`, `_finalize_job`.

---

## Actualización

Este documento debe actualizarse cuando:
- Se elimine un patrón (ya no existe).
- Se agreguen nuevos falsos positivos que el equipo decida aceptar.

Última actualización: 2026-04-22
