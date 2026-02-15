"""Tests for manifest writer."""

from apps.common.manifest import append_manifest_entry, read_manifest
from apps.common.shard_writer import ShardMeta


def _sample_meta() -> ShardMeta:
    return ShardMeta(
        filename="test_part-000001.jsonl.zst",
        path="/tmp/test_part-000001.jsonl.zst",
        bytes=1024,
        records_count=50,
        token_estimate=500,
        checksum="abc123",
        created_at="2026-01-01T00:00:00Z",
    )


def test_append_and_read(tmp_path):
    base = str(tmp_path / "manifests")
    meta = _sample_meta()

    append_manifest_entry("run1", meta, source="commoncrawl", base_dir=base)
    entries = read_manifest("run1", base_dir=base)
    assert len(entries) == 1
    assert entries[0]["filename"] == "test_part-000001.jsonl.zst"
    assert entries[0]["run_id"] == "run1"
    assert entries[0]["source"] == "commoncrawl"


def test_append_multiple(tmp_path):
    base = str(tmp_path / "manifests")
    meta = _sample_meta()

    append_manifest_entry("run1", meta, source="cc", base_dir=base)
    meta.filename = "test_part-000002.jsonl.zst"
    append_manifest_entry("run1", meta, source="cc", base_dir=base)

    entries = read_manifest("run1", base_dir=base)
    assert len(entries) == 2


def test_read_nonexistent(tmp_path):
    entries = read_manifest("nope", base_dir=str(tmp_path))
    assert entries == []
