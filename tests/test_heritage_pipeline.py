"""Tests for heritage pipeline (keep/dedup/Document)."""

from unittest.mock import patch

import pytest

from apps.common.config_types import AppConfig, FiltersConfig, HeritageConfig
from apps.common.dedup_exact import ExactDedupStore
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters
from apps.heritage.pipeline import process_heritage_doc
from apps.targeted_crawler.extract import ExtractedDoc

# Diverse Kinyarwanda text that passes ngram filters
SAMPLE_KIN_TEXT = (
    "Mu Rwanda uburezi ni ingenzi cyane ku iterambere ry'igihugu. "
    "Abanyeshuri biga amasomo atandukanye harimo ikinyarwanda n'ubumenyi rusange. "
    "Igitabo cyiza gifasha umunyeshuri gusobanukirwa neza no gukora imyitozo. "
    "Muri gahunda y'uburezi, abarimu n'ababyeyi bafatanya gutera imbere no gutsinda. "
    "Iyi nyandiko irimo amagambo menshi ahagije kugira ngo irenge imipaka y'iyungurura. "
    "Umuco w'u Rwanda ugaragazwa n'imigenzo myiza y'abanyarwanda. "
    "Inteko y'umuco ishinzwe kubungabunga umurage w'igihugu. "
    "Amateka y'u Rwanda arakomeye kandi afite agaciro kenshi. "
    "Inyandiko z'amateka zigomba kubikwa neza kugira ngo zibere ababana n'abazabakomokaho. "
    "Umurage kamere w'igihugu ugomba kurindwa no gutezwa imbere."
)


@pytest.fixture(autouse=True)
def _reset_filters():
    """Ensure quality filters are in a clean state for each test."""
    clear_registry()
    register_quality_filters()


def _heritage_cfg() -> AppConfig:
    """Build AppConfig with heritage filter overrides applied (mirrors runner)."""
    hcfg = HeritageConfig()
    return AppConfig(
        heritage=hcfg,
        filters=FiltersConfig(
            max_chars=hcfg.max_chars,
            max_word_ngram_rep_2=hcfg.max_word_ngram_rep_2,
            max_word_ngram_rep_3=hcfg.max_word_ngram_rep_3,
            max_word_ngram_rep_4=hcfg.max_word_ngram_rep_4,
        ),
    )


@patch("apps.cc_miner.keep.predict_lang")
def test_keeps_rw_document(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")

    cfg = _heritage_cfg()
    dedup = ExactDedupStore()

    extracted = ExtractedDoc(title="Test Article", text=SAMPLE_KIN_TEXT)

    doc, decision = process_heritage_doc(
        extracted,
        "https://rwandaheritage.gov.rw/news-details/test",
        "news",
        "amakuru",
        "seed_link_follow",
        cfg,
        dedup,
    )

    assert doc is not None
    assert decision.keep is True
    assert doc.source == "heritage_gov_rw"
    assert doc.crawl == "heritage-site"
    assert doc.meta["url_class"] == "news"
    assert doc.meta["section"] == "amakuru"
    assert doc.meta["license_status"] == "government"
    assert doc.meta["source_institution"] == "Rwanda Cultural Heritage Academy"
    assert doc.meta["discovery_origin"] == "seed_link_follow"
    assert doc.meta["retrieval_date"]  # non-empty date string

    dedup.close()


@patch("apps.cc_miner.keep.predict_lang")
def test_rejects_non_rw_document(mock_lid):
    mock_lid.return_value = ("eng_Latn", 0.92, "glotlid")

    cfg = _heritage_cfg()
    dedup = ExactDedupStore()

    extracted = ExtractedDoc(
        title="English Article",
        text="This is an English article about Rwanda heritage. " * 10,
    )

    doc, decision = process_heritage_doc(
        extracted,
        "https://rwandaheritage.gov.rw/en/test",
        "news",
        "amakuru",
        "seed_link_follow",
        cfg,
        dedup,
    )

    assert doc is None
    assert decision.keep is False
    assert "reject" in decision.reason

    dedup.close()


@patch("apps.cc_miner.keep.predict_lang")
def test_dedup_catches_duplicate(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")

    cfg = _heritage_cfg()
    dedup = ExactDedupStore()

    extracted = ExtractedDoc(title="Article", text=SAMPLE_KIN_TEXT)

    # First call: kept
    doc1, _ = process_heritage_doc(
        extracted,
        "https://rwandaheritage.gov.rw/news-details/a",
        "news",
        "amakuru",
        "seed_link_follow",
        cfg,
        dedup,
    )
    assert doc1 is not None

    # Second call: duplicate
    doc2, decision2 = process_heritage_doc(
        extracted,
        "https://rwandaheritage.gov.rw/news-details/b",
        "news",
        "amakuru",
        "seed_link_follow",
        cfg,
        dedup,
    )
    assert doc2 is None
    assert "dedup" in decision2.reason

    dedup.close()


@patch("apps.cc_miner.keep.predict_lang")
def test_pdf_document_metadata(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.90, "glotlid")

    cfg = _heritage_cfg()
    dedup = ExactDedupStore()

    text = (
        "Amategeko y'u Rwanda ku muco n'umutungo kamere urimo ibidukikije. "
        "Itegeko rigenga umurage w'umuco w'igihugu ryemejwe n'inteko ishinga amategeko. "
        "Ingingo ya mbere ivuga ku nshingano z'igihugu mu kubungabunga umutungo. "
        "Ingingo ya kabiri igena inzego zishinzwe gushyira mu bikorwa iri tegeko. "
        "Icyiciro cya gatatu kivuga ku myitwarire y'abaturage mu kubungabunga umurage. "
        "Ingingo ya gatanu igena ibihano ku barenganya amategeko y'umuco. "
        "Itegeko ritangira gukurikizwa nyuma y'iminsi mirongo itatu rishyizweho umukono."
    )
    extracted = ExtractedDoc(title="Amategeko", text=text)

    doc, decision = process_heritage_doc(
        extracted,
        "https://rwandaheritage.gov.rw/fileadmin/user_upload/RCHA/Publications/amategeko.pdf",
        "pdf",
        "inyandiko/amategeko",
        "seed_link_follow",
        cfg,
        dedup,
    )

    assert doc is not None
    assert doc.meta["url_class"] == "pdf"
    assert doc.meta["section"] == "inyandiko/amategeko"

    dedup.close()
