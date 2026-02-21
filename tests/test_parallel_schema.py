"""Tests for ParallelPair schema."""

import json

from apps.common.parallel_schema import PARALLEL_REJECT_REASONS, ParallelPair


def _sample_pair():
    return ParallelPair(
        id="abc123",
        rw_text="Muraho neza",
        en_text="Hello there",
        source="parallel_web",
        url_rw="https://example.rw/rw/page",
        url_en="https://example.rw/en/page",
        domain="example.rw",
        fetched_at="2026-02-21T12:00:00Z",
        rw_lid_score=0.95,
        en_lid_score=0.98,
        meta={"method": "hreflang"},
    )


def test_to_json():
    pair = _sample_pair()
    d = pair.to_json()
    assert d["id"] == "abc123"
    assert d["rw_text"] == "Muraho neza"
    assert d["en_text"] == "Hello there"
    assert d["source"] == "parallel_web"
    assert d["domain"] == "example.rw"
    assert d["meta"]["method"] == "hreflang"


def test_from_json():
    pair = _sample_pair()
    d = pair.to_json()
    restored = ParallelPair.from_json(d)
    assert restored.id == pair.id
    assert restored.rw_text == pair.rw_text
    assert restored.en_text == pair.en_text
    assert restored.rw_lid_score == pair.rw_lid_score


def test_json_serializable():
    pair = _sample_pair()
    serialized = json.dumps(pair.to_json())
    assert isinstance(serialized, str)
    loaded = json.loads(serialized)
    assert loaded["id"] == "abc123"


def test_from_json_ignores_extra_fields():
    d = _sample_pair().to_json()
    d["extra_field"] = "should_be_ignored"
    restored = ParallelPair.from_json(d)
    assert restored.id == "abc123"


def test_reject_reasons_are_stable():
    assert "reject.too_short" in PARALLEL_REJECT_REASONS
    assert "reject.lid.low_confidence" in PARALLEL_REJECT_REASONS
    assert "reject.duplicate" in PARALLEL_REJECT_REASONS
    assert "reject.lid.not_rw" in PARALLEL_REJECT_REASONS
    assert "reject.lid.not_en" in PARALLEL_REJECT_REASONS


def test_default_values():
    pair = ParallelPair(id="x", rw_text="a", en_text="b", source="test")
    assert pair.url_rw == ""
    assert pair.url_en == ""
    assert pair.domain == ""
    assert pair.meta == {}
