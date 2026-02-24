"""Tests verifying stable reject reason codes across the pipeline."""

from unittest.mock import patch

from apps.cc_miner.keep import decide_keep
from apps.common.config_types import AppConfig
from apps.common.filters.base import clear_registry
from apps.common.filters.quality import register_quality_filters

# Canonical list of all stable reason codes
STABLE_REASONS = {
    "keep",
    "reject.too_short",
    "reject.lid.not_rw",
    "reject.lid.low_confidence",
    "reject.filter.min_chars",
    "reject.filter.max_chars",
    "reject.filter.min_words",
    "reject.filter.url_ratio",
    "reject.filter.alpha_ratio",
    "reject.filter.repetition",
    "reject.filter.word_ngram_repetition",
    "reject.filter.mixed_script",
}


def _cfg() -> AppConfig:
    cfg = AppConfig()
    cfg.filters.min_chars = 50
    cfg.lid.min_confidence = 0.80
    return cfg


def setup_function():
    clear_registry()
    register_quality_filters()


def test_keep_produces_stable_reason():
    """Every code path returns a reason from the canonical set."""
    cases = []

    # too_short
    cases.append(decide_keep("x", _cfg()))

    # lid.not_rw
    with patch("apps.cc_miner.keep.predict_lang", return_value=("eng_Latn", 0.99, "m")):
        cases.append(decide_keep("a " * 50, _cfg()))

    # lid.low_confidence
    with patch("apps.cc_miner.keep.predict_lang", return_value=("kin_Latn", 0.50, "m")):
        cases.append(decide_keep("a " * 50, _cfg()))

    # keep
    keep_text = (
        "Umuryango wAbibumbye wafashwe mu mwaka wa 1945 nyuma yintambara. "
        "Intego yayo ni amahoro ku isi yose no gukomeza umutekano. "
        "Abanyarwanda benshi bakunze gukora ubuhinzi cyane mu ntara zose. "
        "Igihugu cyItaliya gifite amateka maremare cyane muri Buraya. "
        "Umujyi wa Kigali ni umurwa mukuru wigihugu cyacu gikunda."
    )
    with patch("apps.cc_miner.keep.predict_lang", return_value=("kin_Latn", 0.95, "m")):
        cases.append(decide_keep(keep_text, _cfg()))

    for decision in cases:
        assert decision.reason in STABLE_REASONS, f"Unstable reason: {decision.reason}"


def test_filter_reasons_are_stable():
    """Quality filter rejections use stable reason prefixes."""
    with patch("apps.cc_miner.keep.predict_lang", return_value=("kin_Latn", 0.95, "m")):
        # url_ratio
        result = decide_keep("https://x.com/a " * 50, _cfg())
        assert result.reason in STABLE_REASONS

    with patch("apps.cc_miner.keep.predict_lang", return_value=("kin_Latn", 0.95, "m")):
        # repetition
        cfg = _cfg()
        cfg.filters.max_repeat_line_ratio = 0.01
        text = ("same line\n" * 50) + ("unique text " * 20)
        result = decide_keep(text, cfg)
        assert result.reason in STABLE_REASONS


def test_all_reason_codes_documented():
    """Verify the canonical set covers expected codes."""
    assert "keep" in STABLE_REASONS
    assert all(r.startswith("reject.") for r in STABLE_REASONS if r != "keep")
