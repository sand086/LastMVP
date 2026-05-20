"""Iter50 — Cleanup retroactivo de `\\uFFFD` (char `�`) en strings persistidos.

Origen del problema: ingestas previas con `errors="replace"` reemplazaron
caracteres no-UTF-8 (ej. byte 0xF3 de cp1252 → `\\uFFFD`). El dato original
("ó" en "Dirección") ya se perdió en el momento del decode lossy.

Estrategia:
  - Para cada guía con `carrier_incidence` (u otros campos) que contenga
    `\\uFFFD`, aplicamos una **tabla de heurística** que repara las palabras
    más comunes del dominio (Dirección, Devolución, Información, etc.).
  - Lo que no matchea el diccionario simplemente queda con el char removido
    (lo prefiero a un `?` ruidoso).
  - Idempotente: re-ejecutar no causa daño porque ya no quedará `\\uFFFD`.

Uso (CLI):
    python -m scripts.fix_encoding_legacy --dry-run    # reporta sin tocar
    python -m scripts.fix_encoding_legacy --apply      # aplica las correcciones

Uso (programático):
    from scripts.fix_encoding_legacy import fix_encoding_in_db
    stats = await fix_encoding_in_db(dry_run=False)
"""
from __future__ import annotations
import argparse
import asyncio
import re

# Diccionario heurístico: patrones tras quitar el `\uFFFD`, qué palabra correcta.
# Se aplica case-insensitive con preservación de capitalización del prefijo.
LEGACY_REPAIRS: dict[str, str] = {
    # Frecuentes en operación CS / logística MX
    "direccin":     "Dirección",
    "direccion":    "Dirección",  # cuando ya cayó el char pero sin reemplazo
    "devolucin":    "Devolución",
    "informacin":   "Información",
    "ubicacin":     "Ubicación",
    "validacin":    "Validación",
    "verificacin":  "Verificación",
    "comunicacin":  "Comunicación",
    "operacin":     "Operación",
    "recepcin":     "Recepción",
    "entregaa":     "Entrega",     # 'entregaá' → 'entrega' tras drop
    "compaa":       "Compañía",
    "seora":        "Señora",
    "seor":         "Señor",
    "telfono":      "Teléfono",
    "nmero":        "Número",
    "cdigo":        "Código",
    "envo":         "Envío",
    "envos":        "Envíos",
    "garanta":      "Garantía",
    "pas":          "País",
    "lnea":         "Línea",
    # Estados/municipios MX habituales (frecuente en recipient.state/colonia)
    "mxico":        "México",
    "len":          "León",
    "nuevo len":    "Nuevo León",
    "michoacn":     "Michoacán",
    "yucatn":       "Yucatán",
    "quertaro":     "Querétaro",
    "cuauhtmoc":    "Cuauhtémoc",
    "obregn":       "Obregón",
    "atizapn":      "Atizapán",
    "tlhuac":       "Tláhuac",
    "anhuac":       "Anáhuac",
    "tlalpan":      "Tlalpan",
    "tlalnepantla": "Tlalnepantla",
    "iztacalco":    "Iztacalco",
    "iztapalapa":   "Iztapalapa",
    "azcapotzalco": "Azcapotzalco",
    "coyoacn":      "Coyoacán",
    "tultitln":     "Tultitlán",
    "naucalpan":    "Naucalpan",
    "jurez":        "Juárez",
    "benito jurez": "Benito Juárez",
    "ciudad de mxico": "Ciudad de México",
    "estado de mxico": "Estado de México",
    "san pedro tlaquepaque": "San Pedro Tlaquepaque",
    "garca":        "García",
    "merida":       "Mérida",
    "mrida":        "Mérida",
    "torren":       "Torreón",
    "pachuca":      "Pachuca",
    "tepoztln":     "Tepoztlán",
    "alvaro obregn": "Álvaro Obregón",
    "lvaro obregn": "Álvaro Obregón",
    "zapotln":      "Zapotlán",
    "tepeji":       "Tepeji",
    "celaya":       "Celaya",
    "mariano":      "Mariano",
    "constitucin":  "Constitución",
    "revolucin":    "Revolución",
    "regin":        "Región",
    "estacin":      "Estación",
    "atizapn de zaragoza": "Atizapán de Zaragoza",
    "tlalnepantla de baz": "Tlalnepantla de Baz",
    "san pedro tlaquepaque": "San Pedro Tlaquepaque",
}


def _apply_repairs(s: str) -> str:
    """Repara una cadena: quita `\\uFFFD` y aplica diccionario heurístico."""
    if not s or "\ufffd" not in s:
        return s
    cleaned = s.replace("\ufffd", "")
    # Aplicar repairs case-insensitive token-by-token. Conservamos
    # capitalización original del primer caracter.
    def repl_token(match: re.Match) -> str:
        original = match.group(0)
        key = original.lower()
        repaired = LEGACY_REPAIRS.get(key)
        if not repaired:
            return original
        # Preservar capitalización del primer char
        if original[:1].isupper():
            return repaired[:1].upper() + repaired[1:]
        return repaired[:1].lower() + repaired[1:]
    # Tokenizar por palabras (incluye unicode letters)
    return re.sub(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", repl_token, cleaned)


async def fix_encoding_in_db(dry_run: bool = True,
                              tenant_id: str | None = None) -> dict:
    """Recorre `guias` y `tickets`, repara campos con `\\uFFFD`.

    - dry_run=True: solo cuenta y devuelve sample de las primeras 5 reparaciones.
    - dry_run=False: persiste $set en cada doc afectado.
    - tenant_id: si se pasa, scope. Si no, cross-tenant (uso ops).

    Devuelve: {scanned, repaired, samples: [{collection, id, field, before, after}]}
    """
    from core.db import get_db
    db = get_db()
    stats = {"scanned": 0, "repaired": 0, "samples": []}

    # Campos a chequear por colección (string fields con potencial \uFFFD)
    targets = {
        "guias": [
            "carrier_incidence", "delivery_notes",
            "recipient.address", "recipient.name", "recipient.company",
            "recipient.state", "recipient.colonia",
            "sender.address", "sender.name", "sender.company",
            "sender.state",
        ],
        "tickets": ["incident_summary"],
    }

    for coll_name, fields in targets.items():
        coll = db[coll_name]
        q = {"tenant_id": tenant_id} if tenant_id else {}
        cursor = coll.find(q, {"_id": 0})
        async for doc in cursor:
            stats["scanned"] += 1
            updates: dict = {}
            for field in fields:
                # Soporta paths con punto (recipient.address)
                if "." in field:
                    parent, child = field.split(".", 1)
                    parent_dict = doc.get(parent) or {}
                    val = parent_dict.get(child)
                else:
                    val = doc.get(field)
                if not isinstance(val, str) or "\ufffd" not in val:
                    continue
                fixed = _apply_repairs(val)
                if fixed != val:
                    updates[field] = fixed
                    if len(stats["samples"]) < 10:
                        stats["samples"].append({
                            "collection": coll_name,
                            "id": doc.get("id"),
                            "field": field,
                            "before": val,
                            "after": fixed,
                        })
            if updates:
                stats["repaired"] += 1
                if not dry_run:
                    await coll.update_one(
                        {"id": doc["id"]}, {"$set": updates})
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Aplicar cambios (default: dry-run)")
    parser.add_argument("--tenant", default=None, help="Scope a un tenant_id")
    args = parser.parse_args()

    async def _run():
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")

        stats = await fix_encoding_in_db(
            dry_run=not args.apply, tenant_id=args.tenant)
        print(f"Scanned: {stats['scanned']}")
        print(f"Repaired: {stats['repaired']} (dry_run={not args.apply})")
        print("Samples (max 10):")
        for s in stats["samples"]:
            print(f"  · {s['collection']}.{s['id']}.{s['field']}")
            print(f"      before: {s['before']!r}")
            print(f"      after:  {s['after']!r}")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
