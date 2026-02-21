"""Tests for link extraction and URL normalization."""

from apps.targeted_crawler.links import extract_links, normalize_url

SAMPLE_HTML = b"""
<html>
<body>
<a href="/about">About</a>
<a href="https://example.com/contact">Contact</a>
<a href="page.html">Page</a>
<a href="#section">Section</a>
<a href="mailto:info@example.com">Email</a>
<a href="javascript:void(0)">JS</a>
<a href="tel:+250123456">Phone</a>
<a href="https://other.com/page#frag">Other</a>
</body>
</html>
"""


class TestExtractLinks:
    def test_extracts_links(self):
        links = extract_links(SAMPLE_HTML, "https://example.com/")
        assert "https://example.com/about" in links
        assert "https://example.com/contact" in links

    def test_resolves_relative_urls(self):
        links = extract_links(SAMPLE_HTML, "https://example.com/dir/")
        assert "https://example.com/dir/page.html" in links

    def test_drops_mailto(self):
        links = extract_links(SAMPLE_HTML, "https://example.com/")
        assert not any("mailto" in link for link in links)

    def test_drops_javascript(self):
        links = extract_links(SAMPLE_HTML, "https://example.com/")
        assert not any("javascript" in link for link in links)

    def test_drops_tel(self):
        links = extract_links(SAMPLE_HTML, "https://example.com/")
        assert not any("tel:" in link for link in links)

    def test_strips_fragments(self):
        links = extract_links(SAMPLE_HTML, "https://example.com/")
        for link in links:
            assert "#" not in link

    def test_empty_html(self):
        assert extract_links(b"", "https://example.com/") == []

    def test_malformed_html(self):
        html = b"<a href='/ok'><div><a href='/also'>"
        links = extract_links(html, "https://example.com/")
        assert len(links) == 2


class TestNormalizeUrl:
    def test_absolute_url(self):
        assert (
            normalize_url("https://example.com/page", "https://base.com/")
            == "https://example.com/page"
        )

    def test_relative_url(self):
        assert normalize_url("/about", "https://example.com/") == "https://example.com/about"

    def test_strip_fragment(self):
        result = normalize_url("https://example.com/page#top", "https://base.com/")
        assert result == "https://example.com/page"

    def test_mailto_returns_none(self):
        assert normalize_url("mailto:x@y.com", "https://base.com/") is None

    def test_javascript_returns_none(self):
        assert normalize_url("javascript:void(0)", "https://base.com/") is None

    def test_empty_returns_none(self):
        assert normalize_url("", "https://base.com/") is None

    def test_lowercases_host(self):
        result = normalize_url("https://EXAMPLE.COM/Page", "https://base.com/")
        assert result == "https://example.com/Page"

    def test_preserves_query(self):
        result = normalize_url("https://example.com/s?q=test", "https://base.com/")
        assert result == "https://example.com/s?q=test"

    def test_ftp_returns_none(self):
        assert normalize_url("ftp://files.example.com/data", "https://base.com/") is None
