"""Polite HTTP fetcher with timeouts, retries, and size limits."""

import time
from dataclasses import dataclass

import requests

from apps.common.config_types import TargetedConfig
from apps.common.logging import get_logger

log = get_logger(__name__)


@dataclass
class FetchResult:
    url: str
    status_code: int = 0
    content_type: str = ""
    content: bytes = b""
    final_url: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and not self.error


def fetch_url(url: str, cfg: TargetedConfig) -> FetchResult:
    """Fetch a URL with retries, timeouts, size limits, and content-type checking."""
    last_error = ""
    for attempt in range(1, cfg.max_retries + 1):
        try:
            resp = requests.get(
                url,
                timeout=cfg.request_timeout_s,
                headers={"User-Agent": cfg.user_agent},
                stream=True,
                allow_redirects=True,
            )

            final_url = resp.url
            content_type = resp.headers.get("Content-Type", "")
            ct_lower = content_type.lower().split(";")[0].strip()

            if ct_lower not in cfg.allowed_content_types:
                return FetchResult(
                    url=url,
                    status_code=resp.status_code,
                    content_type=ct_lower,
                    final_url=final_url,
                    error=f"disallowed_content_type:{ct_lower}",
                )

            if resp.status_code != 200:
                last_error = f"http_{resp.status_code}"
                if resp.status_code < 500:
                    return FetchResult(
                        url=url,
                        status_code=resp.status_code,
                        content_type=ct_lower,
                        final_url=final_url,
                        error=last_error,
                    )
                # 5xx: retry
                if attempt < cfg.max_retries:
                    time.sleep(cfg.retry_backoff_s * attempt)
                continue

            # Read with size limit
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > cfg.max_response_bytes:
                    return FetchResult(
                        url=url,
                        status_code=200,
                        content_type=ct_lower,
                        final_url=final_url,
                        error="response_too_large",
                    )
                chunks.append(chunk)

            return FetchResult(
                url=url,
                status_code=200,
                content_type=ct_lower,
                content=b"".join(chunks),
                final_url=final_url,
            )

        except requests.exceptions.Timeout:
            last_error = "timeout"
            log.debug("Timeout fetching %s (attempt %d/%d)", url, attempt, cfg.max_retries)
        except requests.exceptions.ConnectionError:
            last_error = "connection_error"
            log.debug("Connection error %s (attempt %d/%d)", url, attempt, cfg.max_retries)
        except requests.exceptions.RequestException as e:
            last_error = f"request_error:{type(e).__name__}"
            log.debug("Request error %s: %s", url, e)

        if attempt < cfg.max_retries:
            time.sleep(cfg.retry_backoff_s * attempt)

    return FetchResult(url=url, error=last_error)
