"""Tests for file-based run locking."""

import json
import tempfile
import time

import pytest

from apps.common.run_lock import (
    STALE_THRESHOLD_S,
    RunLockError,
    acquire_lock,
    is_locked,
    release_lock,
)


def test_acquire_and_release():
    with tempfile.TemporaryDirectory() as d:
        acquire_lock("run1", base_dir=d)
        assert is_locked("run1", base_dir=d) is True

        release_lock("run1", base_dir=d)
        assert is_locked("run1", base_dir=d) is False


def test_double_acquire_fails():
    with tempfile.TemporaryDirectory() as d:
        acquire_lock("run1", base_dir=d)
        with pytest.raises(RunLockError, match="already locked"):
            acquire_lock("run1", base_dir=d)
        release_lock("run1", base_dir=d)


def test_force_breaks_stale_lock():
    with tempfile.TemporaryDirectory() as d:
        path = acquire_lock("run1", base_dir=d)
        # Make the lock appear stale
        info = json.loads(path.read_text())
        info["timestamp"] = time.time() - STALE_THRESHOLD_S - 100
        path.write_text(json.dumps(info))

        # Force should succeed on stale lock
        acquire_lock("run1", base_dir=d, force=True)
        assert is_locked("run1", base_dir=d) is True
        release_lock("run1", base_dir=d)


def test_force_rejects_fresh_lock():
    with tempfile.TemporaryDirectory() as d:
        acquire_lock("run1", base_dir=d)
        with pytest.raises(RunLockError, match="not stale yet"):
            acquire_lock("run1", base_dir=d, force=True)
        release_lock("run1", base_dir=d)


def test_release_nonexistent():
    with tempfile.TemporaryDirectory() as d:
        # Should not raise
        release_lock("nonexistent", base_dir=d)


def test_is_locked_false_initially():
    with tempfile.TemporaryDirectory() as d:
        assert is_locked("run1", base_dir=d) is False


def test_lock_contains_pid():
    with tempfile.TemporaryDirectory() as d:
        import os

        path = acquire_lock("run1", base_dir=d)
        info = json.loads(path.read_text())
        assert info["pid"] == os.getpid()
        assert "locked_at" in info
        assert "timestamp" in info
        release_lock("run1", base_dir=d)


def test_separate_run_ids():
    with tempfile.TemporaryDirectory() as d:
        acquire_lock("run1", base_dir=d)
        acquire_lock("run2", base_dir=d)
        assert is_locked("run1", base_dir=d) is True
        assert is_locked("run2", base_dir=d) is True
        release_lock("run1", base_dir=d)
        assert is_locked("run1", base_dir=d) is False
        assert is_locked("run2", base_dir=d) is True
        release_lock("run2", base_dir=d)
