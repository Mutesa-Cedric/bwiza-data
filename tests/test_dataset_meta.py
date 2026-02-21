"""Tests for dataset metadata generator."""

import json

from apps.common.dataset_index import DatasetIndexEntry, write_index
from apps.packaging.dataset_meta import build_and_write_metadata, build_metadata


def _entry(source="commoncrawl", records=10, tokens=250):
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id="run1",
        source=source,
        shard_name="shard_001.jsonl.zst",
        s3_bucket="test-bucket",
        s3_key="prefix/shard_001.jsonl.zst",
        bytes=1000,
        records=records,
        token_estimate=tokens,
        checksum_sha256="abc" + "0" * 61,
        created_at="2026-02-21T00:00:00+00:00",
    )


def _make_index(tmp_path, entries):
    path = tmp_path / "index.jsonl"
    write_index(entries, path)
    return str(path)


def test_metadata_structure(tmp_path):
    index_path = _make_index(tmp_path, [_entry()])
    meta = build_metadata("pretrain", "v1", index_path)

    assert meta["name"] == "bwiza-pretrain"
    assert meta["version"] == "v1"
    assert meta["dataset_type"] == "pretrain"
    assert "build_time" in meta
    assert meta["total_shards"] == 1
    assert meta["total_records"] == 10
    assert meta["total_token_estimate"] == 250
    assert "license_note" in meta
    assert "intended_use" in meta


def test_metadata_sources(tmp_path):
    entries = [_entry(source="commoncrawl"), _entry(source="targeted_web")]
    index_path = _make_index(tmp_path, entries)
    meta = build_metadata("pretrain", "v1", index_path)

    assert meta["sources"] == ["commoncrawl", "targeted_web"]


def test_metadata_config_fingerprints(tmp_path):
    index_path = _make_index(tmp_path, [_entry()])
    meta = build_metadata("pretrain", "v1", index_path, config_fingerprints=["abc123"])

    assert meta["config_fingerprints"] == ["abc123"]


def test_metadata_empty_index(tmp_path):
    path = tmp_path / "index.jsonl"
    path.write_text("")
    meta = build_metadata("pretrain", "v1", str(path))

    assert meta["total_shards"] == 0
    assert meta["sources"] == []


def test_write_metadata(tmp_path):
    index_path = _make_index(tmp_path, [_entry()])
    output = tmp_path / "dataset_meta.json"

    build_and_write_metadata("pretrain", "v1", index_path, output)

    assert output.exists()
    data = json.loads(output.read_text())
    assert data["name"] == "bwiza-pretrain"
