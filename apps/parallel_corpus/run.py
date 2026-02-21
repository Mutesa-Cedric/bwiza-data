"""End-to-end parallel corpus runner (resumable)."""

from datetime import datetime, timezone
from urllib.parse import urlparse

from apps.cc_miner.stats import RunStats
from apps.common.config_fingerprint import fingerprint_config
from apps.common.config_types import AppConfig, TargetedConfig
from apps.common.guardrails import GuardrailChecker
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.run_state import RunState
from apps.common.run_state_store import load_done_set, load_state, mark_done, save_state
from apps.common.run_state_sync import upload_done_list, upload_state
from apps.common.s3_paths import shard_key
from apps.common.s3_upload import upload_file, verify_upload
from apps.common.shard_writer import ShardWriter
from apps.parallel_corpus.dedup import PairDedupStore
from apps.parallel_corpus.find_pairs import find_bilingual_pairs
from apps.parallel_corpus.pipeline import process_candidate_pair
from apps.targeted_crawler.fetch import fetch_url
from apps.targeted_crawler.frontier import CrawlFrontier
from apps.targeted_crawler.rate_limit import DomainRateLimiter
from apps.targeted_crawler.robots import RobotsChecker
from apps.targeted_crawler.seeds import (
    canonical_domain,
    domain_set_from_seeds,
    load_seeds,
)

log = get_logger(__name__)

S3_PREFIX_PARALLEL = "bwiza/supervision/v1/parallel/"


def run_parallel_corpus(cfg: AppConfig, resume_run_id: str = "") -> RunStats:
    """Run the parallel corpus builder end-to-end.

    If resume_run_id is provided, resumes that run (skipping done URLs).
    """
    pcfg = cfg.parallel

    # Load seeds
    seeds = load_seeds(pcfg.seeds_file)
    if not seeds:
        log.warning("No seeds found in %s", pcfg.seeds_file)
        return RunStats()

    allowed_domains = domain_set_from_seeds(seeds)

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
            "Resuming parallel run=%s, %d URLs already done",
            run_id,
            len(done_set),
        )
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set = set()
        state = RunState(
            run_id=run_id,
            pipeline="parallel",
            source="parallel_web",
            config_fingerprint=fingerprint_config(cfg),
        )

    state.start()
    save_state(state)

    log.info(
        "Starting parallel corpus run=%s with %d seed domains",
        run_id,
        len(seeds),
    )

    # Build a TargetedConfig-compatible object for the fetcher
    fetch_cfg = TargetedConfig(
        request_timeout_s=pcfg.request_timeout_s,
        max_retries=pcfg.max_retries,
        retry_backoff_s=pcfg.retry_backoff_s,
        max_response_bytes=pcfg.max_response_bytes,
        user_agent="bwiza-data/0.1",
    )

    frontier = CrawlFrontier(
        allowed_domains=allowed_domains,
        max_pages=pcfg.max_pages,
        per_domain_max_pages=pcfg.per_domain_max_pages,
    )
    frontier.add_seeds([url for url, _ in seeds])

    # Pre-populate frontier's seen set with done URLs
    for done_url in done_set:
        frontier.mark_fetched(done_url)

    guardrails = GuardrailChecker(cfg.guardrails)
    robots = RobotsChecker(user_agent="bwiza-data/0.1", enabled=pcfg.obey_robots_txt)
    rate_limiter = DomainRateLimiter(delay_s=pcfg.crawl_delay_s)
    dedup = PairDedupStore()
    stats = RunStats()

    writer = ShardWriter(cfg.sharding, source=pcfg.output_source, run_id=run_id)

    # S3 setup
    s3_client = None
    if cfg.s3.enabled:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)

    def _sync_state_to_s3():
        if s3_client is not None:
            try:
                upload_state(s3_client, cfg.s3.bucket, state)
                done_file = f"manifests/state/{run_id}.done.txt"
                upload_done_list(s3_client, cfg.s3.bucket, run_id, done_file)
            except Exception:
                log.exception("S3 state sync failed")

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=pcfg.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            key = shard_key(S3_PREFIX_PARALLEL, run_id, meta.filename)
            try:
                result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
                if not result.skipped and cfg.s3.verify_after_upload:
                    if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                        log.error("Verification failed for %s", key)
            except Exception:
                log.exception("S3 upload failed for %s", meta.filename)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    try:
        while True:
            url = frontier.next_url()
            if url is None:
                break

            # Skip if already done (resume)
            if url in done_set:
                state.items_skipped += 1
                continue

            state.current_item = url

            if not robots.is_allowed(url):
                stats.docs_seen += 1
                stats.reject_reasons["reject.robots_blocked"] += 1
                continue

            domain = canonical_domain(urlparse(url).hostname or "")
            rate_limiter.wait_if_needed(domain)

            # Fetch the page
            result = fetch_url(url, fetch_cfg)
            frontier.mark_fetched(url)
            stats.docs_seen += 1
            state.items_done += 1

            if not result.ok:
                stats.reject_reasons[f"reject.fetch.{result.error}"] += 1
                mark_done(run_id, url)
                save_state(state)
                continue

            # Discover bilingual pairs from this page
            candidates = find_bilingual_pairs(result.content, result.final_url or url)
            if not candidates:
                mark_done(run_id, url)
                save_state(state)
                continue

            for candidate in candidates:
                # Fetch both sides
                rate_limiter.wait_if_needed(domain)
                rw_fetch = fetch_url(candidate.url_rw, fetch_cfg)

                rate_limiter.wait_if_needed(domain)
                en_fetch = fetch_url(candidate.url_en, fetch_cfg)

                pair_result = process_candidate_pair(candidate, rw_fetch, en_fetch, pcfg)

                if pair_result.pair is None:
                    stats.reject_reasons[pair_result.reason] += 1
                    continue

                # Dedup
                is_dup, dup_reason = dedup.check_and_add(
                    pair_result.pair.rw_text, pair_result.pair.en_text
                )
                if is_dup:
                    stats.duplicates += 1
                    stats.reject_reasons[dup_reason] += 1
                    continue

                # Write to shard
                shard_result = writer.write(pair_result.pair.to_json())
                stats.docs_kept += 1
                stats.total_kept_chars += len(pair_result.pair.rw_text) + len(
                    pair_result.pair.en_text
                )

                if shard_result is not None:
                    on_shard_closed(shard_result)

            mark_done(run_id, url)
            save_state(state)

            # Check guardrails
            triggered, reason = guardrails.check(state)
            if triggered:
                log.info("Guardrail triggered: %s", reason)
                state.pause(reason)
                break

            if frontier.total_fetched % 50 == 0:
                log.info(
                    "Progress: fetched=%d pairs_kept=%d queue=%d",
                    frontier.total_fetched,
                    stats.docs_kept,
                    frontier.queue_size,
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
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        state.current_item = ""
        save_state(state)
        _sync_state_to_s3()
        stats.write_json("outputs/parallel", run_id)

    log.info(
        "Parallel corpus complete: pairs_kept=%d pages_seen=%d dupes=%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )

    return stats
