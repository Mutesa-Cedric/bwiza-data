"""Tests for global dedup pass at packaging time."""

import json

import zstandard as zstd

from apps.common.dataset_index import DatasetIndexEntry, write_index
from apps.common.dedup_store import DedupStore
from apps.packaging.dedup_pass import DedupReport, run_dedup_pass


def _make_shard(path, docs):
    """Create a zstd-compressed JSONL shard from a list of doc dicts."""
    lines = "\n".join(json.dumps(d) for d in docs)
    cctx = zstd.ZstdCompressor()
    compressed = cctx.compress(lines.encode("utf-8"))
    path.write_bytes(compressed)


def _make_index_entry(shard_name, source="commoncrawl", run_id="run1"):
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id=run_id,
        source=source,
        shard_name=shard_name,
        s3_bucket="test",
        s3_key=f"test/{shard_name}",
        bytes=100,
        records=1,
        token_estimate=50,
        checksum_sha256="abc",
        created_at="2026-01-01",
    )


def test_dedup_pass_no_duplicates(tmp_path):
    # Create shard with unique docs
    shard_dir = tmp_path / "shards"
    shard_dir.mkdir()
    _make_shard(
        shard_dir / "shard1.jsonl.zst",
        [
            {"id": "1", "text": "Unique document one about Rwanda"},
            {"id": "2", "text": "Unique document two about Kigali"},
        ],
    )

    # Create index
    index_path = tmp_path / "index.jsonl"
    write_index([_make_index_entry("shard1.jsonl.zst")], index_path)

    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        report = run_dedup_pass(str(index_path), str(shard_dir), store, str(tmp_path / "out"))

    assert report.total_docs == 2
    assert report.unique_docs == 2
    assert report.exact_dupes == 0
    assert report.dedup_ratio == 0.0


def test_dedup_pass_cross_source_duplicates(tmp_path):
    shard_dir = tmp_path / "shards"
    shard_dir.mkdir()

    # Same text in two shards from different sources
    shared_text = "Igihugu cy'u Rwanda kiherereye mu burasirazuba bw'Afurika."
    _make_shard(
        shard_dir / "cc_shard.jsonl.zst",
        [{"id": "cc1", "text": shared_text}],
    )
    _make_shard(
        shard_dir / "tgt_shard.jsonl.zst",
        [{"id": "tgt1", "text": shared_text}],
    )

    index_path = tmp_path / "index.jsonl"
    write_index(
        [
            _make_index_entry("cc_shard.jsonl.zst", source="commoncrawl"),
            _make_index_entry("tgt_shard.jsonl.zst", source="targeted_web"),
        ],
        index_path,
    )

    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        report = run_dedup_pass(str(index_path), str(shard_dir), store, str(tmp_path / "out"))

    assert report.total_docs == 2
    assert report.unique_docs == 1
    assert report.exact_dupes == 1
    assert report.shards_with_dupes == 1


def test_dedup_pass_writes_report(tmp_path):
    shard_dir = tmp_path / "shards"
    shard_dir.mkdir()
    _make_shard(
        shard_dir / "s1.jsonl.zst",
        [{"id": "1", "text": "Some text"}],
    )

    index_path = tmp_path / "index.jsonl"
    write_index([_make_index_entry("s1.jsonl.zst")], index_path)

    out_dir = tmp_path / "out"
    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        run_dedup_pass(str(index_path), str(shard_dir), store, str(out_dir))

    assert (out_dir / "dedup_report.json").exists()
    assert (out_dir / "index_deduped.jsonl").exists()

    report_data = json.loads((out_dir / "dedup_report.json").read_text())
    assert report_data["total_docs"] == 1
    assert report_data["unique_docs"] == 1


def test_dedup_pass_empty_index(tmp_path):
    index_path = tmp_path / "index.jsonl"
    index_path.write_text("")

    with DedupStore(tmp_path / "dedup.db", enable_fuzzy=False) as store:
        report = run_dedup_pass(str(index_path), str(tmp_path), store, str(tmp_path / "out"))

    assert report.total_docs == 0


def test_dedup_report_to_dict():
    r = DedupReport(total_docs=100, unique_docs=80, exact_dupes=15, fuzzy_dupes=5)
    d = r.to_dict()
    assert d["dedup_ratio"] == 0.2
    assert d["total_docs"] == 100
