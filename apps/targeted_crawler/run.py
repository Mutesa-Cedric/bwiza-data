"""End-to-end targeted crawler runner."""

from datetime import datetime, timezone
from urllib.parse import urlparse

from apps.cc_miner.stats import RunStats
from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.common.logging import get_logger
from apps.common.manifest import append_manifest_entry
from apps.common.shard_writer import ShardWriter
from apps.targeted_crawler.extract import extract_main_text
from apps.targeted_crawler.fetch import fetch_url
from apps.targeted_crawler.frontier import CrawlFrontier
from apps.targeted_crawler.links import extract_links
from apps.targeted_crawler.pipeline import process_page
from apps.targeted_crawler.rate_limit import DomainRateLimiter
from apps.targeted_crawler.robots import RobotsChecker
from apps.targeted_crawler.seeds import canonical_domain, domain_set_from_seeds, load_seeds

log = get_logger(__name__)


def run_targeted_crawler(cfg: AppConfig) -> RunStats:
    """Run the targeted crawler end-to-end."""
    clear_registry()
    register_quality_filters()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tcfg = cfg.targeted

    # Load seeds
    seeds = load_seeds(tcfg.seeds_file)
    if not seeds:
        log.warning("No seeds found in %s. Nothing to crawl.", tcfg.seeds_file)
        return RunStats()

    allowed_domains = domain_set_from_seeds(seeds)
    log.info("Starting targeted crawl run=%s with %d seed domains", run_id, len(seeds))

    # Set up components
    frontier = CrawlFrontier(
        allowed_domains=allowed_domains,
        max_pages=tcfg.max_pages,
        per_domain_max_pages=tcfg.per_domain_max_pages,
    )
    frontier.add_seeds([url for url, _ in seeds])

    robots = RobotsChecker(user_agent=tcfg.user_agent, enabled=tcfg.obey_robots_txt)
    rate_limiter = DomainRateLimiter(delay_s=tcfg.crawl_delay_s)
    dedup = ExactDedupStore()
    stats = RunStats()

    # Shard writer
    writer = ShardWriter(cfg.sharding, source=tcfg.output_source, run_id=run_id)

    def on_shard_closed(meta):
        append_manifest_entry(run_id, meta, source=tcfg.output_source)

    try:
        while True:
            url = frontier.next_url()
            if url is None:
                break

            # Robots check
            if not robots.is_allowed(url):
                log.debug("Blocked by robots.txt: %s", url)
                stats.docs_seen += 1
                stats.reject_reasons["reject.robots_blocked"] += 1
                continue

            # Rate limit
            domain = _domain_from_url(url)
            if domain:
                rate_limiter.wait_if_needed(domain)

            # Fetch
            result = fetch_url(url, tcfg)
            frontier.mark_fetched(url)
            stats.docs_seen += 1

            if not result.ok:
                stats.reject_reasons[f"reject.fetch.{result.error}"] += 1
                continue

            # Safety: check final URL is still in allowlist
            if result.final_url and result.final_url != url:
                final_domain = _domain_from_url(result.final_url)
                if final_domain and final_domain not in allowed_domains:
                    stats.reject_reasons["reject.redirect_off_allowlist"] += 1
                    continue

            # Extract main text
            extracted = extract_main_text(result.content, url=result.final_url or url)
            if extracted is None:
                stats.reject_reasons["reject.extraction_failed"] += 1
                continue

            # Pipeline: keep decision + dedup
            doc, decision = process_page(extracted, result.final_url or url, cfg, dedup)

            if doc is None:
                stats.reject_reasons[decision.reason] += 1
                if decision.reason == "reject.dedup.exact":
                    stats.duplicates += 1
                continue

            # Write to shard
            shard_result = writer.write(doc.to_json())
            stats.docs_kept += 1
            stats.total_kept_chars += len(doc.text)

            if shard_result is not None:
                on_shard_closed(shard_result)

            # Discover links from this page
            links = extract_links(result.content, result.final_url or url)
            frontier.add_links(links)

            if frontier.total_fetched % 100 == 0:
                log.info(
                    "Progress: fetched=%d kept=%d queue=%d",
                    frontier.total_fetched,
                    stats.docs_kept,
                    frontier.queue_size,
                )

    except KeyboardInterrupt:
        log.warning("Interrupted by user. Flushing output.")
    finally:
        final_meta = writer.close()
        if final_meta is not None:
            on_shard_closed(final_meta)
        stats.write_json("outputs/targeted", run_id)

    log.info(
        "Targeted crawl complete: kept=%d seen=%d dupes=%d domains=%s",
        stats.docs_kept,
        stats.docs_seen,
        stats.duplicates,
        dict(frontier.domain_counts),
    )

    return stats


def _domain_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.hostname:
        return None
    return canonical_domain(parsed.hostname)
