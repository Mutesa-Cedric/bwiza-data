"""Tests for robots.txt and rate limiting."""

import time
from unittest.mock import patch

from apps.targeted_crawler.rate_limit import DomainRateLimiter
from apps.targeted_crawler.robots import RobotsChecker


class TestRobotsChecker:
    def test_disabled_allows_all(self):
        checker = RobotsChecker(user_agent="test", enabled=False)
        assert checker.is_allowed("https://example.com/secret")

    @patch("apps.targeted_crawler.robots.RobotFileParser")
    def test_allowed_url(self, mock_parser_cls):
        parser = mock_parser_cls.return_value
        parser.can_fetch.return_value = True

        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://example.com/page")
        parser.can_fetch.assert_called_once_with("test", "https://example.com/page")

    @patch("apps.targeted_crawler.robots.RobotFileParser")
    def test_disallowed_url(self, mock_parser_cls):
        parser = mock_parser_cls.return_value
        parser.can_fetch.return_value = False

        checker = RobotsChecker(user_agent="test", enabled=True)
        assert not checker.is_allowed("https://example.com/admin")

    @patch("apps.targeted_crawler.robots.RobotFileParser")
    def test_robots_fetch_failure_allows(self, mock_parser_cls):
        parser = mock_parser_cls.return_value
        parser.read.side_effect = Exception("network error")

        checker = RobotsChecker(user_agent="test", enabled=True)
        assert checker.is_allowed("https://example.com/page")

    @patch("apps.targeted_crawler.robots.RobotFileParser")
    def test_caches_per_origin(self, mock_parser_cls):
        parser = mock_parser_cls.return_value
        parser.can_fetch.return_value = True

        checker = RobotsChecker(user_agent="test", enabled=True)
        checker.is_allowed("https://example.com/a")
        checker.is_allowed("https://example.com/b")
        # Should only create one parser and call read once
        assert parser.read.call_count == 1


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
