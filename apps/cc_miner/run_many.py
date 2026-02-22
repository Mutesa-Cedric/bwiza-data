"""Run CC miner pipeline over multiple WET files (resumable)."""

from datetime import datetime, timezone

from apps.cc_miner.run_one import run_one_wet
from apps.cc_miner.stats import RunStats
from apps.cc_miner.wet_paths import get_wet_urls
from apps.cc_miner.writer import LocalWriter
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig
from apps.common.dedup_factory import create_dedup
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.guardrails import GuardrailChecker
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, load_state, mark_done, save_state
from apps.common.run_state_sync import upload_done_list, upload_state
from apps.common.s3_paths import shard_key
from apps.common.s3_upload import upload_file, verify_upload
from apps.common.shard_writer import ShardWriter

log = get_logger(__name__)


def run_cc_miner(cfg: AppConfig, resume_run_id: str = "") -> RunStats:
    """Run the CC miner across all configured WET files.

    If resume_run_id is provided, resumes that run (skipping done WETs).
    Otherwise creates a new run.
    """
    clear_registry()
    register_quality_filters()

    wet_urls = get_wet_urls(cfg)
    if not wet_urls:
        log.warning("No WET URLs found. Nothing to process.")
        return RunStats()

    # Load or create RunState
    state = None
    if resume_run_id:
        state = load_state(resume_run_id)
        if state is None:
            log.warning("No state found for %s, starting fresh", resume_run_id)

    if state is not None:
        run_id = state.run_id
        done_set = load_done_set(run_id)
        log.info(
            "Resuming run=%s, %d WETs already done",
            run_id,
            len(done_set),
        )
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set = set()
        state = RunState(
            run_id=run_id,
            pipeline="cc_miner",
            source="commoncrawl",
            config_fingerprint=fingerprint_config(cfg),
            items_total=len(wet_urls),
        )

    state.start()
    save_state(state)

    log.info("CC miner run=%s with %d WET files", run_id, len(wet_urls))

    guardrails = GuardrailChecker(cfg.guardrails)
    dedup = create_dedup(cfg.dedup)
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

    def _sync_state_to_s3():
        if s3_client is not None:
            try:
                upload_state(s3_client, cfg.s3.bucket, state)
                done_file = f"manifests/state/{run_id}.done.txt"
                upload_done_list(s3_client, cfg.s3.bucket, run_id, done_file)
            except Exception:
                log.exception("S3 state sync failed")

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source="commoncrawl")
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            _upload_shard(meta)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    try:
        for i, url in enumerate(wet_urls, 1):
            if url in done_set:
                log.info("WET %d/%d: SKIP (already done) %s", i, len(wet_urls), url)
                state.items_skipped += 1
                continue

            state.current_item = url
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
                mark_done(run_id, url)
                state.items_done += 1
                save_state(state)
            except Exception:
                log.exception("Failed to process WET: %s", url)
                state.items_failed += 1
                save_state(state)
                continue

            # Check guardrails
            triggered, reason = guardrails.check(state)
            if triggered:
                log.info("Guardrail triggered: %s", reason)
                state.pause(reason)
                break

            if cfg.output.max_docs_per_run > 0 and stats.docs_kept >= cfg.output.max_docs_per_run:
                log.info("Global doc limit reached, stopping.")
                break

        if state.status == "running":
            state.complete()
    except KeyboardInterrupt:
        log.warning("Interrupted by user. Flushing output.")
        state.pause("interrupted")
    except Exception as exc:
        state.fail(str(exc))
        raise
    finally:
        final_meta = writer.close()
        if use_sharding and final_meta is not None:
            on_shard_closed(final_meta)
        dedup.close()
        state.current_item = ""
        save_state(state)
        _sync_state_to_s3()
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
