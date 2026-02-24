"""Tests for domain-aware data mixing."""

import json

import pytest

from apps.common.dataset_index import DatasetIndexEntry, write_index
from apps.packaging.enrich import EnrichedMeta
from apps.packaging.mixing import (
    MixConfig,
    build_mixed_splits,
    classify_shard_content_type,
)


def _entry(
    s3_key: str,
    source: str = "commoncrawl",
    token_estimate: int = 1000,
    records: int = 10,
    shard_name: str = "",
) -> DatasetIndexEntry:
    if not shard_name:
        shard_name = s3_key.split("/")[-1] + ".jsonl.zst"
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id="run1",
        source=source,
        shard_name=shard_name,
        s3_bucket="test-bucket",
        s3_key=s3_key,
        bytes=5000,
        records=records,
        token_estimate=token_estimate,
        checksum_sha256="a" * 64,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _make_index(tmp_path, entries):
    path = tmp_path / "index.jsonl"
    write_index(entries, path)
    return str(path)


# --- MixConfig ---


def test_mix_config_validation_passes():
    cfg = MixConfig()
    cfg.validate()  # should not raise


def test_mix_config_validation_bad_sum():
    cfg = MixConfig(ratios={"news": 0.5, "government": 0.6})
    with pytest.raises(ValueError, match="sum to"):
        cfg.validate()


def test_mix_config_validation_negative():
    cfg = MixConfig(ratios={"news": -0.1, "other": 1.1})
    with pytest.raises(ValueError, match="Negative"):
        cfg.validate()


def test_mix_config_from_json(tmp_path):
    data = {"ratios": {"news": 0.5, "other": 0.5}, "seed": "test-seed"}
    path = tmp_path / "mix.json"
    with open(path, "w") as f:
        json.dump(data, f)

    cfg = MixConfig.from_json(path)
    assert cfg.ratios["news"] == 0.5
    assert cfg.seed == "test-seed"


# --- classify_shard_content_type ---


def test_classify_shard_wikipedia():
    entry = _entry("prefix/wiki", source="wikipedia")
    assert classify_shard_content_type(entry) == "wiki"


def test_classify_shard_kinnews():
    entry = _entry("prefix/kinnews", source="kinnews")
    assert classify_shard_content_type(entry) == "external_dataset"


def test_classify_shard_commoncrawl_fallback():
    entry = _entry("prefix/cc", source="commoncrawl")
    # No enrichment, commoncrawl with empty domain -> "other"
    assert classify_shard_content_type(entry) == "other"


def test_classify_shard_with_enrichment():
    entry = _entry("prefix/shard1", source="targeted_web", shard_name="shard1.jsonl.zst")
    enrichment = {
        "doc-1": EnrichedMeta("doc-1", "shard1.jsonl.zst", 100, 250, "igihe.com", "news", 0.9),
        "doc-2": EnrichedMeta("doc-2", "shard1.jsonl.zst", 80, 200, "igihe.com", "news", 0.9),
        "doc-3": EnrichedMeta("doc-3", "other.jsonl.zst", 90, 220, "gov.rw", "government", 0.9),
    }
    assert classify_shard_content_type(entry, enrichment) == "news"


# --- build_mixed_splits ---


def test_build_mixed_splits_empty_index(tmp_path):
    path = tmp_path / "index.jsonl"
    path.write_text("")
    splits = build_mixed_splits(str(path))
    assert splits == {"train": [], "val": [], "test": []}


def test_build_mixed_splits_deterministic(tmp_path):
    entries = [
        _entry(f"prefix/shard_{i:04d}", source="wikipedia", token_estimate=100) for i in range(50)
    ]
    index_path = _make_index(tmp_path, entries)

    splits1 = build_mixed_splits(index_path)
    splits2 = build_mixed_splits(index_path)
    assert splits1 == splits2


def test_build_mixed_splits_all_assigned(tmp_path):
    """All shards should appear in some split."""
    entries = [
        _entry(f"prefix/wiki_{i}", source="wikipedia", token_estimate=100) for i in range(20)
    ] + [_entry(f"prefix/news_{i}", source="targeted_web", token_estimate=100) for i in range(20)]
    index_path = _make_index(tmp_path, entries)

    # Use simple ratios that include relevant types
    config = MixConfig(ratios={"wiki": 0.5, "other": 0.5})
    splits = build_mixed_splits(index_path, config=config)

    total = len(splits["train"]) + len(splits["val"]) + len(splits["test"])
    assert total == 40  # all shards assigned


def test_build_mixed_splits_under_representation(tmp_path):
    """If a content type has fewer tokens than target, take all of it."""
    # Wiki has 5 shards (500 tokens), news has 95 shards (9500 tokens)
    entries = [
        _entry(f"prefix/wiki_{i}", source="wikipedia", token_estimate=100) for i in range(5)
    ] + [_entry(f"prefix/news_{i}", source="commoncrawl", token_estimate=100) for i in range(95)]
    index_path = _make_index(tmp_path, entries)

    # wiki target = 50% = 5000 tokens, but only 500 available
    config = MixConfig(ratios={"wiki": 0.50, "other": 0.50})
    splits = build_mixed_splits(index_path, config=config)

    # All 5 wiki shards should be included
    all_keys = splits["train"] + splits["val"] + splits["test"]
    wiki_keys = [k for k in all_keys if "wiki" in k]
    assert len(wiki_keys) == 5


def test_build_mixed_splits_splits_are_sorted(tmp_path):
    entries = [
        _entry(f"prefix/shard_{i:04d}", source="wikipedia", token_estimate=100) for i in range(20)
    ]
    index_path = _make_index(tmp_path, entries)

    splits = build_mixed_splits(index_path)
    for keys in splits.values():
        assert keys == sorted(keys)
