"""Link extraction and URL normalization for crawl frontier."""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def extract_links(html_bytes: bytes, base_url: str) -> list[str]:
    """Extract and normalize all <a href> links from HTML."""
    try:
        html_str = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return []

    parser = _LinkParser()
    try:
        parser.feed(html_str)
    except Exception:
        pass

    results = []
    for raw_href in parser.links:
        normalized = normalize_url(raw_href, base_url)
        if normalized:
            results.append(normalized)

    return results


def normalize_url(href: str, base_url: str) -> str | None:
    """Normalize a URL: resolve relative, strip fragments, drop non-http schemes.

    Returns None for invalid/unusable URLs.
    """
    href = href.strip()
    if not href:
        return None

    # Skip non-http schemes
    lower = href.lower()
    if any(lower.startswith(s) for s in ("mailto:", "tel:", "javascript:", "data:", "ftp:")):
        return None

    # Resolve relative URLs
    absolute = urljoin(base_url, href)

    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.hostname:
        return None

    # Strip fragment
    cleaned = urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",  # no fragment
        )
    )

    return cleaned
