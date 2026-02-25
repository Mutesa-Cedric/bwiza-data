"""Crawl frontier with allowlist enforcement, per-domain caps, and dedup.

Uses round-robin domain interleaving so workers fetch from different
domains, avoiding rate-limiter contention.
"""

from collections import deque
from urllib.parse import urlparse

from apps.targeted_crawler.seeds import canonical_domain


class CrawlFrontier:
    """Manages the crawl queue with scope enforcement.

    Rules:
    - Only allowlisted domains are crawled.
    - Per-domain page caps are enforced.
    - Global max pages is enforced.
    - URLs are not revisited (seen set).
    - next_url() rotates across domains (round-robin) so concurrent
      workers hit different domains and avoid rate-limiter contention.
    """

    def __init__(
        self,
        allowed_domains: set[str],
        max_pages: int,
        per_domain_max_pages: int,
        path_prefixes: dict[str, str] | None = None,
    ):
        self._allowed = allowed_domains
        self._max_pages = max_pages
        self._per_domain_max = per_domain_max_pages
        self._path_prefixes = path_prefixes or {}
        self._domain_queues: dict[str, deque[str]] = {}
        self._domain_order: deque[str] = deque()
        self._seen: set[str] = set()
        self._domain_counts: dict[str, int] = {}
        self._total_fetched: int = 0

    def add_seeds(self, urls: list[str]) -> None:
        """Add seed URLs to the frontier."""
        for url in urls:
            self._enqueue(url)

    def add_links(self, urls: list[str]) -> None:
        """Add discovered links to the frontier (filtered by allowlist)."""
        for url in urls:
            self._enqueue(url)

    def next_url(self) -> str | None:
        """Get next URL to crawl, or None if done.

        Rotates across domains so consecutive calls return URLs from
        different domains when available.
        """
        if self._total_fetched >= self._max_pages:
            return None

        checked = 0
        while checked < len(self._domain_order):
            domain = self._domain_order[0]
            self._domain_order.rotate(-1)
            checked += 1

            # Skip domains that hit their per-domain cap
            if self._domain_counts.get(domain, 0) >= self._per_domain_max:
                self._domain_order.remove(domain)
                checked -= 1
                continue

            dq = self._domain_queues.get(domain)
            if not dq:
                self._domain_order.remove(domain)
                checked -= 1
                continue

            return dq.popleft()

        return None

    def mark_fetched(self, url: str) -> None:
        """Record that a URL was fetched."""
        self._total_fetched += 1
        domain = self._domain_for_url(url)
        if domain:
            self._domain_counts[domain] = self._domain_counts.get(domain, 0) + 1

    @property
    def total_fetched(self) -> int:
        return self._total_fetched

    @property
    def queue_size(self) -> int:
        return sum(len(dq) for dq in self._domain_queues.values())

    @property
    def domain_counts(self) -> dict[str, int]:
        return dict(self._domain_counts)

    def _enqueue(self, url: str) -> None:
        if url in self._seen:
            return
        parsed = urlparse(url)
        if not parsed.hostname:
            return
        domain = canonical_domain(parsed.hostname)
        if domain not in self._allowed:
            return
        prefix = self._path_prefixes.get(domain, "")
        if prefix and not parsed.path.startswith(prefix):
            return
        self._seen.add(url)
        if domain not in self._domain_queues:
            self._domain_queues[domain] = deque()
            self._domain_order.append(domain)
        self._domain_queues[domain].append(url)

    def _domain_for_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        if not parsed.hostname:
            return None
        return canonical_domain(parsed.hostname)
