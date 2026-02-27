"""Tests for the institutional wave 2 pipeline."""

from __future__ import annotations

from unittest.mock import patch

from apps.institutional.discovery import _classify_url, _extract_section, _is_excluded
from apps.institutional.source_profile import SourceProfile, load_profiles

# ── Source Profile Tests ──────────────────────────────────


def test_load_profiles(tmp_path):
    yaml_content = """\
sources:
  - name: "Test Institution"
    domain: "test.gov.rw"
    output_source: "test_gov_rw"
    license_status: "government"
    seeds:
      - "https://test.gov.rw"
      - "https://test.gov.rw/news"
    excluded_path_prefixes:
      - "/en/"
"""
    p = tmp_path / "profiles.yaml"
    p.write_text(yaml_content)
    profiles = load_profiles(p)
    assert len(profiles) == 1
    assert profiles[0].name == "Test Institution"
    assert profiles[0].domain == "test.gov.rw"
    assert profiles[0].output_source == "test_gov_rw"
    assert profiles[0].license_status == "government"
    assert len(profiles[0].seeds) == 2
    assert profiles[0].excluded_path_prefixes == ["/en/"]


def test_load_profiles_missing_file():
    profiles = load_profiles("/nonexistent/path.yaml")
    assert profiles == []


def test_load_profiles_defaults(tmp_path):
    yaml_content = """\
sources:
  - name: "Minimal"
    domain: "min.gov.rw"
    output_source: "min_gov_rw"
"""
    p = tmp_path / "profiles.yaml"
    p.write_text(yaml_content)
    profiles = load_profiles(p)
    assert profiles[0].license_status == "government"
    assert profiles[0].excluded_path_prefixes == ["/en/", "/fr/"]
    assert profiles[0].seeds == []


# ── Generic Discovery Tests ──────────────────────────────


def test_classify_url_pdf():
    assert _classify_url("https://example.gov.rw/report.pdf") == "pdf"


def test_classify_url_document():
    assert _classify_url("https://example.gov.rw/report.docx") == "document"
    assert _classify_url("https://example.gov.rw/report.doc") == "document"
    assert _classify_url("https://example.gov.rw/slides.pptx") == "document"


def test_classify_url_fileadmin():
    assert _classify_url("https://example.gov.rw/fileadmin/report") == "pdf"


def test_classify_url_page():
    assert _classify_url("https://example.gov.rw/news/article-1") == "page"
    assert _classify_url("https://example.gov.rw/") == "page"


def test_is_excluded_english():
    profile = SourceProfile(
        name="Test",
        domain="test.gov.rw",
        output_source="test",
        license_status="government",
        excluded_path_prefixes=["/en/", "/fr/"],
    )
    assert _is_excluded("https://test.gov.rw/en/home", profile)
    assert _is_excluded("https://test.gov.rw/fr/accueil", profile)
    assert not _is_excluded("https://test.gov.rw/amakuru", profile)


def test_is_excluded_static_assets():
    profile = SourceProfile(
        name="Test",
        domain="test.gov.rw",
        output_source="test",
        license_status="government",
    )
    assert _is_excluded("https://test.gov.rw/logo.png", profile)
    assert _is_excluded("https://test.gov.rw/style.css", profile)
    assert _is_excluded("https://test.gov.rw/app.js", profile)
    assert not _is_excluded("https://test.gov.rw/report.pdf", profile)


def test_extract_section():
    assert _extract_section("https://example.gov.rw/news/article-1") == "news"
    assert _extract_section("https://example.gov.rw/publications/report") == "publications"
    assert _extract_section("https://example.gov.rw/") == "root"


# ── Discovery Integration Test ───────────────────────────


def test_discovery_follows_links():
    """Test that discovery follows HTML page links and classifies URLs."""
    from apps.institutional.discovery import run_discovery

    profile = SourceProfile(
        name="Test",
        domain="test.gov.rw",
        output_source="test",
        license_status="government",
        seeds=["https://test.gov.rw"],
    )

    html_content = b"""<html><body>
    <a href="/news/article-1">Article 1</a>
    <a href="/docs/report.pdf">Report PDF</a>
    <a href="/en/english">English</a>
    <a href="https://other.com/page">Off domain</a>
    <a href="/news/article-2">Article 2</a>
    </body></html>"""

    from apps.common.config import load_config
    from apps.targeted_crawler.fetch import FetchResult

    cfg = load_config()
    cfg.heritage.max_listing_pages = 5

    call_count = 0

    def mock_fetch(url, _cfg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First call: seed page with links
            return FetchResult(
                url=url,
                status_code=200,
                content=html_content,
                content_type="text/html",
                final_url=url,
            )
        # Subsequent pages: empty
        return FetchResult(
            url=url,
            status_code=200,
            content=b"<html></html>",
            content_type="text/html",
            final_url=url,
        )

    with patch("apps.institutional.discovery.fetch_url", side_effect=mock_fetch):
        result = run_discovery(profile, cfg)

    urls = {d.url for d in result.discovered}
    classes = {d.url: d.url_class for d in result.discovered}

    # Should find: seed page + 2 news articles + 1 PDF
    assert "https://test.gov.rw/docs/report.pdf" in urls
    assert classes.get("https://test.gov.rw/docs/report.pdf") == "pdf"
    # English page should be excluded
    assert "https://test.gov.rw/en/english" not in urls
    # Off-domain should be excluded
    assert "https://other.com/page" not in urls
    assert result.pdf_count >= 1


# ── Pipeline Parameterization Test ────────────────────────


def test_process_heritage_doc_custom_metadata():
    """Test that process_heritage_doc accepts custom institution metadata."""
    from apps.common.config import load_config
    from apps.common.dedup_exact import ExactDedupStore
    from apps.heritage.pipeline import process_heritage_doc
    from apps.targeted_crawler.extract import ExtractedDoc

    cfg = load_config()
    cfg.lid.min_confidence = 0.5

    extracted = ExtractedDoc(title="Test", text="A" * 200)

    dedup = ExactDedupStore()

    with (
        patch("apps.cc_miner.keep.predict_lang") as mock_lid,
        patch("apps.cc_miner.keep.run_filters", return_value=(True, "")),
    ):
        mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")

        doc, decision = process_heritage_doc(
            extracted,
            "https://test.gov.rw/page",
            "page",
            "news",
            "seed_manual",
            cfg,
            dedup,
            output_source="test_gov_rw",
            source_institution="Test Institution",
            license_status="government",
            crawl_tag="institutional-test.gov.rw",
        )

    assert doc is not None
    assert doc.source == "test_gov_rw"
    assert doc.crawl == "institutional-test.gov.rw"
    assert doc.meta["source_institution"] == "Test Institution"
    assert doc.meta["license_status"] == "government"
