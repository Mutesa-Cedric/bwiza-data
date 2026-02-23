"""Tests for robots.txt and rate limiting."""

import time
from unittest.mock import MagicMock, patch

from apps.targeted_crawler.rate_limit import DomainRateLimiter
from apps.targeted_crawler.robots import RobotsChecker


def _mock_response(status_code: int, text: str = "") -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


class TestRobotsChecker:
    def test_disabled_allows_all(self):
        checker = RobotsChecker(user_agent="test", enabled=False)
        assert checker.is_allowed("https://example.com/secret")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_allowed_url(self, mock_get):
        mock_get.return_value = _mock_response(200, "User-agent: *\nDisallow: /private\n")
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://example.com/page")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_disallowed_url(self, mock_get):
        mock_get.return_value = _mock_response(200, "User-agent: *\nDisallow: /admin\n")
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert not checker.is_allowed("https://example.com/admin")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_robots_fetch_failure_allows(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError("network error")
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://example.com/page")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_caches_per_origin(self, mock_get):
        mock_get.return_value = _mock_response(200, "User-agent: *\nDisallow:\n")
        checker = RobotsChecker(user_agent="test", enabled=True)
        checker.is_allowed("https://example.com/a")
        checker.is_allowed("https://example.com/b")
        # Should only fetch robots.txt once per origin
        assert mock_get.call_count == 1

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_403_blocks_all(self, mock_get):
        """HTTP 403 from robots.txt means the server blocks our UA — respect it."""
        mock_get.return_value = _mock_response(403)
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert not checker.is_allowed("https://blocked.com/page")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_404_allows_all(self, mock_get):
        """HTTP 404 means no robots.txt — allow everything (RFC 9309 §2.4)."""
        mock_get.return_value = _mock_response(404)
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://norules.com/anything")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_500_allows_all(self, mock_get):
        """Server error fetching robots.txt — allow everything."""
        mock_get.return_value = _mock_response(500)
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://broken.com/page")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_empty_disallow_allows_all(self, mock_get):
        """'Disallow:' (empty value) means allow all paths."""
        mock_get.return_value = _mock_response(200, "User-agent: *\nDisallow:\n")
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://open.com/anything")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_html_response_allows_all(self, mock_get):
        """Non-robots content (e.g. Cloudflare challenge) parses as no rules."""
        mock_get.return_value = _mock_response(
            200, "<html><head><title>Challenge</title></head></html>"
        )
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://cloudflare.com/page")

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_uses_custom_user_agent(self, mock_get):
        """Fetches robots.txt with the crawler's own User-Agent."""
        mock_get.return_value = _mock_response(200, "")
        checker = RobotsChecker(user_agent="bwiza-data/0.1", enabled=True)
        checker.is_allowed("https://example.com/page")
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["headers"]["User-Agent"] == "bwiza-data/0.1"

    @patch("apps.targeted_crawler.robots.requests.get")
    def test_timeout_allows_all(self, mock_get):
        import requests

        mock_get.side_effect = requests.Timeout("timeout")
        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://slow.com/page")


class TestDomainRateLimiter:
    def test_first_request_no_wait(self):
        limiter = DomainRateLimiter(delay_s=1.0)
        start = time.monotonic()
        limiter.wait_if_needed("example.com")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_second_request_waits(self):
        limiter = DomainRateLimiter(delay_s=0.15)
        limiter.wait_if_needed("example.com")
        start = time.monotonic()
        limiter.wait_if_needed("example.com")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.1

    def test_different_domains_no_wait(self):
        limiter = DomainRateLimiter(delay_s=1.0)
        limiter.wait_if_needed("a.com")
        start = time.monotonic()
        limiter.wait_if_needed("b.com")
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_normalizes_domain(self):
        limiter = DomainRateLimiter(delay_s=0.15)
        limiter.wait_if_needed("www.Example.COM")
        start = time.monotonic()
        limiter.wait_if_needed("example.com")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.1
