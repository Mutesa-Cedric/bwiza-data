"""Domain-locked URL discovery for rwandaheritage.gov.rw.

Two-stage architecture: this module handles stage 1 (discovery).
It crawls listing/pagination pages and classifies discovered URLs
into news articles, PDFs, listing pages, and static content.

TYPO3 CMS pagination uses cHash validation — URLs must be scraped
from HTML, not constructed programmatically.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from apps.common.config_types import AppConfig, TargetedConfig
from apps.common.logging import get_logger
from apps.targeted_crawler.fetch import FetchResult, fetch_url
from apps.targeted_crawler.links import extract_links
from apps.targeted_crawler.rate_limit import DomainRateLimiter

log = get_logger(__name__)


@dataclass
class DiscoveredURL:
    url: str
    url_class: str  # "news", "pdf", "listing", "static"
    parent_url: str = ""
    discovery_origin: str = ""  # "seed_manual", "seed_link_follow"
    section: str = ""  # "amakuru", "inyandiko", etc.


@dataclass
class DiscoveryResult:
    discovered: list[DiscoveredURL] = field(default_factory=list)
    pages_crawled: int = 0
    news_count: int = 0
    pdf_count: int = 0
    listing_count: int = 0
    static_count: int = 0


# Paths that are English translations or site boilerplate — never harvest.
_EXCLUDED_PATH_PREFIXES = ("/en/", "/fr/", "/index.php/")
_EXCLUDED_PATHS = {
    "/1/servisi-kuri-murandasi",
    "/servisi-kuri-murandasi",
    "/online-services",
    "/en/online-services",
}


def _is_excluded(url: str) -> bool:
    """Check if URL should be excluded (English paths, boilerplate)."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(path.startswith(p) for p in _EXCLUDED_PATH_PREFIXES):
        return True
    return path.rstrip("/") in _EXCLUDED_PATHS


def _classify_url(url: str) -> str:
    """Classify a heritage URL by type."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()

    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".docx", ".doc", ".pptx")):
        return "document"
    if "/fileadmin/" in path and not path.endswith(
        (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js")
    ):
        return "pdf"
    if "/news-details/" in path:
        return "news"
    if "tx_news_pi1" in query or "tx_filelist_filelist" in query:
        return "listing"
    if "/amakuru" in path and "currentpage" not in query.lower():
        return "listing"
    return "static"


def _extract_section(url: str) -> str:
    """Extract the content section from a heritage URL path."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    if "/amakuru" in path or "/news-details/" in path:
        return "amakuru"
    if "/inyandiko/" in path:
        # Extract sub-section: e.g. /1/inyandiko/ibitabo-byatangajwe
        parts = path.split("/inyandiko/")
        if len(parts) > 1:
            sub = parts[1].strip("/").split("/")[0]
            if sub:
                return f"inyandiko/{sub}"
        return "inyandiko"
    if "/fileadmin/" in path:
        if "laws" in path or "policies" in path:
            return "inyandiko/amategeko"
        if "books" in path or "published" in path:
            return "inyandiko/ibitabo"
        if "educational" in path:
            return "inyandiko/ubukangurambaga"
        return "inyandiko"
    if "/ikigo" in path:
        return "ikigo"
    if "/serivisi" in path or "/serivski" in path:
        return "serivisi"
    return "other"


def _is_on_domain(url: str, allowed_domain: str) -> bool:
    """Check if URL belongs to the allowed domain."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname == allowed_domain or hostname.endswith(f".{allowed_domain}")


def _make_fetch_cfg(cfg: AppConfig) -> TargetedConfig:
    """Build a TargetedConfig adapter for fetch_url from heritage config."""
    hcfg = cfg.heritage
    return TargetedConfig(
        request_timeout_s=hcfg.request_timeout_s,
        max_retries=hcfg.max_retries,
        retry_backoff_s=hcfg.retry_backoff_s,
        max_response_bytes=hcfg.max_response_bytes,
        user_agent=hcfg.user_agent,
        allowed_content_types=hcfg.allowed_content_types,
    )


def run_discovery(
    cfg: AppConfig,
    discovery_done: set[str] | None = None,
) -> DiscoveryResult:
    """Discover all content URLs on rwandaheritage.gov.rw.

    Crawls listing pages breadth-first, following pagination links,
    and classifies discovered URLs. Enforces domain lock and
    max_listing_pages guardrail.

    Returns a DiscoveryResult with all discovered URLs classified.
    """
    hcfg = cfg.heritage
    fetch_cfg = _make_fetch_cfg(cfg)
    rate_limiter = DomainRateLimiter(delay_s=hcfg.domain_delay_s)

    seen_urls: set[str] = set(discovery_done or set())
    queue: deque[tuple[str, str]] = deque()  # (url, origin)
    result = DiscoveryResult()

    # Seed the queue with configured listing URLs
    for seed_url in hcfg.seed_listing_urls:
        if seed_url not in seen_urls:
            queue.append((seed_url, "seed_manual"))
            seen_urls.add(seed_url)

    while queue and result.pages_crawled < hcfg.max_listing_pages:
        current_url, origin = queue.popleft()

        rate_limiter.wait_if_needed(hcfg.allowed_domain)
        fetch_result: FetchResult = fetch_url(current_url, fetch_cfg)

        if not fetch_result.ok:
            log.debug("Discovery fetch failed: %s — %s", current_url, fetch_result.error)
            continue

        result.pages_crawled += 1
        log.debug(
            "Discovery crawled page %d: %s",
            result.pages_crawled,
            current_url,
        )

        # Extract all links from the page
        links = extract_links(fetch_result.content, fetch_result.final_url or current_url)

        for link in links:
            if link in seen_urls:
                continue
            if not _is_on_domain(link, hcfg.allowed_domain):
                continue
            if _is_excluded(link):
                continue

            seen_urls.add(link)
            url_class = _classify_url(link)
            section = _extract_section(link)

            discovered = DiscoveredURL(
                url=link,
                url_class=url_class,
                parent_url=current_url,
                discovery_origin=origin if origin == "seed_manual" else "seed_link_follow",
                section=section,
            )
            result.discovered.append(discovered)

            if url_class == "news":
                result.news_count += 1
            elif url_class == "pdf":
                result.pdf_count += 1
            elif url_class == "listing":
                result.listing_count += 1
                # Follow pagination links
                queue.append((link, "seed_link_follow"))
            else:
                result.static_count += 1

    log.info(
        "Discovery complete: pages_crawled=%d news=%d pdf=%d listing=%d static=%d total=%d",
        result.pages_crawled,
        result.news_count,
        result.pdf_count,
        result.listing_count,
        result.static_count,
        len(result.discovered),
    )
    return result


def save_discovery_index(
    result: DiscoveryResult,
    output_dir: Path,
    run_id: str,
) -> Path:
    """Persist discovery results as append-only JSONL."""
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / f"{run_id}_discovery_index.jsonl"

    with open(index_path, "w") as f:
        for item in result.discovered:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    log.info("Discovery index saved: %s (%d entries)", index_path, len(result.discovered))
    return index_path


def load_discovery_index(index_path: Path) -> list[DiscoveredURL]:
    """Load a previously saved discovery index."""
    items = []
    with open(index_path) as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                items.append(DiscoveredURL(**data))
    return items
