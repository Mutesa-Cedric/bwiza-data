"""URL parsing utilities."""

from urllib.parse import ParseResult, urlparse


def safe_parse_url(url: str) -> ParseResult | None:
    """Parse a URL safely, returning None on failure."""
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return parsed
        return None
    except Exception:
        return None


def get_domain(url: str) -> str:
    """Extract lowercase domain, stripping leading www."""
    parsed = safe_parse_url(url)
    if parsed is None:
        return ""
    domain = parsed.netloc.lower()
    if ":" in domain:
        domain = domain.split(":")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
