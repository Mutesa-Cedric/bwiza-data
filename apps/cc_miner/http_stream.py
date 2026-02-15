"""Streaming HTTP downloader with retries."""

import time
from collections.abc import Iterator

import requests

from apps.common.config_types import AppConfig
from apps.common.logging import get_logger

log = get_logger(__name__)


def stream_download(url: str, cfg: AppConfig) -> Iterator[bytes]:
    """Stream download a URL with retries and backoff."""
    last_exc = None
    for attempt in range(1, cfg.cc.max_retries + 1):
        try:
            resp = requests.get(
                url,
                stream=True,
                timeout=cfg.cc.request_timeout_s,
                headers={"User-Agent": cfg.cc.user_agent},
            )
            resp.raise_for_status()
            yield from resp.iter_content(chunk_size=65536)
            return
        except (requests.RequestException, IOError) as exc:
            last_exc = exc
            if attempt < cfg.cc.max_retries:
                wait = cfg.cc.retry_backoff_s * (2 ** (attempt - 1))
                log.warning("Attempt %d/%d failed for %s: %s. Retrying in %ds",
                            attempt, cfg.cc.max_retries, url, exc, wait)
                time.sleep(wait)
            else:
                log.error("All %d attempts failed for %s: %s",
                          cfg.cc.max_retries, url, exc)

    raise ConnectionError(f"Failed to download {url} after {cfg.cc.max_retries} attempts") from last_exc
