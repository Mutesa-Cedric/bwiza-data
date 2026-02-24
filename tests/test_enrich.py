"""Tests for document-level metadata enrichment."""

import json
from pathlib import Path

import zstandard as zstd

from apps.common.dataset_index import DatasetIndexEntry
from apps.packaging.enrich import (
    EnrichedMeta,
    classify_content_type,
    compute_quality_score,
    enrich_shard,
    read_enrichment_index,
)

# --- classify_content_type ---


def test_classify_wikipedia():
    assert classify_content_type("wikipedia", "") == "wiki"


def test_classify_wikipedia_ignores_domain():
    assert classify_content_type("wikipedia", "igihe.com") == "wiki"


def test_classify_external_dataset_kinnews():
    assert classify_content_type("kinnews", "") == "external_dataset"


def test_classify_external_dataset_mbazanlp():
    assert classify_content_type("mbazanlp_v01.1", "") == "external_dataset"


def test_classify_government_gov_rw():
    assert classify_content_type("targeted_web", "mineduc.gov.rw") == "government"


def test_classify_government_bare_gov_rw():
    assert classify_content_type("targeted_web", "gov.rw") == "government"


def test_classify_news_igihe():
    assert classify_content_type("targeted_web", "igihe.com") == "news"


def test_classify_news_umuseke():
    assert classify_content_type("targeted_web", "umuseke.rw") == "news"


def test_classify_religious_bible():
    assert classify_content_type("targeted_web", "bible.com") == "religious"


def test_classify_religious_jw():
    assert classify_content_type("targeted_web", "jw.org") == "religious"


def test_classify_academic_ur():
    assert classify_content_type("targeted_web", "ur.ac.rw") == "academic"


def test_classify_academic_suffix():
    assert classify_content_type("targeted_web", "newuniversity.ac.rw") == "academic"


def test_classify_other_unknown_domain():
    assert classify_content_type("targeted_web", "example.com") == "other"


def test_classify_other_empty_domain():
    assert classify_content_type("commoncrawl", "") == "other"


# --- compute_quality_score ---


def test_quality_score_normal():
    assert compute_quality_score(0.95) == 0.95


def test_quality_score_clamp_high():
    assert compute_quality_score(1.5) == 1.0


def test_quality_score_clamp_low():
    assert compute_quality_score(-0.1) == 0.0


def test_quality_score_zero():
    assert compute_quality_score(0.0) == 0.0


# --- EnrichedMeta roundtrip ---


def test_enriched_meta_roundtrip():
    meta = EnrichedMeta(
        doc_id="doc-001",
        shard_name="shard_001.jsonl.zst",
        token_count=500,
        char_count=1200,
        domain="igihe.com",
        content_type="news",
        quality_score=0.95,
    )
    data = meta.to_json()
    restored = EnrichedMeta.from_json(data)
    assert restored.doc_id == meta.doc_id
    assert restored.token_count == meta.token_count
    assert restored.content_type == meta.content_type


# --- enrich_shard with mock tokenizer ---


class _MockTokenizer:
    """Mock tokenizer: returns one token per word."""

    def encode(self, text: str) -> list[int]:
        return list(range(len(text.split())))


def _make_shard(tmp_dir: Path, docs: list[dict]) -> Path:
    """Create a zstd-compressed JSONL shard."""
    shard_path = tmp_dir / "test_shard.jsonl.zst"
    cctx = zstd.ZstdCompressor()
    lines = [json.dumps(d, ensure_ascii=False) + "\n" for d in docs]
    raw = "".join(lines).encode("utf-8")
    with open(shard_path, "wb") as f:
        f.write(cctx.compress(raw))
    return shard_path


def _make_entry(shard_name: str = "test_shard.jsonl.zst") -> DatasetIndexEntry:
    return DatasetIndexEntry(
        dataset="pretrain",
        version="v1",
        run_id="run1",
        source="targeted_web",
        shard_name=shard_name,
        s3_bucket="test",
        s3_key=f"prefix/{shard_name}",
        bytes=1000,
        records=2,
        token_estimate=100,
        checksum_sha256="a" * 64,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_enrich_shard_basic(tmp_path):
    docs = [
        {
            "id": "doc-1",
            "text": "Umugore arimo gusoma igitabo cyiza cyane",
            "source": "targeted_web",
            "url": "https://igihe.com/article1",
            "lid_score": 0.95,
        },
        {
            "id": "doc-2",
            "text": "Guverinoma yashyizeho amategeko mashya",
            "source": "targeted_web",
            "url": "https://mineduc.gov.rw/news",
            "lid_score": 0.88,
        },
    ]
    shard_path = _make_shard(tmp_path, docs)
    entry = _make_entry()
    tokenizer = _MockTokenizer()

    results = enrich_shard(shard_path, entry, tokenizer)

    assert len(results) == 2

    # First doc: igihe.com → news
    assert results[0].doc_id == "doc-1"
    assert results[0].domain == "igihe.com"
    assert results[0].content_type == "news"
    assert results[0].token_count == 6  # 6 words
    assert results[0].char_count == len(docs[0]["text"])
    assert results[0].quality_score == 0.95

    # Second doc: gov.rw → government
    assert results[1].doc_id == "doc-2"
    assert results[1].content_type == "government"
    assert results[1].quality_score == 0.88


def test_enrich_shard_skips_empty_text(tmp_path):
    docs = [
        {"id": "doc-1", "text": "", "source": "targeted_web", "url": "https://x.com"},
        {
            "id": "doc-2",
            "text": "Valid text here",
            "source": "targeted_web",
            "url": "https://x.com",
            "lid_score": 0.9,
        },
    ]
    shard_path = _make_shard(tmp_path, docs)
    entry = _make_entry()

    results = enrich_shard(shard_path, entry, _MockTokenizer())
    assert len(results) == 1
    assert results[0].doc_id == "doc-2"


def test_enrich_shard_max_docs(tmp_path):
    docs = [
        {
            "id": f"doc-{i}",
            "text": f"Word{i} text",
            "source": "targeted_web",
            "url": "https://x.com",
            "lid_score": 0.9,
        }
        for i in range(10)
    ]
    shard_path = _make_shard(tmp_path, docs)
    entry = _make_entry()

    results = enrich_shard(shard_path, entry, _MockTokenizer(), max_docs=3)
    assert len(results) == 3


# --- read_enrichment_index ---


def test_read_enrichment_index_roundtrip(tmp_path):
    metas = [
        EnrichedMeta("doc-1", "shard1", 100, 250, "igihe.com", "news", 0.95),
        EnrichedMeta("doc-2", "shard1", 80, 200, "gov.rw", "government", 0.88),
    ]
    path = tmp_path / "enrichment.jsonl"
    with open(path, "w") as f:
        for m in metas:
            f.write(json.dumps(m.to_json()) + "\n")

    result = read_enrichment_index(path)
    assert len(result) == 2
    assert result["doc-1"].content_type == "news"
    assert result["doc-2"].token_count == 80


def test_read_enrichment_index_nonexistent(tmp_path):
    result = read_enrichment_index(tmp_path / "missing.jsonl")
    assert result == {}
