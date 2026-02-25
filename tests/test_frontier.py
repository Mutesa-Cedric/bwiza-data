"""Tests for crawl frontier with allowlist enforcement."""

from apps.targeted_crawler.frontier import CrawlFrontier


def _make_frontier(**kwargs):
    defaults = {
        "allowed_domains": {"example.com", "test.rw"},
        "max_pages": 100,
        "per_domain_max_pages": 50,
    }
    defaults.update(kwargs)
    return CrawlFrontier(**defaults)


class TestCrawlFrontier:
    def test_seed_urls_queued(self):
        f = _make_frontier()
        f.add_seeds(["https://example.com/", "https://test.rw/"])
        assert f.queue_size == 2

    def test_next_url_returns_seeds(self):
        f = _make_frontier()
        f.add_seeds(["https://example.com/"])
        url = f.next_url()
        assert url == "https://example.com/"

    def test_off_allowlist_rejected(self):
        f = _make_frontier()
        f.add_seeds(["https://evil.com/"])
        assert f.queue_size == 0
        assert f.next_url() is None

    def test_links_filtered_by_allowlist(self):
        f = _make_frontier()
        f.add_links(
            [
                "https://example.com/page1",
                "https://evil.com/page2",
                "https://test.rw/page3",
            ]
        )
        assert f.queue_size == 2

    def test_seen_urls_not_revisited(self):
        f = _make_frontier()
        f.add_seeds(["https://example.com/"])
        f.add_links(["https://example.com/"])  # duplicate
        assert f.queue_size == 1

    def test_per_domain_cap(self):
        f = _make_frontier(per_domain_max_pages=2)
        f.add_seeds(["https://example.com/a", "https://example.com/b", "https://example.com/c"])
        f.mark_fetched("https://example.com/a")
        f.mark_fetched("https://example.com/b")
        # Next should skip /c since domain cap reached
        url = f.next_url()
        assert url is None

    def test_global_max_pages(self):
        f = _make_frontier(max_pages=1)
        f.add_seeds(["https://example.com/a", "https://example.com/b"])
        f.mark_fetched("https://example.com/a")
        # Global cap reached
        url = f.next_url()
        assert url is None

    def test_mark_fetched_increments(self):
        f = _make_frontier()
        assert f.total_fetched == 0
        f.mark_fetched("https://example.com/page")
        assert f.total_fetched == 1

    def test_domain_counts(self):
        f = _make_frontier()
        f.mark_fetched("https://example.com/a")
        f.mark_fetched("https://example.com/b")
        f.mark_fetched("https://test.rw/c")
        assert f.domain_counts == {"example.com": 2, "test.rw": 1}

    def test_www_normalized(self):
        f = _make_frontier(allowed_domains={"example.com"})
        f.add_seeds(["https://www.example.com/page"])
        assert f.queue_size == 1

    def test_empty_frontier(self):
        f = _make_frontier()
        assert f.next_url() is None
        assert f.total_fetched == 0
        assert f.queue_size == 0

    def test_path_prefix_accepts_matching(self):
        f = _make_frontier(
            allowed_domains={"who.int"},
            path_prefixes={"who.int": "/rw"},
        )
        f.add_seeds(["https://who.int/rw"])
        f.add_links(["https://who.int/rw/about", "https://who.int/rw/news"])
        assert f.queue_size == 3

    def test_path_prefix_rejects_non_matching(self):
        f = _make_frontier(
            allowed_domains={"who.int"},
            path_prefixes={"who.int": "/rw"},
        )
        f.add_links(["https://who.int/en/about", "https://who.int/fr/news"])
        assert f.queue_size == 0

    def test_path_prefix_no_prefix_accepts_all(self):
        f = _make_frontier(
            allowed_domains={"example.com"},
            path_prefixes={},
        )
        f.add_links(["https://example.com/anything", "https://example.com/page2"])
        assert f.queue_size == 2

    def test_path_prefix_deep_path(self):
        f = _make_frontier(
            allowed_domains={"bible.com"},
            path_prefixes={"bible.com": "/languages/kin"},
        )
        f.add_links(
            [
                "https://bible.com/languages/kin/verse1",
                "https://bible.com/languages/eng/verse1",
                "https://bible.com/about",
            ]
        )
        assert f.queue_size == 1

    def test_round_robin_interleaving(self):
        """Consecutive next_url() calls should rotate across domains."""
        f = _make_frontier(allowed_domains={"a.rw", "b.rw", "c.rw"})
        # Add many URLs per domain — FIFO would return a.rw, a.rw, a.rw...
        f.add_links(
            [
                "https://a.rw/1",
                "https://a.rw/2",
                "https://a.rw/3",
                "https://b.rw/1",
                "https://b.rw/2",
                "https://c.rw/1",
            ]
        )
        # First 3 URLs should come from 3 different domains
        urls = []
        for _ in range(3):
            url = f.next_url()
            assert url is not None
            urls.append(url)
        domains = {u.split("/")[2] for u in urls}
        assert len(domains) == 3

    def test_round_robin_exhausted_domain(self):
        """Domains that hit per_domain_max are removed from rotation."""
        f = _make_frontier(
            allowed_domains={"a.rw", "b.rw"},
            per_domain_max_pages=1,
        )
        f.add_links(
            [
                "https://a.rw/1",
                "https://a.rw/2",
                "https://b.rw/1",
                "https://b.rw/2",
            ]
        )
        # Fetch from both, hitting the cap
        url1 = f.next_url()
        assert url1 is not None
        f.mark_fetched(url1)
        url2 = f.next_url()
        assert url2 is not None
        f.mark_fetched(url2)
        # Both domains exhausted
        assert f.next_url() is None

    def test_round_robin_all_urls_consumed(self):
        """All enqueued URLs are eventually returned."""
        f = _make_frontier(allowed_domains={"a.rw", "b.rw"})
        f.add_links(
            [
                "https://a.rw/1",
                "https://a.rw/2",
                "https://b.rw/1",
            ]
        )
        urls = []
        while True:
            url = f.next_url()
            if url is None:
                break
            f.mark_fetched(url)
            urls.append(url)
        assert len(urls) == 3
        assert {"https://a.rw/1", "https://a.rw/2", "https://b.rw/1"} == set(urls)
