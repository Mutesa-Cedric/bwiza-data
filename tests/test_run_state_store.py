"""Tests for RunState persistence (atomic writes + done list)."""

import tempfile
from pathlib import Path

from apps.common.run_state import RunState
from apps.common.run_state_store import (
    has_done,
    load_done_set,
    load_state,
    mark_done,
    save_state,
)


def _make_state(run_id="test_run_001"):
    return RunState(
        run_id=run_id,
        pipeline="cc_miner",
        source="commoncrawl",
    )


def test_save_and_load():
    with tempfile.TemporaryDirectory() as d:
        state = _make_state()
        state.start()
        save_state(state, base_dir=d)

        loaded = load_state("test_run_001", base_dir=d)
        assert loaded is not None
        assert loaded.run_id == "test_run_001"
        assert loaded.status == "running"
        assert loaded.pipeline == "cc_miner"


def test_load_nonexistent():
    with tempfile.TemporaryDirectory() as d:
        loaded = load_state("nonexistent", base_dir=d)
        assert loaded is None


def test_save_overwrites_atomically():
    with tempfile.TemporaryDirectory() as d:
        state = _make_state()
        state.start()
        save_state(state, base_dir=d)

        state.items_done = 5
        save_state(state, base_dir=d)

        loaded = load_state("test_run_001", base_dir=d)
        assert loaded is not None
        assert loaded.items_done == 5


def test_save_updates_updated_at():
    with tempfile.TemporaryDirectory() as d:
        state = _make_state()
        assert state.updated_at == ""
        save_state(state, base_dir=d)

        loaded = load_state("test_run_001", base_dir=d)
        assert loaded is not None
        assert loaded.updated_at != ""


def test_no_tmp_files_left():
    with tempfile.TemporaryDirectory() as d:
        state = _make_state()
        save_state(state, base_dir=d)

        files = list(Path(d).glob("*.tmp"))
        assert files == []


def test_mark_done_and_load():
    with tempfile.TemporaryDirectory() as d:
        mark_done("run1", "item_a", base_dir=d)
        mark_done("run1", "item_b", base_dir=d)

        done = load_done_set("run1", base_dir=d)
        assert done == {"item_a", "item_b"}


def test_mark_done_appends():
    with tempfile.TemporaryDirectory() as d:
        mark_done("run1", "a", base_dir=d)
        mark_done("run1", "b", base_dir=d)
        mark_done("run1", "c", base_dir=d)

        done = load_done_set("run1", base_dir=d)
        assert len(done) == 3


def test_has_done():
    with tempfile.TemporaryDirectory() as d:
        mark_done("run1", "wet_001", base_dir=d)

        assert has_done("run1", "wet_001", base_dir=d) is True
        assert has_done("run1", "wet_999", base_dir=d) is False


def test_load_done_set_empty():
    with tempfile.TemporaryDirectory() as d:
        done = load_done_set("nonexistent", base_dir=d)
        assert done == set()


def test_done_list_deduplicates():
    with tempfile.TemporaryDirectory() as d:
        mark_done("run1", "x", base_dir=d)
        mark_done("run1", "x", base_dir=d)
        mark_done("run1", "y", base_dir=d)

        done = load_done_set("run1", base_dir=d)
        assert done == {"x", "y"}


def test_state_file_is_valid_json():
    with tempfile.TemporaryDirectory() as d:
        state = _make_state()
        state.start()
        path = save_state(state, base_dir=d)

        import json

        with open(path) as f:
            data = json.load(f)
        assert data["run_id"] == "test_run_001"
        assert data["status"] == "running"
