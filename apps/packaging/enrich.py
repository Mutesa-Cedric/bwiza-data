"""Document-level metadata enrichment for training readiness."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from apps.common.dataset_index import DatasetIndexEntry, read_index
from apps.common.logging import get_logger
from apps.common.url_utils import get_domain

log = get_logger(__name__)

# --- Content-type domain sets ---

NEWS_DOMAINS: set[str] = {
    "igihe.com",
    "umuseke.rw",
    "ktpress.rw",
    "newtimes.co.rw",
    "kigalitoday.com",
    "inyarwanda.com",
    "isimbi.rw",
    "intyoza.com",
    "rba.co.rw",
    "imvahonshya.co.rw",
    "umuryango.rw",
    "flash.rw",
    "taarifa.rw",
}

RELIGIOUS_DOMAINS: set[str] = {
    "bible.com",
    "jw.org",
    "diocesecyangugu.com",
    "bfrw.org",
    "eglisecatholiquerwanda.org",
    "adepr.rw",
}

ACADEMIC_DOMAINS: set[str] = {
    "ur.ac.rw",
    "ines.ac.rw",
    "reb.rw",
    "nesa.gov.rw",
}

EXTERNAL_DATASET_SOURCES: set[str] = {
    "kinnews",
    "mbazanlp_v01.1",
}

# Text fields to check in document dicts (priority order)
_TEXT_FIELDS = ("text", "rw_text", "en_text", "prompt", "response")


def classify_content_type(source: str, domain: str) -> str:
    """Classify a document's content type from its source and domain.

    Returns one of: wiki, external_dataset, government, news, religious,
    academic, other.
    """
    if source == "wikipedia":
        return "wiki"
    if source in EXTERNAL_DATASET_SOURCES:
        return "external_dataset"
    if domain.endswith(".gov.rw") or domain == "gov.rw":
        return "government"
    if domain in NEWS_DOMAINS:
        return "news"
    if domain in RELIGIOUS_DOMAINS:
        return "religious"
    # Check suffix for academic .ac.rw domains
    if domain in ACADEMIC_DOMAINS or domain.endswith(".ac.rw"):
        return "academic"
    return "other"


def compute_quality_score(lid_score: float) -> float:
    """Compute quality score from LID confidence.

    Currently a direct pass-through of lid_score (already 0-1).
    Placeholder for future composite scoring.
    """
    return max(0.0, min(1.0, lid_score))


@dataclass
class EnrichedMeta:
    """Per-document enrichment metadata (sidecar index)."""

    doc_id: str
    shard_name: str
    token_count: int
    char_count: int
    domain: str
    content_type: str
    quality_score: float

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> EnrichedMeta:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def _extract_text(doc: dict) -> str:
    """Extract primary text content from a document dict."""
    for key in _TEXT_FIELDS:
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def _resolve_shard_path(entry: DatasetIndexEntry, shard_dir: str) -> Path | None:
    """Try to find the local shard file for an index entry."""
    candidates = [
        Path(shard_dir) / entry.shard_name,
        Path(shard_dir) / entry.source / entry.run_id / entry.shard_name,
        Path(shard_dir) / entry.run_id / entry.shard_name,
    ]
    for c in candidates:
        if c.exists():
            return c
    for match in Path(shard_dir).rglob(entry.shard_name):
        return match
    return None


def _iter_shard_docs(shard_path: Path) -> list[dict]:
    """Read all docs from a zstd-compressed JSONL shard."""
    import zstandard as zstd

    dctx = zstd.ZstdDecompressor()
    with open(shard_path, "rb") as f:
        data = dctx.stream_reader(f).read()
    docs = []
    for line in data.decode("utf-8").strip().split("\n"):
        if line.strip():
            docs.append(json.loads(line))
    return docs


def enrich_shard(
    shard_path: Path,
    entry: DatasetIndexEntry,
    tokenizer: object,
    max_docs: int = 0,
) -> list[EnrichedMeta]:
    """Read a shard and compute per-document enrichment metadata.

    Args:
        shard_path: Path to the zstd-compressed JSONL shard.
        entry: Index entry for this shard (provides source, shard_name).
        tokenizer: HuggingFace tokenizer with .encode() method.
        max_docs: If >0, limit to this many documents.

    Returns:
        List of EnrichedMeta, one per document.
    """
    docs = _iter_shard_docs(shard_path)
    if max_docs > 0:
        docs = docs[:max_docs]

    results: list[EnrichedMeta] = []
    for doc in docs:
        text = _extract_text(doc)
        if not text:
            continue

        doc_id = doc.get("id", "")
        url = doc.get("url", "")
        domain = get_domain(url) if url else ""
        source = doc.get("source", entry.source)
        lid_score = doc.get("lid_score", 0.0)
        if not isinstance(lid_score, (int, float)):
            lid_score = 0.0

        token_ids = tokenizer.encode(text)  # type: ignore[union-attr]
        token_count = len(token_ids)

        results.append(
            EnrichedMeta(
                doc_id=doc_id,
                shard_name=entry.shard_name,
                token_count=token_count,
                char_count=len(text),
                domain=domain,
                content_type=classify_content_type(source, domain),
                quality_score=compute_quality_score(lid_score),
            )
        )

    return results


def enrich_index(
    index_path: str,
    shard_dir: str,
    output_path: str,
    tokenizer_name: str = "Qwen/Qwen3-8B",
) -> Path:
    """Enrich all shards referenced by an index. Write enrichment JSONL.

    Each line in the output is a JSON dict with EnrichedMeta fields.
    Skips shards that cannot be found locally.

    Returns:
        Path to the enrichment JSONL file.
    """
    from transformers import AutoTokenizer  # type: ignore[import-untyped]

    entries = read_index(index_path)
    if not entries:
        log.warning("No entries in index %s", index_path)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("")
        return out

    log.info("Loading tokenizer: %s", tokenizer_name)
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    total_docs = 0
    skipped_shards = 0

    with open(out, "w", encoding="utf-8") as f:
        for i, entry in enumerate(entries):
            shard_path = _resolve_shard_path(entry, shard_dir)
            if shard_path is None:
                skipped_shards += 1
                log.warning("Shard not found: %s", entry.shard_name)
                continue

            metas = enrich_shard(shard_path, entry, tokenizer)
            for meta in metas:
                f.write(json.dumps(meta.to_json(), ensure_ascii=False) + "\n")
                total_docs += 1

            if (i + 1) % 10 == 0:
                log.info(
                    "Progress: %d/%d shards, %d docs enriched",
                    i + 1,
                    len(entries),
                    total_docs,
                )

    log.info(
        "Enrichment complete: %d docs, %d shards skipped, written to %s",
        total_docs,
        skipped_shards,
        out,
    )
    return out


def read_enrichment_index(path: str | Path) -> dict[str, EnrichedMeta]:
    """Read enrichment JSONL into a dict keyed by doc_id."""
    result: dict[str, EnrichedMeta] = {}
    p = Path(path)
    if not p.exists():
        return result
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                meta = EnrichedMeta.from_json(json.loads(line))
                result[meta.doc_id] = meta
    return result
