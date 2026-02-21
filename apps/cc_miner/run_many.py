"""Run CC miner pipeline over multiple WET files."""

from datetime import datetime, timezone

from apps.cc_miner.run_one import run_one_wet
from apps.cc_miner.stats import RunStats
from apps.cc_miner.wet_paths import get_wet_urls
from apps.cc_miner.writer import LocalWriter
from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.s3_paths import shard_key
from apps.common.s3_upload import upload_file, verify_upload
from apps.common.shard_writer import ShardWriter

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

    # Use ShardWriter when sharding is enabled, else fallback to LocalWriter
    use_sharding = cfg.sharding.enabled
    if use_sharding:
        writer = ShardWriter(cfg.sharding, source="commoncrawl", run_id=run_id)
    else:
        writer = LocalWriter(cfg, run_id)

    # Set up S3 client for continuous upload
    s3_client = None
    if cfg.s3.enabled and use_sharding:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)
        log.info("S3 upload enabled: bucket=%s", cfg.s3.bucket)

    def _upload_shard(meta):
        """Upload a closed shard to S3 immediately."""
        key = shard_key(cfg.s3.prefix, run_id, meta.filename)
        try:
            result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
            if not result.skipped and cfg.s3.verify_after_upload:
                if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                    log.error("Verification failed for %s, keeping local copy", key)
        except Exception:
            log.exception("S3 upload failed for %s, keeping local copy", meta.filename)

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source="commoncrawl")
        if s3_client is not None:
            _upload_shard(meta)

    try:
        for i, url in enumerate(wet_urls, 1):
            log.info("WET file %d/%d: %s", i, len(wet_urls), url)
            try:
                run_one_wet(
                    url,
                    cfg,
                    writer,
                    dedup,
                    stats,
                    on_shard_closed=on_shard_closed if use_sharding else None,
                )
            except Exception:
                log.exception("Failed to process WET: %s", url)
                continue

            if cfg.output.max_docs_per_run > 0 and stats.docs_kept >= cfg.output.max_docs_per_run:
                log.info("Global doc limit reached, stopping.")
                break
    except KeyboardInterrupt:
        log.warning("Interrupted by user. Flushing output.")
    finally:
        final_meta = writer.close()
        if use_sharding and final_meta is not None:
            on_shard_closed(final_meta)
        stats.write_json(cfg.output.local_dir, run_id)

    log.info(
        "Run complete: kept=%d seen=%d dupes=%d ratio=%.4f tokens~%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
        stats.keep_ratio,
        stats.token_estimate,
    )

    return stats
