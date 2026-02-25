"""Fetch individual WARC records via HTTP byte-range requests."""

import time
from dataclasses import dataclass

import requests

from apps.common.config_types import CCIndexConfig
from apps.common.logging import get_logger

log = get_logger(__name__)

CC_DATA_BASE = "https://data.commoncrawl.org"


@dataclass
class WARCFetchResult:
    """Result of fetching a single WARC record."""

    raw_data: bytes = b""
    ok: bool = True
    error: str = ""


def fetch_warc_record(
    filename: str,
    offset: int,
    length: int,
    cfg: CCIndexConfig,
) -> WARCFetchResult:
    """Fetch a single WARC record using byte-range request.

    Returns the raw (still gzipped) bytes of the WARC record.
    """
    url = f"{CC_DATA_BASE}/{filename}"
    end_byte = offset + length - 1
    headers = {
        "Range": f"bytes={offset}-{end_byte}",
        "User-Agent": cfg.user_agent,
    }

    for attempt in range(cfg.warc_max_retries):
        if attempt == 0 and cfg.warc_rate_limit_s > 0:
            time.sleep(cfg.warc_rate_limit_s)
        try:
            resp = requests.get(url, headers=headers, timeout=cfg.warc_timeout_s)
            if resp.status_code in (200, 206):
                return WARCFetchResult(raw_data=resp.content)
            if resp.status_code == 429:
                wait = cfg.warc_retry_backoff_s * (2**attempt)
                log.warning("WARC fetch rate limited, waiting %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                wait = cfg.warc_retry_backoff_s * (2**attempt)
                log.warning(
                    "WARC fetch %d for %s, retrying in %ds", resp.status_code, filename, wait
                )
                time.sleep(wait)
                continue
            return WARCFetchResult(ok=False, error=f"http_{resp.status_code}")
        except requests.RequestException as exc:
            if attempt == cfg.warc_max_retries - 1:
                log.warning("WARC fetch failed for %s: %s", filename, exc)
                return WARCFetchResult(ok=False, error="connection_error")
            time.sleep(cfg.warc_retry_backoff_s * (2**attempt))

    return WARCFetchResult(ok=False, error="max_retries_exceeded")
