"""End-to-end targeted crawler runner (resumable, concurrent)."""

from datetime import datetime, timezone
from urllib.parse import urlparse

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
from apps.targeted_crawler.extract import extract_main_text
from apps.targeted_crawler.fetch import FetchResult, fetch_url
from apps.targeted_crawler.frontier import CrawlFrontier
from apps.targeted_crawler.links import extract_links
from apps.targeted_crawler.pipeline import process_page
from apps.targeted_crawler.rate_limit import DomainRateLimiter
from apps.targeted_crawler.robots import RobotsChecker
from apps.targeted_crawler.safety import check_redirect_safety, is_safe_url
from apps.targeted_crawler.seeds import (
    canonical_domain,
    domain_set_from_seeds,
    load_seeds,
    path_prefix_map_from_seeds,
)

log = get_logger(__name__)


def _domain_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    return canonical_domain(parsed.hostname)


def _fetch_one(url: str, tcfg, rate_limiter: DomainRateLimiter) -> tuple[str, FetchResult]:
    """Fetch a single URL with rate limiting. Runs in a worker thread."""
    domain = _domain_from_url(url)
    if domain:
        rate_limiter.wait_if_needed(domain)
    result = fetch_url(url, tcfg)
    return url, result


def run_targeted_crawler(cfg: AppConfig, resume_run_id: str = "") -> RunStats:
    """Run the targeted crawler end-to-end.

    If resume_run_id is provided, resumes that run (skipping done URLs).
    Uses BoundedWorkerPool for concurrent fetching with sequential processing.
    """
    clear_registry()
    register_quality_filters()

    tcfg = cfg.targeted

    # Apply targeted-specific LID floor (stricter than global default)
    if tcfg.min_lid_confidence > cfg.lid.min_confidence:
        cfg.lid.min_confidence = tcfg.min_lid_confidence

    # Load seeds
    seeds = load_seeds(tcfg.seeds_file)
    if not seeds:
        log.warning("No seeds found in %s. Nothing to crawl.", tcfg.seeds_file)
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
            "Resuming targeted run=%s, %d URLs already done",
            run_id,
            len(done_set),
        )
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        done_set = set()
        state = RunState(
            run_id=run_id,
            pipeline="targeted_crawler",
            source="targeted_web",
            config_fingerprint=fingerprint_config(cfg),
        )

    state.start()
    save_state(state)

    log.info(
        "Targeted crawl run=%s with %d seed domains, concurrency=%d",
        run_id,
        len(seeds),
        tcfg.concurrency,
    )

    # Set up components
    frontier = CrawlFrontier(
        allowed_domains=allowed_domains,
        max_pages=tcfg.max_pages,
        per_domain_max_pages=tcfg.per_domain_max_pages,
        path_prefixes=path_prefix_map_from_seeds(seeds),
    )
    frontier.add_seeds([url for url, _, _ in seeds])

    # Pre-populate frontier's seen set with done URLs
    for done_url in done_set:
        frontier.mark_fetched(done_url)

    guardrails = GuardrailChecker(cfg.guardrails)
    robots = RobotsChecker(user_agent=tcfg.user_agent, enabled=tcfg.obey_robots_txt)
    rate_limiter = DomainRateLimiter(delay_s=tcfg.crawl_delay_s)
    dedup = create_dedup(cfg.dedup)
    stats = RunStats()

    # Shard writer
    writer = ShardWriter(cfg.sharding, source=tcfg.output_source, run_id=run_id)

    # S3 upload setup
    s3_client = None
    s3_prefix = "bwiza/curated/v1/targeted_web/"
    if cfg.s3.enabled:
        from apps.common.s3_client import get_s3_client

        s3_client = get_s3_client(cfg.s3)
        log.info("S3 upload enabled for targeted: bucket=%s prefix=%s", cfg.s3.bucket, s3_prefix)

    def _upload_shard(meta):
        """Upload a closed shard to S3."""
        key = shard_key(s3_prefix, run_id, meta.filename)
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
        append_manifest_entry(run_id, meta, source=tcfg.output_source)
        state.shards_closed += 1
        state.bytes_written += meta.bytes
        state.last_shard_name = meta.filename
        save_state(state)
        if s3_client is not None:
            _upload_shard(meta)
            state.uploaded_shards += 1
            _sync_state_to_s3()

    pool = BoundedWorkerPool(max_workers=tcfg.concurrency, name="crawler")
    guardrail_hit = False

    try:
        while not guardrail_hit:
            # 1. Collect a batch of URLs to fetch in parallel
            batch: list[str] = []
            while len(batch) < pool.max_workers:
                url = frontier.next_url()
                if url is None:
                    break
                if url in done_set:
                    state.items_skipped += 1
                    continue
                if not robots.is_allowed(url):
                    log.debug("Blocked by robots.txt: %s", url)
                    stats.docs_seen += 1
                    stats.reject_reasons["reject.robots_blocked"] += 1
                    continue
                batch.append(url)

            if not batch:
                break

            # 2. Submit fetch tasks in parallel (I/O-bound)
            for url in batch:
                pool.submit(_fetch_one, url, tcfg, rate_limiter)
            fetch_results = pool.drain()

            # 3. Process results sequentially (fast, no locking needed)
            for url, result in fetch_results:
                frontier.mark_fetched(url)
                stats.docs_seen += 1
                state.items_done += 1
                state.current_item = url
                url_domain = _domain_from_url(result.final_url or url) or ""
                if url_domain:
                    stats.domain_seen[url_domain] += 1

                if not result.ok:
                    stats.reject_reasons[f"reject.fetch.{result.error}"] += 1
                    mark_done(run_id, url)
                    continue

                # Safety: check redirect stays in allowlist
                redirect_ok, redirect_reason = check_redirect_safety(
                    url, result.final_url, allowed_domains
                )
                if not redirect_ok:
                    stats.reject_reasons[f"reject.{redirect_reason}"] += 1
                    mark_done(run_id, url)
                    continue

                # Discover links from every fetched page (even if content
                # fails LID/quality filters — an English homepage may link
                # to Kinyarwanda articles).
                raw_links = extract_links(result.content, result.final_url or url)
                safe_links = [lnk for lnk in raw_links if is_safe_url(lnk, allowed_domains)[0]]
                frontier.add_links(safe_links)

                # Extract main text
                extracted = extract_main_text(result.content, url=result.final_url or url)
                if extracted is None:
                    stats.reject_reasons["reject.extraction_failed"] += 1
                    mark_done(run_id, url)
                    continue

                # Pipeline: keep decision + dedup
                doc, decision = process_page(extracted, result.final_url or url, cfg, dedup)

                if doc is None:
                    stats.reject_reasons[decision.reason] += 1
                    if decision.reason == "reject.dedup.exact":
                        stats.duplicates += 1
                    mark_done(run_id, url)
                    continue

                # Write to shard
                shard_result = writer.write(doc.to_json())
                stats.docs_kept += 1
                stats.total_kept_chars += len(doc.text)
                if url_domain:
                    stats.domain_kept[url_domain] += 1
                mark_done(run_id, url)

                if shard_result is not None:
                    on_shard_closed(shard_result)

                # Check guardrails
                triggered, reason = guardrails.check(state)
                if triggered:
                    log.info("Guardrail triggered: %s", reason)
                    state.pause(reason)
                    guardrail_hit = True
                    break

            # Periodic state save and progress logging
            if frontier.total_fetched % 50 < pool.max_workers:
                save_state(state)
                log.info(
                    "Progress: fetched=%d kept=%d queue=%d",
                    frontier.total_fetched,
                    stats.docs_kept,
                    frontier.queue_size,
                )

        if state.status == "running":
            state.complete()
    except KeyboardInterrupt:
        log.warning("Interrupted by user. Flushing output.")
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
        stats.write_json("outputs/targeted", run_id)

    log.info(
        "Targeted crawl complete: kept=%d seen=%d dupes=%d domains=%s",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
        dict(frontier.domain_counts),
    )

    return stats
