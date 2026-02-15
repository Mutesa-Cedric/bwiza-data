"""Tests for keep decision function (mocked LID)."""

from unittest.mock import patch

from apps.cc_miner.keep import decide_keep
from apps.common.config_types import AppConfig
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters


def _cfg() -> AppConfig:
    cfg = AppConfig()
    cfg.filters.min_chars = 50
    cfg.lid.min_confidence = 0.80
    return cfg


def setup_function():
    clear_registry()
    register_quality_filters()


@patch("apps.cc_miner.keep.predict_lang")
def test_keep_rw_document(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    text = "Muraho neza. " * 20
    result = decide_keep(text, _cfg())
    assert result.keep is True
    assert result.reason == "keep"
    assert result.lid_score == 0.95


@patch("apps.cc_miner.keep.predict_lang")
def test_reject_non_rw(mock_lid):
    mock_lid.return_value = ("eng_Latn", 0.95, "glotlid")
    text = "Hello world. " * 20
    result = decide_keep(text, _cfg())
    assert result.keep is False
    assert result.reason == "reject.lid.not_rw"


@patch("apps.cc_miner.keep.predict_lang")
def test_reject_low_confidence(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.50, "glotlid")
    text = "Muraho neza. " * 20
    result = decide_keep(text, _cfg())
    assert result.keep is False
    assert result.reason == "reject.lid.low_confidence"


def test_reject_too_short():
    text = "short"
    result = decide_keep(text, _cfg())
    assert result.keep is False
    assert result.reason == "reject.too_short"


@patch("apps.cc_miner.keep.predict_lang")
def test_reject_filter_failure(mock_lid):
    mock_lid.return_value = ("kin_Latn", 0.95, "glotlid")
    text = "https://spam.com/link " * 50  # high URL ratio
    result = decide_keep(text, _cfg())
    assert result.keep is False
    assert "reject.filter" in result.reason
