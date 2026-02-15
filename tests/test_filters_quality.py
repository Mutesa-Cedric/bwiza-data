"""Tests for core quality filters."""

from apps.common.config_types import AppConfig
from apps.common.filters.base import clear_registry, run_filters
from apps.common.filters.quality import register_quality_filters


def setup_function():
    clear_registry()
    register_quality_filters()


def _cfg(**overrides) -> AppConfig:
    cfg = AppConfig()
    for k, v in overrides.items():
        section, attr = k.split(".")
        setattr(getattr(cfg, section), attr, v)
    return cfg


def test_passes_good_text():
    text = "Muraho neza. " * 50  # long enough, alpha-heavy
    cfg = _cfg()
    passed, reasons = run_filters(text, cfg)
    assert passed is True


def test_rejects_short_text():
    cfg = _cfg(**{"filters.min_chars": 200})
    passed, reasons = run_filters("short", cfg)
    assert passed is False
    assert "reject.filter.min_chars" in reasons


def test_rejects_high_url_ratio():
    text = "https://example.com/very/long/url " * 20
    cfg = _cfg(**{"filters.max_url_ratio": 0.20})
    passed, reasons = run_filters(text, cfg)
    assert passed is False
    assert "reject.filter.url_ratio" in reasons


def test_rejects_low_alpha_ratio():
    text = "12345 67890 !@#$% " * 30
    cfg = _cfg(**{"filters.min_alpha_ratio": 0.70})
    passed, reasons = run_filters(text, cfg)
    assert passed is False
    assert "reject.filter.alpha_ratio" in reasons


def test_rejects_repetitive_text():
    text = "same line\n" * 20
    cfg = _cfg(**{"filters.max_repeat_line_ratio": 0.30})
    passed, reasons = run_filters(text, cfg)
    assert passed is False
    assert "reject.filter.repetition" in reasons


def test_passes_diverse_lines():
    lines = [f"Line number {i} with unique content about topic {i}" for i in range(20)]
    text = "\n".join(lines)
    cfg = _cfg(**{"filters.min_chars": 10})
    passed, reasons = run_filters(text, cfg)
    assert passed is True
