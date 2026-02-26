"""Tests for heritage discovery pass."""

from unittest.mock import patch

from apps.common.config_types import AppConfig, HeritageConfig
from apps.heritage.discovery import (
    _classify_url,
    _extract_section,
    _is_excluded,
    _is_on_domain,
    run_discovery,
)
from apps.targeted_crawler.fetch import FetchResult

LISTING_HTML = b"""
<html><body>
<div class="news-list">
  <a href="/news-details/inteko-yumuco">Inteko y'umuco</a>
  <a href="/news-details/umuganura-2025">Umuganura 2025</a>
  <a href="/fileadmin/user_upload/RCHA/Publications/Laws___Policies/amategeko.pdf">PDF</a>
  <a href="/amakuru/page?tx_news_pi1%5BcurrentPage%5D=2&cHash=abc123">Page 2</a>
  <a href="https://external.com/offsite">External</a>
  <a href="/1/ikigo">About</a>
</div>
</body></html>
"""

PAGINATION_HTML = b"""
<html><body>
<div class="news-list">
  <a href="/news-details/heritage-day">Heritage Day</a>
  <a href="/news-details/cultural-fest">Cultural Fest</a>
</div>
</body></html>
"""


def test_classify_url_news():
    assert _classify_url("https://rwandaheritage.gov.rw/news-details/some-article") == "news"


def test_classify_url_pdf():
    assert _classify_url("https://rwandaheritage.gov.rw/fileadmin/doc.pdf") == "pdf"
    assert (
        _classify_url("https://rwandaheritage.gov.rw/fileadmin/user_upload/RCHA/report.pdf")
        == "pdf"
    )


def test_classify_url_listing():
    url = "https://rwandaheritage.gov.rw/amakuru/page?tx_news_pi1%5BcurrentPage%5D=2&cHash=abc"
    assert _classify_url(url) == "listing"


def test_classify_url_static():
    assert _classify_url("https://rwandaheritage.gov.rw/1/ikigo") == "static"


def test_classify_url_fileadmin_image_not_pdf():
    assert _classify_url("https://rwandaheritage.gov.rw/fileadmin/photo.jpg") == "static"


def test_extract_section_amakuru():
    assert _extract_section("https://rwandaheritage.gov.rw/amakuru") == "amakuru"
    assert _extract_section("https://rwandaheritage.gov.rw/news-details/foo") == "amakuru"


def test_extract_section_inyandiko():
    url = "https://rwandaheritage.gov.rw/1/inyandiko/ibitabo-byatangajwe"
    assert _extract_section(url) == "inyandiko/ibitabo-byatangajwe"


def test_extract_section_ikigo():
    assert _extract_section("https://rwandaheritage.gov.rw/1/ikigo") == "ikigo"


def test_is_on_domain():
    assert _is_on_domain("https://rwandaheritage.gov.rw/amakuru", "rwandaheritage.gov.rw")
    assert not _is_on_domain("https://external.com/page", "rwandaheritage.gov.rw")
    assert not _is_on_domain("https://gov.rw/page", "rwandaheritage.gov.rw")


@patch("apps.heritage.discovery.fetch_url")
def test_discovery_finds_news_and_pdf_urls(mock_fetch):
    """Discovery should extract news, PDF, and pagination links from listing pages."""
    call_count = 0

    def _side_effect(url, cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: seed listing page
            return FetchResult(
                url=url,
                status_code=200,
                content_type="text/html",
                content=LISTING_HTML,
                final_url=url,
            )
        else:
            # Pagination pages
            return FetchResult(
                url=url,
                status_code=200,
                content_type="text/html",
                content=PAGINATION_HTML,
                final_url=url,
            )

    mock_fetch.side_effect = _side_effect

    cfg = AppConfig(
        heritage=HeritageConfig(
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=10,
            domain_delay_s=0,
        ),
    )

    result = run_discovery(cfg)

    assert result.pages_crawled >= 1
    assert result.news_count >= 2  # At least the 2 news-details links
    assert result.pdf_count >= 1  # The fileadmin PDF link

    # Verify no off-domain URLs
    for item in result.discovered:
        assert "external.com" not in item.url


@patch("apps.heritage.discovery.fetch_url")
def test_discovery_enforces_domain_lock(mock_fetch):
    """Off-domain links should be excluded from discovery."""
    html = b"""
    <html><body>
    <a href="https://external.com/page">External</a>
    <a href="https://rwandaheritage.gov.rw/news-details/good">Good</a>
    </body></html>
    """
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=html,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    cfg = AppConfig(
        heritage=HeritageConfig(
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=5,
            domain_delay_s=0,
        ),
    )

    result = run_discovery(cfg)

    urls = [item.url for item in result.discovered]
    assert any("/news-details/good" in u for u in urls)
    assert not any("external.com" in u for u in urls)


@patch("apps.heritage.discovery.fetch_url")
def test_discovery_respects_max_listing_pages(mock_fetch):
    """Discovery should stop after max_listing_pages."""
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=LISTING_HTML,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    cfg = AppConfig(
        heritage=HeritageConfig(
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=1,
            domain_delay_s=0,
        ),
    )

    result = run_discovery(cfg)
    assert result.pages_crawled == 1


@patch("apps.heritage.discovery.fetch_url")
def test_discovery_handles_fetch_errors(mock_fetch):
    """Discovery should continue when individual fetches fail."""
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        error="timeout",
    )

    cfg = AppConfig(
        heritage=HeritageConfig(
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=5,
            domain_delay_s=0,
        ),
    )

    result = run_discovery(cfg)
    assert result.pages_crawled == 0
    assert len(result.discovered) == 0


@patch("apps.heritage.discovery.fetch_url")
def test_discovery_preserves_chash_in_pagination(mock_fetch):
    """Pagination links with cHash should be preserved as-is."""
    html = b"""
    <html><body>
    <a href="/amakuru/page?tx_news_pi1%5BcurrentPage%5D=2&cHash=secret123">Page 2</a>
    </body></html>
    """
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=html,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    cfg = AppConfig(
        heritage=HeritageConfig(
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=5,
            domain_delay_s=0,
        ),
    )

    result = run_discovery(cfg)

    listing_urls = [item.url for item in result.discovered if item.url_class == "listing"]
    assert len(listing_urls) >= 1
    # cHash should be preserved in the URL
    assert any("cHash" in u for u in listing_urls)


def test_is_excluded_english_paths():
    assert _is_excluded("https://rwandaheritage.gov.rw/en/updates/news")
    assert _is_excluded("https://rwandaheritage.gov.rw/en/online-services")
    assert _is_excluded("https://rwandaheritage.gov.rw/fr/page")


def test_is_excluded_boilerplate():
    assert _is_excluded("https://rwandaheritage.gov.rw/1/servisi-kuri-murandasi")
    assert _is_excluded("https://rwandaheritage.gov.rw/online-services")


def test_is_excluded_allows_kinyarwanda_content():
    assert not _is_excluded("https://rwandaheritage.gov.rw/amakuru")
    assert not _is_excluded("https://rwandaheritage.gov.rw/news-details/inteko-yumuco")
    assert not _is_excluded("https://rwandaheritage.gov.rw/fileadmin/doc.pdf")
    assert not _is_excluded("https://rwandaheritage.gov.rw/1/inyandiko/ibitabo")


@patch("apps.heritage.discovery.fetch_url")
def test_discovery_excludes_english_paths(mock_fetch):
    """English /en/ paths should be excluded from discovery."""
    html = b"""
    <html><body>
    <a href="https://rwandaheritage.gov.rw/en/updates">English</a>
    <a href="https://rwandaheritage.gov.rw/news-details/good">Good</a>
    <a href="https://rwandaheritage.gov.rw/1/servisi-kuri-murandasi">Boilerplate</a>
    </body></html>
    """
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/amakuru",
        status_code=200,
        content_type="text/html",
        content=html,
        final_url="https://rwandaheritage.gov.rw/amakuru",
    )

    cfg = AppConfig(
        heritage=HeritageConfig(
            seed_listing_urls=["https://rwandaheritage.gov.rw/amakuru"],
            allowed_domain="rwandaheritage.gov.rw",
            max_listing_pages=5,
            domain_delay_s=0,
        ),
    )

    result = run_discovery(cfg)

    urls = [item.url for item in result.discovered]
    assert any("/news-details/good" in u for u in urls)
    assert not any("/en/" in u for u in urls)
    assert not any("servisi-kuri-murandasi" in u for u in urls)
