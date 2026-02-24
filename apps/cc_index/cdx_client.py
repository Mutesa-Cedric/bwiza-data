"""Common Crawl CDX API client for index-assisted record discovery."""

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass

import requests

from apps.common.config_types import CCIndexConfig
from apps.common.logging import get_logger

log = get_logger(__name__)

CDX_BASE = "https://index.commoncrawl.org"
COLLINFO_URL = f"{CDX_BASE}/collinfo.json"


@dataclass
class CDXRecord:
    """A single record from the CC CDX index."""

    url: str
    filename: str
    offset: int
    length: int
    status: str
    mime: str
    crawl: str
    digest: str = ""


def discover_crawls(
    min_date: str = "",
    max_date: str = "",
    max_crawls: int = 6,
    timeout_s: int = 30,
    user_agent: str = "bwiza-data/0.1",
) -> list[str]:
    """Fetch available crawl IDs from collinfo.json, filtered by date.

    Returns crawl IDs sorted newest-first, limited to max_crawls.
    """
    resp = requests.get(
        COLLINFO_URL,
        timeout=timeout_s,
        headers={"User-Agent": user_agent},
    )
    resp.raise_for_status()
    crawls = resp.json()

    # Each entry has an "id" like "CC-MAIN-2025-51" and a "name" field.
    # Filter by date range if specified.  The id encodes year-week.
    ids = []
    for entry in crawls:
        cid = entry.get("id", "")
        if not cid.startswith("CC-MAIN-"):
            continue
        # Extract date portion: "CC-MAIN-2025-51" -> "2025-51"
        date_part = cid.replace("CC-MAIN-", "")
        # Convert to comparable string: "2025-51" -> "2025-51"
        # min/max_date are like "2024-01"
        if min_date and date_part < min_date:
            continue
        if max_date and date_part > max_date:
            continue
        ids.append(cid)

    # CC returns newest first already, but ensure sorting
    ids.sort(reverse=True)
    return ids[:max_crawls]


def query_cdx(
    crawl_id: str,
    url_pattern: str,
    cfg: CCIndexConfig,
) -> Iterator[CDXRecord]:
    """Query the CDX API for a single crawl + URL pattern.

    Handles pagination and rate limiting.
    Yields CDXRecord for each matching entry.
    """
    index_url = f"{CDX_BASE}/{crawl_id}-index"

    # First, get the number of pages
    num_pages = _get_num_pages(index_url, url_pattern, cfg)
    if num_pages == 0:
        return

    for page in range(min(num_pages, cfg.cdx_page_size)):
        yield from _fetch_cdx_page(index_url, url_pattern, page, crawl_id, cfg)
        if page < num_pages - 1:
            time.sleep(cfg.cdx_rate_limit_s)


def _get_num_pages(index_url: str, url_pattern: str, cfg: CCIndexConfig) -> int:
    """Get the number of pages for a CDX query."""
    params = {
        "url": url_pattern,
        "output": "json",
        "showNumPages": "true",
    }
    for attempt in range(cfg.cdx_max_retries):
        try:
            resp = requests.get(
                index_url,
                params=params,
                timeout=cfg.cdx_timeout_s,
                headers={"User-Agent": cfg.user_agent},
            )
            if resp.status_code == 429:
                wait = cfg.cdx_retry_backoff_s * (2**attempt)
                log.warning("CDX rate limited, waiting %ds", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return int(resp.text.strip())
        except (requests.RequestException, ValueError) as exc:
            if attempt == cfg.cdx_max_retries - 1:
                log.error("CDX page count failed for %s: %s", url_pattern, exc)
                return 0
            time.sleep(cfg.cdx_retry_backoff_s * (2**attempt))
    return 0


def _fetch_cdx_page(
    index_url: str,
    url_pattern: str,
    page: int,
    crawl_id: str,
    cfg: CCIndexConfig,
) -> Iterator[CDXRecord]:
    """Fetch a single page of CDX results."""
    params = {
        "url": url_pattern,
        "output": "json",
        "page": str(page),
    }
    for attempt in range(cfg.cdx_max_retries):
        try:
            resp = requests.get(
                index_url,
                params=params,
                timeout=cfg.cdx_timeout_s,
                headers={"User-Agent": cfg.user_agent},
            )
            if resp.status_code == 429:
                wait = cfg.cdx_retry_backoff_s * (2**attempt)
                log.warning("CDX rate limited on page %d, waiting %ds", page, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == cfg.cdx_max_retries - 1:
                log.error("CDX page %d fetch failed: %s", page, exc)
                return
            time.sleep(cfg.cdx_retry_backoff_s * (2**attempt))
    else:
        return

    status_filter = set(cfg.status_filter)
    mime_filter = set(cfg.mime_filter)

    for line in resp.text.strip().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        status = str(entry.get("status", ""))
        mime = entry.get("mime", "")

        if status_filter and status not in status_filter:
            continue
        if mime_filter and mime not in mime_filter:
            continue

        try:
            record = CDXRecord(
                url=entry["url"],
                filename=entry["filename"],
                offset=int(entry["offset"]),
                length=int(entry["length"]),
                status=status,
                mime=mime,
                crawl=crawl_id,
                digest=entry.get("digest", ""),
            )
            yield record
        except (KeyError, ValueError) as exc:
            log.debug("Skipping malformed CDX entry: %s", exc)


def build_record_list(
    crawl_ids: list[str],
    cfg: CCIndexConfig,
) -> list[CDXRecord]:
    """Query CDX for all configured crawls and domain patterns.

    Deduplicates by (url, digest), keeping the latest crawl.
    """
    all_patterns = list(cfg.domain_queries) + list(cfg.extra_domain_queries)
    seen: dict[tuple[str, str], CDXRecord] = {}
    total_raw = 0

    for crawl_id in crawl_ids:
        for pattern in all_patterns:
            log.info("Querying CDX: crawl=%s pattern=%s", crawl_id, pattern)
            for record in query_cdx(crawl_id, pattern, cfg):
                total_raw += 1
                key = (record.url, record.digest)
                if key not in seen:
                    seen[key] = record
            time.sleep(cfg.cdx_rate_limit_s)

    records = list(seen.values())
    log.info(
        "CDX discovery: %d raw records -> %d unique (url+digest)",
        total_raw,
        len(records),
    )
    return records
