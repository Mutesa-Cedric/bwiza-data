"""Tests for Wikipedia processing pipeline."""

from unittest.mock import patch

from apps.common.config_types import AppConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.wiki_miner.extract import WikiArticle
from apps.wiki_miner.pipeline import (
    WikiRunReport,
    process_article,
    process_articles,
)

# Realistic Kinyarwanda text (>200 chars for min_chars filter)
RW_TEXT = (
    "U Rwanda ni igihugu kiri mu burasirazuba bw'Afurika. "
    "Umurwa mukuru w'u Rwanda ni Kigali. "
    "U Rwanda rufite abaturage bagera kuri miliyoni cumi n'ebyiri. "
    "Igihugu cy'u Rwanda kiherereye mu turere dutandukanye. "
    "Ubukungu bw'u Rwanda burimo gukura cyane mu myaka ya vuba. "
    "Amateka y'u Rwanda aratandukanye kandi arakomeye cyane."
)


def _make_article(title="U Rwanda", text=None, page_id=1):
    return WikiArticle(title=title, text=text or RW_TEXT, page_id=page_id)


def _mock_predict_lang(text):
    """Mock LID returning Kinyarwanda with high confidence."""
    return ("kin_Latn", 0.98, "glotlid")


@patch("apps.cc_miner.keep.predict_lang", side_effect=_mock_predict_lang)
def test_process_article_keeps_good_rw(mock_lid):
    cfg = AppConfig()
    dedup = ExactDedupStore()
    article = _make_article()

    doc, decision = process_article(article, cfg, dedup)

    assert doc is not None
    assert decision.keep is True
    assert doc.source == "wikipedia"
    assert doc.lang == "kin_Latn"
    assert doc.url is not None and "U_Rwanda" in doc.url
    assert doc.meta["title"] == "U Rwanda"
    assert doc.meta["page_id"] == 1
    assert doc.crawl == "wikipedia-dump"


@patch("apps.cc_miner.keep.predict_lang", side_effect=_mock_predict_lang)
def test_process_article_rejects_short(mock_lid):
    cfg = AppConfig()
    dedup = ExactDedupStore()
    article = _make_article(text="Too short")

    doc, decision = process_article(article, cfg, dedup)

    assert doc is None
    assert decision.keep is False
    assert "too_short" in decision.reason


@patch("apps.cc_miner.keep.predict_lang", return_value=("eng_Latn", 0.99, "glotlid"))
def test_process_article_rejects_non_rw(mock_lid):
    cfg = AppConfig()
    dedup = ExactDedupStore()
    article = _make_article(text="This is a long English text. " * 20)

    doc, decision = process_article(article, cfg, dedup)

    assert doc is None
    assert "not_rw" in decision.reason


@patch("apps.cc_miner.keep.predict_lang", side_effect=_mock_predict_lang)
def test_process_article_dedup_catches_duplicate(mock_lid):
    cfg = AppConfig()
    dedup = ExactDedupStore()
    article = _make_article()

    # First time — kept
    doc1, _ = process_article(article, cfg, dedup)
    assert doc1 is not None

    # Second time — duplicate
    doc2, decision2 = process_article(article, cfg, dedup)
    assert doc2 is None
    assert "dedup" in decision2.reason


@patch("apps.cc_miner.keep.predict_lang", side_effect=_mock_predict_lang)
def test_process_articles_yields_docs(mock_lid):
    cfg = AppConfig()
    dedup = ExactDedupStore()
    articles = [
        _make_article(title="Article 1", page_id=1),
        _make_article(title="Article 2", page_id=2, text=RW_TEXT + " Ikindi kintu."),
    ]

    results = list(process_articles(iter(articles), cfg, dedup))
    assert len(results) == 2

    # Each result is (doc, report)
    doc1, report1 = results[0]
    doc2, report2 = results[1]

    assert doc1.meta["title"] == "Article 1"
    assert doc2.meta["title"] == "Article 2"
    assert report2.articles_seen == 2
    assert report2.articles_kept == 2


@patch("apps.cc_miner.keep.predict_lang", side_effect=_mock_predict_lang)
def test_process_articles_tracks_rejections(mock_lid):
    cfg = AppConfig()
    dedup = ExactDedupStore()
    articles = [
        _make_article(text="Too short"),  # rejected
        _make_article(title="Good", page_id=2),  # kept
    ]

    results = list(process_articles(iter(articles), cfg, dedup))
    assert len(results) == 1

    _, report = results[0]
    assert report.articles_seen == 2
    assert report.articles_kept == 1
    assert report.reject_reasons["reject.too_short"] == 1


@patch("apps.cc_miner.keep.predict_lang", side_effect=_mock_predict_lang)
def test_process_articles_respects_max_articles(mock_lid):
    cfg = AppConfig()
    cfg.wiki.max_articles = 1
    dedup = ExactDedupStore()
    articles = [
        _make_article(title="A1", page_id=1),
        _make_article(title="A2", page_id=2, text=RW_TEXT + " Ikindi."),
    ]

    results = list(process_articles(iter(articles), cfg, dedup))
    assert len(results) == 1


def test_wiki_run_report_to_dict():
    report = WikiRunReport(articles_seen=100, articles_kept=80, total_kept_chars=50000)
    d = report.to_dict()
    assert d["keep_rate"] == 0.8
    assert d["articles_seen"] == 100


def test_wiki_run_report_empty():
    report = WikiRunReport()
    d = report.to_dict()
    assert d["keep_rate"] == 0.0
