"""Bilingual page-pair discovery heuristics for rw↔en."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


@dataclass
class CandidatePair:
    url_rw: str
    url_en: str
    confidence: float
    method: str  # "hreflang" | "url_pattern" | "toggle"


class _HreflangParser(HTMLParser):
    """Extract hreflang link tags from HTML <head>."""

    def __init__(self):
        super().__init__()
        self.hreflangs: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        if tag == "link":
            attr_dict = dict(attrs)
            rel = attr_dict.get("rel", "")
            hreflang = attr_dict.get("hreflang", "")
            href = attr_dict.get("href", "")
            if "alternate" in rel and hreflang and href:
                self.hreflangs[hreflang.lower()] = href


class _ToggleLinkParser(HTMLParser):
    """Find language toggle links by anchor text patterns."""

    RW_PATTERNS = re.compile(r"\b(kinyarwanda|ikinyarwanda)\b", re.IGNORECASE)
    EN_PATTERNS = re.compile(r"\b(english|icyongereza)\b", re.IGNORECASE)

    def __init__(self):
        super().__init__()
        self._current_href = ""
        self._in_a = False
        self.rw_links: list[str] = []
        self.en_links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attr_dict = dict(attrs)
            self._current_href = attr_dict.get("href", "")
            self._in_a = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_a = False
            self._current_href = ""

    def handle_data(self, data):
        if not self._in_a or not self._current_href:
            return
        if self.RW_PATTERNS.search(data):
            self.rw_links.append(self._current_href)
        if self.EN_PATTERNS.search(data):
            self.en_links.append(self._current_href)


# URL path patterns for language switching
_RW_PATH_PATTERNS = ["/rw/", "/rw-rw/", "/kin/"]
_EN_PATH_PATTERNS = ["/en/", "/en-us/", "/en-gb/", "/eng/"]
_LANG_QUERY_PAIRS = [("lang=rw", "lang=en"), ("language=rw", "language=en")]


def find_bilingual_pairs(html_bytes: bytes, page_url: str) -> list[CandidatePair]:
    """Discover bilingual rw↔en page pairs from a single page.

    Tries multiple heuristics in order of reliability:
    1. hreflang links (highest confidence)
    2. Language toggle anchor text
    3. URL path patterns (/rw/ ↔ /en/)
    """
    try:
        html_str = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return []

    pairs: list[CandidatePair] = []

    # 1. hreflang links
    hreflang_pairs = _find_hreflang_pairs(html_str, page_url)
    pairs.extend(hreflang_pairs)

    # 2. Toggle links
    if not pairs:
        toggle_pairs = _find_toggle_pairs(html_str, page_url)
        pairs.extend(toggle_pairs)

    # 3. URL pattern
    if not pairs:
        pattern_pairs = _find_url_pattern_pairs(page_url)
        pairs.extend(pattern_pairs)

    return pairs


def _find_hreflang_pairs(html_str: str, page_url: str) -> list[CandidatePair]:
    parser = _HreflangParser()
    try:
        parser.feed(html_str)
    except Exception:
        return []

    hreflangs = parser.hreflangs
    rw_url = hreflangs.get("rw") or hreflangs.get("rw-rw")
    en_url = hreflangs.get("en") or hreflangs.get("en-us") or hreflangs.get("en-gb")

    if not rw_url or not en_url:
        return []

    rw_url = urljoin(page_url, rw_url)
    en_url = urljoin(page_url, en_url)

    return [CandidatePair(url_rw=rw_url, url_en=en_url, confidence=0.95, method="hreflang")]


def _find_toggle_pairs(html_str: str, page_url: str) -> list[CandidatePair]:
    parser = _ToggleLinkParser()
    try:
        parser.feed(html_str)
    except Exception:
        return []

    if not parser.rw_links or not parser.en_links:
        return []

    rw_url = urljoin(page_url, parser.rw_links[0])
    en_url = urljoin(page_url, parser.en_links[0])

    return [CandidatePair(url_rw=rw_url, url_en=en_url, confidence=0.7, method="toggle")]


def _find_url_pattern_pairs(page_url: str) -> list[CandidatePair]:
    parsed = urlparse(page_url)
    path = parsed.path.lower()
    query = (parsed.query or "").lower()

    # Check path patterns: /rw/ -> /en/
    for rw_pat, en_pat in zip(_RW_PATH_PATTERNS, _EN_PATH_PATTERNS):
        if rw_pat in path:
            en_url = page_url.replace(rw_pat, en_pat, 1)
            return [
                CandidatePair(url_rw=page_url, url_en=en_url, confidence=0.5, method="url_pattern")
            ]
        if en_pat in path:
            rw_url = page_url.replace(en_pat, rw_pat, 1)
            return [
                CandidatePair(url_rw=rw_url, url_en=page_url, confidence=0.5, method="url_pattern")
            ]

    # Check query patterns: lang=rw -> lang=en
    for rw_q, en_q in _LANG_QUERY_PAIRS:
        if rw_q in query:
            en_url = page_url.replace(rw_q, en_q, 1)
            return [
                CandidatePair(url_rw=page_url, url_en=en_url, confidence=0.4, method="url_pattern")
            ]
        if en_q in query:
            rw_url = page_url.replace(en_q, rw_q, 1)
            return [
                CandidatePair(url_rw=rw_url, url_en=page_url, confidence=0.4, method="url_pattern")
            ]

    return []
