"""Per-domain rate limiter for polite crawling."""

import time

from apps.targeted_crawler.seeds import canonical_domain


class DomainRateLimiter:
    """Enforce a minimum delay between requests to the same domain."""

    def __init__(self, delay_s: float):
        self._delay_s = delay_s
        self._last_request: dict[str, float] = {}

    def wait_if_needed(self, domain: str) -> None:
        """Block until the per-domain delay has elapsed."""
        domain = canonical_domain(domain)
        now = time.monotonic()
        last = self._last_request.get(domain, 0.0)
        elapsed = now - last

        if elapsed < self._delay_s:
            time.sleep(self._delay_s - elapsed)

        self._last_request[domain] = time.monotonic()

    def record_request(self, domain: str) -> None:
        """Record that a request was just made to this domain."""
        self._last_request[canonical_domain(domain)] = time.monotonic()
