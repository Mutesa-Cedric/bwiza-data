"""Tests for CC index pipeline (WARC HTML -> extract -> keep -> dedup)."""

from unittest.mock import patch

import pytest

from apps.cc_index.pipeline import process_warc_html
from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters


@pytest.fixture(autouse=True)
def _ensure_filters():
    """Ensure quality filters are registered regardless of test ordering."""
    clear_registry()
    register_quality_filters()


SAMPLE_HTML = (
    b"<html><body><main><p>"
    b"Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu. "
    b"Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye. "
    b"Guverinoma yashyizeho politiki zitandukanye zo guteza imbere "
    b"uburezi mu gihugu hose. Ibi birimo gushyiraho amashuri mashya "
    b"no guteza imbere ikoranabuhanga mu mashuri. Abarimu bakora "
    b"umurimo ukomeye wo kwigisha abana amasomo yose akenewe. "
    b"Ababyeyi nabo bafasha abana babo kwiga mu rugo. Igihugu "
    b"cyose kigomba gufatanya kugira ngo uburezi burusheho kuba bwiza."
    b"</p></main></body></html>"
)


@patch("apps.cc_miner.keep.predict_lang")
def test_keeps_kinyarwanda_html(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, decision = process_warc_html(
        SAMPLE_HTML, "https://umuseke.rw/article", "CC-MAIN-2025-51", cfg, dedup
    )

    assert doc is not None
    assert decision.keep
    assert doc.source == "cc_index"
    assert doc.crawl == "CC-MAIN-2025-51"
    assert doc.url == "https://umuseke.rw/article"
    assert doc.lang == "kin_Latn"


@patch("apps.cc_miner.keep.predict_lang")
def test_rejects_english(mock_lid):
    mock_lid.return_value = ("eng_Latn", 0.99, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()
    html = b"<html><body><p>" + b"This is english content. " * 20 + b"</p></body></html>"

    doc, decision = process_warc_html(html, "https://a.rw/en", "CC-MAIN-2025-51", cfg, dedup)

    assert doc is None
    assert not decision.keep
    assert "not_rw" in decision.reason


@patch("apps.cc_miner.keep.predict_lang")
def test_deduplicates(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc1, _ = process_warc_html(SAMPLE_HTML, "https://a.rw/page1", "CC-MAIN-2025-51", cfg, dedup)
    doc2, decision2 = process_warc_html(
        SAMPLE_HTML, "https://a.rw/page2", "CC-MAIN-2025-51", cfg, dedup
    )

    assert doc1 is not None
    assert doc2 is None
    assert decision2.reason == "reject.dedup.exact"


def test_rejects_empty_html():
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, decision = process_warc_html(
        b"<html><body></body></html>", "https://a.rw/empty", "CC-MAIN-2025-51", cfg, dedup
    )

    assert doc is None
    assert not decision.keep


def test_rejects_non_html():
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, decision = process_warc_html(
        b"not html at all", "https://a.rw/bad", "CC-MAIN-2025-51", cfg, dedup
    )

    assert doc is None
    assert not decision.keep
