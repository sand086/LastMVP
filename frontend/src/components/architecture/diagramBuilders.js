/**
 * Convierte un snapshot de arquitectura en diagramas Mermaid:
 *  - Capa 1: vista sistemica (frontend → backend → mongo → integraciones)
 *  - Capa 2: modelo de datos (ER simple con ownership)
 *  - Capa 3: flujo de evaluacion IA (diagrama de secuencia)
 */

export function buildSystemDiagram(snapshot) {
    const { stats, integrations } = snapshot;
    const integrationNodes = (integrations || [])
        .slice(0, 6)
        .map((i, idx) => `    EXT${idx}["${i.package}<br/><i>${i.description.split(' ')[0]}</i>"]`)
        .join('\n');
    const integrationEdges = (integrations || [])
        .slice(0, 6)
        .map((_, idx) => `    BACKEND -.-> EXT${idx}`)
        .join('\n');

    return `flowchart LR
    subgraph Cliente["👤 Cliente"]
        WEB["React SPA<br/>${stats.pages} páginas · ${stats.components} componentes"]
    end

    subgraph Edge["🌐 Emergent ingress"]
        ING["NGINX Ingress<br/>TLS · CORS · Rate limit"]
    end

    subgraph App["🛠 LastMile OS"]
        FRONTEND["Static bundle<br/>:3000"]
        BACKEND["FastAPI<br/>${stats.endpoints} endpoints<br/>:8001"]
        WORKER["Workers async<br/>Kosmo + AI Eval"]
    end

    subgraph Data["💾 Datos"]
        MONGO["MongoDB<br/>${stats.collections} colecciones"]
    end

    subgraph External["🔌 Integraciones externas"]
${integrationNodes}
    end

    WEB --> ING
    ING --> FRONTEND
    ING --> BACKEND
    BACKEND --> MONGO
    WORKER --> MONGO
    BACKEND -.-> WORKER
${integrationEdges}`;
}

export function buildDataModelDiagram(snapshot) {
    const collections = snapshot.collections || {};
    const topCols = Object.entries(collections)
        .filter(([, meta]) => (meta.writers || []).length > 0 || (meta.readers || []).length > 0)
        .sort((a, b) => (b[1].operations?.length || 0) - (a[1].operations?.length || 0))
        .slice(0, 15);

    const lines = ['erDiagram'];
    for (const [col, meta] of topCols) {
        const ops = (meta.operations || []).slice(0, 4).join(', ');
        const owners = (meta.write_ownership?.owners || []).length;
        const statusIcon =
            meta.write_ownership?.status === 'violation'
                ? '⚠'
                : meta.write_ownership?.status === 'single'
                  ? '✓'
                  : '•';
        lines.push(`    ${sanitize(col)} {`);
        lines.push(`        string ownership "${statusIcon} ${owners} writer(s)"`);
        if (ops) lines.push(`        string operations "${ops}"`);
        lines.push('    }');
    }
    // Relaciones heuristicas conocidas
    const rels = [
        ['users', 'journeys', 'creates'],
        ['journeys', 'packages', 'contains'],
        ['journeys', 'incidents', 'has'],
        ['packages', 'incidents', 'triggers'],
        ['drivers', 'journeys', 'assigned_to'],
        ['clients', 'journeys', 'owns'],
        ['ai_evaluation_jobs', 'packages', 'evaluates'],
    ];
    const known = new Set(topCols.map(([c]) => c));
    for (const [from, to, label] of rels) {
        if (known.has(from) && known.has(to)) {
            lines.push(`    ${sanitize(from)} ||--o{ ${sanitize(to)} : ${label}`);
        }
    }
    return lines.join('\n');
}

export function buildAIEvalFlowDiagram(snapshot) {
    // Sequence diagram of the AI evaluation flow
    return `sequenceDiagram
    autonumber
    actor Coord as Coordinador
    participant UI as Frontend<br/>(GuiasTab)
    participant API as /api/journeys/<br/>evaluate-evidence-all
    participant Q as ai_evaluation_jobs<br/>(cola Mongo)
    participant W as AI Eval Worker<br/>(asyncio loop)
    participant LLM as Emergent LLM<br/>(Claude Sonnet 4.5)
    participant DB as packages<br/>(Mongo)

    Coord->>UI: Click "Evaluar IA todas"
    UI->>API: POST evaluate-evidence-all
    API->>Q: enqueue_job (status=En_Cola)
    API-->>UI: {job_id, total_enqueued}
    UI-->>Coord: Toast "Encolado — ver Monitor IA"

    loop cada 10s
        W->>Q: pick En_Cola (limit=MAX_CONCURRENT)
        W->>Q: set status=Evaluando
        loop batch de 5 guias
            W->>DB: find package + incidents
            W->>LLM: _call_ai_vision (6 imgs base64)
            LLM-->>W: JSON (evidence_score, ai_errors)
            W->>DB: update package con resultado
            W->>Q: update guias_detail.status=Evaluada
        end
        W->>Q: status=Evaluada/Parcial/Error
    end

    Note over W,Q: Cron sweep 30min recupera huerfanos<br/>y orphan recovery al startup`;
}

function sanitize(s) {
    return (s || '').replace(/[^A-Za-z0-9_]/g, '_');
}
