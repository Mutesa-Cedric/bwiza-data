"""Internet Archive Wayback Machine CDX API client."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass

import requests

from apps.common.config_types import WaybackConfig
from apps.common.logging import get_logger

log = get_logger(__name__)

CDX_BASE = "https://web.archive.org/cdx/search/cdx"


@dataclass
class WaybackRecord:
    """A single record from the Wayback CDX index."""

    timestamp: str
    original_url: str
    status_code: str
    mime_type: str
    length: int

    @property
    def wayback_url(self) -> str:
        """Raw-content Wayback URL (id_ flag skips toolbar injection)."""
        return f"https://web.archive.org/web/{self.timestamp}id_/{self.original_url}"


def query_wayback_cdx(
    domain: str,
    cfg: WaybackConfig,
) -> Iterator[WaybackRecord]:
    """Query Wayback CDX for all captures of a domain.

    Uses server-side filters (statuscode, mimetype) and date range.
    Yields WaybackRecord for each matching entry.
    """
    yield from _fetch_cdx_records(domain, cfg)


def _fetch_cdx_records(
    domain: str,
    cfg: WaybackConfig,
) -> Iterator[WaybackRecord]:
    """Fetch CDX results with server-side filters.

    The Wayback CDX API returns a JSON array of arrays.
    The first row is the header: ["timestamp","original","statuscode",...].
    Server-side filter params avoid the pagination+date-filter incompatibility.
    """
    params: list[tuple[str, str]] = [
        ("url", f"{domain}/*"),
        ("output", "json"),
        ("fl", "timestamp,original,statuscode,mimetype,length"),
    ]
    if cfg.from_year:
        params.append(("from", f"{cfg.from_year}0101"))
    if cfg.to_year:
        params.append(("to", f"{cfg.to_year}1231"))
    for status in cfg.status_filter:
        params.append(("filter", f"statuscode:{status}"))
    for mime in cfg.mime_filter:
        params.append(("filter", f"mimetype:{mime}"))

    for attempt in range(cfg.cdx_max_retries):
        try:
            resp = requests.get(
                CDX_BASE,
                params=params,
                timeout=cfg.cdx_timeout_s,
                headers={"User-Agent": cfg.user_agent},
            )
            if resp.status_code == 429:
                wait = cfg.cdx_retry_backoff_s * (2**attempt)
                log.warning("Wayback CDX rate limited for %s, waiting %ds", domain, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == cfg.cdx_max_retries - 1:
                log.error("Wayback CDX fetch failed for %s: %s", domain, exc)
                return
            time.sleep(cfg.cdx_retry_backoff_s * (2**attempt))
    else:
        return

    try:
        rows = json.loads(resp.text)
    except json.JSONDecodeError:
        log.error("Wayback CDX returned invalid JSON for %s", domain)
        return

    if not isinstance(rows, list) or len(rows) < 2:
        return

    # First row is the header — skip it
    for row in rows[1:]:
        if not isinstance(row, list) or len(row) < 5:
            continue

        timestamp, original_url, status_code, mime_type, length_str = (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
        )

        try:
            length = int(length_str)
        except ValueError:
            length = 0

        yield WaybackRecord(
            timestamp=timestamp,
            original_url=original_url,
            status_code=status_code,
            mime_type=mime_type,
            length=length,
        )


def build_wayback_record_list(
    domains: list[str],
    cfg: WaybackConfig,
) -> list[WaybackRecord]:
    """Query CDX for all domains, pre-dedup by original_url (keep latest).

    The Wayback Machine archives the same URL monthly for years.
    Pre-deduplication by URL (keeping the latest timestamp) dramatically
    reduces the number of pages to fetch.
    """
    seen: dict[str, WaybackRecord] = {}
    total_raw = 0

    for domain in domains:
        log.info("Querying Wayback CDX: domain=%s", domain)
        for record in query_wayback_cdx(domain, cfg):
            total_raw += 1
            existing = seen.get(record.original_url)
            if existing is None or record.timestamp > existing.timestamp:
                seen[record.original_url] = record
        time.sleep(cfg.cdx_rate_limit_s)

    records = list(seen.values())
    log.info(
        "Wayback CDX discovery: %d raw records -> %d unique URLs",
        total_raw,
        len(records),
    )
    return records
