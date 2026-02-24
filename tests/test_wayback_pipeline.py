"""Tests for the Wayback processing pipeline."""

from unittest.mock import patch

from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.wayback.pipeline import process_wayback_page

# Diverse Kinyarwanda HTML that passes quality filters (30+ words)
RW_HTML = b"""
<html>
<head><title>Amakuru y'u Rwanda</title></head>
<body>
<main>
<p>Mu Rwanda, uburezi ni ingenzi cyane ku iterambere ry'igihugu.
Abanyarwanda bose bagomba kubona uburezi bwiza kandi bukwiye.
Guverinoma y'u Rwanda yashyizeho politiki zitandukanye zo guteza
imbere uburezi mu gihugu hose. Ibi birimo gushyiraho amashuri
mashya no guteza imbere ikoranabuhanga mu burezi bwose.
Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda cyane.
Abantu bo mu turere dutandukanye bafite imico itandukanye koko.
Ubuhinzi bwigihugu bugomba guhindurwa kugirango butange umusaruro.
Inyamaswa zo mu mashyamba azwi muri Afurika zikurura abashakashatsi.
Imyidagaduro itandukanye irimo umupira no kwiruka bikunzwe neza.</p>
</main>
</body>
</html>
"""


@patch("apps.cc_miner.keep.predict_lang")
def test_process_wayback_page_keeps_rw(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, decision = process_wayback_page(
        RW_HTML, "https://igihe.com/article1", "20231215120000", cfg, dedup
    )

    assert doc is not None
    assert decision.keep
    assert doc.source == "wayback"
    assert doc.crawl == "wayback-20231215120000"
    assert doc.lang == "kin_Latn"
    assert "wayback_timestamp" in doc.meta


@patch("apps.cc_miner.keep.predict_lang")
def test_process_wayback_page_rejects_non_rw(mock_lid):
    mock_lid.return_value = ("eng_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, decision = process_wayback_page(
        RW_HTML, "https://igihe.com/en/article", "20231215120000", cfg, dedup
    )

    assert doc is None
    assert not decision.keep
    assert "lid" in decision.reason


def test_process_wayback_page_rejects_extraction_failure():
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, decision = process_wayback_page(
        b"", "https://igihe.com/broken", "20231215120000", cfg, dedup
    )

    assert doc is None
    assert decision.reason == "reject.extraction_failed"


@patch("apps.cc_miner.keep.predict_lang")
def test_process_wayback_page_dedup(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()

    # First time: kept
    doc1, dec1 = process_wayback_page(
        RW_HTML, "https://igihe.com/article1", "20231201000000", cfg, dedup
    )
    assert doc1 is not None

    # Second time: duplicate
    doc2, dec2 = process_wayback_page(
        RW_HTML, "https://igihe.com/article1", "20231215120000", cfg, dedup
    )
    assert doc2 is None
    assert "dedup" in dec2.reason


@patch("apps.cc_miner.keep.predict_lang")
def test_process_wayback_page_has_timestamp_meta(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    cfg = AppConfig()
    dedup = ExactDedupStore()

    doc, _ = process_wayback_page(
        RW_HTML, "https://igihe.com/article1", "20231215120000", cfg, dedup
    )

    assert doc is not None
    assert doc.meta["wayback_timestamp"] == "20231215120000"
    assert doc.crawl == "wayback-20231215120000"
