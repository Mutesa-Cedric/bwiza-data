"""Tests for URL utilities."""

from apps.common.url_utils import get_domain, safe_parse_url


def test_safe_parse_valid():
    result = safe_parse_url("https://example.com/path")
    assert result is not None
    assert result.netloc == "example.com"


def test_safe_parse_invalid():
    assert safe_parse_url("not a url") is None
    assert safe_parse_url("") is None


def test_safe_parse_no_scheme():
    assert safe_parse_url("example.com") is None


def test_get_domain_basic():
    assert get_domain("https://example.com/page") == "example.com"


def test_get_domain_strips_www():
    assert get_domain("https://www.example.com/page") == "example.com"


def test_get_domain_lowercase():
    assert get_domain("https://EXAMPLE.COM/page") == "example.com"


def test_get_domain_with_port():
    assert get_domain("https://example.com:8080/page") == "example.com"


def test_get_domain_invalid():
    assert get_domain("garbage") == ""
    assert get_domain("") == ""
