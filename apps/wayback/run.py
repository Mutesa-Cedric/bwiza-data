"""End-to-end Wayback Machine mining runner (resumable, concurrent)."""

import random
from datetime import datetime, timezone

from apps.cc_miner.stats import RunStats
from apps.common.concurrency import BoundedWorkerPool
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
from apps.common.url_utils import get_domain
from apps.targeted_crawler.rate_limit import DomainRateLimiter
from apps.wayback.cdx_client import WaybackRecord, build_wayback_record_list
from apps.wayback.fetch import WaybackFetchResult, fetch_wayback_page
from apps.wayback.pipeline import process_wayback_page

log = get_logger(__name__)


def _done_key(record: WaybackRecord) -> str:
    """Unique key for a Wayback record in the done set."""
    return f"{record.original_url}:{record.timestamp}"


def _fetch_one(
    record: WaybackRecord,
    cfg: AppConfig,
    rate_limiter: DomainRateLimiter,
) -> tuple[WaybackRecord, WaybackFetchResult]:
    """Fetch a single archived page. Runs in a worker thread."""
    rate_limiter.wait_if_needed("web.archive.org")
    result = fetch_wayback_page(record, cfg.wayback)
    return record, result


def run_wayback_miner(cfg: AppConfig, resume_run_id: str = "") -> RunStats:
    """Run Wayback mining end-to-end.

    Steps:
    1. Query Wayback CDX for all configured domains
    2. Pre-dedup records by original_url (keep latest timestamp)
    3. Fetch pages concurrently (rate-limited)
    4. Extract -> LID -> quality -> dedup -> shard
    """
    clear_registry()
    register_quality_filters()

    wcfg = cfg.wayback

    # Load or create RunState
    state = None
    if resume_run_id:
        state = load_state(resume_run_id)
        if state is None:
            log.warning("No state found for %s, starting fresh", resume_run_id)

    if state is not None:
        run_id = state.run_id
        done_set = load_done_set(run_id)
        log.info("Resuming wayback run=%s, %d records already done", run_id, len(done_set))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set: set[str] = set()
        state = RunState(
            run_id=run_id,
            pipeline="wayback",
            source=wcfg.output_source,
            config_fingerprint=fingerprint_config(cfg),
        )

    state.start()
    save_state(state)

    # Query CDX API
    log.info("Querying Wayback CDX for %d domains...", len(wcfg.domains))
    records = build_wayback_record_list(wcfg.domains, wcfg)
    if not records:
        log.warning("Wayback CDX returned 0 records. Nothing to fetch.")
        state.complete()
        save_state(state)
        return RunStats()

    # Shuffle to avoid domain-alphabetical bias
    random.shuffle(records)

    # Apply max_records cap
    if wcfg.max_records > 0 and len(records) > wcfg.max_records:
        log.info("Capping records from %d to %d", len(records), wcfg.max_records)
        records = records[: wcfg.max_records]

    state.items_total = len(records)
    save_state(state)
    log.info(
        "Wayback run=%s: %d records to fetch, concurrency=%d",
        run_id,
        len(records),
        wcfg.fetch_concurrency,
    )

    # Set up components
    guardrails = GuardrailChecker(cfg.guardrails)
    dedup = create_dedup(cfg.dedup)
    stats = RunStats()
    writer = ShardWriter(cfg.sharding, source=wcfg.output_source, run_id=run_id)
    rate_limiter = DomainRateLimiter(delay_s=wcfg.fetch_rate_limit_s)

    # S3 upload setup
    s3_client = None
    s3_prefix = f"bwiza/curated/v1/{wcfg.output_source}/"
    if cfg.s3.enabled:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)

    def _upload_shard(meta):
        key = shard_key(s3_prefix, run_id, meta.filename)
        try:
            result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
            if not result.skipped and cfg.s3.verify_after_upload:
                if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                    log.error("Verification failed for %s", key)
        except Exception:
            log.exception("S3 upload failed for %s", meta.filename)

    def _sync_state_to_s3():
        if s3_client is not None:
            try:
                upload_state(s3_client, cfg.s3.bucket, state)
                done_file = f"manifests/state/{run_id}.done.txt"
                upload_done_list(s3_client, cfg.s3.bucket, run_id, done_file)
            except Exception:
                log.exception("S3 state sync failed")

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=wcfg.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            _upload_shard(meta)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    pool = BoundedWorkerPool(max_workers=wcfg.fetch_concurrency, name="wayback")
    guardrail_hit = False

    # Filter out already-done records
    pending = [r for r in records if _done_key(r) not in done_set]
    if len(pending) < len(records):
        state.items_skipped += len(records) - len(pending)
        log.info("Skipping %d already-done records", len(records) - len(pending))

    try:
        idx = 0
        while idx < len(pending) and not guardrail_hit:
            # Collect a batch
            batch_end = min(idx + pool.max_workers, len(pending))
            batch = pending[idx:batch_end]
            idx = batch_end

            # Submit fetch tasks in parallel
            for record in batch:
                pool.submit(_fetch_one, record, cfg, rate_limiter)
            fetch_results = pool.drain()

            # Process results sequentially
            for record, wayback_result in fetch_results:
                stats.docs_seen += 1
                state.items_done += 1
                state.current_item = record.original_url

                url_domain = get_domain(record.original_url)
                if url_domain:
                    stats.domain_seen[url_domain] += 1

                if not wayback_result.ok:
                    stats.reject_reasons[f"reject.wayback_fetch.{wayback_result.error}"] += 1
                    mark_done(run_id, _done_key(record))
                    continue

                # Process through quality pipeline
                doc, decision = process_wayback_page(
                    wayback_result.html_bytes,
                    record.original_url,
                    record.timestamp,
                    cfg,
                    dedup,
                )

                if doc is None:
                    stats.reject_reasons[decision.reason] += 1
                    if decision.reason == "reject.dedup.exact":
                        stats.duplicates += 1
                    mark_done(run_id, _done_key(record))
                    continue

                # Write to shard
                shard_result = writer.write(doc.to_json())
                stats.docs_kept += 1
                stats.total_kept_chars += len(doc.text)
                if url_domain:
                    stats.domain_kept[url_domain] += 1
                mark_done(run_id, _done_key(record))

                if shard_result is not None:
                    on_shard_closed(shard_result)

                # Check guardrails
                triggered, reason = guardrails.check(state)
                if triggered:
                    log.info("Guardrail triggered: %s", reason)
                    state.pause(reason)
                    guardrail_hit = True
                    break

            # Periodic progress logging
            if state.items_done % 100 < pool.max_workers:
                save_state(state)
                log.info(
                    "Progress: processed=%d kept=%d remaining=%d",
                    state.items_done,
                    stats.docs_kept,
                    len(pending) - idx,
                )

        if state.status == "running":
            state.complete()
    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
        state.pause("interrupted")
    except Exception as exc:
        state.fail(str(exc))
        raise
    finally:
        pool.shutdown(wait=True)
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        dedup.close()
        state.current_item = ""
        save_state(state)
        _sync_state_to_s3()
        stats.write_json("outputs/wayback", run_id)

    log.info(
        "Wayback mining complete: kept=%d seen=%d dupes=%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )

    return stats
