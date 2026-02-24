"""Fetch archived pages from the Wayback Machine."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from apps.common.config_types import WaybackConfig
from apps.common.logging import get_logger
from apps.wayback.cdx_client import WaybackRecord

log = get_logger(__name__)


@dataclass
class WaybackFetchResult:
    """Result of fetching a single Wayback page."""

    html_bytes: bytes = b""
    ok: bool = True
    error: str = ""


def fetch_wayback_page(record: WaybackRecord, cfg: WaybackConfig) -> WaybackFetchResult:
    """Fetch a single archived page using the id_ URL (raw content, no toolbar).

    Retries on 429 (rate limit) and 5xx errors with exponential backoff.
    Returns immediately on 4xx client errors.
    """
    url = record.wayback_url

    for attempt in range(cfg.fetch_max_retries):
        try:
            resp = requests.get(
                url,
                timeout=cfg.fetch_timeout_s,
                headers={"User-Agent": cfg.user_agent},
            )
            if resp.status_code == 200:
                return WaybackFetchResult(html_bytes=resp.content)

            if resp.status_code == 429:
                wait = cfg.fetch_retry_backoff_s * (2**attempt)
                log.warning("Wayback rate limited, waiting %ds", wait)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                wait = cfg.fetch_retry_backoff_s * (2**attempt)
                log.debug("Wayback 5xx on attempt %d, retrying in %ds", attempt + 1, wait)
                time.sleep(wait)
                continue

            # 4xx: no retry
            return WaybackFetchResult(ok=False, error=f"http_{resp.status_code}")

        except requests.exceptions.Timeout:
            if attempt == cfg.fetch_max_retries - 1:
                return WaybackFetchResult(ok=False, error="timeout")
            time.sleep(cfg.fetch_retry_backoff_s * (2**attempt))

        except requests.exceptions.ConnectionError:
            if attempt == cfg.fetch_max_retries - 1:
                return WaybackFetchResult(ok=False, error="connection_error")
            time.sleep(cfg.fetch_retry_backoff_s * (2**attempt))

    return WaybackFetchResult(ok=False, error="max_retries_exceeded")
