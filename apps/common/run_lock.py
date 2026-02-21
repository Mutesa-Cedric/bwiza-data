"""File-based run locking to prevent double execution."""

import json
import os
import time
from pathlib import Path

from apps.common.logging import get_logger

log = get_logger(__name__)

LOCK_DIR = "manifests/state"
STALE_THRESHOLD_S = 3600  # 1 hour


class RunLockError(RuntimeError):
    """Raised when a run lock cannot be acquired."""


def _lock_path(run_id: str, base_dir: str = LOCK_DIR) -> Path:
    return Path(base_dir) / f"{run_id}.lock"


def acquire_lock(
    run_id: str,
    base_dir: str = LOCK_DIR,
    force: bool = False,
) -> Path:
    """Acquire a lock for a run_id. Raises RunLockError if already locked.

    If force=True, breaks stale locks (older than STALE_THRESHOLD_S).
    """
    path = _lock_path(run_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        lock_info = _read_lock(path)
        if not force:
            raise RunLockError(
                f"Run {run_id} is already locked by PID {lock_info.get('pid')}"
                f" since {lock_info.get('locked_at', '?')}"
                f". Use force=True to break stale lock."
            )
        # Check if stale
        age = time.time() - lock_info.get("timestamp", 0)
        if age < STALE_THRESHOLD_S:
            raise RunLockError(
                f"Run {run_id} is locked by PID {lock_info.get('pid')}"
                f" ({age:.0f}s ago, not stale yet)."
                f" Stale threshold: {STALE_THRESHOLD_S}s."
            )
        log.warning(
            "Breaking stale lock for %s (age=%.0fs, pid=%s)",
            run_id,
            age,
            lock_info.get("pid"),
        )

    _write_lock(path)
    log.info("Lock acquired for run %s", run_id)
    return path


def release_lock(run_id: str, base_dir: str = LOCK_DIR) -> None:
    """Release the lock for a run_id."""
    path = _lock_path(run_id, base_dir)
    if path.exists():
        path.unlink()
        log.info("Lock released for run %s", run_id)


def is_locked(run_id: str, base_dir: str = LOCK_DIR) -> bool:
    """Check if a run is locked."""
    return _lock_path(run_id, base_dir).exists()


def _write_lock(path: Path) -> None:
    info = {
        "pid": os.getpid(),
        "timestamp": time.time(),
        "locked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.write_text(json.dumps(info, indent=2))


def _read_lock(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
