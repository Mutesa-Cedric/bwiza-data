"""Tests for RunState schema."""

import json

from apps.common.run_state import PIPELINES, STATUSES, RunState


def _sample_state():
    return RunState(
        run_id="20260221T120000Z",
        pipeline="cc_miner",
        source="commoncrawl",
        config_fingerprint="abc123",
        git_commit="deadbeef",
    )


def test_default_status():
    s = RunState()
    assert s.status == "created"
    assert s.started_at == ""
    assert s.ended_at == ""
    assert s.items_done == 0


def test_start_transition():
    s = _sample_state()
    s.start()
    assert s.status == "running"
    assert s.started_at != ""
    assert s.updated_at != ""


def test_start_preserves_original_started_at():
    s = _sample_state()
    s.started_at = "2026-01-01T00:00:00Z"
    s.start()
    assert s.started_at == "2026-01-01T00:00:00Z"
    assert s.status == "running"


def test_complete_transition():
    s = _sample_state()
    s.start()
    s.complete()
    assert s.status == "completed"
    assert s.ended_at != ""


def test_fail_transition():
    s = _sample_state()
    s.start()
    s.fail("timeout")
    assert s.status == "failed"
    assert s.failure_reason == "timeout"
    assert s.ended_at != ""


def test_pause_transition():
    s = _sample_state()
    s.start()
    s.pause("guardrail.max_runtime")
    assert s.status == "paused"
    assert s.failure_reason == "guardrail.max_runtime"


def test_touch_updates_timestamp():
    s = _sample_state()
    assert s.updated_at == ""
    s.touch()
    assert s.updated_at != ""


def test_to_dict():
    s = _sample_state()
    d = s.to_dict()
    assert d["run_id"] == "20260221T120000Z"
    assert d["pipeline"] == "cc_miner"
    assert d["source"] == "commoncrawl"
    assert d["config_fingerprint"] == "abc123"
    assert d["status"] == "created"


def test_to_json():
    s = _sample_state()
    text = s.to_json()
    parsed = json.loads(text)
    assert parsed["run_id"] == "20260221T120000Z"


def test_from_dict():
    s = _sample_state()
    s.start()
    d = s.to_dict()
    restored = RunState.from_dict(d)
    assert restored.run_id == s.run_id
    assert restored.status == "running"
    assert restored.started_at == s.started_at


def test_from_json():
    s = _sample_state()
    text = s.to_json()
    restored = RunState.from_json(text)
    assert restored.run_id == s.run_id
    assert restored.pipeline == "cc_miner"


def test_from_dict_ignores_extra_fields():
    d = _sample_state().to_dict()
    d["unknown_field"] = "should_be_ignored"
    restored = RunState.from_dict(d)
    assert restored.run_id == "20260221T120000Z"


def test_pipelines_stable():
    assert "cc_miner" in PIPELINES
    assert "targeted_crawler" in PIPELINES
    assert "books_corpus" in PIPELINES
    assert "parallel" in PIPELINES
    assert "instructions" in PIPELINES


def test_statuses_stable():
    assert "created" in STATUSES
    assert "running" in STATUSES
    assert "paused" in STATUSES
    assert "completed" in STATUSES
    assert "failed" in STATUSES


def test_meta_default():
    s = RunState()
    assert s.meta == {}
    s.meta["key"] = "value"
    assert s.meta["key"] == "value"
