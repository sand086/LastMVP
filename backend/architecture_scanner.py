"""
Architecture Scanner — Auto-documents LastMile OS by parsing the live codebase.

Extrae de forma determinista:
  1. Colecciones MongoDB (desde operaciones db.X.find/insert/update/delete).
  2. Endpoints FastAPI (parse de @router.get/post/put/delete).
  3. Rutas frontend React (desde App.js).
  4. Integraciones externas (litellm, httpx, SDK providers).
  5. Ownership de escritura (single-write-point).

No introduce deps nuevas — solo ast/re/pathlib.
"""
from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

BACKEND_DIR = Path("/app/backend")
FRONTEND_DIR = Path("/app/frontend/src")

# Evita scanear paths enormes / tests / node_modules
EXCLUDE_DIRS = {"__pycache__", "tests", "node_modules", ".git", "dist", "build"}

# Operaciones que califican como "escritura" en Mongo
WRITE_OPS = {"insert_one", "insert_many", "update_one", "update_many", "delete_one", "delete_many",
             "find_one_and_update", "find_one_and_delete", "replace_one", "bulk_write"}
READ_OPS = {"find", "find_one", "aggregate", "count_documents", "distinct"}

# External integration markers
EXTERNAL_MARKERS = {
    "emergentintegrations": "Emergent LLM (Claude / GPT / Gemini / Nano Banana)",
    "litellm": "LiteLLM (proxy for Claude Sonnet / Haiku 4.5)",
    "resend": "Resend (email transactional)",
    "stripe": "Stripe (payments)",
    "httpx": "HTTPX (Kosmo tracking scraper)",
    "motor": "Motor (async MongoDB driver)",
    "slowapi": "SlowAPI (rate limiting)",
    "slack_sdk": "Slack notifications",
    "boto3": "AWS S3 / SES",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if any(ex in p.parts for ex in EXCLUDE_DIRS):
            continue
        yield p


def _iter_js_files(root: Path):
    for p in root.rglob("*.jsx"):
        if any(ex in p.parts for ex in EXCLUDE_DIRS):
            continue
        yield p
    for p in root.rglob("*.js"):
        if any(ex in p.parts for ex in EXCLUDE_DIRS):
            continue
        yield p


def _safe_parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return None


# ── Scanner: colecciones MongoDB + write ownership ──────────────────────────

def scan_collections() -> dict:
    """Retorna {collection_name: {writers: [...], readers: [...]}}"""
    ops: dict[str, dict] = defaultdict(lambda: {"writers": set(), "readers": set(), "operations": set()})

    for path in _iter_py_files(BACKEND_DIR):
        tree = _safe_parse(path)
        if tree is None:
            continue
        module = path.relative_to(BACKEND_DIR).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            op_name = node.attr
            if op_name not in WRITE_OPS and op_name not in READ_OPS:
                continue
            # Buscar patron db.<collection>.<op>
            parent = node.value
            if not isinstance(parent, ast.Attribute):
                continue
            collection_name = parent.attr
            # Verificar que el "grandparent" sea `db` (o alias conocido)
            root = parent.value
            root_name = None
            if isinstance(root, ast.Name):
                root_name = root.id
            elif isinstance(root, ast.Attribute):
                root_name = root.attr
            if root_name not in ("db", "database"):
                continue

            ops[collection_name]["operations"].add(op_name)
            if op_name in WRITE_OPS:
                ops[collection_name]["writers"].add(module)
            else:
                ops[collection_name]["readers"].add(module)

    return {
        col: {
            "writers": sorted(data["writers"]),
            "readers": sorted(data["readers"]),
            "operations": sorted(data["operations"]),
            "write_ownership": _assess_ownership(data["writers"]),
        }
        for col, data in sorted(ops.items())
    }


def _assess_ownership(writers: set) -> dict:
    """Determina si la coleccion respeta single-write-point."""
    unique_modules = set(writers)
    if len(unique_modules) == 0:
        return {"status": "read_only", "owners": []}
    if len(unique_modules) == 1:
        return {"status": "single", "owners": list(unique_modules)}
    # Varios modulos: aceptable si todos estan en /routes (es normal que user_routes + admin_routes
    # escriban en users). Flag si mezclan /routes + /workers + /middleware.
    categories = set()
    for w in unique_modules:
        if "routes/" in w:
            categories.add("routes")
        elif "worker" in w or w.startswith("ai_eval") or w.startswith("kosmo_sync"):
            categories.add("worker")
        elif "middleware" in w:
            categories.add("middleware")
        else:
            categories.add("other")
    if len(categories) > 1:
        return {"status": "violation", "owners": sorted(unique_modules), "reason": "multi-layer writers"}
    return {"status": "multi_route", "owners": sorted(unique_modules)}


# ── Scanner: endpoints FastAPI ──────────────────────────────────────────────

ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "websocket"}


def scan_endpoints() -> list[dict]:
    endpoints = []
    for path in _iter_py_files(BACKEND_DIR):
        tree = _safe_parse(path)
        if tree is None:
            continue
        module = path.relative_to(BACKEND_DIR).as_posix()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                # @router.get("/path") or @app.post("/path")
                if isinstance(deco.func, ast.Attribute) and deco.func.attr in ROUTE_DECORATORS:
                    path_arg = None
                    if deco.args:
                        arg = deco.args[0]
                        if isinstance(arg, ast.Constant):
                            path_arg = arg.value
                    if path_arg is None:
                        continue
                    endpoints.append({
                        "method": deco.func.attr.upper(),
                        "path": path_arg,
                        "handler": node.name,
                        "module": module,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "dependencies": _extract_dependencies(node),
                    })
    return sorted(endpoints, key=lambda e: (e["module"], e["path"]))


def _extract_dependencies(node) -> list[str]:
    """Extrae Depends(...) de los args del handler para identificar auth/role."""
    deps = []
    for arg in node.args.args:
        # Look at default expressions in args.defaults — but simpler: search body text
        pass
    # Fallback: look at argument annotations / defaults
    for default in getattr(node.args, "defaults", []):
        if isinstance(default, ast.Call) and isinstance(default.func, ast.Name) and default.func.id == "Depends":
            if default.args and isinstance(default.args[0], ast.Name):
                deps.append(default.args[0].id)
            elif default.args and isinstance(default.args[0], ast.Call) and isinstance(default.args[0].func, ast.Name):
                deps.append(default.args[0].func.id)
    return deps


# ── Scanner: rutas frontend React ───────────────────────────────────────────

REACT_ROUTE_RE = re.compile(r"""<Route\s+path=["']([^"']+)["']""")
REACT_COMPONENT_RE = re.compile(r"""element=\{<(\w+)""")


def scan_frontend_routes() -> list[dict]:
    app_js = FRONTEND_DIR / "App.js"
    if not app_js.exists():
        return []
    content = app_js.read_text(encoding="utf-8")
    routes = []
    # Rough parse: each <Route> block
    for match in re.finditer(r"<Route[\s\S]*?/>", content):
        block = match.group(0)
        p = REACT_ROUTE_RE.search(block)
        c = REACT_COMPONENT_RE.search(block)
        if p:
            routes.append({
                "path": p.group(1),
                "component": c.group(1) if c else "?",
                "protected": "ProtectedRoute" in block,
                "roles": _extract_roles(block),
            })
    return routes


def _extract_roles(block: str) -> list[str]:
    m = re.search(r"allowedRoles=\{\[([^\]]+)\]", block)
    if not m:
        return []
    return [r.strip().strip("'\"") for r in m.group(1).split(",") if r.strip()]


def count_frontend_components() -> dict:
    totals = {"pages": 0, "components": 0, "total_lines": 0}
    pages_dir = FRONTEND_DIR / "pages"
    components_dir = FRONTEND_DIR / "components"
    for p in (_iter_js_files(pages_dir) if pages_dir.exists() else []):
        totals["pages"] += 1
        totals["total_lines"] += sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
    for p in (_iter_js_files(components_dir) if components_dir.exists() else []):
        if p.parent.name != "ui":  # exclude shadcn
            totals["components"] += 1
            totals["total_lines"] += sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
    return totals


# ── Scanner: integraciones externas ─────────────────────────────────────────

def scan_external_integrations() -> list[dict]:
    seen: dict[str, set] = defaultdict(set)
    for path in _iter_py_files(BACKEND_DIR):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        module = path.relative_to(BACKEND_DIR).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    base = n.name.split(".")[0]
                    if base in EXTERNAL_MARKERS:
                        seen[base].add(module)
            elif isinstance(node, ast.ImportFrom) and node.module:
                base = node.module.split(".")[0]
                if base in EXTERNAL_MARKERS:
                    seen[base].add(module)
    return [
        {"package": p, "description": EXTERNAL_MARKERS[p], "used_in": sorted(mods)}
        for p, mods in sorted(seen.items())
    ]


# ── Modulos funcionales (heuristica por nombre de archivo) ──────────────────

MODULE_MAP = {
    "journey_routes": "Gestión de Rutas (Journeys)",
    "ai_eval_worker": "Evaluación IA (async worker)",
    "ai_eval_routes": "Evaluación IA (API)",
    "kosmo_sync": "Sincronización Kosmo (background)",
    "webhook_routes": "Webhooks Plug & Play",
    "driver_routes": "Gestión de Drivers",
    "manual_routes": "Platform Manuals",
    "lumi_routes": "Lumi AI Chat",
    "dashboard_routes": "Dashboard",
    "analytics_routes": "Analytics & KPIs",
    "upload_routes": "Carga de archivos (layouts, CSV)",
    "admin_module_routes": "Admin Module",
    "system_routes": "Observabilidad",
    "quality_criteria_routes": "Criterios de Calidad",
    "user_routes": "Gestión de Usuarios",
    "auth_routes": "Autenticación (JWT cookies)",
}


def scan_modules() -> list[dict]:
    modules = []
    for fname, label in MODULE_MAP.items():
        candidates = list(BACKEND_DIR.rglob(f"{fname}.py"))
        if not candidates:
            continue
        p = candidates[0]
        content = p.read_text(encoding="utf-8")
        modules.append({
            "module": fname,
            "label": label,
            "file": p.relative_to(BACKEND_DIR).as_posix(),
            "lines": len(content.splitlines()),
            "endpoint_count": content.count("@router."),
        })
    return modules


# ── Entry point ──────────────────────────────────────────────────────────────

def generate_snapshot() -> dict:
    """Genera un snapshot completo del estado actual del codebase."""
    now = datetime.now(timezone.utc).isoformat()
    collections = scan_collections()
    endpoints = scan_endpoints()
    frontend_routes = scan_frontend_routes()
    components = count_frontend_components()
    integrations = scan_external_integrations()
    modules = scan_modules()

    # Antipatrones detectados
    antipatterns = []
    for col, meta in collections.items():
        if meta["write_ownership"]["status"] == "violation":
            antipatterns.append({
                "severity": "high",
                "type": "multi_layer_write",
                "collection": col,
                "description": f"Coleccion '{col}' es escrita desde capas distintas: {meta['write_ownership']['owners']}",
            })
    # Rutas sin proteccion
    for r in frontend_routes:
        if not r["protected"] and r["path"] not in ("/login", "/", "*"):
            antipatterns.append({
                "severity": "medium",
                "type": "unprotected_route",
                "path": r["path"],
                "description": f"Ruta {r['path']} carece de ProtectedRoute wrapper",
            })

    snapshot = {
        "generated_at": now,
        "stats": {
            "collections": len(collections),
            "endpoints": len(endpoints),
            "frontend_routes": len(frontend_routes),
            "pages": components["pages"],
            "components": components["components"],
            "frontend_total_lines": components["total_lines"],
            "modules": len(modules),
            "integrations": len(integrations),
            "antipatterns": len(antipatterns),
        },
        "collections": collections,
        "endpoints": endpoints,
        "frontend_routes": frontend_routes,
        "modules": modules,
        "integrations": integrations,
        "antipatterns": antipatterns,
    }
    # Hash canonico para detectar "no cambio" (excluyendo timestamp)
    payload_for_hash = {k: v for k, v in snapshot.items() if k != "generated_at"}
    snapshot["content_hash"] = sha256(
        json.dumps(payload_for_hash, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return snapshot


def diff_snapshots(prev: dict, curr: dict) -> dict:
    """Calcula el diff estructural entre dos snapshots."""
    changes: dict[str, list] = defaultdict(list)

    prev_cols = set(prev.get("collections", {}).keys())
    curr_cols = set(curr.get("collections", {}).keys())
    for c in curr_cols - prev_cols:
        changes["collections_added"].append(c)
    for c in prev_cols - curr_cols:
        changes["collections_removed"].append(c)

    prev_eps = {f"{e['method']} {e['path']}" for e in prev.get("endpoints", [])}
    curr_eps = {f"{e['method']} {e['path']}" for e in curr.get("endpoints", [])}
    for e in curr_eps - prev_eps:
        changes["endpoints_added"].append(e)
    for e in prev_eps - curr_eps:
        changes["endpoints_removed"].append(e)

    prev_routes = {r["path"] for r in prev.get("frontend_routes", [])}
    curr_routes = {r["path"] for r in curr.get("frontend_routes", [])}
    for r in curr_routes - prev_routes:
        changes["frontend_routes_added"].append(r)
    for r in prev_routes - curr_routes:
        changes["frontend_routes_removed"].append(r)

    prev_ints = {i["package"] for i in prev.get("integrations", [])}
    curr_ints = {i["package"] for i in curr.get("integrations", [])}
    for i in curr_ints - prev_ints:
        changes["integrations_added"].append(i)
    for i in prev_ints - curr_ints:
        changes["integrations_removed"].append(i)

    # Nuevas violaciones
    prev_violations = {
        (a["type"], a.get("collection") or a.get("path"))
        for a in prev.get("antipatterns", [])
    }
    curr_violations = {
        (a["type"], a.get("collection") or a.get("path"))
        for a in curr.get("antipatterns", [])
    }
    new_viol = curr_violations - prev_violations
    if new_viol:
        changes["new_antipatterns"] = [f"{t}: {k}" for t, k in sorted(new_viol)]

    total_changes = sum(len(v) for v in changes.values())
    return {
        "total_changes": total_changes,
        "is_significant": total_changes > 0,
        "changes": dict(changes),
    }
