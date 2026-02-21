"""Tests for bilingual page-pair discovery heuristics."""

from apps.parallel_corpus.find_pairs import find_bilingual_pairs

HREFLANG_HTML = b"""
<html>
<head>
<link rel="alternate" hreflang="rw" href="/rw/page" />
<link rel="alternate" hreflang="en" href="/en/page" />
<link rel="alternate" hreflang="fr" href="/fr/page" />
</head>
<body><p>Content</p></body>
</html>
"""

TOGGLE_HTML = b"""
<html>
<body>
<nav>
<a href="/rw/home">Kinyarwanda</a>
<a href="/en/home">English</a>
</nav>
<p>Main content here</p>
</body>
</html>
"""

NO_LANG_HTML = b"""
<html>
<body><p>Just a regular page with no language switching</p></body>
</html>
"""


class TestHreflangDiscovery:
    def test_finds_rw_en_pair(self):
        pairs = find_bilingual_pairs(HREFLANG_HTML, "https://example.rw/rw/page")
        assert len(pairs) == 1
        assert pairs[0].method == "hreflang"
        assert pairs[0].confidence >= 0.9
        assert "/rw/page" in pairs[0].url_rw
        assert "/en/page" in pairs[0].url_en

    def test_resolves_relative_urls(self):
        pairs = find_bilingual_pairs(HREFLANG_HTML, "https://example.rw/some/path")
        assert pairs[0].url_rw.startswith("https://example.rw")
        assert pairs[0].url_en.startswith("https://example.rw")

    def test_hreflang_rw_rw_variant(self):
        html = b'<html><head><link rel="alternate" hreflang="rw-rw" href="/rw" />'
        html += b'<link rel="alternate" hreflang="en-us" href="/en" /></head></html>'
        pairs = find_bilingual_pairs(html, "https://example.rw/")
        assert len(pairs) == 1
        assert pairs[0].method == "hreflang"


class TestToggleDiscovery:
    def test_finds_toggle_pair(self):
        pairs = find_bilingual_pairs(TOGGLE_HTML, "https://example.rw/")
        assert len(pairs) == 1
        assert pairs[0].method == "toggle"
        assert pairs[0].confidence < 0.9

    def test_toggle_ikinyarwanda(self):
        html = (
            b'<html><body><a href="/rw">Ikinyarwanda</a>'
            b'<a href="/en">Icyongereza</a></body></html>'
        )
        pairs = find_bilingual_pairs(html, "https://example.rw/")
        assert len(pairs) == 1


class TestUrlPatternDiscovery:
    def test_rw_path_pattern(self):
        pairs = find_bilingual_pairs(NO_LANG_HTML, "https://example.rw/rw/article/123")
        assert len(pairs) == 1
        assert pairs[0].method == "url_pattern"
        assert "/en/" in pairs[0].url_en
        assert "/rw/" in pairs[0].url_rw

    def test_en_path_pattern(self):
        pairs = find_bilingual_pairs(NO_LANG_HTML, "https://example.rw/en/article/123")
        assert len(pairs) == 1
        assert "/rw/" in pairs[0].url_rw

    def test_query_pattern(self):
        pairs = find_bilingual_pairs(NO_LANG_HTML, "https://example.rw/page?lang=rw")
        assert len(pairs) == 1
        assert "lang=en" in pairs[0].url_en

    def test_no_pattern_found(self):
        pairs = find_bilingual_pairs(NO_LANG_HTML, "https://example.rw/article/123")
        assert len(pairs) == 0


class TestPriorityOrder:
    def test_hreflang_preferred_over_toggle(self):
        html = b"""<html><head>
        <link rel="alternate" hreflang="rw" href="/rw/p" />
        <link rel="alternate" hreflang="en" href="/en/p" />
        </head><body>
        <a href="/rw2">Kinyarwanda</a><a href="/en2">English</a>
        </body></html>"""
        pairs = find_bilingual_pairs(html, "https://example.rw/")
        assert pairs[0].method == "hreflang"

    def test_empty_html(self):
        pairs = find_bilingual_pairs(b"", "https://example.rw/")
        assert pairs == []

    def test_malformed_html(self):
        pairs = find_bilingual_pairs(b"<html><head>broken", "https://example.rw/")
        assert isinstance(pairs, list)
