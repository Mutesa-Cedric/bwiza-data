"""Tests for dataset stats builder."""

import json

from apps.common.dataset_index import DatasetIndexEntry, write_index
from apps.packaging.dataset_stats import build_and_write_stats, build_stats


def _entry(run_id="run1", source="commoncrawl", bytes_=1000, records=10, tokens=250):
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id=run_id,
        source=source,
        shard_name=f"shard_{run_id}.jsonl.zst",
        s3_bucket="test-bucket",
        s3_key=f"prefix/{run_id}/shard.jsonl.zst",
        bytes=bytes_,
        records=records,
        token_estimate=tokens,
        checksum_sha256="abc" + "0" * 61,
        created_at="2026-02-21T00:00:00+00:00",
    )


def _make_index(tmp_path, entries):
    path = tmp_path / "index.jsonl"
    write_index(entries, path)
    return str(path)


def test_totals(tmp_path):
    entries = [
        _entry(run_id="r1", bytes_=100, records=5, tokens=25),
        _entry(run_id="r2", bytes_=200, records=10, tokens=50),
    ]
    stats = build_stats(_make_index(tmp_path, entries))

    assert stats["total_shards"] == 2
    assert stats["total_bytes"] == 300
    assert stats["total_records"] == 15
    assert stats["total_token_estimate"] == 75


def test_per_source(tmp_path):
    entries = [
        _entry(source="commoncrawl", bytes_=100, records=5, tokens=25),
        _entry(run_id="r2", source="targeted_web", bytes_=200, records=10, tokens=50),
    ]
    stats = build_stats(_make_index(tmp_path, entries))

    assert stats["per_source"]["commoncrawl"]["shards"] == 1
    assert stats["per_source"]["commoncrawl"]["bytes"] == 100
    assert stats["per_source"]["targeted_web"]["shards"] == 1
    assert stats["per_source"]["targeted_web"]["bytes"] == 200


def test_per_run(tmp_path):
    entries = [
        _entry(run_id="r1", bytes_=100),
        _entry(run_id="r1", source="targeted_web", bytes_=50),
        _entry(run_id="r2", bytes_=200),
    ]
    stats = build_stats(_make_index(tmp_path, entries))

    assert stats["per_run"]["r1"]["shards"] == 2
    assert stats["per_run"]["r1"]["bytes"] == 150
    assert stats["per_run"]["r2"]["shards"] == 1


def test_empty_index(tmp_path):
    path = tmp_path / "index.jsonl"
    path.write_text("")
    stats = build_stats(str(path))

    assert stats["total_shards"] == 0
    assert stats["total_bytes"] == 0
    assert stats["per_source"] == {}
    assert stats["per_run"] == {}


def test_write_stats(tmp_path):
    entries = [_entry()]
    index_path = _make_index(tmp_path, entries)
    output = tmp_path / "stats.json"

    build_and_write_stats(index_path, output)

    assert output.exists()
    data = json.loads(output.read_text())
    assert data["total_shards"] == 1
