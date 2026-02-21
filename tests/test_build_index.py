"""Tests for dataset index builder."""

import json

from apps.common.dataset_index import read_index
from apps.packaging.build_index import build_and_write_index, build_index


def _write_manifest(path, entries):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _manifest_entry(
    run_id="run1",
    source="commoncrawl",
    filename="shard_001.jsonl.zst",
    bytes_=1000,
    records_count=10,
    token_estimate=250,
    checksum="abc123" + "0" * 58,
    created_at="2026-02-21T00:00:00+00:00",
):
    return {
        "run_id": run_id,
        "source": source,
        "filename": filename,
        "path": f"/tmp/{filename}",
        "bytes": bytes_,
        "records_count": records_count,
        "token_estimate": token_estimate,
        "checksum": checksum,
        "created_at": created_at,
    }


def test_build_index_filters_by_dataset(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "run1.jsonl",
        [
            _manifest_entry(source="commoncrawl"),
            _manifest_entry(source="parallel_web", filename="parallel_001.jsonl.zst"),
        ],
    )

    entries = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    assert len(entries) == 1
    assert entries[0].source == "commoncrawl"


def test_build_index_skips_empty_checksum(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "run1.jsonl",
        [
            _manifest_entry(checksum=""),
            _manifest_entry(filename="shard_002.jsonl.zst", checksum="valid" + "0" * 59),
        ],
    )

    entries = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    assert len(entries) == 1
    assert entries[0].shard_name == "shard_002.jsonl.zst"


def test_build_index_deterministic_sort(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "runB.jsonl",
        [_manifest_entry(run_id="runB", filename="shard_002.jsonl.zst")],
    )
    _write_manifest(
        manifest_dir / "runA.jsonl",
        [_manifest_entry(run_id="runA", filename="shard_001.jsonl.zst")],
    )

    entries = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    assert len(entries) == 2
    assert entries[0].run_id == "runA"
    assert entries[1].run_id == "runB"


def test_build_index_s3_key_format(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "run1.jsonl",
        [_manifest_entry(run_id="20260221T053814Z", filename="bwiza_cc_part-001.jsonl.zst")],
    )

    entries = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    assert len(entries) == 1
    assert "run_id=20260221T053814Z" in entries[0].s3_key
    assert "bwiza_cc_part-001.jsonl.zst" in entries[0].s3_key


def test_build_index_multiple_sources_same_dataset(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "run1.jsonl",
        [
            _manifest_entry(source="commoncrawl", filename="cc_001.jsonl.zst"),
            _manifest_entry(source="targeted_web", filename="tw_001.jsonl.zst"),
        ],
    )

    entries = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    assert len(entries) == 2
    sources = {e.source for e in entries}
    assert sources == {"commoncrawl", "targeted_web"}


def test_build_and_write_index(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "run1.jsonl",
        [_manifest_entry()],
    )

    output_dir = tmp_path / "output"
    path = build_and_write_index(
        "pretrain", "test-bucket", manifest_dir=str(manifest_dir), output_dir=str(output_dir)
    )

    assert path.exists()
    entries = read_index(path)
    assert len(entries) == 1


def test_build_index_empty_manifest_dir(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    entries = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    assert entries == []


def test_build_index_nonexistent_dir(tmp_path):
    entries = build_index("pretrain", "test-bucket", manifest_dir=str(tmp_path / "nope"))
    assert entries == []


def test_build_index_repeated_runs_identical(tmp_path):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "run1.jsonl",
        [
            _manifest_entry(run_id="r1", filename="s1.jsonl.zst"),
            _manifest_entry(run_id="r2", filename="s2.jsonl.zst"),
        ],
    )

    entries1 = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))
    entries2 = build_index("pretrain", "test-bucket", manifest_dir=str(manifest_dir))

    assert len(entries1) == len(entries2)
    for a, b in zip(entries1, entries2):
        assert a.to_json() == b.to_json()
