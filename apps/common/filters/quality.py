"""Core quality filters."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import TYPE_CHECKING

from apps.common.filters.base import FilterResult, register_filter

if TYPE_CHECKING:
    from apps.common.config_types import AppConfig

_URL_PATTERN = re.compile(r"https?://\S+")


def _min_chars_filter(text: str, cfg: AppConfig) -> FilterResult:
    threshold = cfg.filters.min_chars
    if len(text) < threshold:
        return FilterResult(passed=False, reason="reject.filter.min_chars")
    return FilterResult(passed=True, reason="keep")


def _max_chars_filter(text: str, cfg: AppConfig) -> FilterResult:
    if len(text) > cfg.filters.max_chars:
        return FilterResult(
            passed=False,
            reason="reject.filter.max_chars",
            metrics={"char_count": len(text)},
        )
    return FilterResult(passed=True, reason="keep")


def _min_words_filter(text: str, cfg: AppConfig) -> FilterResult:
    word_count = len(text.split())
    if word_count < cfg.filters.min_words:
        return FilterResult(
            passed=False,
            reason="reject.filter.min_words",
            metrics={"word_count": word_count},
        )
    return FilterResult(passed=True, reason="keep")


def _url_ratio_filter(text: str, cfg: AppConfig) -> FilterResult:
    if not text:
        return FilterResult(passed=True, reason="keep")
    url_chars = sum(len(m.group()) for m in _URL_PATTERN.finditer(text))
    ratio = url_chars / len(text)
    if ratio > cfg.filters.max_url_ratio:
        return FilterResult(
            passed=False,
            reason="reject.filter.url_ratio",
            metrics={"url_ratio": round(ratio, 4)},
        )
    return FilterResult(passed=True, reason="keep")


def _alpha_ratio_filter(text: str, cfg: AppConfig) -> FilterResult:
    if not text:
        return FilterResult(passed=False, reason="reject.filter.alpha_ratio")
    alpha_count = sum(1 for c in text if c.isalpha())
    ratio = alpha_count / len(text)
    if ratio < cfg.filters.min_alpha_ratio:
        return FilterResult(
            passed=False,
            reason="reject.filter.alpha_ratio",
            metrics={"alpha_ratio": round(ratio, 4)},
        )
    return FilterResult(passed=True, reason="keep")


def _repetition_filter(text: str, cfg: AppConfig) -> FilterResult:
    counts = Counter(line.strip() for line in text.split("\n") if line.strip())
    if not counts:
        return FilterResult(passed=True, reason="keep")
    total = sum(counts.values())
    # Need enough lines for the ratio to be meaningful; with <=3 non-empty
    # lines the most-common ratio is always >=0.33, producing false positives.
    if total <= 3:
        return FilterResult(passed=True, reason="keep")
    most_common_count = counts.most_common(1)[0][1]
    repeat_ratio = most_common_count / total
    if repeat_ratio > cfg.filters.max_repeat_line_ratio:
        return FilterResult(
            passed=False,
            reason="reject.filter.repetition",
            metrics={"repeat_line_ratio": round(repeat_ratio, 4)},
        )
    return FilterResult(passed=True, reason="keep")


def _word_ngram_repetition_filter(text: str, cfg: AppConfig) -> FilterResult:
    words = text.split()
    if len(words) < 10:
        return FilterResult(passed=True, reason="keep")

    for n, attr in (
        (2, "max_word_ngram_rep_2"),
        (3, "max_word_ngram_rep_3"),
        (4, "max_word_ngram_rep_4"),
    ):
        if len(words) < n:
            continue
        threshold = getattr(cfg.filters, attr)
        ngrams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
        total = len(ngrams)
        if total == 0:
            continue
        counts = Counter(ngrams)
        repeated_slots = sum(c for c in counts.values() if c > 1)
        ratio = repeated_slots / total
        if ratio > threshold:
            return FilterResult(
                passed=False,
                reason="reject.filter.word_ngram_repetition",
                metrics={"ngram_n": n, "repetition_ratio": round(ratio, 4)},
            )
    return FilterResult(passed=True, reason="keep")


def _is_latin(c: str) -> bool:
    """Check if a character belongs to a Latin script block."""
    name = unicodedata.name(c, "")
    return "LATIN" in name


def _mixed_script_filter(text: str, cfg: AppConfig) -> FilterResult:
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return FilterResult(passed=True, reason="keep")

    non_latin = sum(1 for c in alpha_chars if not _is_latin(c))
    ratio = non_latin / len(alpha_chars)
    if ratio > cfg.filters.max_non_latin_alpha_ratio:
        return FilterResult(
            passed=False,
            reason="reject.filter.mixed_script",
            metrics={"non_latin_alpha_ratio": round(ratio, 4)},
        )
    return FilterResult(passed=True, reason="keep")


def register_quality_filters() -> None:
    """Register all quality filters."""
    register_filter("min_chars", _min_chars_filter)
    register_filter("max_chars", _max_chars_filter)
    register_filter("min_words", _min_words_filter)
    register_filter("url_ratio", _url_ratio_filter)
    register_filter("alpha_ratio", _alpha_ratio_filter)
    register_filter("repetition", _repetition_filter)
    register_filter("word_ngram_repetition", _word_ngram_repetition_filter)
    register_filter("mixed_script", _mixed_script_filter)
