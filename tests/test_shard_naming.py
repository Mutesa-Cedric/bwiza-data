"""Tests for shard naming."""

from apps.common.shard_naming import shard_name


def test_basic_name():
    result = shard_name("bwiza", "commoncrawl", "20260215T120000Z", 1)
    assert result == "bwiza_commoncrawl_20260215T120000Z_part-000001.jsonl.zst"


def test_part_padding():
    result = shard_name("bwiza", "commoncrawl", "run1", 123)
    assert "part-000123" in result


def test_different_source():
    result = shard_name("bwiza", "targeted_web", "run1", 1)
    assert "targeted_web" in result
