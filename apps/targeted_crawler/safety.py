"""Safety checks for targeted crawler: redirect enforcement, content filtering."""

from urllib.parse import urlparse

from apps.targeted_crawler.seeds import canonical_domain

# File extensions that should never be crawled
SKIP_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".rar",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".ico",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".exe",
        ".dmg",
        ".msi",
        ".deb",
        ".rpm",
        ".css",
        ".js",
        ".json",
        ".xml",
        ".rss",
        ".atom",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
    }
)


def is_safe_url(url: str, allowed_domains: set[str]) -> tuple[bool, str]:
    """Check if a URL is safe to crawl.

    Returns (is_safe, reason) where reason explains why it's not safe.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False, "bad_scheme"

    if not parsed.hostname:
        return False, "no_hostname"

    domain = canonical_domain(parsed.hostname)
    if domain not in allowed_domains:
        return False, "off_allowlist"

    # Check path extension
    path_lower = parsed.path.lower()
    for ext in SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return False, f"skip_extension:{ext}"

    return True, "ok"


def check_redirect_safety(
    original_url: str, final_url: str, allowed_domains: set[str]
) -> tuple[bool, str]:
    """Check if a redirect target is still within allowed scope.

    Returns (is_safe, reason).
    """
    if not final_url or final_url == original_url:
        return True, "no_redirect"

    final_parsed = urlparse(final_url)
    if not final_parsed.hostname:
        return False, "redirect_no_hostname"

    final_domain = canonical_domain(final_parsed.hostname)
    if final_domain not in allowed_domains:
        return False, "redirect_off_allowlist"

    return True, "ok"
