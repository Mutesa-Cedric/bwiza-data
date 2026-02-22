"""Global dedup pass across all sources at packaging time."""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import zstandard as zstd

from apps.common.dataset_index import DatasetIndexEntry, read_index, write_index
from apps.common.dedup_store import DedupStore
from apps.common.hashing import hash_text
from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class DedupReport:
    """Report from a global dedup pass."""

    total_docs: int = 0
    unique_docs: int = 0
    exact_dupes: int = 0
    fuzzy_dupes: int = 0
    docs_by_source: Counter = field(default_factory=Counter)
    dupes_by_source: Counter = field(default_factory=Counter)
    shards_processed: int = 0
    shards_with_dupes: int = 0

    @property
    def dedup_ratio(self) -> float:
        if self.total_docs == 0:
            return 0.0
        return (self.exact_dupes + self.fuzzy_dupes) / self.total_docs

    def to_dict(self) -> dict:
        return {
            "total_docs": self.total_docs,
            "unique_docs": self.unique_docs,
            "exact_dupes": self.exact_dupes,
            "fuzzy_dupes": self.fuzzy_dupes,
            "dedup_ratio": round(self.dedup_ratio, 4),
            "docs_by_source": dict(self.docs_by_source),
            "dupes_by_source": dict(self.dupes_by_source),
            "shards_processed": self.shards_processed,
            "shards_with_dupes": self.shards_with_dupes,
        }


def _iter_shard_docs(shard_path: Path) -> list[dict]:
    """Read all docs from a zstd-compressed JSONL shard."""
    dctx = zstd.ZstdDecompressor()
    with open(shard_path, "rb") as f:
        data = dctx.stream_reader(f).read()
    docs = []
    for line in data.decode("utf-8").strip().split("\n"):
        if line.strip():
            docs.append(json.loads(line))
    return docs


def _resolve_shard_path(entry: DatasetIndexEntry, shard_dir: str) -> Path | None:
    """Try to find the local shard file for an index entry."""
    # Try direct shard_name match under shard_dir
    candidates = [
        Path(shard_dir) / entry.shard_name,
        Path(shard_dir) / entry.source / entry.run_id / entry.shard_name,
    ]
    for c in candidates:
        if c.exists():
            return c
    # Glob for partial match
    for match in Path(shard_dir).rglob(entry.shard_name):
        return match
    return None


def run_dedup_pass(
    index_path: str,
    shard_dir: str,
    store: DedupStore,
    output_dir: str = "outputs/packaging",
) -> DedupReport:
    """Run global dedup pass across all shards in an index.

    Reads each shard, checks every doc against the dedup store.
    Produces a filtered index (excluding shards where all docs are dupes)
    and a dedup report.
    """
    entries = read_index(index_path)
    if not entries:
        log.warning("No entries in index %s", index_path)
        return DedupReport()

    report = DedupReport()
    kept_entries: list[DatasetIndexEntry] = []

    for entry in entries:
        shard_path = _resolve_shard_path(entry, shard_dir)
        if shard_path is None:
            log.warning("Shard not found locally: %s", entry.shard_name)
            kept_entries.append(entry)  # Keep entry if we can't check
            continue

        docs = _iter_shard_docs(shard_path)
        shard_dupes = 0

        for doc in docs:
            report.total_docs += 1
            report.docs_by_source[entry.source] += 1

            # Get text for dedup
            text = doc.get("text", "")
            doc_hash = hash_text(text)
            doc_id = doc.get("id", doc_hash)

            is_dup, reason = store.is_duplicate(doc_hash, text, doc_id, entry.source, entry.run_id)
            if is_dup:
                shard_dupes += 1
                report.dupes_by_source[entry.source] += 1
                if "fuzzy" in reason:
                    report.fuzzy_dupes += 1
                else:
                    report.exact_dupes += 1
            else:
                report.unique_docs += 1

        report.shards_processed += 1
        if shard_dupes > 0:
            report.shards_with_dupes += 1

        # Keep the entry in the index (dedup is informational at this stage)
        kept_entries.append(entry)
        log.info(
            "Shard %s: %d docs, %d dupes",
            entry.shard_name,
            len(docs),
            shard_dupes,
        )

    # Write filtered index
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filtered_index_path = out_dir / "index_deduped.jsonl"
    write_index(kept_entries, filtered_index_path)

    # Write report
    report_path = out_dir / "dedup_report.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)
    log.info("Dedup report written to %s", report_path)

    log.info(
        "Dedup pass complete: %d/%d docs unique (%.1f%% dupes)",
        report.unique_docs,
        report.total_docs,
        report.dedup_ratio * 100,
    )

    return report
