"""Per-domain rate limiter for polite crawling."""

import threading
import time

from apps.targeted_crawler.seeds import canonical_domain


class DomainRateLimiter:
    """Enforce a minimum delay between requests to the same domain.

    Thread-safe: multiple workers can call wait_if_needed concurrently.
    Each domain is serialized independently via per-domain locks.
    """

    def __init__(self, delay_s: float):
        self._delay_s = delay_s
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()
        self._domain_locks: dict[str, threading.Lock] = {}

    def _get_domain_lock(self, domain: str) -> threading.Lock:
        with self._lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = threading.Lock()
            return self._domain_locks[domain]

    def wait_if_needed(self, domain: str) -> None:
        """Block until the per-domain delay has elapsed."""
        domain = canonical_domain(domain)
        domain_lock = self._get_domain_lock(domain)

        with domain_lock:
            now = time.monotonic()
            last = self._last_request.get(domain, 0.0)
            elapsed = now - last

            if elapsed < self._delay_s:
                time.sleep(self._delay_s - elapsed)

            self._last_request[domain] = time.monotonic()

    def record_request(self, domain: str) -> None:
        """Record that a request was just made to this domain."""
        domain = canonical_domain(domain)
        domain_lock = self._get_domain_lock(domain)
        with domain_lock:
            self._last_request[domain] = time.monotonic()
