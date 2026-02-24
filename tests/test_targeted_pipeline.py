"""Tests for targeted crawler pipeline (keep decision reuse)."""

from unittest.mock import patch

from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.targeted_crawler.extract import ExtractedDoc
from apps.targeted_crawler.pipeline import process_page

RW_TEXT = (
    "Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu. "
    "Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye. "
    "Guverinoma y'u Rwanda yashyizeho politiki zitandukanye zo guteza "
    "imbere uburezi mu gihugu hose. Ibi birimo gushyiraho amashuri "
    "mashya no guteza imbere ikoranabuhanga mu burezi. "
    "Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda cyane. "
    "Abantu bo mu turere dutandukanye bafite imico itandukanye koko. "
    "Ubuhinzi bwigihugu bugomba guhindurwa kugirango butange umusaruro mwiza. "
    "Inyamaswa zo mu mashyamba azwi muri Afurika zikurura abashakashatsi. "
    "Imyidagaduro itandukanye irimo umupira no kwiruka bikunzwe neza."
)


@patch("apps.cc_miner.keep.predict_lang")
def test_process_page_keeps_rw(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()
    extracted = ExtractedDoc(title="Test Title", text=RW_TEXT)

    doc, decision = process_page(extracted, "https://test.rw/page", cfg, dedup)

    assert doc is not None
    assert decision.keep
    assert doc.source == "targeted_web"
    assert doc.url == "https://test.rw/page"
    assert doc.lang == "kin_Latn"
    assert doc.meta["title"] == "Test Title"


@patch("apps.cc_miner.keep.predict_lang")
def test_process_page_rejects_non_rw(mock_lid):
    mock_lid.return_value = ("eng_Latn", 0.99, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()
    extracted = ExtractedDoc(title="English", text="This is english content. " * 20)

    doc, decision = process_page(extracted, "https://test.rw/en", cfg, dedup)

    assert doc is None
    assert not decision.keep
    assert "not_rw" in decision.reason


@patch("apps.cc_miner.keep.predict_lang")
def test_process_page_dedup(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()
    extracted = ExtractedDoc(title="Test", text=RW_TEXT)

    doc1, _ = process_page(extracted, "https://test.rw/page1", cfg, dedup)
    doc2, decision2 = process_page(extracted, "https://test.rw/page2", cfg, dedup)

    assert doc1 is not None
    assert doc2 is None
    assert decision2.reason == "reject.dedup.exact"


def test_process_page_too_short():
    cfg = AppConfig()
    dedup = ExactDedupStore()
    extracted = ExtractedDoc(title="Short", text="Too short")

    doc, decision = process_page(extracted, "https://test.rw/short", cfg, dedup)

    assert doc is None
    assert decision.reason == "reject.too_short"


@patch("apps.cc_miner.keep.predict_lang")
def test_process_page_no_title(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()
    extracted = ExtractedDoc(title="", text=RW_TEXT)

    doc, _ = process_page(extracted, "https://test.rw/notitle", cfg, dedup)

    assert doc is not None
    assert doc.meta == {}
