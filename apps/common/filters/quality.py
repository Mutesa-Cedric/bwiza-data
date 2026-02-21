"""Core quality filters (v1)."""

from __future__ import annotations

import re
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
    lines = text.split("\n")
    if len(lines) < 2:
        return FilterResult(passed=True, reason="keep")
    from collections import Counter

    counts = Counter(line.strip() for line in lines if line.strip())
    if not counts:
        return FilterResult(passed=True, reason="keep")
    total = sum(counts.values())
    most_common_count = counts.most_common(1)[0][1]
    repeat_ratio = most_common_count / total
    if repeat_ratio > cfg.filters.max_repeat_line_ratio:
        return FilterResult(
            passed=False,
            reason="reject.filter.repetition",
            metrics={"repeat_line_ratio": round(repeat_ratio, 4)},
        )
    return FilterResult(passed=True, reason="keep")


def register_quality_filters() -> None:
    """Register all v1 quality filters."""
    register_filter("min_chars", _min_chars_filter)
    register_filter("url_ratio", _url_ratio_filter)
    register_filter("alpha_ratio", _alpha_ratio_filter)
    register_filter("repetition", _repetition_filter)
