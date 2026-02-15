"""Run CC miner pipeline over multiple WET files."""

from datetime import datetime, timezone

from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import get_logger
from apps.cc_miner.run_one import run_one_wet
from apps.cc_miner.stats import RunStats
from apps.cc_miner.wet_paths import get_wet_urls
from apps.cc_miner.writer import LocalWriter

log = get_logger(__name__)


def run_cc_miner(cfg: AppConfig) -> RunStats:
    """Run the CC miner across all configured WET files."""
    clear_registry()
    register_quality_filters()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    wet_urls = get_wet_urls(cfg)

    if not wet_urls:
        log.warning("No WET URLs found. Nothing to process.")
        return RunStats()

    log.info("Starting CC miner run=%s with %d WET files", run_id, len(wet_urls))

    dedup = ExactDedupStore()
    stats = RunStats()
    writer = LocalWriter(cfg, run_id)

    try:
        for i, url in enumerate(wet_urls, 1):
            log.info("WET file %d/%d: %s", i, len(wet_urls), url)
            try:
                run_one_wet(url, cfg, writer, dedup, stats)
            except Exception:
                log.exception("Failed to process WET: %s", url)
                continue

            if cfg.output.max_docs_per_run > 0 and stats.docs_kept >= cfg.output.max_docs_per_run:
                log.info("Global doc limit reached, stopping.")
                break
    except KeyboardInterrupt:
        log.warning("Interrupted by user. Flushing output.")
    finally:
        writer.close()
        stats.write_json(cfg.output.local_dir, run_id)

    log.info("Run complete: kept=%d seen=%d dupes=%d ratio=%.4f tokens~%d",
             stats.docs_kept, stats.docs_seen, stats.duplicates,
             stats.keep_ratio, stats.token_estimate)

    return stats
