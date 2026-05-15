"""
Subprocess Manager for the standalone worker process (capa 6).

Responsibilities:
- Spawn the worker subprocess on FastAPI startup.
- Monitor it; respawn on crash with exponential backoff.
- Send SIGTERM on FastAPI shutdown; SIGKILL fallback after grace period.
- Expose status via `is_worker_alive()` for /api/admin/event-loop-health.
"""
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)

_proc: Optional[subprocess.Popen] = None
_monitor_task: Optional[asyncio.Task] = None
_shutdown_requested = False
_restart_backoff = 1
_RESTART_BACKOFF_MAX = 60
_BACKEND_DIR = "/app/backend"


def _spawn() -> Optional[subprocess.Popen]:
    """Spawn the worker subprocess. Returns the Popen handle or None on failure."""
    try:
        env = os.environ.copy()
        # Mark process so the child knows it's standalone (avoid recursion if
        # someone ever imports server.py from inside the child)
        env["WORKERS_PROCESS_ROLE"] = "standalone"
        proc = subprocess.Popen(
            [sys.executable, "-m", "workers.standalone_runner"],
            cwd=_BACKEND_DIR,
            env=env,
            stdout=None,  # inherit parent stdout
            stderr=None,  # inherit parent stderr
            start_new_session=False,  # keep in same session so SIGTERM propagates
        )
        logger.info(f"[workers-subprocess] spawned PID={proc.pid}")
        return proc
    except Exception as e:
        logger.error(f"[workers-subprocess] spawn failed: {e}")
        return None


async def _monitor():
    """Watch the subprocess. Respawn on unexpected exit with exponential backoff."""
    global _proc, _restart_backoff
    while not _shutdown_requested:
        if _proc is None:
            _proc = _spawn()
            if _proc is None:
                await asyncio.sleep(_restart_backoff)
                _restart_backoff = min(_restart_backoff * 2, _RESTART_BACKOFF_MAX)
                continue
            _restart_backoff = 1

        # Check liveness every 5s
        await asyncio.sleep(5)
        rc = _proc.poll()
        if rc is None:
            continue  # still alive

        # Exited. If shutdown was requested, just stop.
        if _shutdown_requested:
            logger.info(f"[workers-subprocess] subprocess exited (rc={rc}) during shutdown")
            return

        logger.warning(
            f"[workers-subprocess] subprocess exited unexpectedly with rc={rc}, "
            f"respawning in {_restart_backoff}s"
        )
        _proc = None
        await asyncio.sleep(_restart_backoff)
        _restart_backoff = min(_restart_backoff * 2, _RESTART_BACKOFF_MAX)


def start_worker_subprocess() -> None:
    """Idempotent: starts the worker subprocess + monitor task once."""
    global _monitor_task, _shutdown_requested
    _shutdown_requested = False
    if _monitor_task and not _monitor_task.done():
        logger.info("[workers-subprocess] monitor already running — skip duplicate start")
        return
    _monitor_task = asyncio.create_task(_monitor())
    logger.info("[workers-subprocess] monitor started")


async def stop_worker_subprocess(grace_seconds: int = 10) -> None:
    """Gracefully stop the worker subprocess and the monitor task."""
    global _proc, _monitor_task, _shutdown_requested
    _shutdown_requested = True

    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        try:
            await _monitor_task
        except (asyncio.CancelledError, Exception):
            pass

    if _proc is not None and _proc.poll() is None:
        logger.info(f"[workers-subprocess] sending SIGTERM to PID={_proc.pid}")
        try:
            _proc.send_signal(signal.SIGTERM)
        except Exception as e:
            logger.warning(f"[workers-subprocess] SIGTERM failed: {e}")

        # Wait up to grace_seconds for graceful exit
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if _proc.poll() is not None:
                logger.info(f"[workers-subprocess] subprocess exited gracefully rc={_proc.returncode}")
                _proc = None
                return
            await asyncio.sleep(0.5)

        # Force kill
        try:
            logger.warning(f"[workers-subprocess] grace expired — SIGKILL PID={_proc.pid}")
            _proc.kill()
            _proc.wait(timeout=5)
        except Exception as e:
            logger.error(f"[workers-subprocess] kill failed: {e}")
    _proc = None


def is_worker_alive() -> bool:
    """Returns True iff the standalone worker subprocess is running."""
    return _proc is not None and _proc.poll() is None


def get_worker_pid() -> Optional[int]:
    return _proc.pid if (_proc is not None and _proc.poll() is None) else None
