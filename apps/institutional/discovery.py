"""Generic URL discovery for institutional domains.

Generalized from apps/heritage/discovery.py. Works with any domain
by using extension-based URL classification instead of TYPO3-specific
patterns. Follows the same two-stage architecture: discovery → harvest.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from apps.common.config_types import AppConfig, TargetedConfig
from apps.common.logging import get_logger
from apps.heritage.discovery import DiscoveredURL, DiscoveryResult
from apps.institutional.source_profile import SourceProfile
from apps.targeted_crawler.fetch import FetchResult, fetch_url
from apps.targeted_crawler.links import extract_links
from apps.targeted_crawler.rate_limit import DomainRateLimiter

log = get_logger(__name__)

# File extensions that are never content.
_STATIC_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".css",
        ".js",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".zip",
        ".rar",
        ".gz",
        ".tar",
        ".xml",
        ".json",
        ".rss",
    }
)


def _is_excluded(url: str, profile: SourceProfile) -> bool:
    """Check if URL should be excluded."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    # Profile-specific exclusions
    for prefix in profile.excluded_path_prefixes:
        if path.startswith(prefix.lower()):
            return True
    # Static asset exclusions
    for ext in _STATIC_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def _classify_url(url: str) -> str:
    """Classify a URL by type using extension-based heuristics."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    if path.endswith(".pdf"):
        return "pdf"
    if path.endswith((".docx", ".doc", ".pptx", ".xlsx")):
        return "document"
    # /fileadmin/ paths on TYPO3 sites are usually documents
    if "/fileadmin/" in path and not any(path.endswith(ext) for ext in _STATIC_EXTENSIONS):
        return "pdf"
    return "page"


def _extract_section(url: str) -> str:
    """Extract a generic section from URL path."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        return "root"
    # Skip numeric-only segments and very short ones
    for part in parts:
        if not part.isdigit() and len(part) > 1:
            return part
    return parts[0]


def _is_on_domain(url: str, domain: str) -> bool:
    """Check if URL belongs to the allowed domain."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname == domain or hostname.endswith(f".{domain}")


def _make_fetch_cfg(cfg: AppConfig) -> TargetedConfig:
    """Build a TargetedConfig for fetching from heritage config settings."""
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
    profile: SourceProfile,
    cfg: AppConfig,
    discovery_done: set[str] | None = None,
) -> DiscoveryResult:
    """Discover content URLs on an institutional domain.

    Crawls seed URLs breadth-first, following links on the same domain,
    and classifies discovered URLs by extension.
    """
    hcfg = cfg.heritage
    fetch_cfg = _make_fetch_cfg(cfg)
    rate_limiter = DomainRateLimiter(delay_s=hcfg.domain_delay_s)

    seen_urls: set[str] = set(discovery_done or set())
    queue: deque[tuple[str, str]] = deque()
    result = DiscoveryResult()

    for seed_url in profile.seeds:
        if seed_url not in seen_urls:
            queue.append((seed_url, "seed_manual"))
            seen_urls.add(seed_url)

    while queue and result.pages_crawled < hcfg.max_listing_pages:
        current_url, origin = queue.popleft()

        # Only fetch HTML pages for link discovery
        url_class = _classify_url(current_url)
        if url_class in ("pdf", "document"):
            # Don't fetch PDFs/docs during discovery, just record them
            section = _extract_section(current_url)
            result.discovered.append(
                DiscoveredURL(
                    url=current_url,
                    url_class=url_class,
                    parent_url="",
                    discovery_origin=origin,
                    section=section,
                )
            )
            if url_class == "pdf":
                result.pdf_count += 1
            continue

        rate_limiter.wait_if_needed(profile.domain)
        fetch_result: FetchResult = fetch_url(current_url, fetch_cfg)

        if not fetch_result.ok:
            log.debug("Discovery fetch failed: %s — %s", current_url, fetch_result.error)
            continue

        result.pages_crawled += 1

        # Record this page as a discovered content page
        section = _extract_section(current_url)
        result.discovered.append(
            DiscoveredURL(
                url=current_url,
                url_class="page",
                parent_url="",
                discovery_origin=origin,
                section=section,
            )
        )

        links = extract_links(fetch_result.content, fetch_result.final_url or current_url)

        for link in links:
            if link in seen_urls:
                continue
            if not _is_on_domain(link, profile.domain):
                continue
            if _is_excluded(link, profile):
                continue

            seen_urls.add(link)
            link_class = _classify_url(link)
            link_section = _extract_section(link)

            discovered = DiscoveredURL(
                url=link,
                url_class=link_class,
                parent_url=current_url,
                discovery_origin="seed_link_follow",
                section=link_section,
            )
            result.discovered.append(discovered)

            if link_class == "pdf":
                result.pdf_count += 1
            elif link_class == "page":
                # Follow HTML pages for more links
                queue.append((link, "seed_link_follow"))
                result.listing_count += 1

        log.debug(
            "Discovery [%s] page %d: %s (found %d links)",
            profile.domain,
            result.pages_crawled,
            current_url,
            len(links),
        )

    # Count page-type discovered URLs as news_count for compatibility
    result.news_count = sum(1 for d in result.discovered if d.url_class == "page")

    log.info(
        "Discovery [%s] complete: pages_crawled=%d pages=%d pdf=%d total=%d",
        profile.domain,
        result.pages_crawled,
        result.news_count,
        result.pdf_count,
        len(result.discovered),
    )
    return result


def save_discovery_index(
    result: DiscoveryResult,
    output_dir: Path,
    run_id: str,
) -> Path:
    """Persist discovery results as JSONL."""
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / f"{run_id}_discovery_index.jsonl"

    with open(index_path, "w") as f:
        for item in result.discovered:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    log.info("Discovery index saved: %s (%d entries)", index_path, len(result.discovered))
    return index_path
