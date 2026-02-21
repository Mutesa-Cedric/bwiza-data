"""Atomic RunState persistence with append-only done list."""

import os
import tempfile
from pathlib import Path

from apps.common.logging import get_logger
from apps.common.run_state import RunState

log = get_logger(__name__)

STATE_DIR = "manifests/state"


def _state_path(run_id: str, base_dir: str = STATE_DIR) -> Path:
    return Path(base_dir) / f"{run_id}.json"


def _done_path(run_id: str, base_dir: str = STATE_DIR) -> Path:
    return Path(base_dir) / f"{run_id}.done.txt"


def save_state(state: RunState, base_dir: str = STATE_DIR) -> Path:
    """Atomically write RunState to disk (write-tmp-then-rename)."""
    state.touch()
    dest = _state_path(state.run_id, base_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp", prefix=".state_")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(state.to_json())
        os.replace(tmp, str(dest))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    log.debug("State saved: %s (status=%s)", dest, state.status)
    return dest


def load_state(run_id: str, base_dir: str = STATE_DIR) -> RunState | None:
    """Load RunState from disk. Returns None if not found."""
    path = _state_path(run_id, base_dir)
    if not path.exists():
        return None
    return RunState.from_json(path.read_text())


def mark_done(run_id: str, item: str, base_dir: str = STATE_DIR) -> None:
    """Append an item to the done list (one item per line)."""
    path = _done_path(run_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(item + "\n")


def load_done_set(run_id: str, base_dir: str = STATE_DIR) -> set[str]:
    """Load the done set from disk. Returns empty set if not found."""
    path = _done_path(run_id, base_dir)
    if not path.exists():
        return set()
    items = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.add(line)
    return items


def has_done(run_id: str, item: str, base_dir: str = STATE_DIR) -> bool:
    """Check if an item is in the done list (loads full set)."""
    return item in load_done_set(run_id, base_dir)
