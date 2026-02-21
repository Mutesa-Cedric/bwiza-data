"""End-to-end parallel corpus runner."""

from datetime import datetime, timezone

from apps.cc_miner.stats import RunStats
from apps.common.config_types import AppConfig, TargetedConfig
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
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
from apps.targeted_crawler.seeds import domain_set_from_seeds, load_seeds

log = get_logger(__name__)

S3_PREFIX_PARALLEL = "bwiza/supervision/v1/parallel/"


def run_parallel_corpus(cfg: AppConfig) -> RunStats:
    """Run the parallel corpus builder end-to-end."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pcfg = cfg.parallel

    # Load seeds
    seeds = load_seeds(pcfg.seeds_file)
    if not seeds:
        log.warning("No seeds found in %s", pcfg.seeds_file)
        return RunStats()

    allowed_domains = domain_set_from_seeds(seeds)
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

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=pcfg.output_source)
        if s3_client is not None:
            key = shard_key(S3_PREFIX_PARALLEL, run_id, meta.filename)
            try:
                result = upload_file(s3_client, meta.path, cfg.s3.bucket, key, cfg.s3)
                if not result.skipped and cfg.s3.verify_after_upload:
                    if not verify_upload(s3_client, meta.path, cfg.s3.bucket, key):
                        log.error("Verification failed for %s", key)
            except Exception:
                log.exception("S3 upload failed for %s", meta.filename)

    try:
        while True:
            url = frontier.next_url()
            if url is None:
                break

            if not robots.is_allowed(url):
                stats.docs_seen += 1
                stats.reject_reasons["reject.robots_blocked"] += 1
                continue

            from urllib.parse import urlparse

            from apps.targeted_crawler.seeds import canonical_domain

            domain = canonical_domain(urlparse(url).hostname or "")
            rate_limiter.wait_if_needed(domain)

            # Fetch the page
            result = fetch_url(url, fetch_cfg)
            frontier.mark_fetched(url)
            stats.docs_seen += 1

            if not result.ok:
                stats.reject_reasons[f"reject.fetch.{result.error}"] += 1
                continue

            # Discover bilingual pairs from this page
            candidates = find_bilingual_pairs(result.content, result.final_url or url)
            if not candidates:
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

            if frontier.total_fetched % 50 == 0:
                log.info(
                    "Progress: fetched=%d pairs_kept=%d queue=%d",
                    frontier.total_fetched,
                    stats.docs_kept,
                    frontier.queue_size,
                )

    except KeyboardInterrupt:
        log.warning("Interrupted. Flushing output.")
    finally:
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        stats.write_json("outputs/parallel", run_id)

    log.info(
        "Parallel corpus complete: pairs_kept=%d pages_seen=%d dupes=%d",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
    )

    return stats
