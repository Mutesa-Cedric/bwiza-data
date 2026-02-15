"""Run CC miner pipeline over a single WET file."""

from datetime import datetime, timezone
from typing import Protocol

from apps.cc_miner.decompress import iter_text_lines
from apps.cc_miner.http_stream import stream_download
from apps.cc_miner.keep import decide_keep
from apps.cc_miner.stats import RunStats
from apps.cc_miner.wet_parser import parse_wet
from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.hashing import hash_text
from apps.common.logging import get_logger
from apps.common.schema import Document

log = get_logger(__name__)


class DocWriter(Protocol):
    """Protocol for any writer that accepts doc dicts."""

    def write(self, doc_dict: dict) -> object: ...


def run_one_wet(
    wet_url: str,
    cfg: AppConfig,
    writer: DocWriter,
    dedup: ExactDedupStore,
    stats: RunStats,
    on_shard_closed=None,
) -> None:
    """Process a single WET file through the full pipeline."""
    log.info("Processing WET: %s", wet_url)

    byte_chunks = stream_download(wet_url, cfg)
    lines = iter_text_lines(byte_chunks)

    for record in parse_wet(lines):
        stats.docs_seen += 1

        decision = decide_keep(record.text, cfg)

        if not decision.keep:
            stats.reject_reasons[decision.reason] += 1
            continue

        text_hash = hash_text(decision.normalized_text)
        if dedup.check_and_add(text_hash):
            stats.duplicates += 1
            stats.reject_reasons["reject.dedup.exact"] += 1
            continue

        doc = Document(
            id=text_hash,
            text=decision.normalized_text,
            source="commoncrawl",
            url=record.url,
            crawl=cfg.cc.crawl,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            lang=decision.lang,
            lid_model="glotlid",
            lid_score=decision.lid_score,
        )

        result = writer.write(doc.to_json())
        stats.docs_kept += 1
        stats.total_kept_chars += len(decision.normalized_text)

        # If shard writer returned metadata (rotation), notify caller
        if result is not None and on_shard_closed:
            on_shard_closed(result)

        if cfg.output.max_docs_per_run > 0 and stats.docs_kept >= cfg.output.max_docs_per_run:
            log.info("Reached max_docs_per_run=%d", cfg.output.max_docs_per_run)
            return

    stats.wet_files_processed += 1
    log.info(
        "WET done: seen=%d kept=%d dupes=%d", stats.docs_seen, stats.docs_kept, stats.duplicates
    )
