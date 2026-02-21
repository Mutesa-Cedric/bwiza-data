"""Tests for parallel corpus extraction pipeline."""

from apps.common.config_types import ParallelConfig
from apps.parallel_corpus.find_pairs import CandidatePair
from apps.parallel_corpus.pipeline import process_candidate_pair
from apps.targeted_crawler.fetch import FetchResult

RW_HTML = b"""
<html><body><main>
<p>Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye.
Guverinoma yashyizeho politiki zo guteza imbere uburezi.</p>
</main></body></html>
"""

EN_HTML = b"""
<html><body><main>
<p>In Rwanda, education is very important for the country's development.
All Rwandans must have access to quality and appropriate education.
The government has put in place policies to promote education.</p>
</main></body></html>
"""


def _cfg():
    return ParallelConfig(min_chars=50, min_lid_conf=0.8)


def _candidate():
    return CandidatePair(
        url_rw="https://example.rw/rw/page",
        url_en="https://example.rw/en/page",
        confidence=0.95,
        method="hreflang",
    )


def _rw_fetch():
    return FetchResult(
        url="https://example.rw/rw/page",
        status_code=200,
        content_type="text/html",
        content=RW_HTML,
        final_url="https://example.rw/rw/page",
    )


def _en_fetch():
    return FetchResult(
        url="https://example.rw/en/page",
        status_code=200,
        content_type="text/html",
        content=EN_HTML,
        final_url="https://example.rw/en/page",
    )


def _mock_lid(text):
    if "Rwanda" in text and "education" in text:
        return ("eng_Latn", 0.95, "glotlid")
    return ("kin_Latn", 0.92, "glotlid")


def test_process_pair_success():
    result = process_candidate_pair(
        _candidate(), _rw_fetch(), _en_fetch(), _cfg(), predict_lang_fn=_mock_lid
    )
    assert result.pair is not None
    assert result.reason == "keep"
    assert result.pair.source == "parallel_web"
    assert result.pair.domain == "example.rw"
    assert result.pair.meta["method"] == "hreflang"


def test_process_pair_fetch_failed():
    bad_fetch = FetchResult(url="https://example.rw/rw/page", error="timeout")
    result = process_candidate_pair(
        _candidate(), bad_fetch, _en_fetch(), _cfg(), predict_lang_fn=_mock_lid
    )
    assert result.pair is None
    assert result.reason == "reject.fetch_failed"


def test_process_pair_rw_too_short():
    short_html = b"<html><body><p>Hi</p></body></html>"
    rw_fetch = FetchResult(
        url="https://example.rw/rw/page",
        status_code=200,
        content_type="text/html",
        content=short_html,
        final_url="https://example.rw/rw/page",
    )
    result = process_candidate_pair(
        _candidate(), rw_fetch, _en_fetch(), _cfg(), predict_lang_fn=_mock_lid
    )
    assert result.pair is None
    # Either extraction_failed or too_short
    assert "reject" in result.reason


def test_process_pair_not_rw():
    def lid_all_english(text):
        return ("eng_Latn", 0.99, "glotlid")

    result = process_candidate_pair(
        _candidate(), _rw_fetch(), _en_fetch(), _cfg(), predict_lang_fn=lid_all_english
    )
    assert result.pair is None
    assert result.reason == "reject.lid.not_rw"


def test_process_pair_low_confidence():
    def lid_low_conf(text):
        if "education" in text:
            return ("eng_Latn", 0.95, "glotlid")
        return ("kin_Latn", 0.5, "glotlid")  # below min_lid_conf

    result = process_candidate_pair(
        _candidate(), _rw_fetch(), _en_fetch(), _cfg(), predict_lang_fn=lid_low_conf
    )
    assert result.pair is None
    assert result.reason == "reject.lid.low_confidence"
