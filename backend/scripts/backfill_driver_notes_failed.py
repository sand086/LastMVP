"""
One-shot: re-sincroniza desde Routal las guías failed que están sin
kosmo_driver_note para llenar retroactivamente la nota del driver
("Comentarios" en Routal).

Causa raíz: la rama `failed` de sync_journey_from_routal no persistía
kosmo_driver_note (solo lo hacía la rama delivered). Resultado: 433/434
packages failed quedaron con "Sin nota del driver" en la UI desde la
migración a flujo Routal-only.

Uso:
    cd /app/backend && python -m scripts.backfill_driver_notes_failed [--dry-run] [--limit N]

Notas:
- Idempotente: re-correrlo no daña nada, solo actualiza lo que aún falta.
- Trabaja por journey (1 llamada a Routal por journey, no por package),
  evitando cientos de llamadas redundantes.
- Solo toca packages con status="failed" y kosmo_driver_note vacío.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

# Ensure /app/backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from services.routal_sync import sync_journey_from_routal  # noqa: E402


async def main(dry_run: bool, limit: int):
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    db = AsyncIOMotorClient(mongo_url)[db_name]

    # Encryption singleton (needed by IntegrationService.get_routal_client →
    # decrypts the per-client API key from DB).
    from utils.encryption import init_encryption
    await init_encryption(db)

    api_base = os.environ.get("REACT_APP_BACKEND_URL", "")

    started_at = datetime.now(timezone.utc)
    print(f"[backfill] started at {started_at.isoformat()}")
    print(f"[backfill] dry_run={dry_run} limit={limit}")

    # 1. Identificar journeys con al menos 1 package failed sin nota.
    # NO filtramos por routal_report_id en el package porque la rama failed
    # del sync histórico tampoco persistía ese campo; en su lugar nos basamos
    # en que el journey sea de fuente Routal (tenga routal_plan_id).
    routal_journey_ids = [
        j["id"]
        async for j in db.journeys.find(
            {"source": "routal", "routal_plan_id": {"$exists": True, "$ne": None}},
            {"_id": 0, "id": 1},
        )
    ]
    pipeline = [
        {"$match": {
            "status": "failed",
            "$or": [
                {"kosmo_driver_note": None},
                {"kosmo_driver_note": ""},
                {"kosmo_driver_note": {"$exists": False}},
            ],
            "journey_id": {"$in": routal_journey_ids},
        }},
        {"$group": {"_id": "$journey_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    if limit > 0:
        pipeline.append({"$limit": limit})

    target_journeys = []
    async for j in db.packages.aggregate(pipeline):
        target_journeys.append((j["_id"], j["count"]))

    total_pkgs = sum(c for _, c in target_journeys)
    print(f"[backfill] {len(target_journeys)} journeys to sync · {total_pkgs} packages affected")

    if dry_run:
        for jid, n in target_journeys[:10]:
            print(f"  [DRY] journey={jid} packages_failed_without_note={n}")
        if len(target_journeys) > 10:
            print(f"  ... and {len(target_journeys)-10} more")
        print("[backfill] DRY RUN — no DB writes")
        return

    healed_total = 0
    errors = []
    for i, (jid, n) in enumerate(target_journeys, 1):
        try:
            summary = await sync_journey_from_routal(db, jid, api_base)
            if summary.get("ok"):
                # Re-verificar cuántos packages ya tienen nota
                still_empty = await db.packages.count_documents({
                    "journey_id": jid,
                    "status": "failed",
                    "$or": [
                        {"kosmo_driver_note": None},
                        {"kosmo_driver_note": ""},
                        {"kosmo_driver_note": {"$exists": False}},
                    ],
                })
                healed = n - still_empty
                healed_total += healed
                print(f"  [{i}/{len(target_journeys)}] journey={jid[:8]} healed={healed}/{n} (still_empty={still_empty})")
            else:
                msg = summary.get("error") or summary.get("reason") or "no error msg"
                errors.append((jid, msg))
                print(f"  [{i}/{len(target_journeys)}] journey={jid[:8]} ERROR: {msg}")
        except Exception as e:
            errors.append((jid, str(e)))
            print(f"  [{i}/{len(target_journeys)}] journey={jid[:8]} EXCEPTION: {e}")

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    print()
    print(f"[backfill] done in {elapsed:.1f}s")
    print(f"[backfill] healed: {healed_total}/{total_pkgs} packages")
    print(f"[backfill] errors: {len(errors)}")
    if errors:
        for jid, msg in errors[:5]:
            print(f"  - {jid}: {msg}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Backfill kosmo_driver_note for failed packages")
    p.add_argument("--dry-run", action="store_true", help="don't write, just count")
    p.add_argument("--limit", type=int, default=0, help="limit journeys (0 = all)")
    args = p.parse_args()
    asyncio.run(main(args.dry_run, args.limit))
