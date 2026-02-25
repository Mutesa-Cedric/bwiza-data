"""Tests for dataset index schema."""

import json

from apps.common.dataset_index import (
    VALID_DATASETS,
    DatasetIndexEntry,
    dataset_for_source,
    read_index,
    write_index,
)


def _entry(**overrides: object) -> DatasetIndexEntry:
    entry = DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id="20260221T053814Z",
        source="commoncrawl",
        shard_name="bwiza_commoncrawl_20260221T053814Z_part-000001.jsonl.zst",
        s3_bucket="my-bucket",
        s3_key="bwiza/cc/v1/shards/run_id=20260221T053814Z/bwiza_commoncrawl_20260221T053814Z_part-000001.jsonl.zst",
        bytes=28174,
        records=10,
        token_estimate=17792,
        checksum_sha256="06bce6c2ebcc" + "a" * 52,
        created_at="2026-02-21T05:38:14+00:00",
    )
    for k, v in overrides.items():
        setattr(entry, k, v)
    return entry


def test_to_json_round_trip():
    entry = _entry()
    data = entry.to_json()
    restored = DatasetIndexEntry.from_json(data)
    assert restored.dataset == entry.dataset
    assert restored.run_id == entry.run_id
    assert restored.bytes == entry.bytes
    assert restored.checksum_sha256 == entry.checksum_sha256


def test_to_json_includes_all_fields():
    entry = _entry(meta={"crawl_id": "CC-MAIN-2026-04"})
    data = entry.to_json()
    assert data["dataset"] == "pretrain"
    assert data["meta"] == {"crawl_id": "CC-MAIN-2026-04"}
    assert isinstance(data["bytes"], int)


def test_from_json_ignores_unknown_keys():
    data = _entry().to_json()
    data["unknown_field"] = "should be ignored"
    entry = DatasetIndexEntry.from_json(data)
    assert entry.dataset == "pretrain"


def test_dataset_for_source_commoncrawl():
    assert dataset_for_source("commoncrawl") == "pretrain"


def test_dataset_for_source_targeted():
    assert dataset_for_source("targeted_web") == "pretrain"


def test_dataset_for_source_parallel():
    assert dataset_for_source("parallel_web") == "parallel"


def test_dataset_for_source_instructions():
    assert dataset_for_source("instructions_rw") == "instructions"


def test_dataset_for_source_wayback():
    assert dataset_for_source("wayback") == "pretrain"


def test_dataset_for_source_cc_index():
    assert dataset_for_source("cc_index") == "pretrain"


def test_dataset_for_source_books_corpus():
    assert dataset_for_source("books_corpus") == "pretrain"


def test_dataset_for_source_unknown():
    import pytest

    with pytest.raises(ValueError, match="Unknown source"):
        dataset_for_source("unknown_source")


def test_valid_datasets_covers_all_sources():
    from apps.common.dataset_index import SOURCE_TO_DATASET

    for ds in SOURCE_TO_DATASET.values():
        assert ds in VALID_DATASETS


def test_write_and_read_index(tmp_path):
    entries = [_entry(run_id="run1"), _entry(run_id="run2")]
    path = tmp_path / "index.jsonl"
    write_index(entries, path)

    loaded = read_index(path)
    assert len(loaded) == 2
    assert loaded[0].run_id == "run1"
    assert loaded[1].run_id == "run2"


def test_write_index_is_valid_jsonl(tmp_path):
    entries = [_entry()]
    path = tmp_path / "index.jsonl"
    write_index(entries, path)

    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["dataset"] == "pretrain"


def test_read_index_empty_file(tmp_path):
    path = tmp_path / "index.jsonl"
    path.write_text("")
    assert read_index(path) == []


def test_read_index_nonexistent(tmp_path):
    path = tmp_path / "nonexistent.jsonl"
    assert read_index(path) == []
