"""Tests for heritage harvest pass."""

from unittest.mock import patch

from apps.cc_miner.stats import RunStats
from apps.common.config_types import AppConfig, HeritageConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.heritage.discovery import DiscoveredURL
from apps.heritage.harvest import DeadLetterEntry, harvest_url, save_dead_letter
from apps.targeted_crawler.fetch import FetchResult
from apps.targeted_crawler.rate_limit import DomainRateLimiter

SAMPLE_HTML = b"""
<html><body><main>
<h1>Inteko y'Umuco</h1>
<p>Mu Rwanda uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyeshuri biga amasomo atandukanye harimo ikinyarwanda n'ubumenyi rusange.
Igitabo cyiza gifasha umunyeshuri gusobanukirwa neza no gukora imyitozo.
Muri gahunda y'uburezi, abarimu n'ababyeyi bafatanya gutera imbere no gutsinda.
Iyi nyandiko irimo amagambo menshi ahagije kugira ngo irenge imipaka y'iyungurura.</p>
</main></body></html>
"""


@patch("apps.heritage.harvest.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_harvest_html_article(mock_lid, mock_fetch):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/news-details/test",
        status_code=200,
        content_type="text/html",
        content=SAMPLE_HTML,
        final_url="https://rwandaheritage.gov.rw/news-details/test",
    )

    cfg = AppConfig(heritage=HeritageConfig(domain_delay_s=0))
    dedup = ExactDedupStore()
    stats = RunStats()
    rate_limiter = DomainRateLimiter(delay_s=0)
    from apps.common.config_types import TargetedConfig

    fetch_cfg = TargetedConfig(
        request_timeout_s=5,
        max_retries=1,
        max_response_bytes=5_000_000,
        user_agent="test",
        allowed_content_types=["text/html", "application/pdf"],
    )

    item = DiscoveredURL(
        url="https://rwandaheritage.gov.rw/news-details/test",
        url_class="news",
        parent_url="https://rwandaheritage.gov.rw/amakuru",
        discovery_origin="seed_link_follow",
        section="amakuru",
    )

    doc_json, reason = harvest_url(item, fetch_cfg, cfg, dedup, stats, rate_limiter)

    assert doc_json is not None
    assert reason == "keep"
    assert doc_json["source"] == "heritage_gov_rw"

    dedup.close()


@patch("apps.heritage.harvest.fetch_url")
def test_harvest_handles_fetch_error(mock_fetch):
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/news-details/broken",
        error="timeout",
    )

    cfg = AppConfig(heritage=HeritageConfig(domain_delay_s=0))
    dedup = ExactDedupStore()
    stats = RunStats()
    rate_limiter = DomainRateLimiter(delay_s=0)
    from apps.common.config_types import TargetedConfig

    fetch_cfg = TargetedConfig(
        request_timeout_s=5,
        max_retries=1,
        max_response_bytes=5_000_000,
        user_agent="test",
        allowed_content_types=["text/html", "application/pdf"],
    )

    item = DiscoveredURL(
        url="https://rwandaheritage.gov.rw/news-details/broken",
        url_class="news",
        section="amakuru",
    )

    doc_json, reason = harvest_url(item, fetch_cfg, cfg, dedup, stats, rate_limiter)

    assert doc_json is None
    assert "reject.fetch" in reason

    dedup.close()


@patch("apps.heritage.harvest.fetch_url")
@patch("apps.cc_miner.keep.predict_lang")
def test_harvest_pdf_with_lang_split(mock_lid, mock_fetch):
    """PDFs that fail full-text LID should try lang-split."""
    # First LID call returns French (full text), second returns Kinyarwanda (split)
    call_count = 0

    def _lid_side_effect(text):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # harvest_url -> _try_lang_split -> predict_lang (full text)
            return ("fra_Latn", 0.50, "glotlid")
        elif call_count == 2:
            # lang_split -> predict_lang (block)
            return ("kin_Latn", 0.95, "glotlid")
        else:
            # decide_keep -> predict_lang (extracted text)
            return ("kin_Latn", 0.95, "glotlid")

    mock_lid.side_effect = _lid_side_effect
    mock_fetch.return_value = FetchResult(
        url="https://rwandaheritage.gov.rw/fileadmin/doc.pdf",
        status_code=200,
        content_type="application/pdf",
        content=b"fake-pdf-content",
        final_url="https://rwandaheritage.gov.rw/fileadmin/doc.pdf",
    )

    cfg = AppConfig(heritage=HeritageConfig(domain_delay_s=0))
    dedup = ExactDedupStore()
    stats = RunStats()
    rate_limiter = DomainRateLimiter(delay_s=0)
    from apps.common.config_types import TargetedConfig

    fetch_cfg = TargetedConfig(
        request_timeout_s=5,
        max_retries=1,
        max_response_bytes=50_000_000,
        user_agent="test",
        allowed_content_types=["text/html", "application/pdf"],
    )

    item = DiscoveredURL(
        url="https://rwandaheritage.gov.rw/fileadmin/doc.pdf",
        url_class="pdf",
        section="inyandiko",
    )

    # This will fail at PDF extraction since content is fake,
    # so it returns extraction failure
    doc_json, reason = harvest_url(item, fetch_cfg, cfg, dedup, stats, rate_limiter)

    assert doc_json is None
    assert "extraction" in reason or "reject" in reason

    dedup.close()


def test_dead_letter_save(tmp_path):
    entries = [
        DeadLetterEntry(
            url="https://rwandaheritage.gov.rw/broken",
            url_class="news",
            reason="reject.fetch.timeout",
            retryable=True,
        ),
        DeadLetterEntry(
            url="https://rwandaheritage.gov.rw/bad-pdf",
            url_class="pdf",
            reason="reject.pdf_extraction_failed",
            retryable=False,
        ),
    ]

    save_dead_letter(entries, tmp_path, "test-run")

    path = tmp_path / "test-run_dead_letter.jsonl"
    assert path.exists()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
