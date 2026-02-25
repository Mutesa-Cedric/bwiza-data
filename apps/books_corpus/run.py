"""End-to-end books corpus ingestion runner (resumable, concurrent)."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.books_corpus.pipeline import process_book_doc
from apps.books_corpus.seeds import BookSeed, domain_for_seed, load_book_seeds
from apps.cc_miner.stats import RunStats
from apps.common.concurrency import BoundedWorkerPool
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig, TargetedConfig
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
from apps.targeted_crawler.extract import extract_main_text
from apps.targeted_crawler.fetch import fetch_url
from apps.targeted_crawler.pdf import extract_pdf_text
from apps.targeted_crawler.rate_limit import DomainRateLimiter

log = get_logger(__name__)


def _fetch_one(seed: BookSeed, fetch_cfg: TargetedConfig, rate_limiter: DomainRateLimiter):
    domain = domain_for_seed(seed)
    if domain:
        rate_limiter.wait_if_needed(domain)
    result = fetch_url(seed.url, fetch_cfg)
    return seed, result


def run_books_corpus(cfg: AppConfig, resume_run_id: str = "") -> RunStats:
    """Run the books corpus pipeline end-to-end."""
    clear_registry()
    register_quality_filters()

    bcfg = cfg.books

    # Apply book-specific overrides to shared config
    cfg.lid.min_confidence = bcfg.min_lid_confidence
    if bcfg.max_chars:
        cfg.filters.max_chars = bcfg.max_chars
    if bcfg.max_word_ngram_rep_2:
        cfg.filters.max_word_ngram_rep_2 = bcfg.max_word_ngram_rep_2
    if bcfg.max_word_ngram_rep_3:
        cfg.filters.max_word_ngram_rep_3 = bcfg.max_word_ngram_rep_3
    if bcfg.max_word_ngram_rep_4:
        cfg.filters.max_word_ngram_rep_4 = bcfg.max_word_ngram_rep_4

    seeds = load_book_seeds(bcfg.seeds_file)
    if not seeds:
        log.warning("No book seeds found in %s", bcfg.seeds_file)
        return RunStats()

    state = None
    if resume_run_id:
        state = load_state(resume_run_id)
        if state is None:
            log.warning("No state found for %s, starting fresh", resume_run_id)

    if state is not None:
        run_id = state.run_id
        done_set = load_done_set(run_id)
        log.info("Resuming books run=%s, %d URLs already done", run_id, len(done_set))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set = set()
        state = RunState(
            run_id=run_id,
            pipeline="books_corpus",
            source=bcfg.output_source,
            config_fingerprint=fingerprint_config(cfg),
        )

    state.items_total = len(seeds)
    state.start()
    save_state(state)

    fetch_cfg = TargetedConfig(
        request_timeout_s=bcfg.request_timeout_s,
        max_retries=bcfg.max_retries,
        retry_backoff_s=bcfg.retry_backoff_s,
        max_response_bytes=bcfg.max_response_bytes,
        user_agent=bcfg.user_agent,
        allowed_content_types=bcfg.allowed_content_types,
    )

    guardrails = GuardrailChecker(cfg.guardrails)
    dedup = create_dedup(cfg.dedup)
    stats = RunStats()
    writer = ShardWriter(cfg.sharding, source=bcfg.output_source, run_id=run_id)
    rate_limiter = DomainRateLimiter(delay_s=bcfg.domain_delay_s)

    s3_client = None
    if cfg.s3.enabled:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)

    def _upload_shard(meta):
        key = shard_key(bcfg.s3_prefix, run_id, meta.filename)
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
        append_manifest_entry(run_id, meta, source=bcfg.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            _upload_shard(meta)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    pending = [seed for seed in seeds if seed.url not in done_set]
    if len(pending) < len(seeds):
        skipped = len(seeds) - len(pending)
        state.items_skipped += skipped
        log.info("Skipping %d already-done book URLs", skipped)

    pool = BoundedWorkerPool(max_workers=bcfg.concurrency, name="books")
    guardrail_hit = False

    try:
        idx = 0
        while idx < len(pending) and not guardrail_hit:
            batch_end = min(idx + pool.max_workers, len(pending))
            batch = pending[idx:batch_end]
            idx = batch_end

            for seed in batch:
                pool.submit(_fetch_one, seed, fetch_cfg, rate_limiter)
            fetch_results = pool.drain()

            for seed, result in fetch_results:
                stats.docs_seen += 1
                state.items_done += 1
                state.current_item = seed.url

                seen_domain = get_domain(result.final_url or seed.url)
                if seen_domain:
                    stats.domain_seen[seen_domain] += 1

                if not result.ok:
                    stats.reject_reasons[f"reject.fetch.{result.error}"] += 1
                    mark_done(run_id, seed.url)
                    continue

                is_pdf = "application/pdf" in (result.content_type or "")
                if is_pdf:
                    extracted = extract_pdf_text(
                        result.content,
                        url=result.final_url or seed.url,
                        max_pages=bcfg.pdf_max_pages,
                        min_text_ratio=bcfg.pdf_min_text_ratio,
                    )
                else:
                    extracted = extract_main_text(
                        result.content,
                        url=result.final_url or seed.url,
                        extraction_mode=bcfg.extract_mode,
                    )

                if extracted is None:
                    reason = (
                        "reject.pdf_extraction_failed" if is_pdf else "reject.extraction_failed"
                    )
                    stats.reject_reasons[reason] += 1
                    mark_done(run_id, seed.url)
                    continue

                doc, decision = process_book_doc(
                    extracted,
                    result.final_url or seed.url,
                    seed,
                    cfg,
                    dedup,
                )

                if doc is None:
                    stats.reject_reasons[decision.reason] += 1
                    if decision.reason.startswith("reject.dedup"):
                        stats.duplicates += 1
                    mark_done(run_id, seed.url)
                    continue

                shard_result = writer.write(doc.to_json())
                stats.docs_kept += 1
                stats.total_kept_chars += len(doc.text)

                kept_domain = get_domain(doc.url or seed.url)
                if kept_domain:
                    stats.domain_kept[kept_domain] += 1

                mark_done(run_id, seed.url)

                if shard_result is not None:
                    on_shard_closed(shard_result)

                triggered, reason = guardrails.check(state)
                if triggered:
                    log.info("Guardrail triggered: %s", reason)
                    state.pause(reason)
                    guardrail_hit = True
                    break

            if state.items_done % 50 < pool.max_workers:
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
        stats.write_json("outputs/books", run_id)

    log.info(
        "Books corpus complete: kept=%d seen=%d dupes=%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )
    return stats
