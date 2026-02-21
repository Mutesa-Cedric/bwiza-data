"""Tests for S3 path builders."""

from apps.common.s3_paths import manifest_key, shard_key, stats_key


def test_shard_key():
    result = shard_key("bwiza/cc/v1/", "20250101T000000Z", "shard_part-000001.jsonl.zst")
    assert result == "bwiza/cc/v1/shards/run_id=20250101T000000Z/shard_part-000001.jsonl.zst"


def test_shard_key_no_trailing_slash():
    result = shard_key("bwiza/cc/v1", "run1", "f.jsonl.zst")
    assert result == "bwiza/cc/v1/shards/run_id=run1/f.jsonl.zst"


def test_manifest_key():
    result = manifest_key("bwiza/cc/v1/", "20250101T000000Z")
    assert result == "bwiza/cc/v1/manifests/run_id=20250101T000000Z.jsonl"


def test_stats_key():
    result = stats_key("bwiza/cc/v1/", "20250101T000000Z")
    assert result == "bwiza/cc/v1/stats/run_id=20250101T000000Z.json"


def test_deterministic():
    """Same inputs always produce same keys."""
    a = shard_key("p/", "r", "f.zst")
    b = shard_key("p/", "r", "f.zst")
    assert a == b
