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
