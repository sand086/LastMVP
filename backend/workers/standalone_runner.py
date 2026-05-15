"""
Standalone Worker Runner (capa 6 — process isolation).

Runs ALL LastMile background workers in a DEDICATED OS process, isolated
from the FastAPI HTTP server's event loop. Eliminates the event loop
contention that caused /health timeouts under heavy LLM/sync load.

Workers managed here:
- ai_eval_worker (Claude vision evaluation)
- kosmo_sync (Kosmo tracking scraper)
- routal_sync_worker (Routal plan sync)
- routal_selection_scheduler (auto-select Routal plans)

Lifecycle:
- Spawned by FastAPI's lifespan via subprocess.Popen.
- Monitored by FastAPI; respawned if it dies.
- On SIGTERM (parent shutdown), gracefully stops workers and exits.
- On Linux, registers PR_SET_PDEATHSIG=SIGTERM so it auto-dies if parent
  is SIGKILL'd (no zombie processes).

This is independent from FastAPI: its own asyncio loop, its own motor
client. They share only the MongoDB collections (the source of truth).
"""
import asyncio
import logging
import os
import signal
import sys

# Ensure /app/backend is importable when launched as a module.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Linux-only: die when parent FastAPI process dies (avoids orphans)
def _install_parent_death_signal():
    try:
        import ctypes
        PR_SET_PDEATHSIG = 1
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
    except Exception:
        pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [worker-proc] %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("standalone_runner")


async def _main():
    _install_parent_death_signal()

    # Late imports so logging is configured first
    from motor.motor_asyncio import AsyncIOMotorClient
    from leader_election import acquire_leader, release_leader, register_on_leader_callback, worker_id
    from ai_eval_worker import start_ai_eval_worker, stop_ai_eval_worker
    from kosmo_sync import start_periodic_sync, stop_periodic_sync, close_http_client
    from workers.routal_sync_worker import start_routal_sync_worker, stop_routal_sync_worker
    from workers.routal_selection_worker import start_selection_scheduler, stop_selection_scheduler

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        logger.error("MONGO_URL/DB_NAME missing — cannot start workers")
        return 1

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # PII encryption must be initialized so workers can decrypt fields when needed
    try:
        from utils.encryption import init_encryption
        await init_encryption(db)
    except Exception as e:
        logger.warning(f"init_encryption failed: {e}")

    stop_event = asyncio.Event()
    running_loop = asyncio.get_running_loop()

    def _on_signal():
        logger.info("[standalone] received shutdown signal — stopping workers")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            running_loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows fallback (not relevant in Emergent Linux pods)
            signal.signal(sig, lambda *_: _on_signal())

    # Leader election still applies — if some day there are multiple worker
    # processes (e.g. >1 replica), only one acquires bg_tasks.
    def _start_workers():
        logger.info(f"[standalone] Worker {worker_id()} is LEADER — starting all workers")
        start_periodic_sync(db)
        start_ai_eval_worker(db)
        start_selection_scheduler(db)
        start_routal_sync_worker(db)

    register_on_leader_callback("bg_tasks", _start_workers)
    elected = await acquire_leader(db, role="bg_tasks")
    if elected:
        _start_workers()
    else:
        logger.info(
            f"[standalone] Worker {worker_id()} is FOLLOWER — bg tasks will auto-start "
            f"when leader lease expires."
        )

    logger.info("[standalone] entering main loop")
    await stop_event.wait()

    logger.info("[standalone] shutting down workers")
    try:
        stop_periodic_sync()
        stop_ai_eval_worker()
        stop_selection_scheduler()
        stop_routal_sync_worker()
        await close_http_client()
    except Exception as e:
        logger.warning(f"[standalone] error during stop: {e}")
    try:
        await release_leader(db, role="bg_tasks")
    except Exception as e:
        logger.warning(f"[standalone] error releasing leader: {e}")
    client.close()
    logger.info("[standalone] exit")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(_main())
    except KeyboardInterrupt:
        code = 0
    sys.exit(code or 0)
