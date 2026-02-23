"""Crawl frontier with allowlist enforcement, per-domain caps, and dedup."""

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
        self._queue: deque[str] = deque()
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
        """Get next URL to crawl, or None if done."""
        if self._total_fetched >= self._max_pages:
            return None

        while self._queue:
            url = self._queue.popleft()
            domain = self._domain_for_url(url)

            if domain and self._domain_counts.get(domain, 0) >= self._per_domain_max:
                continue

            return url

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
        return len(self._queue)

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
        self._queue.append(url)

    def _domain_for_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        if not parsed.hostname:
            return None
        return canonical_domain(parsed.hostname)
