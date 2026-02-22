"""End-to-end Wikipedia miner: download → extract → pipeline → shard → report."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apps.common.config_types import AppConfig
from apps.common.dedup_factory import create_dedup
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.shard_writer import ShardWriter
from apps.wiki_miner.download import download_rw_dump
from apps.wiki_miner.extract import parse_dump
from apps.wiki_miner.pipeline import WikiRunReport, process_articles

log = get_logger(__name__)


def run_wiki_miner(cfg: AppConfig) -> WikiRunReport:
    """Run the full Wikipedia mining pipeline."""
    clear_registry()
    register_quality_filters()

    run_id = datetime.now(timezone.utc).strftime("wiki_%Y%m%dT%H%M%SZ")
    source = cfg.wiki.output_source

    log.info("Wikipedia miner run=%s", run_id)

    # Download dump
    dump_path = download_rw_dump(cfg.wiki.output_dir, url=cfg.wiki.dump_url)
    log.info("Using dump: %s", dump_path)

    # Set up dedup + shard writer
    dedup = create_dedup(cfg.dedup)
    writer = ShardWriter(cfg.sharding, source=source, run_id=run_id)

    report = WikiRunReport()

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=source)

    try:
        articles = parse_dump(dump_path)
        for doc, report in process_articles(articles, cfg, dedup):
            result = writer.write(doc.to_json())
            if result is not None:
                on_shard_closed(result)
    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
    finally:
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        dedup.close()

    # Write report
    report_dir = Path(cfg.wiki.output_dir) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    log.info(
        "Wikipedia miner done: seen=%d kept=%d chars=%d keep_rate=%.2f%%",
        report.articles_seen,
        report.articles_kept,
        report.total_kept_chars,
        (report.to_dict()["keep_rate"] * 100),
    )
    log.info("Report: %s", report_path)

    return report
