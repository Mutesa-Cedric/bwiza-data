"""Tests for deterministic split generator."""

from apps.common.dataset_index import DatasetIndexEntry, write_index
from apps.packaging.splits import build_splits, write_splits


def _entry(s3_key):
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id="run1",
        source="commoncrawl",
        shard_name=f"{s3_key}.jsonl.zst",
        s3_bucket="test-bucket",
        s3_key=s3_key,
        bytes=1000,
        records=10,
        token_estimate=250,
        checksum_sha256="abc" + "0" * 61,
        created_at="2026-02-21T00:00:00+00:00",
    )


def _make_index(tmp_path, n_entries=10):
    entries = [_entry(f"prefix/shard_{i:04d}") for i in range(n_entries)]
    path = tmp_path / "index.jsonl"
    write_index(entries, path)
    return str(path)


def test_determinism(tmp_path):
    index_path = _make_index(tmp_path, 100)

    splits1 = build_splits(index_path, seed="test-seed")
    splits2 = build_splits(index_path, seed="test-seed")

    assert splits1 == splits2


def test_different_seeds_different_splits(tmp_path):
    index_path = _make_index(tmp_path, 100)

    splits1 = build_splits(index_path, seed="seed-a")
    splits2 = build_splits(index_path, seed="seed-b")

    # With 100 entries, at least one should differ
    assert splits1 != splits2


def test_all_entries_assigned(tmp_path):
    index_path = _make_index(tmp_path, 50)

    splits = build_splits(index_path, seed="test-seed")
    total = len(splits["train"]) + len(splits["val"]) + len(splits["test"])
    assert total == 50


def test_approximate_ratios_large_set(tmp_path):
    # With 10000 entries, ratios should be approximately correct
    entries = [_entry(f"prefix/shard_{i:06d}") for i in range(10000)]
    path = tmp_path / "index.jsonl"
    write_index(entries, path)

    splits = build_splits(str(path), seed="ratio-test")

    train_ratio = len(splits["train"]) / 10000
    val_ratio = len(splits["val"]) / 10000
    test_ratio = len(splits["test"]) / 10000

    # Allow 2% tolerance
    assert 0.96 <= train_ratio <= 1.0
    assert 0.0 <= val_ratio <= 0.03
    assert 0.0 <= test_ratio <= 0.03


def test_splits_are_sorted(tmp_path):
    index_path = _make_index(tmp_path, 50)

    splits = build_splits(index_path, seed="sort-test")
    for keys in splits.values():
        assert keys == sorted(keys)


def test_write_splits(tmp_path):
    splits = {"train": ["k1", "k2"], "val": ["k3"], "test": ["k4"]}
    out = write_splits(splits, tmp_path / "splits")

    assert (out / "train.txt").exists()
    assert (out / "val.txt").exists()
    assert (out / "test.txt").exists()

    train_keys = (out / "train.txt").read_text().strip().split("\n")
    assert train_keys == ["k1", "k2"]


def test_empty_index(tmp_path):
    path = tmp_path / "index.jsonl"
    path.write_text("")

    splits = build_splits(str(path))
    assert splits == {"train": [], "val": [], "test": []}
